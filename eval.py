"""
准确性评测：拿人工标注的 JD 对比工具评级，算吻合率和错例。

用法：
    python eval.py                                  # 用 eval/ 下的默认文件
    python eval.py --resume 简历.txt --labels 标注.csv

标注文件格式（CSV）：
    id,岗位,JD,人工判断,备注
    人工判断只能填：够格 / 勉强 / 不够

判定规则：
    够格 → 工具应给 A 或 B
    勉强 → 工具应给 C
    不够 → 工具应给 D
    落在期望档位算吻合，否则算偏差（记一档还是两档）
"""
import argparse
import csv
import sys
from pathlib import Path

import analysis
import report as deep
from matcher import Matcher

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent

# 人工判断 → 允许的评级
EXPECT = {"够格": {"A", "B"}, "勉强": {"C"}, "不够": {"D"}}
ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def load_labels(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            jd = (r.get("JD") or "").strip()
            label = (r.get("人工判断") or "").strip()
            if not jd or label not in EXPECT:
                continue
            rows.append({"id": r.get("id", ""), "岗位": r.get("岗位", ""),
                         "JD": jd, "人工": label,
                         "备注": r.get("备注", "")})
    return rows


def evaluate(resume, rows):
    m = Matcher()
    out = []
    for r in rows:
        try:
            res = m.match(resume, r["JD"])
            rep = analysis.analyze(resume, r["JD"], res)
            dp = deep.deep_report(res, rep["dims"], rep["checks"],
                                  r["JD"], rep["req"], resume)
            grade = dp["grade"]
            score = res.score if res.has_skills else rep["dims"]["综合"]
            miss = [s for s, _, _ in res.missing]
            err = None
        except ValueError as e:
            grade, score, miss, err = "—", 0.0, [], str(e)

        ok = grade in EXPECT[r["人工"]]
        gap = abs(ORDER.get(grade, 9) - min(ORDER[g] for g in EXPECT[r["人工"]])) \
            if grade in ORDER else 9
        jd_dir = deep.detect_direction(r["JD"])
        cv_dir = deep.detect_direction(resume)
        direction_mismatch = (jd_dir != "未识别" and cv_dir != "未识别"
                              and jd_dir != cv_dir)
        out.append({**r, "工具": grade, "分数": score,
                    "吻合": ok, "偏差档数": gap, "缺失": miss, "错误": err,
                    "JD方向": jd_dir, "简历方向": cv_dir,
                    "方向不符": direction_mismatch})
    return out


def render(results):
    n = len(results)
    hit = sum(1 for r in results if r["吻合"])
    lines = ["", f"  样本 {n} 条　吻合 {hit} 条　"
                 f"**吻合率 {hit / n * 100:.0f}%**", ""]

    lines.append("  | # | 岗位 | 人工 | 工具 | 分数 | 吻合 | 缺失技能 |")
    lines.append("  |---|---|---|---|---|---|---|")
    for r in results:
        mark = "✅" if r["吻合"] else f"❌ 偏{r['偏差档数']}档"
        miss = "、".join(r["缺失"][:3]) or ("—" if not r["错误"] else r["错误"])
        lines.append(f"  | {r['id']} | {r['岗位']} | {r['人工']} | "
                     f"{r['工具']} | {r['分数']*100:.0f}% | {mark} | {miss} |")

    bad = [r for r in results if not r["吻合"]]
    if bad:
        lines += ["", "  **错例分析**"]
        for r in bad:
            if r["错误"]:
                lines.append(f"  - #{r['id']} {r['岗位']}：无法分析（{r['错误']}）")
                continue
            if r.get("方向不符"):
                reason = "职能方向不匹配：简历偏「" + r["简历方向"] + \
                         "」，JD 偏「" + r["JD方向"] + "」"
            elif not r["缺失"] and r["分数"] > 0.8:
                reason = "技能全中但被人工判低，可能是软性要求（行业/职能）未建模"
            else:
                reason = "权重或门槛偏松/偏紧"
            lines.append(f"  - #{r['id']} {r['岗位']}：你判「{r['人工']}」，"
                         f"工具判「{r['工具']}」（偏 {r['偏差档数']} 档）；"
                         f"缺失 {'、'.join(r['缺失'][:3]) or '无'}；疑似原因：{reason}")
    else:
        lines += ["", "  ✅ 全部吻合，没有错例"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", default=str(BASE / "eval" / "resume.txt"))
    ap.add_argument("--labels", default=str(BASE / "eval" / "labeled.csv"))
    args = ap.parse_args()

    rp, lp = Path(args.resume), Path(args.labels)
    if not rp.exists() or not lp.exists():
        print(f"✗ 找不到文件：{rp} 或 {lp}")
        sys.exit(1)

    resume = rp.read_text(encoding="utf-8")
    rows = load_labels(lp)
    if not rows:
        print("✗ 标注文件里没有有效行（人工判断只能填 够格/勉强/不够）")
        sys.exit(1)

    results = evaluate(resume, rows)
    print(render(results))
    print()


if __name__ == "__main__":
    main()
