"""
大厂风格评估：岗位画像 / 要求分级 / 竞争力评级 / 面试预测 / 行动清单

全部基于规则，每条结论都能追溯到 JD 或简历里的具体证据。
"""
import re

from analysis import edu_level, years_of

# ---------- 岗位画像 ----------
DIRECTIONS = [
    ("算法 / 研究", r"算法|模型训练|预训练|论文|CV|NLP|推荐|强化学习|发表"),
    ("应用 / 落地", r"RAG|Agent|智能体|大模型应用|落地|业务场景|Prompt|应用开发"),
    ("工程 / 平台", r"部署|推理|性能|平台|架构|运维|稳定性|高并发"),
    ("产品 / 方案", r"产品|需求|方案|客户|售前|交付|运营"),
]

SENIORITY = [(0, "应届 / 实习"), (1, "初级（0–1 年）"), (3, "中级（1–3 年）"),
             (5, "高级（3–5 年）"), (99, "资深（5 年以上）")]


# 职能词优先：产品岗的 JD 也会写 RAG/Prompt，光看技能词会误判成应用岗
ROLE_PRIORITY = [
    ("产品 / 方案", r"产品经理|产品设计|产品需求|产品经验|需求分析|需求拆解"),
    ("算法 / 研究", r"算法工程师|研究员|科学家|论文|顶会|预训练"),
    ("工程 / 平台", r"平台建设|架构设计|运维|稳定性|高并发|部署"),
    ("应用 / 落地", r"应用开发|落地|业务场景|RAG|Agent|智能体"),
]


def detect_direction(text):
    """判断一段文本偏哪个职能方向：先看职能词，再看技能词。"""
    for name, pat in ROLE_PRIORITY:
        if len(re.findall(pat, text, re.I)) >= 2:
            return name
    best, hits = "未识别", 0
    for name, pat in DIRECTIONS:
        n = len(re.findall(pat, text, re.I))
        if n > hits:
            best, hits = name, n
    return best


def job_profile(jd, req):
    """岗位方向 + 职级 + 硬性门槛一句话。"""
    scores = []
    for name, pat in DIRECTIONS:
        hits = len(re.findall(pat, jd, re.I))
        if hits:
            scores.append((name, hits))
    scores.sort(key=lambda x: -x[1])
    direction = scores[0][0] if scores else "未识别"

    years = req.get("经验年数")
    if years is None:
        level = "未写明"
    else:
        level = next(label for cap, label in SENIORITY if years < cap) \
            if years < 99 else "资深（5 年以上）"

    edu_map = {0: "未要求", 2: "大专及以上", 3: "本科及以上",
               4: "硕士及以上", 5: "博士"}
    return {
        "方向": direction,
        "方向分布": scores[:3],
        "职级": level,
        "学历门槛": edu_map.get(req.get("学历", 0), "未要求"),
    }


def tier_hits(res):
    """按「必须 / 应该 / 加分」三档统计命中率。"""
    matched = {s for s, _, _ in res.matched}
    tiers = {"必须": [0, 0], "应该": [0, 0], "加分": [0, 0]}
    for r in res.requirements:
        if r.negated:
            continue
        tier = "必须" if r.hard else ("加分" if r.bonus else "应该")
        for s in r.skills:
            tiers[tier][1] += 1
            if s in matched:
                tiers[tier][0] += 1
    out = {}
    for k, (hit, total) in tiers.items():
        if total:
            out[k] = {"命中": hit, "总数": total, "比例": round(hit / total, 3)}
    return out


def competitiveness(overall, tiers):
    """A/B/C/D 评级 + 一句话结论。"""
    if overall >= 0.8 and tiers.get("必须", {}).get("比例", 1) >= 0.8:
        return "A", "高度匹配，建议直接投，简历再按 JD 微调关键词"
    if overall >= 0.65:
        return "B", "基本匹配，补 1–2 个缺口就有竞争力"
    if overall >= 0.5:
        return "C", "有差距，建议补核心缺口后再投，或换相近岗位"
    return "D", "差距较大，更适合作为 1–3 个月的学习目标"


def interview_questions(res):
    """根据命中/缺失生成可能的面试问题。"""
    qs = []
    hits = [s for s, w, _ in res.matched][:2]
    miss = [s for s, w, _ in res.missing][:2]

    for s in hits:
        qs.append(f"【追问】你说熟悉 {s}，讲一个具体项目：怎么做的？效果怎么衡量？")
    for s in miss:
        qs.append(f"【缺口】JD 要求 {s}，你目前没相关经历——面试官大概率会问你怎么补")
    qs.append("【通用】这个岗位最看重什么？你为什么觉得自己合适？")
    return qs[:4]


def action_plan(res, dims, checks):
    """按时间排的行动清单。"""
    plan = []
    worst = next((c for c in checks if not c[1]), None)
    if worst:
        plan.append(("本周", f"改简历：{worst[0]} —— {worst[2]}"))

    if res.missing:
        s, w, c = res.missing[0]
        plan.append(("两周内", f"补 {s}：做一个能演示的小项目，写进简历"))

    if dims.get("经验") is not None and dims["经验"] < 0.7:
        plan.append(("一个月", "用项目深度对冲年限差距：挑 1 个完整项目做深，写成案例"))

    if not plan:
        plan.append(("本周", "简历已达标，按 JD 调整关键词后直接投"))
    return plan[:3]


def deep_report(res, dims, checks, jd, req, resume=""):
    tiers = tier_hits(res) if getattr(res, "has_skills", True) else {}
    grade, verdict = competitiveness(dims["综合"], tiers)

    # 职能方向校验：技能全中也救不了"方向不对"
    jd_dir = detect_direction(jd)
    cv_dir = detect_direction(resume) if resume else "未识别"
    mismatch = (jd_dir != "未识别" and cv_dir != "未识别" and jd_dir != cv_dir)
    if mismatch and grade in ("A", "B"):
        grade = "C"
        verdict = (f"技能匹配度不低，但方向不一致：JD 偏「{jd_dir}」，"
                   f"你的经历偏「{cv_dir}」。建议补相关经历，或优先投 {cv_dir} 类岗位")

    # 领域未覆盖：一个字都没认出来，不给 A/B，直接压到 C
    if getattr(res, "uncovered", False) and grade in ("A", "B"):
        grade = "C"
        verdict = ("这条 JD 的技能要求全部落在词表覆盖之外（可能是前端/后端/运营等"
                   "非 AI 领域），评级仅供参考")

    # 门槛校准：低门槛岗不该判太低，高门槛岗未达标不该判太高
    edu_need = req.get("学历", 0)
    years_need = req.get("经验年数")
    low_bar = edu_need <= 2 or years_need == 0
    high_bar = edu_need >= 4 or (years_need or 0) >= 5

    if low_bar and grade in ("C", "D"):
        grade = "B"
        verdict = ("这是一类低门槛岗位（学历/经验要求宽松），门槛不是筛人依据；"
                   "能否胜任主要看具体技能与稳定性")
    elif high_bar:
        cv_edu = edu_level(resume) if resume else 0
        cv_years = years_of(resume) if resume else 0
        edu_gap = edu_need - cv_edu
        year_gap = (years_need or 0) - cv_years
        if edu_gap >= 1 or year_gap >= 2:
            grade = "D"
            reason = []
            if edu_gap >= 1:
                reason.append(f"学历差 {edu_gap} 档")
            if year_gap >= 2:
                reason.append(f"年限差 {year_gap} 年")
            verdict = (f"岗位门槛偏高（{'、'.join(reason)}），"
                       f"硬性条件未达标，技能对口也难以过筛")

    # 置信度：只认出 1 条要求时，百分比会虚高，单独标出来而不改评级
    n_req = getattr(res, "n_requirements", 0)
    low_conf = bool(getattr(res, "has_skills", True) and n_req < 2)
    uncovered = bool(getattr(res, "uncovered", False))

    return {
        "confidence": ("低" if (low_conf or uncovered) else "正常"),
        "confidence_note": (
            "领域未覆盖" if uncovered else
            ("只识别到 1 项技能要求，百分比偏高" if low_conf else "")),
        "profile": job_profile(jd, req),
        "tiers": tiers,
        "grade": grade,
        "verdict": verdict,
        "direction": {"JD": jd_dir, "简历": cv_dir, "不符": mismatch},
        "questions": interview_questions(res) if getattr(res, "has_skills", True) else [],
        "plan": action_plan(res, dims, checks),
    }
