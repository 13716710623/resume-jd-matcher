"""
命令行入口

用法：
    python cli.py --demo                       # 跑内置示例
    python cli.py --resume 简历.txt --jd jd.txt  # 指定文件
    python cli.py --resume-  # 从标准输入粘贴（Ctrl+Z 回车结束）
"""
import argparse
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

DEMO_RESUME = """本科计算机，3 年 Python 开发经验。
做过一个基于 RAG 的企业知识库，用 LangChain 搭的，接入了 Milvus 做向量检索，
自己写过提示词模板，也调过 Qwen 的接口。熟悉 Docker 部署，用过 FastAPI。
了解微调，做过 LoRA 实验，接触过多智能体协作。
"""

DEMO_JD = """岗位职责：
1. 负责大模型应用开发，必须熟悉 RAG 检索增强方案；
2. 要求熟练使用 LangChain 或 LlamaIndex 搭建 Agent 工作流；
3. 熟悉向量库（Milvus / Faiss）的选型与调优；
4. 有提示词工程经验，能独立完成 Prompt 设计与迭代；
5. 熟悉模型评测，能建立效果验证体系；
6. 了解模型微调（LoRA / SFT）者优先；
7. 熟悉 Docker / K8s 部署；
8. 不需要论文复现经验。
"""


def bar(score, width=32):
    n = int(round(score * width))
    return "█" * n + "░" * (width - n)


def render(res):
    lines = []
    lines.append("")
    if getattr(res, "has_skills", True):
        lines.append(f"  匹配度  {res.score * 100:5.1f}%   {bar(res.score)}")
    else:
        lines.append("  匹配度  ——   JD 里没有技能要求（只评学历/经验）")
    lines.append(f"          已拿 {res.got_weight:g} / 总 {res.total_weight:g} 权重")
    lines.append("")

    lines.append("  【已具备】")
    if res.matched:
        for s, w, c in res.matched:
            lines.append(f"    ✓ {s:<10} 权重 {w:g}  出现在 {c} 条要求里")
    else:
        lines.append("    （一项都没对上）")

    lines.append("")
    lines.append("  【缺失】")
    if res.missing:
        for s, w, c in res.missing:
            lines.append(f"    ✗ {s:<10} 权重 {w:g}  出现在 {c} 条要求里")
    else:
        lines.append("    （没有缺口）")

    if res.missing:
        top = res.missing[0]
        lines.append("")
        lines.append(f"  【建议】先补「{top[0]}」——JD 里权重最高（{top[1]:g}）")

    lines.append("")
    lines.append("  【JD 拆解】")
    for r in res.requirements:
        if r.negated:
            flag = "否"
        elif r.bonus:
            flag = "加"
        elif r.hard:
            flag = "硬"
        else:
            flag = "普"
        lines.append(f"    [{flag}] {r.text[:46]}")
        lines.append(f"         → {', '.join(r.skills)}  (权重 {r.weight:g})")

    if res.notes:
        lines.append("")
        for n in res.notes:
            lines.append(f"    ⚠ {n}")
    return "\n".join(lines)


def render_report(rep):
    """分项评分 + 简历质量 + 改进建议。"""
    d = rep["dims"]
    lines = ["", "  【分项评分】"]
    for k in ("技能匹配", "经验", "学历"):
        v = d.get(k)
        if v is None:
            lines.append(f"    {k:<5}  JD 未提要求")
        else:
            lines.append(f"    {k:<5}  {v * 100:5.1f}%  {bar(v, 18)}")
    lines.append(f"    {'综合':<5}  {d['综合'] * 100:5.1f}%  {bar(d['综合'], 18)}")

    lines += ["", "  【简历质量】"]
    for name, ok, note in rep["checks"]:
        lines.append(f"    {'✓' if ok else '✗'} {name:<5} {note}")

    lines += ["", "  【改进建议】"]
    for i, s in enumerate(rep["suggestions"], 1):
        lines.append(f"    {i}. {s}")
    return "\n".join(lines)


def render_deep(d):
    lines = ["", "  【岗位画像】"]
    prof = d["profile"]
    dist = "、".join(f"{n}({c})" for n, c in prof["方向分布"]) or "—"
    lines.append(f"    方向     {prof['方向']}    证据：{dist}")
    lines.append(f"    职级     {prof['职级']}")
    lines.append(f"    学历     {prof['学历门槛']}")

    if d["tiers"]:
        lines += ["", "  【要求分级命中】"]
        for k in ("必须", "应该", "加分"):
            if k in d["tiers"]:
                v = d["tiers"][k]
                lines.append(f"    {k}  {v['命中']}/{v['总数']}  "
                             f"{bar(v['比例'], 14)} {v['比例']*100:.0f}%")

    lines += ["", f"  【竞争力】 {d['grade']} —— {d['verdict']}"]

    if d["questions"]:
        lines += ["", "  【可能的面试问题】"]
        for i, q in enumerate(d["questions"], 1):
            lines.append(f"    {i}. {q}")

    lines += ["", "  【行动清单】"]
    for when, what in d["plan"]:
        lines.append(f"    {when:<5} {what}")
    return "\n".join(lines)


def read_input(path, prompt):
    if path:
        p = Path(path)
        if not p.exists():
            print(f"✗ 文件不存在：{p}")
            sys.exit(1)
        return p.read_text(encoding="utf-8")
    print(f"请粘贴{p}（结束按 Ctrl+Z 回车）：")
    return sys.stdin.read()


def main():
    ap = argparse.ArgumentParser(description="简历 — JD 匹配器")
    ap.add_argument("--resume", help="简历文本文件路径")
    ap.add_argument("--jd", help="JD 文本文件路径")
    ap.add_argument("--demo", action="store_true", help="跑内置示例")
    ap.add_argument("--synonyms", help="自定义同义词表路径")
    args = ap.parse_args()

    m = Matcher(args.synonyms)

    if args.demo:
        resume, jd = DEMO_RESUME, DEMO_JD
        print("（使用内置示例）")
    else:
        resume = read_input(args.resume, "简历")
        jd = read_input(args.jd, "JD")

    try:
        res = m.match(resume, jd)
    except ValueError as e:
        print(f"✗ {e}")
        sys.exit(1)

    rep = analysis.analyze(resume, jd, res)
    print(render(res))
    print(render_report(rep))
    print(render_deep(deep.deep_report(res, rep["dims"], rep["checks"], jd, rep["req"], resume)))
    print()


if __name__ == "__main__":
    main()
