"""匹配器单元测试（只用标准库 unittest，不依赖 pytest）"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from matcher import Matcher  # noqa: E402


class TestSynonym(unittest.TestCase):
    """同义词归一"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_alias_maps_to_standard(self):
        # 简历写「多智能体」，JD 写「Agent」，应视为同一技能
        res = self.m.match("做过智能体编排，熟悉多智能体协作", "要求熟悉 Agent 开发")
        self.assertEqual([s for s, _, _ in res.matched], ["Agent"])
        self.assertAlmostEqual(res.score, 1.0)

    def test_case_insensitive(self):
        res = self.m.match("熟悉 PYTHON", "要求 Python")
        self.assertAlmostEqual(res.score, 1.0)

    def test_chinese_alias(self):
        res = self.m.match("做过检索增强", "要熟悉 RAG")
        self.assertAlmostEqual(res.score, 1.0)


class TestBoundary(unittest.TestCase):
    """英文词边界：避免短词误命中"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_storage_not_rag(self):
        # storage 里含 rag，但不应算作 RAG
        res = self.m.match("维护过 storage 系统", "要求 RAG 检索")
        self.assertEqual(res.matched, [])
        self.assertAlmostEqual(res.score, 0.0)

    def test_agent_not_agentic(self):
        res = self.m.match("写过 agentic workflow", "要求 Agent 开发")
        self.assertEqual(res.matched, [])

    def test_cjk_adjacent_english(self):
        # 中文紧挨英文（真实 JD 常见写法）：不能因为边界判定被跳过
        res = self.m.match("会点 Python", "熟练掌握python")
        self.assertEqual([s for s, _, _ in res.matched], ["Python"])
        self.assertAlmostEqual(res.score, 1.0)

    def test_cjk_both_sides_english(self):
        # 两边都紧贴中文：简历「我用Python写后端」，JD「熟悉Python开发」
        res = self.m.match("我用Python写后端", "熟悉Python开发")
        self.assertAlmostEqual(res.score, 1.0)

    def test_cpp_matches(self):
        res = self.m.match("熟悉 C++", "要求 C++")
        self.assertAlmostEqual(res.score, 1.0)


class TestWeight(unittest.TestCase):
    """权重：硬性 > 普通 > 加分"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_hard_beats_bonus(self):
        # 只满足加分项，分数应低于 1
        res = self.m.match("了解 LoRA", "必须精通 Python；了解 LoRA 者优先")
        self.assertGreater(res.score, 0)
        self.assertLess(res.score, 1)

    def test_repeated_mention_adds_weight(self):
        jd = "必须熟悉 Python；日常用 Python 开发；Python 是硬要求"
        res = self.m.match("熟悉 Python", jd)
        self.assertAlmostEqual(res.score, 1.0)
        # 三句里只有两句含硬性词：2 + 1 + 2 = 5.0
        self.assertAlmostEqual(res.total_weight, 5.0)

    def test_partial_credit(self):
        jd = "必须熟悉 Python；必须熟悉 Docker"
        res = self.m.match("熟悉 Python", jd)
        self.assertAlmostEqual(res.score, 0.5)


class TestProficiency(unittest.TestCase):
    """熟练度：了解 ≠ 精通"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_zhiliao_lower_than_shuxi(self):
        low = self.m.match("了解 Docker", "必须精通 Docker")
        high = self.m.match("熟悉 Docker", "必须精通 Docker")
        self.assertLess(low.score, high.score)
        self.assertAlmostEqual(high.score, 1.0)

    def test_decimal_year_not_split(self):
        # 「3.5 年」不能被编号规则切成「3.」和「5 年」
        reqs = self.m.parse_jd("要求 3.5 年经验，必须熟悉 Python")
        self.assertEqual(len(reqs), 1)
        self.assertIn("Python", reqs[0].skills)
        self.assertAlmostEqual(reqs[0].weight, 2.0)


class TestNegation(unittest.TestCase):
    """否定句不应计入要求"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_negated_requirement_ignored(self):
        jd = "必须熟悉 Python。不需要论文复现经验。"
        res = self.m.match("熟悉 Python", jd)
        self.assertAlmostEqual(res.score, 1.0)
        self.assertTrue(any(r.negated for r in res.requirements))

    def test_negated_does_not_create_missing(self):
        jd = "熟悉 Python；不要求 CUDA"
        res = self.m.match("熟悉 Python", jd)
        self.assertEqual(res.missing, [])


class TestErrors(unittest.TestCase):
    """输入异常要有明确报错"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_empty_resume(self):
        with self.assertRaises(ValueError):
            self.m.match("   ", "要求 Python")

    def test_empty_jd(self):
        with self.assertRaises(ValueError):
            self.m.match("熟悉 Python", "")

    def test_jd_without_skills(self):
        with self.assertRaises(ValueError):
            self.m.match("熟悉 Python", "负责办公区日常行政事务与考勤登记")

    def test_jd_only_education(self):
        # JD 只有学历要求时不应报错，只是不评估技能
        res = self.m.match("本科", "本科及以上")
        self.assertFalse(res.has_skills)
        self.assertAlmostEqual(res.score, 0.0)

    def test_long_text_no_crash(self):
        # 10 万字符不应崩
        big = "熟悉 Python。" * 8000
        res = self.m.match("熟悉 Python", big)
        self.assertGreater(res.score, 0.9)


class TestCalibration(unittest.TestCase):
    """子句否定 + 门槛校准"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_clause_level_negation(self):
        # "不需要论文复现，但需要 RAG"：前半句否定，后半句不受影响
        reqs = self.m.parse_jd("不需要论文复现，但需要 RAG 经验")
        by_skill = {s: r.negated for r in reqs for s in r.skills}
        self.assertTrue(by_skill.get("论文复现"))
        self.assertFalse(by_skill.get("RAG"))

    def test_rag_still_counts_after_negation(self):
        res = self.m.match("做过 RAG 项目", "不需要论文复现，但需要 RAG 经验")
        self.assertAlmostEqual(res.score, 1.0)

    def test_low_bar_not_judged_too_low(self):
        # 低门槛岗位（大专 + 无经验）不该因为技能没写就判 C/D
        import analysis
        import report as deep
        jd = "负责数据标注；任职要求：大专及以上，无经验要求"
        res = self.m.match("本科，3 年开发", jd)
        rep = analysis.analyze("本科，3 年开发", jd, res)
        dp = deep.deep_report(res, rep["dims"], rep["checks"], jd, rep["req"],
                              "本科，3 年开发")
        self.assertIn(dp["grade"], ("A", "B"))

    def test_high_bar_judged_low(self):
        # 高门槛岗位（硕士 + 5 年）未达标时应判低
        import analysis
        import report as deep
        jd = "任职要求：硕士及以上，5 年以上经验，必须熟悉 CUDA"
        res = self.m.match("本科，3 年 Python", jd)
        rep = analysis.analyze("本科，3 年 Python", jd, res)
        dp = deep.deep_report(res, rep["dims"], rep["checks"], jd, rep["req"],
                              "本科，3 年 Python")
        self.assertEqual(dp["grade"], "D")


class TestCoverage(unittest.TestCase):
    """信息量与领域覆盖"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_n_requirements_counted(self):
        res = self.m.match("熟悉 Python", "必须熟悉 Python；必须熟悉 Docker；熟悉 RAG")
        self.assertGreaterEqual(res.n_requirements, 2)

    def test_uncovered_domain_flagged(self):
        res = self.m.match("会 Python，本科",
                           "本科及以上，负责前端开发，精通 React 与 TypeScript，熟悉 Webpack")
        self.assertFalse(res.has_skills)
        self.assertTrue(res.uncovered)

    def test_low_coverage_marks_low_confidence(self):
        import analysis
        import report as deep
        jd = "熟悉 Python"
        res = self.m.match("熟悉 Python", jd)
        rep = analysis.analyze("熟悉 Python", jd, res)
        dp = deep.deep_report(res, rep["dims"], rep["checks"], jd, rep["req"], "熟悉 Python")
        self.assertEqual(dp["confidence"], "低")


class TestExplain(unittest.TestCase):
    """可解释性：每个要求都能说清来源"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_requirements_have_text_and_skills(self):
        jd = "岗位职责：\n1. 必须熟悉 RAG；\n2. 熟悉 LangChain 者优先。"
        res = self.m.match("做过 RAG", jd)
        self.assertEqual(len(res.requirements), 2)
        for r in res.requirements:
            self.assertTrue(r.text)
            self.assertTrue(r.skills)

    def test_notes_for_negation(self):
        res = self.m.match("懂 Python", "要求 Python；不需要 CUDA")
        self.assertTrue(res.notes)


class TestDeepReport(unittest.TestCase):
    """岗位画像 / 分级 / 评级"""

    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def test_direction_detected(self):
        import report
        self.m.match("会 Python", "负责 RAG 应用落地，搭建 Agent 工作流")
        prof = report.job_profile("负责 RAG 应用落地，搭建 Agent 工作流", {"经验年数": None, "学历": 0})
        self.assertIn("应用", prof["方向"])

    def test_grade_levels(self):
        import report
        self.assertEqual(report.competitiveness(0.9, {"必须": {"比例": 1.0}})[0], "A")
        self.assertEqual(report.competitiveness(0.7, {})[0], "B")
        self.assertEqual(report.competitiveness(0.55, {})[0], "C")
        self.assertEqual(report.competitiveness(0.2, {})[0], "D")

    def test_tiers_split(self):
        import report
        res = self.m.match("熟悉 Python", "必须精通 Python；熟悉 Docker；了解 LoRA 者优先")
        tiers = report.tier_hits(res)
        self.assertIn("必须", tiers)
        self.assertEqual(tiers["必须"]["比例"], 1.0)
        self.assertEqual(tiers["应该"]["比例"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
