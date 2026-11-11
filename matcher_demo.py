"""
简历 — JD 匹配器 · 原型

输入：一份简历文本 + 一份 JD 文本
输出：匹配度、已具备、缺失、建议

核心不是"算得准"，而是"说得清"——每一项分数都能追溯到具体词。
"""
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------- 同义词表（这个项目最值钱的部分）----------
# 同一概念的不同写法归成一个标准词，否则"RAG"和"检索增强"会被当成两个技能
SYNONYMS = {
    "RAG": ["rag", "检索增强", "向量检索", "知识库检索"],
    "Agent": ["agent", "智能体", "多智能体", "function calling", "工具调用"],
    "LangChain": ["langchain", "langgraph", "llamaindex"],
    "提示词": ["提示词", "prompt", "prompt engineering"],
    "微调": ["微调", "fine-tune", "finetune", "lora", "sft"],
    "向量库": ["向量库", "向量数据库", "milvus", "faiss", "chromadb", "pgvector"],
    "评测": ["评测", "评估", "benchmark", "效果验证"],
    "部署": ["部署", "docker", "k8s", "kubernetes", "容器化"],
    "Python": ["python"],
    "大模型": ["大模型", "llm", "大语言模型", "gpt", "qwen", "deepseek"],
}

# JD 里出现这些词，说明是"硬性要求"，权重更高
HARD_WORDS = ["必须", "要求", "熟悉", "精通", "至少", "年以上", "优先"]


def normalize(text):
    """把文本里出现的同义词，统一替换成标准词，返回标准词集合。"""
    low = text.lower()
    found = {}
    for std, aliases in SYNONYMS.items():
        hits = [a for a in aliases if a in low]
        if hits:
            found[std] = hits
    return found


def split_requirements(jd):
    """把 JD 按句/行切开，逐句统计哪些标准词出现。"""
    chunks = re.split(r"[。;；\n]", jd)
    out = []
    for c in chunks:
        c = c.strip()
        if not c:
            continue
        words = normalize(c)
        if words:
            hard = any(w in c for w in HARD_WORDS)
            out.append({"句子": c, "技能": list(words), "硬性": hard})
    return out


def match(resume, jd):
    r_words = normalize(resume)
    reqs = split_requirements(jd)

    # 每个技能在 JD 里被提到几次、是否硬性
    weight = Counter()
    hard = set()
    for r in reqs:
        for s in r["技能"]:
            weight[s] += 1
            if r["硬性"]:
                hard.add(s)

    if not weight:
        return None

    total = sum(weight.values())
    got = [s for s in weight if s in r_words]
    miss = [s for s in weight if s not in r_words]
    score = sum(weight[s] for s in got) / total

    return {
        "score": score,
        "got": sorted(got, key=lambda s: -weight[s]),
        "miss": sorted(miss, key=lambda s: -weight[s]),
        "weight": weight,
        "hard": hard,
        "reqs": reqs,
    }


RESUME = """
本科计算机，3 年 Python 开发经验。
做过一个基于 RAG 的企业知识库，用 LangChain 搭的，接入了 Milvus 做向量检索，
自己写过提示词模板，也调过 Qwen 的接口。熟悉 Docker 部署，用过 FastAPI。
了解微调，做过 LoRA 实验。
"""

JD = """
岗位职责：
1. 负责大模型应用开发，必须熟悉 RAG 检索增强方案；
2. 要求熟练使用 LangChain 或 LlamaIndex 搭建 Agent 工作流；
3. 熟悉向量库（Milvus / Faiss）的选型与调优；
4. 有提示词工程经验，能独立完成 Prompt 设计与迭代；
5. 熟悉模型评测，能建立效果验证体系；
6. 了解模型微调（LoRA / SFT）者优先；
7. 熟悉 Docker / K8s 部署。
"""


def main():
    res = match(RESUME, JD)
    if not res:
        print("没匹配到任何技能，检查 JD 文本")
        return

    print("=" * 54)
    print(f"匹配度：{res['score']*100:.0f}%")
    print("=" * 54)

    print("\n【已具备】")
    for s in res["got"]:
        tag = "（硬性）" if s in res["hard"] else ""
        print(f"  ✓ {s:<10} JD 提到 {res['weight'][s]} 次 {tag}")

    print("\n【缺失】")
    for s in res["miss"]:
        tag = "（硬性）" if s in res["hard"] else ""
        print(f"  ✗ {s:<10} JD 提到 {res['weight'][s]} 次 {tag}")

    print("\n【建议优先补】")
    if res["miss"]:
        top = res["miss"][0]
        print(f"  → 先补「{top}」：JD 里出现 {res['weight'][top]} 次"
              f"{'，而且是硬性要求' if top in res['hard'] else ''}")
    else:
        print("  → 没有明显缺口")

    print("\n【JD 拆解】")
    for r in res["reqs"]:
        flag = "硬" if r["硬性"] else "  "
        print(f"  [{flag}] {r['句子'][:44]}")
        print(f"        → {', '.join(r['技能'])}")


if __name__ == "__main__":
    main()
