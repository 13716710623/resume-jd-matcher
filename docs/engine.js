/* 人岗匹配引擎 —— matcher.py / analysis.py / report.py 的浏览器移植版
 * 目标：与 Python 版输出一致（用 eval 的 10 条样本校验）
 * 依赖：synonyms.js 提供 globalThis.SYNONYMS = [[标准名, 类别, "别名|别名"], ...]
 */
(function (root) {
  "use strict";

  const HARD_WORDS = ["必须", "要求", "熟练", "精通", "掌握", "至少", "年以上", "年起", "能够独立"];
  const BONUS_WORDS = ["优先", "加分", "更佳", "者优先", "有则更好"];
  const NEG_WORDS = ["不需要", "无需", "不用", "不要求", "非必须", "不必须", "不必"];
  const PROFICIENCY = [["精通", 1], ["熟练", 1], ["熟悉", 1], ["掌握", 1],
                       ["用过", 0.8], ["使用过", 0.8], ["了解", 0.6], ["接触过", 0.5]];
  const W_HARD = 2, W_NORMAL = 1, W_BONUS = 0.5;

  const SPLIT_RE = /[。;；\n]|(?<!\d)\d{1,2}[.、](?!\d)\s*/;
  const CONTRAST_RE = /但是|但|不过|然而|；/;
  const ASCII_ALIAS = /^[a-z0-9+#./ -]+$/i;
  const ASCII_WORD = /[A-Za-z0-9]/;

  const EDU = { "博士": 5, "硕士": 4, "研究生": 4, "本科": 3, "学士": 3, "大专": 2, "专科": 2, "高职": 2 };
  const QUANT_RE = /\d+(\.\d+)?\s*(%|％|倍|万|千|w|W|ms|毫秒|秒|个|条|人|次|QPS|qps)/g;
  const PROJECT_WORDS = ["项目", "负责", "主导", "设计", "实现", "落地", "上线", "重构", "优化",
                         "做过", "搭建", "开发", "编写", "部署", "迁移"];

  const DIRECTIONS = [
    ["算法 / 研究", /算法|模型训练|预训练|论文|CV|NLP|推荐|强化学习|发表/gi],
    ["应用 / 落地", /RAG|Agent|智能体|大模型应用|落地|业务场景|Prompt|应用开发/gi],
    ["工程 / 平台", /部署|推理|性能|平台|架构|运维|稳定性|高并发/gi],
    ["产品 / 方案", /产品|需求|方案|客户|售前|交付|运营/gi],
  ];
  const ROLE_PRIORITY = [
    ["产品 / 方案", /产品经理|产品设计|产品需求|产品经验|需求分析|需求拆解/gi],
    ["算法 / 研究", /算法工程师|研究员|科学家|论文|顶会|预训练/gi],
    ["工程 / 平台", /平台建设|架构设计|运维|稳定性|高并发|部署/gi],
    ["应用 / 落地", /应用开发|落地|业务场景|RAG|Agent|智能体/gi],
  ];

  let ALIAS = null;

  function count(text, re) {
    const m = text.match(re);
    return m ? m.length : 0;
  }

  function buildAlias() {
    if (ALIAS) return ALIAS;
    const seen = new Set();
    const out = [];
    for (const [std, , aliases] of (root.SYNONYMS || [])) {
      const all = new Set([std, ...String(aliases).split("|").map((s) => s.trim()).filter(Boolean)]);
      for (const a of all) {
        if (a.length <= 1) continue;
        const key = std + "\u0000" + a.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        out.push([std, a]);
      }
    }
    out.sort((x, y) => y[1].length - x[1].length);
    ALIAS = out;
    return ALIAS;
  }

  function findSkills(text) {
    const low = String(text || "").toLowerCase();
    const hits = [];
    const seen = new Set();
    for (const [std, a] of buildAlias()) {
      const needle = a.toLowerCase();
      let start = 0;
      for (;;) {
        const i = low.indexOf(needle, start);
        if (i < 0) break;
        if (ASCII_ALIAS.test(a)) {
          const leftOk = i === 0 || !ASCII_WORD.test(low[i - 1]);
          const rightOk = i + a.length >= low.length || !ASCII_WORD.test(low[i + a.length]);
          if (!(leftOk && rightOk)) { start = i + 1; continue; }
        }
        if (!seen.has(std)) { seen.add(std); hits.push([std, i]); }
        start = i + a.length;
      }
    }
    return hits;
  }

  function needsAny(text, words) {
    return words.some((w) => text.includes(w));
  }

  function parseJD(jd) {
    const reqs = [];
    for (const chunk of String(jd || "").split(SPLIT_RE)) {
      for (let part of String(chunk || "").split(CONTRAST_RE)) {
        part = part.replace(/^[\s，,;；\t]+|[\s，,;；\t]+$/g, "");
        if (part.length < 2) continue;
        const skills = findSkills(part).map((h) => h[0]);
        if (!skills.length) continue;
        const hard = needsAny(part, HARD_WORDS);
        const bonus = needsAny(part, BONUS_WORDS);
        const weight = hard ? W_HARD : (bonus ? W_BONUS : W_NORMAL);
        const negated = needsAny(part, NEG_WORDS);
        reqs.push({ text: part, skills, weight, hard, bonus, negated });
      }
    }
    return reqs;
  }

  function proficiencyAt(resume, pos) {
    const win = resume.slice(Math.max(0, pos - 12), pos);
    for (const [w, v] of PROFICIENCY) if (win.includes(w)) return v;
    return 1.0;
  }

  function match(resume, jd) {
    resume = String(resume || "");
    jd = String(jd || "");
    if (!resume.trim()) throw new Error("简历是空的");
    if (!jd.trim()) throw new Error("JD 是空的");

    const resumeSkills = new Map();
    for (const [s, pos] of findSkills(resume)) {
      const lv = proficiencyAt(resume, pos);
      resumeSkills.set(s, Math.max(resumeSkills.get(s) || 0, lv));
    }

    const reqs = parseJD(jd);
    const notes = [];
    const active = [];
    for (const r of reqs) {
      if (r.negated) notes.push("已忽略否定要求：" + r.text.slice(0, 30));
      else active.push(r);
    }

    if (!active.length) {
      const hasEdu = /本科|硕士|大专|博士|研究生|学士|专科/.test(jd);
      const hasExp = /\d{1,2}\s*年|应届|在校|无经验/.test(jd);
      if (!hasEdu && !hasExp) throw new Error("这段 JD 里既没有技能要求，也没有学历/经验要求，没法分析");
      notes.push("JD 里没有技能要求，只按学历/经验评估");
      return { score: 0, matched: [], missing: [], requirements: reqs,
               totalWeight: 0, gotWeight: 0, notes, hasSkills: false };
    }

    const weight = new Map(), countMap = new Map();
    for (const r of active) {
      for (const s of r.skills) {
        weight.set(s, (weight.get(s) || 0) + r.weight);
        countMap.set(s, (countMap.get(s) || 0) + 1);
      }
    }

    let total = 0, got = 0;
    const matched = [], missing = [];
    for (const [s, w] of weight) {
      total += w;
      if (resumeSkills.has(s)) {
        got += w * resumeSkills.get(s);
        matched.push([s, w, countMap.get(s)]);
      } else {
        missing.push([s, w, countMap.get(s)]);
      }
    }
    const byWeight = (a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0], "zh");
    matched.sort(byWeight);
    missing.sort(byWeight);

    return { score: total ? got / total : 0, matched, missing, requirements: reqs,
             totalWeight: total, gotWeight: got, notes, hasSkills: true };
  }

  // ---------- analysis ----------
  function eduLevel(text) {
    let best = 0;
    for (const k in EDU) if (String(text).includes(k)) best = Math.max(best, EDU[k]);
    return best;
  }

  function yearsOf(text) {
    const s = String(text);
    const cn = { "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10 };
    let best = 0;
    for (const m of s.matchAll(/(\d{1,2})\s*年/g)) best = Math.max(best, parseInt(m[1], 10));
    for (const ch in cn) if (new RegExp(ch + "\\s*年").test(s)) best = Math.max(best, cn[ch]);
    return best;
  }

  function jdRequirement(jd) {
    let exp = null;
    let m = jd.match(/(\d{1,2})\s*年(以上|及以上)/);
    if (m) exp = parseInt(m[1], 10);
    else {
      m = jd.match(/(\d{1,2})\s*[-~到]\s*(\d{1,2})\s*年/);
      if (m) exp = parseInt(m[1], 10);
      else if (/应届|在校|无经验/.test(jd)) exp = 0;
    }
    return { years: exp, edu: eduLevel(jd) };
  }

  function scoreDims(resume, jd, skillScore, hasSkills) {
    const req = jdRequirement(jd);
    const rYears = yearsOf(resume), rEdu = eduLevel(resume);
    const dims = { "技能匹配": hasSkills ? skillScore : null };

    if (req.years === null) dims["经验"] = null;
    else {
      const need = req.years;
      if (need === 0) dims["经验"] = rYears <= 1 ? 1 : 0.8;
      else if (rYears >= need) dims["经验"] = 1;
      else if (rYears >= need - 1) dims["经验"] = 0.6;
      else dims["经验"] = Math.max(0.2, 1 - (need - rYears) * 0.25);
    }

    if (req.edu === 0) dims["学历"] = null;
    else if (rEdu >= req.edu) dims["学历"] = 1;
    else if (rEdu === req.edu - 1) dims["学历"] = 0.5;
    else dims["学历"] = rEdu ? 0.2 : 0;

    const W = { "技能匹配": 0.6, "经验": 0.2, "学历": 0.2 };
    let tw = 0, sum = 0;
    for (const k in dims) if (dims[k] !== null) { tw += W[k]; sum += dims[k] * W[k]; }
    dims["综合"] = tw ? sum / tw : 0;
    return { dims, req };
  }

  function qualityChecks(resume) {
    const s = String(resume || "");
    const n = s.trim().length;
    const out = [];

    if (n < 120) out.push(["篇幅", false, `只有 ${n} 字，太短，建议至少 300 字`]);
    else if (n > 3000) out.push(["篇幅", false, `${n} 字，偏长，HR 平均只看 30 秒`]);
    else out.push(["篇幅", true, `${n} 字，长度合适`]);

    const q = s.match(QUANT_RE);
    const qn = q ? q.length : 0;
    if (qn >= 2) out.push(["量化成果", true, `有 ${qn} 处数字指标，很好`]);
    else if (qn === 1) out.push(["量化成果", false, "只有 1 处数据，建议多写结果指标"]);
    else out.push(["量化成果", false, "没有数据，全是形容词，说服力弱"]);

    const hits = PROJECT_WORDS.filter((w) => s.includes(w)).length;
    if (hits >= 2) out.push(["项目描述", true, `出现 ${hits} 类项目动词`]);
    else out.push(["项目描述", false, "看不出做过什么项目，建议补「做了什么 + 结果」"]);

    if (/(熟悉|掌握|了解|精通).{0,6}(、|，|,).{0,6}(熟悉|掌握|了解|精通)/.test(s))
      out.push(["技能呈现", true, "有分层次描述掌握程度"]);
    else out.push(["技能呈现", false, "建议区分「精通 / 熟悉 / 了解」，别一锅端"]);

    return out;
  }

  function buildSuggestions(res, dims, checks, cjk) {
    const out = [];
    for (const [name, ok, note] of checks) if (!ok) out.push(`【简历】${name}：${note}`);
    for (const [s, w, c] of res.missing.slice(0, 3))
      out.push(`【补技能】${s} —— 出现在 ${c} 条要求里，权重 ${cjk ? w : w}，优先补`);
    if (dims["经验"] !== null && dims["经验"] < 0.6)
      out.push("【经验】年限差距明显，投递时可突出项目深度来对冲");
    if (dims["学历"] !== null && dims["学历"] < 0.6)
      out.push("【学历】低于 JD 要求，建议优先投学历要求匹配的岗位");
    if (!out.length) out.push("没有明显短板，可以直接投");
    return out;
  }

  // ---------- report ----------
  function detectDirection(text) {
    for (const [name, re] of ROLE_PRIORITY) if (count(text, re) >= 2) return name;
    let best = "未识别", hits = 0;
    for (const [name, re] of DIRECTIONS) {
      const n = count(text, re);
      if (n > hits) { best = name; hits = n; }
    }
    return best;
  }

  function jobProfile(jd, req) {
    const scores = [];
    for (const [name, re] of DIRECTIONS) {
      const n = count(jd, re);
      if (n) scores.push([name, n]);
    }
    scores.sort((a, b) => b[1] - a[1]);
    const eduMap = { 0: "未要求", 2: "大专及以上", 3: "本科及以上", 4: "硕士及以上", 5: "博士" };
    let level = "未写明";
    if (req.years !== null) {
      const y = req.years;
      level = y === 0 ? "应届 / 实习" : y < 1 ? "初级（0–1 年）" : y < 3 ? "中级（1–3 年）" : y < 5 ? "高级（3–5 年）" : "资深（5 年以上）";
    }
    return { direction: scores.length ? scores[0][0] : "未识别",
             distribution: scores.slice(0, 3), level,
             edu: eduMap[req.edu] || "未要求" };
  }

  function tierHits(res) {
    const matched = new Set(res.matched.map((m) => m[0]));
    const tiers = { "必须": [0, 0], "应该": [0, 0], "加分": [0, 0] };
    for (const r of res.requirements) {
      if (r.negated) continue;
      const tier = r.hard ? "必须" : (r.bonus ? "加分" : "应该");
      for (const s of r.skills) {
        tiers[tier][1] += 1;
        if (matched.has(s)) tiers[tier][0] += 1;
      }
    }
    const out = {};
    for (const k in tiers) {
      const [hit, total] = tiers[k];
      if (total) out[k] = { hit, total, ratio: hit / total };
    }
    return out;
  }

  function competitiveness(overall, tiers) {
    const mustRatio = tiers["必须"] ? tiers["必须"].ratio : 1;
    if (overall >= 0.8 && mustRatio >= 0.8) return ["A", "高度匹配，建议直接投，简历再按 JD 微调关键词"];
    if (overall >= 0.65) return ["B", "基本匹配，补 1–2 个缺口就有竞争力"];
    if (overall >= 0.5) return ["C", "有差距，建议补核心缺口后再投，或换相近岗位"];
    return ["D", "差距较大，更适合作为 1–3 个月的学习目标"];
  }

  function deepReport(res, dims, checks, jd, req, resume) {
    const tiers = res.hasSkills ? tierHits(res) : {};
    let [grade, verdict] = competitiveness(dims["综合"], tiers);

    const jdDir = detectDirection(jd);
    const cvDir = resume ? detectDirection(resume) : "未识别";
    const mismatch = jdDir !== "未识别" && cvDir !== "未识别" && jdDir !== cvDir;
    if (mismatch && (grade === "A" || grade === "B")) {
      grade = "C";
      verdict = `技能匹配度不低，但方向不一致：JD 偏「${jdDir}」，你的经历偏「${cvDir}」。建议补相关经历，或优先投 ${cvDir} 类岗位`;
    }

    const eduNeed = req.edu || 0;
    const yearsNeed = req.years;
    const lowBar = eduNeed <= 2 || yearsNeed === 0;
    const highBar = eduNeed >= 4 || (yearsNeed || 0) >= 5;

    if (lowBar && (grade === "C" || grade === "D")) {
      grade = "B";
      verdict = "这是一类低门槛岗位（学历/经验要求宽松），门槛不是筛人依据；能否胜任主要看具体技能与稳定性";
    } else if (highBar) {
      const cvEdu = resume ? eduLevel(resume) : 0;
      const cvYears = resume ? yearsOf(resume) : 0;
      const eduGap = eduNeed - cvEdu;
      const yearGap = (yearsNeed || 0) - cvYears;
      if (eduGap >= 1 || yearGap >= 2) {
        grade = "D";
        const reason = [];
        if (eduGap >= 1) reason.push(`学历差 ${eduGap} 档`);
        if (yearGap >= 2) reason.push(`年限差 ${yearGap} 年`);
        verdict = `岗位门槛偏高（${reason.join("、")}），硬性条件未达标，技能对口也难以过筛`;
      }
    }

    const questions = [];
    if (res.hasSkills) {
      for (const [s] of res.matched.slice(0, 2))
        questions.push(`【追问】你说熟悉 ${s}，讲一个具体项目：怎么做的？效果怎么衡量？`);
      for (const [s] of res.missing.slice(0, 2))
        questions.push(`【缺口】JD 要求 ${s}，你目前没相关经历——面试官大概率会问你怎么补`);
      questions.push("【通用】这个岗位最看重什么？你为什么觉得自己合适？");
    }

    const plan = [];
    const worst = checks.find((c) => !c[1]);
    if (worst) plan.push(["本周", `改简历：${worst[0]} —— ${worst[2]}`]);
    if (res.missing.length) plan.push(["两周内", `补 ${res.missing[0][0]}：做一个能演示的小项目，写进简历`]);
    if (dims["经验"] !== null && dims["经验"] < 0.7)
      plan.push(["一个月", "用项目深度对冲年限差距：挑 1 个完整项目做深，写成案例"]);
    if (!plan.length) plan.push(["本周", "简历已达标，按 JD 调整关键词后直接投"]);

    return { profile: jobProfile(jd, req), tiers, grade, verdict,
             direction: { jd: jdDir, cv: cvDir, mismatch },
             questions: questions.slice(0, 4), plan: plan.slice(0, 3) };
  }

  function fullReport(resume, jd) {
    const res = match(resume, jd);
    const { dims, req } = scoreDims(resume, jd, res.score, res.hasSkills);
    const checks = qualityChecks(resume);
    const suggestions = buildSuggestions(res, dims, checks, true);
    const deep = deepReport(res, dims, checks, jd, req, resume);
    return { res, dims, req, checks, suggestions, deep };
  }

  const api = { findSkills, parseJD, match, scoreDims, qualityChecks,
                detectDirection, jobProfile, tierHits, competitiveness,
                deepReport, fullReport, eduLevel, yearsOf };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.Engine = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
