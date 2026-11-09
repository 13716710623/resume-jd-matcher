"""
简历 — JD 匹配器 · 核心逻辑

设计原则：**可解释**。任何一项得分都能追溯到 JD 里的具体句子。
不用模型、不联网，纯规则 + 词表。
"""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

BASE = Path(__file__).resolve().parent

# 权重规则：同一句话里出现这些词，说明是硬性要求
HARD_WORDS = ("必须", "要求", "熟练", "精通", "掌握", "至少", "年以上", "年起", "能够独立")
# 出现这些词 → 加分项，权重降低
BONUS_WORDS = ("优先", "加分", "更佳", "者优先", "有则更好")
# 否定词：出现在技能之前，说明这项不被要求
NEG_WORDS = ("不需要", "无需", "不用", "不要求", "非必须", "不必须", "不必")

# 简历侧的熟练度：写"了解"和写"精通"不该一样
PROFICIENCY = (("精通", 1.0), ("熟练", 1.0), ("熟悉", 1.0), ("掌握", 1.0),
               ("用过", 0.8), ("使用过", 0.8), ("了解", 0.6), ("接触过", 0.5))

WEIGHT_HARD = 2.0
WEIGHT_NORMAL = 1.0
WEIGHT_BONUS = 0.5

# 转折词：把"不需要 A，但需要 B"拆成两个子句，否则 B 会被一起误杀
CONTRAST_RE = re.compile(r"但是|但|不过|然而|；")

# 句子切分：句号、分号、换行、编号
SPLIT_RE = re.compile(r"[。;；\n]|(?<!\d)\d{1,2}[.、](?!\d)\s*")


@dataclass
class Requirement:
    text: str
    skills: list
    weight: float
    hard: bool
    bonus: bool
    negated: bool


@dataclass
class MatchResult:
    score: float
    matched: list            # [(技能, 权重, 次数)]
    missing: list
    requirements: list
    total_weight: float
    got_weight: float
    notes: list = field(default_factory=list)
    has_skills: bool = True          # JD 里是否真的提到技能
    n_requirements: int = 0          # 识别出的要求条数（衡量信息量）
    uncovered: bool = False          # 领域是否超出词表覆盖


def _word_char(ch):
    """只把 ASCII 字母数字算作「单词内部」，中文/标点都算边界。"""
    return ch.isascii() and ch.isalnum()


class Matcher:
    def __init__(self, synonyms_path=None):
        self.table = self._load(synonyms_path or BASE / "synonyms.csv")
        # 别名 -> 标准名，长别名优先
        seen_alias = set()
        self.alias = []
        for std, cat, aliases in self.table:
            for a in aliases:
                if len(a) <= 1:
                    continue
                key = (std, a.lower())
                if key in seen_alias:      # 标准名本身也在同义词里，会重复
                    continue
                seen_alias.add(key)
                self.alias.append((std, a))
        self.alias.sort(key=lambda x: -len(x[1]))

    @staticmethod
    def _load(path):
        rows = []
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                std = (r.get("标准名") or "").strip()
                if not std:
                    continue
                cat = (r.get("类别") or "").strip()
                al = [a.strip() for a in (r.get("同义词") or "").split("|") if a.strip()]
                rows.append((std, cat, {std} | set(al)))
        return rows

    def find_skills(self, text):
        """返回 [(标准名, 命中位置)]，长别名优先，避免短词误命中。"""
        low = text.lower()
        hits, seen = [], set()
        for std, a in self.alias:
            start = 0
            while True:
                i = low.find(a.lower(), start)
                if i < 0:
                    break
                # 英文别名要求词边界，避免 rag 命中 storage
                if re.match(r"^[a-z0-9+#./ -]+$", a, re.I):
                    # 注意：中文字符的 isalnum() 也是 True，
                    # 所以只把「ASCII 字母数字」当作单词的一部分，
                    # 否则「熟练掌握python」会把 python 当成半个词跳过。
                    left_ok = i == 0 or not _word_char(low[i - 1])
                    right_ok = i + len(a) >= len(low) or not _word_char(low[i + len(a)])
                    if not (left_ok and right_ok):
                        start = i + 1
                        continue
                if std not in seen:
                    seen.add(std)
                    hits.append((std, i))
                start = i + len(a)
        return hits

    def parse_jd(self, jd):
        reqs = []
        for chunk in SPLIT_RE.split(jd):
            # 先按转折词拆子句：前半句的"不需要"不该影响后半句
            for part in CONTRAST_RE.split(chunk or ""):
                part = part.strip(" ，,;；\t")
                if len(part) < 2:
                    continue
                skills = [s for s, _ in self.find_skills(part)]
                if not skills:
                    continue
                hard = any(w in part for w in HARD_WORDS)
                bonus = any(w in part for w in BONUS_WORDS)
                weight = (WEIGHT_HARD if hard
                          else (WEIGHT_BONUS if bonus else WEIGHT_NORMAL))
                # 否定只在当前子句内生效
                negated = any(n in part for n in NEG_WORDS)
                reqs.append(Requirement(part, skills, weight, hard, bonus, negated))
        return reqs

    def match(self, resume, jd):
        notes = []
        if not (resume or "").strip():
            raise ValueError("简历是空的")
        if not (jd or "").strip():
            raise ValueError("JD 是空的")

        # 简历技能 -> 熟练度系数（"了解"打 0.6 折）
        resume_skills = {}
        for s, pos in self.find_skills(resume):
            window = resume[max(0, pos - 12):pos]
            lv = 1.0
            for word, val in PROFICIENCY:
                if word in window:
                    lv = val
                    break
            resume_skills[s] = max(resume_skills.get(s, 0.0), lv)
        reqs = self.parse_jd(jd)

        active = [r for r in reqs if not r.negated]
        for r in reqs:
            if r.negated:
                notes.append(f"已忽略否定要求：{r.text[:30]}")

        if not active:
            # 没有技能要求不代表不能分析：JD 可能只写了学历/经验
            has_edu = re.search(r"本科|硕士|大专|博士|研究生|学士|专科", jd)
            has_exp = re.search(r"\d{1,2}\s*年|应届|在校|无经验", jd)
            if not (has_edu or has_exp):
                raise ValueError("这段 JD 里既没有技能要求，也没有学历/经验要求，没法分析")

            # 判断是不是「这个领域不在词表覆盖范围内」
            UNCOVERED_HINT = r"前端|后端|React|Vue|TypeScript|Java|Go\b|PHP|测试|运维|" \
                             r"数据仓库|数仓|Spark|Flink|Hadoop|SQL|DBA|客户端|Android|iOS|" \
                             r"UI|设计|运营|销售|客服|财务|人事|法务|产品经理"
            uncovered = bool(re.search(UNCOVERED_HINT, jd, re.I))
            if uncovered:
                notes.append("未识别到任何技能：这条 JD 的领域可能不在词表覆盖范围内，"
                             "评级仅供参考")
            else:
                notes.append("JD 里没有技能要求，只按学历/经验评估")
            return MatchResult(score=0.0, matched=[], missing=[], requirements=reqs,
                               total_weight=0.0, got_weight=0.0,
                               notes=notes, has_skills=False, uncovered=uncovered,
                               n_requirements=0)

        weight = {}
        count = {}
        for r in active:
            for s in r.skills:
                weight[s] = weight.get(s, 0) + r.weight
                count[s] = count.get(s, 0) + 1

        total = sum(weight.values())
        matched = [(s, w, count[s]) for s, w in weight.items() if s in resume_skills]
        missing = [(s, w, count[s]) for s, w in weight.items() if s not in resume_skills]
        # 满足度按熟练度打折
        got = sum(w * resume_skills[s] for s, w, _ in matched)

        matched.sort(key=lambda x: (-x[1], x[0]))
        missing.sort(key=lambda x: (-x[1], x[0]))

        return MatchResult(
            score=got / total if total else 0.0,
            matched=matched, missing=missing, requirements=reqs,
            total_weight=total, got_weight=got, notes=notes,
            n_requirements=len(active),
        )
