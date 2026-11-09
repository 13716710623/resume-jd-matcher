"""
简历深度诊断：在关键词匹配之外，再给出分维度评分、简历质量检查和改进建议。

设计原则仍然是「可解释」：每一条分数和建议都能说清依据。
"""
import re

# 学历档位
EDU_LEVEL = {"博士": 5, "硕士": 4, "研究生": 4, "本科": 3, "学士": 3,
             "大专": 2, "专科": 2, "高职": 2}

# 量化成果：数字 + 百分比/倍数/万/千/ms 等
QUANT_RE = re.compile(r"\d+(\.\d+)?\s*(%|％|倍|万|千|w|W|ms|毫秒|秒|个|条|人|次|QPS|qps)")

# 项目/成果类描述
PROJECT_WORDS = ("项目", "负责", "主导", "设计", "实现", "落地", "上线", "重构", "优化",
                 "做过", "搭建", "开发", "编写", "部署", "迁移")


def edu_level(text):
    best = 0
    for k, v in EDU_LEVEL.items():
        if k in text:
            best = max(best, v)
    return best


def years_of(text):
    """取简历/ JD 里最大的「N 年」，同时支持中文数字。"""
    nums = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    best = 0
    for m in re.finditer(r"(\d{1,2})\s*年", text):
        best = max(best, int(m.group(1)))
    for ch, val in nums.items():
        if re.search(ch + r"\s*年", text):
            best = max(best, val)
    return best


def jd_requirement(jd):
    """从 JD 里抽经验与学历要求。"""
    exp = None
    m = re.search(r"(\d{1,2})\s*年(以上|及以上)", jd)
    if m:
        exp = int(m.group(1))
    else:
        m = re.search(r"(\d{1,2})\s*[-~到]\s*(\d{1,2})\s*年", jd)
        if m:
            exp = int(m.group(1))
        elif re.search(r"应届|在校|无经验", jd):
            exp = 0
    return {"经验年数": exp, "学历": edu_level(jd)}


def score_dims(resume, jd, skill_score, has_skills=True):
    """四个维度打分（0~1）。"""
    req = jd_requirement(jd)
    r_years = years_of(resume)
    r_edu = edu_level(resume)

    # 技能：直接用匹配器结果；JD 没提技能就留空
    dims = {"技能匹配": round(skill_score, 3) if has_skills else None}

    # 经验
    if req["经验年数"] is None:
        dims["经验"] = None
    else:
        need = req["经验年数"]
        if need == 0:
            dims["经验"] = 1.0 if r_years <= 1 else 0.8
        elif r_years >= need:
            dims["经验"] = 1.0
        elif r_years >= need - 1:
            dims["经验"] = 0.6
        else:
            dims["经验"] = max(0.2, 1 - (need - r_years) * 0.25)

    # 学历
    if req["学历"] == 0:
        dims["学历"] = None
    elif r_edu >= req["学历"]:
        dims["学历"] = 1.0
    elif r_edu == req["学历"] - 1:
        dims["学历"] = 0.5
    else:
        dims["学历"] = 0.2 if r_edu else 0.0

    # 综合：技能 0.6、经验 0.2、学历 0.2（缺失维度按权重重新归一）
    weights = {"技能匹配": 0.6, "经验": 0.2, "学历": 0.2}
    total_w = sum(weights[k] for k, v in dims.items() if v is not None)
    overall = sum(dims[k] * weights[k] for k, v in dims.items()
                  if v is not None) / total_w if total_w else 0.0
    dims["综合"] = round(overall, 3)
    return dims, req


def quality_checks(resume):
    """简历硬质量检查，返回 [(项目, 是否通过, 说明)]。"""
    out = []
    n = len(resume.strip())

    # 1. 长度
    if n < 120:
        out.append(("篇幅", False, f"只有 {n} 字，太短，建议至少 300 字"))
    elif n > 3000:
        out.append(("篇幅", False, f"{n} 字，偏长，HR 平均只看 30 秒"))
    else:
        out.append(("篇幅", True, f"{n} 字，长度合适"))

    # 2. 量化成果
    q = QUANT_RE.findall(resume)
    if len(q) >= 2:
        out.append(("量化成果", True, f"有 {len(q)} 处数字指标，很好"))
    elif len(q) == 1:
        out.append(("量化成果", False, "只有 1 处数据，建议多写结果指标"))
    else:
        out.append(("量化成果", False, "没有数据，全是形容词，说服力弱"))

    # 3. 项目描述
    hits = sum(1 for w in PROJECT_WORDS if w in resume)
    if hits >= 2:
        out.append(("项目描述", True, f"出现 {hits} 类项目动词"))
    else:
        out.append(("项目描述", False, "看不出做过什么项目，建议补「做了什么 + 结果」"))

    # 4. 技能罗列
    if re.search(r"(熟悉|掌握|了解|精通).{0,6}(、|，|,).{0,6}(熟悉|掌握|了解|精通)", resume):
        out.append(("技能呈现", True, "有分层次描述掌握程度"))
    else:
        out.append(("技能呈现", False, "建议区分「精通 / 熟悉 / 了解」，别一锅端"))

    return out


def build_suggestions(res, dims, checks):
    """按优先级生成改进建议。"""
    out = []

    # 1. 硬伤优先
    for name, ok, note in checks:
        if not ok:
            out.append(f"【简历】{name}：{note}")

    # 2. 缺失技能（按权重）
    for s, w, c in res.missing[:3]:
        out.append(f"【补技能】{s} —— 出现在 {c} 条要求里，权重 {w:g}，优先补")

    # 3. 维度短板
    if dims.get("经验") is not None and dims["经验"] < 0.6:
        out.append("【经验】年限差距明显，投递时可突出项目深度来对冲")
    if dims.get("学历") is not None and dims["学历"] < 0.6:
        out.append("【学历】低于 JD 要求，建议优先投学历要求匹配的岗位")

    if not out:
        out.append("没有明显短板，可以直接投")
    return out


def analyze(resume, jd, match_result):
    dims, req = score_dims(resume, jd, match_result.score,
                           getattr(match_result, "has_skills", True))
    checks = quality_checks(resume)
    suggestions = build_suggestions(match_result, dims, checks)
    return {"dims": dims, "req": req, "checks": checks,
            "suggestions": suggestions}
