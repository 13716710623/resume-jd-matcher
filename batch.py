"""
批量模式：一次分析多条 JD，按匹配度排序，输出该投哪几家。

用法：
    python batch.py                          # 用 batch_jds.csv
    python batch.py --jd batch_jds.csv --resume 我的简历.txt --top 10
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


def load_jds(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            jd = (r.get("JD") or "").strip()
            if jd:
                rows.append({"岗位": (r.get("岗位") or "").strip(), "JD": jd,
                             "公司": (r.get("公司") or "").strip()})
    return rows


def run(resume, rows):
    m = Matcher()
    out = []
    for r in rows:
        try:
            res = m.match(resume, r["JD"])
            rep = analysis.analyze(resume, r["JD"], res)
            dp = deep.deep_report(res, rep["dims"], rep["checks"],
                                  r["JD"], rep["req"], resume)
            out.append({**r, "分数": res.score if res.has_skills else None,
                        "评级": dp["grade"], "结论": dp["verdict"],
                        "缺失": [s for s, _, _ in res.missing][:3],
                        "未覆盖": getattr(res, "uncovered", False),
                        "置信度": dp.get("confidence", "正常")})
        except ValueError as e:
            out.append({**r, "分数": None, "评级": "—", "结论": str(e),
                        "缺失": [], "未覆盖": False})
    # 排 A→D，同档按分数降序
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "—": 9}
    out.sort(key=lambda x: (order.get(x["评级"], 9),
                            -(x["分数"] or 0)))
    return out


def render(rows, top=None):
    lines = []
    show = rows if top is None else rows[:top]
    good = [r for r in rows if r["评级"] in ("A", "B")]
    lines.append(f"\n  共 {len(rows)} 条 JD　｜　A/B 档 {len(good)} 条"
                 f"　（建议优先投）\n")
    lines.append("  | 排名 | 评级 | 匹配度 | 置信度 | 岗位 | 缺失技能 |")
    lines.append("  |---:|:--:|---:|:--:|---|---|")
    for i, r in enumerate(show, 1):
        if r["未覆盖"]:
            score = "未覆盖"
        elif r["分数"] is None:
            score = "—"
        else:
            score = f"{r['分数']*100:.0f}%"
        miss = "、".join(r["缺失"]) or "—"
        lines.append(f"  | {i} | **{r['评级']}** | {score} | {r.get('置信度','正常')} | "
                     f"{r['岗位'] or '（未命名）'} | {miss} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd", default=str(BASE / "eval" / "batch_jds.csv"))
    ap.add_argument("--resume", default=str(BASE / "eval" / "resume.txt"))
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--out", default=str(BASE / "output" / "batch_result.csv"))
    args = ap.parse_args()

    rp, jp = Path(args.resume), Path(args.jd)
    if not rp.exists() or not jp.exists():
        print(f"✗ 找不到文件：{rp} 或 {jp}")
        sys.exit(1)

    resume = rp.read_text(encoding="utf-8")
    rows = load_jds(jp)
    if not rows:
        print("✗ JD 文件为空")
        sys.exit(1)

    result = run(resume, rows)
    print(render(result, args.top))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["排名", "评级", "匹配度", "岗位", "公司", "缺失技能", "结论"])
        for i, r in enumerate(result, 1):
            w.writerow([i, r["评级"],
                        "" if r["分数"] is None else f"{r['分数']*100:.1f}%",
                        r["岗位"], r["公司"],
                        "、".join(r["缺失"]), r["结论"]])
    print(f"\n  明细已导出：{out}")


if __name__ == "__main__":
    main()
