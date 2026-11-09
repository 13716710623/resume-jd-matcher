"""
图形界面（tkinter，Python 自带，不需要额外安装）

用法：
    python gui.py
"""
import json
import os
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import analysis
import report as deep
from cli import DEMO_JD, DEMO_RESUME
from matcher import Matcher

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FEEDBACK_PATH = Path(__file__).resolve().parent / "feedback.jsonl"

BG = "#F5F6F7"          # 页面底色
PANEL = "#FFFFFF"       # 卡片
FG = "#191919"          # 主文字
DIM = "#8C8C8C"         # 次要文字
ACCENT = "#FF6900"      # 小米橙
GREEN = "#00A854"
RED = "#E54D42"
BORDER = "#E6E6E6"


class App:
    def __init__(self, root):
        self.root = root
        self.matcher = Matcher()
        root.title("简历 — JD 匹配器")
        root.geometry("1180x760")
        root.configure(bg=BG)

        base = tkfont.nametofont("TkDefaultFont")
        ui = base.copy()
        ui.configure(family="Microsoft YaHei UI", size=10)
        root.option_add("*Font", ui)
        mono = base.copy()
        mono.configure(family="Consolas", size=10)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        # 次要按钮：白底 + 浅灰描边
        style.configure("TButton", background=PANEL, foreground=FG,
                        bordercolor=BORDER, lightcolor=PANEL, darkcolor=PANEL,
                        borderwidth=1, relief="flat", padding=(14, 7))
        style.map("TButton",
                  background=[("active", "#F0F0F0"), ("pressed", "#E8E8E8")],
                  bordercolor=[("active", "#D9D9D9")])
        # 主按钮：小米橙实心
        style.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF",
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                        borderwidth=1, relief="flat", padding=(18, 8))
        style.map("Accent.TButton",
                  background=[("active", "#E85D00"), ("pressed", "#CC5200"),
                              ("disabled", "#FFC299")],
                  bordercolor=[("active", "#E85D00")])

        # 顶部
        head = ttk.Frame(root)
        head.pack(fill="x", padx=16, pady=(14, 6))
        ttk.Label(head, text="简历 — JD 匹配器",
                  font=(ui.actual("family"), 14, "bold")).pack(side="left")
        ttk.Label(head, text="  粘贴两段文本，看看够不够格",
                  foreground=DIM).pack(side="left")

        # 主体三栏
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=16, pady=8)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        mid = ttk.Frame(body)
        mid.pack(side="left", fill="both", expand=True, padx=12)
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        self.txt_resume = self._pane(left, "① 你的简历")
        self.txt_jd = self._pane(mid, "② 岗位 JD")

        self.kpi = tk.Frame(right, bg=PANEL, highlightthickness=1,
                            highlightbackground=BORDER)
        self.kpi.pack(fill="x", pady=(0, 8))

        self.txt_out = self._pane(right, "③ 分析结果", mono, readonly=True)

        # 底部按钮
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(bar, text="加载示例", command=self.load_demo).pack(side="left")
        ttk.Button(bar, text="清空", command=self.clear).pack(side="left", padx=8)
        ttk.Button(bar, text="导出 HTML 报告",
                   command=self.export_report).pack(side="left")

        self.btn_analyze = ttk.Button(bar, text="分析", style="Accent.TButton",
                                      command=self.analyze)
        self.btn_analyze.pack(side="right")

        self.status = ttk.Label(bar, text="等输入", foreground=DIM)
        self.status.pack(side="right", padx=12)

        # 反馈条：结果准不准
        fb = ttk.Frame(root)
        fb.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Label(fb, text="这个结果准吗？", foreground=DIM).pack(side="left")
        self.btn_ok = ttk.Button(fb, text="👍 准确", width=10,
                                 command=lambda: self.record_feedback(+1))
        self.btn_ok.pack(side="left", padx=(10, 6))
        self.btn_bad = ttk.Button(fb, text="👎 有误", width=10,
                                  command=lambda: self.record_feedback(-1))
        self.btn_bad.pack(side="left")
        self.fb_note = ttk.Label(fb, text="（分析完可以点一下，会记到本地）",
                                 foreground=DIM)
        self.fb_note.pack(side="left", padx=14)
        self._enable_feedback(False)

    def _pane(self, parent, title, font=None, readonly=False):
        ttk.Label(parent, text=title, foreground=DIM).pack(anchor="w", pady=(0, 5))
        wrap = tk.Frame(parent, bg=PANEL, highlightthickness=1,
                        highlightbackground=BORDER)
        wrap.pack(fill="both", expand=True)
        txt = tk.Text(wrap, bg=PANEL, fg=FG, insertbackground=FG,
                      selectbackground="#FFE0CC", selectforeground=FG,
                      relief="flat", wrap="word", undo=True,
                      padx=12, pady=10, font=font)
        sb = ttk.Scrollbar(wrap, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        if readonly:
            txt.configure(state="disabled")
        return txt

    def load_demo(self):
        self._set(self.txt_resume, DEMO_RESUME)
        self._set(self.txt_jd, DEMO_JD)
        self.status.configure(text="已载入示例")
        self.analyze()

    def clear(self):
        self._set(self.txt_resume, "")
        self._set(self.txt_jd, "")
        self._set(self.txt_out, "", readonly=True)
        self.status.configure(text="")

    @staticmethod
    def _set(txt, value, readonly=False):
        state = txt.cget("state")
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("1.0", value)
        if readonly or state == "disabled":
            txt.configure(state="disabled")

    def analyze(self):
        resume = self.txt_resume.get("1.0", "end").strip()
        jd = self.txt_jd.get("1.0", "end").strip()
        if not resume or not jd:
            messagebox.showwarning("缺输入", "简历和 JD 都要填")
            self.status.configure(text="缺少输入", foreground=RED)
            return

        # ---- 立刻给反馈：按钮变灰 + 状态提示 ----
        self.last_result = None
        self._enable_feedback(False)
        self.fb_note.configure(text="", foreground=DIM)
        self.btn_analyze.configure(state="disabled", text="分析中…")
        self.status.configure(text="分析中…", foreground=ACCENT)
        self.root.update_idletasks()

        t0 = time.perf_counter()
        try:
            res = self.matcher.match(resume, jd)
        except ValueError as e:
            # 先更新状态条再弹窗，否则弹窗期间界面还停在「分析中…」
            self.status.configure(text=f"失败：{e}", foreground=RED)
            self.root.update_idletasks()
            messagebox.showerror("无法分析", str(e))
            return
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            self.btn_analyze.configure(state="normal", text="分析")
            self.root.update_idletasks()

        self.txt_out.configure(state="normal")
        self.txt_out.delete("1.0", "end")

        self._tag("h", ACCENT, bold=True)
        self._tag("ok", GREEN)
        self._tag("bad", RED)
        self._tag("dim", DIM)

        if getattr(res, "has_skills", True):
            self._w(f"匹配度  {res.score*100:.1f}%\n", "h")
            n = int(round(res.score * 30))
            self._w("█" * n + "░" * (30 - n) + "\n\n",
                    "ok" if res.score >= 0.6 else "bad")
        else:
            self._w("匹配度  ——\n", "h")
            self._w("JD 里没有技能要求，只评估学历/经验\n\n", "dim")

        self._w("已具备\n", "h")
        if res.matched:
            for s, w, c in res.matched:
                self._w(f"  ✓ {s}  (权重 {w:g}, 提到 {c} 次)\n", "ok")
        else:
            self._w("  （一项都没对上）\n", "dim")

        self._w("\n缺失\n", "h")
        if res.missing:
            for s, w, c in res.missing:
                self._w(f"  ✗ {s}  (权重 {w:g}, 提到 {c} 次)\n", "bad")
            self._w(f"\n建议先补「{res.missing[0][0]}」\n", "dim")
        else:
            self._w("  （没有缺口）\n", "dim")

        self._w("\nJD 拆解\n", "h")
        for r in res.requirements:
            flag = "否" if r.negated else ("加" if r.bonus else ("硬" if r.hard else "普"))
            self._w(f"  [{flag}] {r.text[:40]}\n", "dim")
            self._w(f"       → {', '.join(r.skills)}\n", "dim")

        # ---- 深度诊断 ----
        rep = analysis.analyze(resume, jd, res)
        d = rep["dims"]
        self._w("\n分项评分\n", "h")
        for k in ("技能匹配", "经验", "学历"):
            v = d.get(k)
            if v is None:
                self._w(f"  {k}  JD 未提要求\n", "dim")
            else:
                bar = "█" * int(round(v * 14)) + "░" * (14 - int(round(v * 14)))
                tag = "ok" if v >= 0.6 else "bad"
                self._w(f"  {k}  {bar} {v*100:.0f}%\n", tag)
        self._w(f"  综合    {d['综合']*100:.0f}%\n", "h")

        self._w("\n简历质量\n", "h")
        for name, ok, note in rep["checks"]:
            self._w(f"  {'✓' if ok else '✗'} {name}：{note}\n",
                    "ok" if ok else "bad")

        self._w("\n改进建议\n", "h")
        for i, s in enumerate(rep["suggestions"], 1):
            self._w(f"  {i}. {s}\n", "dim")

        dp = deep.deep_report(res, d, rep["checks"], jd, rep["req"], resume)
        self._render_kpi(res, dp)
        prof = dp["profile"]
        self._w("\n岗位画像\n", "h")
        self._w(f"  方向：{prof['方向']}　职级：{prof['职级']}\n", "dim")
        self._w(f"  学历门槛：{prof['学历门槛']}\n", "dim")

        if dp["tiers"]:
            self._w("\n要求分级命中\n", "h")
            for k in ("必须", "应该", "加分"):
                if k in dp["tiers"]:
                    v = dp["tiers"][k]
                    bar = "█" * int(round(v["比例"] * 12)) + "░" * (12 - int(round(v["比例"] * 12)))
                    self._w(f"  {k}  {v['命中']}/{v['总数']}  {bar} {v['比例']*100:.0f}%\n",
                            "ok" if v["比例"] >= 0.6 else "bad")

        self._w(f"\n竞争力  {dp['grade']} —— {dp['verdict']}\n", "h")

        if dp["questions"]:
            self._w("\n可能的面试问题\n", "h")
            for i, q in enumerate(dp["questions"], 1):
                self._w(f"  {i}. {q}\n", "dim")

        self._w("\n行动清单\n", "h")
        for when, what in dp["plan"]:
            self._w(f"  {when}：{what}\n", "dim")

        self.txt_out.configure(state="disabled")
        self.last_result = res
        self.btn_ok.configure(state="normal")
        self.btn_bad.configure(state="normal")
        self.fb_note.configure(text="（结果准不准？点一下上面）", foreground=DIM)
        if getattr(res, "has_skills", True):
            self.status.configure(
                text=f"完成 · {elapsed:.1f} ms · {len(res.matched)} 命中 / "
                     f"{len(res.missing)} 缺失",
                foreground=GREEN if res.score >= 0.6 else "#d29922")
        else:
            self.status.configure(text=f"完成 · {elapsed:.1f} ms · 无技能要求",
                                  foreground=DIM)

    def export_report(self):
        """把当前结果导成网页仪表盘，并用浏览器打开。"""
        resume = self.txt_resume.get("1.0", "end").strip()
        jd = self.txt_jd.get("1.0", "end").strip()
        if not resume or not jd:
            messagebox.showwarning("缺输入", "简历和 JD 都要填")
            return
        try:
            import export_html
            out, res, dims, dp = export_html.build(resume, jd)
        except ValueError as e:
            messagebox.showerror("无法生成", str(e))
            return
        except Exception as e:                      # noqa: BLE001
            messagebox.showerror("生成失败", f"{type(e).__name__}: {e}")
            return
        try:
            os.startfile(out)                       # Windows 用默认浏览器打开
        except Exception:
            pass
        self.fb_note.configure(text=f"已导出：{out.name}（评级 {dp['grade']}）",
                               foreground=GREEN)

    def _render_kpi(self, res, dp):
        """顶部仪表盘：大分数 + 评级徽章 + 进度条。"""
        for w in self.kpi.winfo_children():
            w.destroy()

        has_skills = getattr(res, "has_skills", True)
        score = res.score if has_skills else 0.0
        color = GREEN if score >= 0.6 else ACCENT

        left = tk.Frame(self.kpi, bg=PANEL)
        left.pack(side="left", padx=(16, 10), pady=10)
        if has_skills:
            tk.Label(left, text=f"{score*100:.0f}%", bg=PANEL, fg=color,
                     font=("Microsoft YaHei UI", 25, "bold")).pack(anchor="w")
            tk.Label(left, text="综合匹配度", bg=PANEL, fg=DIM,
                     font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        else:
            tk.Label(left, text="—", bg=PANEL, fg=DIM,
                     font=("Microsoft YaHei UI", 25, "bold")).pack(anchor="w")
            tk.Label(left, text="无技能要求", bg=PANEL, fg=DIM,
                     font=("Microsoft YaHei UI", 9)).pack(anchor="w")

        right = tk.Frame(self.kpi, bg=PANEL)
        right.pack(side="left", fill="both", expand=True, padx=(0, 16), pady=10)

        top = tk.Frame(right, bg=PANEL)
        top.pack(fill="x")
        tk.Label(top, text=f" 竞争力 {dp['grade']} ", bg=ACCENT, fg="#FFFFFF",
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        tk.Label(top, text=f"   {len(res.matched)} 命中 / {len(res.missing)} 缺失",
                 bg=PANEL, fg=DIM, font=("Microsoft YaHei UI", 9)).pack(side="left")

        canvas = tk.Canvas(right, height=8, bg=PANEL, highlightthickness=0)
        canvas.pack(fill="x", pady=(9, 4))
        canvas.update_idletasks()
        width = max(canvas.winfo_width(), 240)
        canvas.create_rectangle(0, 0, width, 8, fill="#EFEFEF", outline="")
        if score > 0:
            canvas.create_rectangle(0, 0, width * score, 8, fill=color, outline="")

        tk.Label(right, text="需求：技能 60% / 经验 20% / 学历 20%",
                 bg=PANEL, fg=DIM, font=("Microsoft YaHei UI", 8)).pack(anchor="w")

    def _enable_feedback(self, on):
        state = "normal" if on else "disabled"
        self.btn_ok.configure(state=state)
        self.btn_bad.configure(state=state)

    def record_feedback(self, vote):
        """把这次评价追加到 feedback.jsonl，方便以后挑词表毛病。"""
        res = getattr(self, "last_result", None)
        if res is None:
            return
        rec = {
            "时间": datetime.now().isoformat(timespec="seconds"),
            "评价": "准确" if vote > 0 else "有误",
            "匹配度": round(res.score, 4),
            "命中": [s for s, _, _ in res.matched],
            "缺失": [s for s, _, _ in res.missing],
            "简历摘要": self.txt_resume.get("1.0", "end").strip()[:200],
            "JD摘要": self.txt_jd.get("1.0", "end").strip()[:300],
        }
        try:
            with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.fb_note.configure(
                text=f"已记录（{rec['评价']}）→ {FEEDBACK_PATH.name}",
                foreground=GREEN)
        except OSError as e:
            self.fb_note.configure(text=f"记录失败：{e}", foreground=RED)
        self._enable_feedback(False)

    def _tag(self, name, color, bold=False):
        self.txt_out.tag_configure(name, foreground=color)

    def _w(self, text, tag=None):
        self.txt_out.insert("end", text, tag or ())


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
