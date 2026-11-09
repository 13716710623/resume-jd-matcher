"""
把人岗匹配结果导成一份单文件 HTML 仪表盘。

为什么用 HTML 而不是 tkinter：卡片、圆角、阴影、进度环、配色，
这些用 CSS 几行就搞定，tkinter 要写一堆 Canvas 自绘。
"""
import html
import sys
from datetime import datetime
from pathlib import Path

import analysis
import report as deep
from matcher import Matcher

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#F5F6F7;color:#191919;
  font:15px/1.65 "MiSans","Microsoft YaHei","PingFang SC",system-ui,sans-serif;
  padding:32px 20px 60px}
.wrap{max-width:1080px;margin:0 auto}
.top{margin-bottom:22px}
.top h1{font-size:26px;font-weight:700;letter-spacing:.3px}
.top p{color:#8C8C8C;font-size:13.5px;margin-top:6px}
.card{background:#fff;border-radius:16px;padding:22px 24px;margin-bottom:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.06),0 8px 24px rgba(0,0,0,.04)}
.card h2{font-size:14px;font-weight:600;color:#8C8C8C;letter-spacing:1px;
  margin-bottom:16px;text-transform:none}
.hero{display:flex;align-items:center;gap:34px;flex-wrap:wrap}
.ring{position:relative;width:150px;height:150px;flex:none}
.ring svg{transform:rotate(-90deg)}
.ring .val{position:absolute;inset:0;display:flex;align-items:center;
  justify-content:center;flex-direction:column}
.ring .val b{font-size:34px;font-weight:700;line-height:1}
.ring .val span{font-size:12px;color:#8C8C8C;margin-top:4px}
.hero-info{flex:1;min-width:260px}
.badge{display:inline-block;padding:5px 14px;border-radius:99px;
  font-size:13px;font-weight:600;color:#fff;background:#FF6900}
.badge.B{background:#F59E0B}.badge.C{background:#64748B}.badge.D{background:#9CA3AF}
.verdict{font-size:16px;margin-top:12px;line-height:1.6}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
.metric{margin-bottom:14px}
.metric .row{display:flex;justify-content:space-between;font-size:13.5px;
  margin-bottom:5px}
.metric .row span:last-child{color:#8C8C8C;font-variant-numeric:tabular-nums}
.bar{height:8px;background:#F0F0F0;border-radius:99px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:99px;background:#FF6900}
.bar i.ok{background:#00A854}.bar i.mid{background:#F59E0B}.bar i.bad{background:#E54D42}
.tier{display:flex;gap:3px;height:10px;border-radius:99px;overflow:hidden;
  background:#F0F0F0;margin:6px 0 4px}
.tier i{display:block;height:100%}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{padding:6px 12px;border-radius:99px;font-size:13px;background:#F5F6F7;
  border:1px solid #E6E6E6}
.chip.miss{background:#FEF2F2;border-color:#FECACA;color:#B91C1C}
.chip.hit{background:#F0FDF4;border-color:#BBF7D0;color:#15803D}
ul.plain{list-style:none}
ul.plain li{padding:9px 0;border-bottom:1px solid #F3F4F6;font-size:14px;
  display:flex;gap:10px;align-items:flex-start}
ul.plain li:last-child{border:0}
.ok{color:#00A854;font-weight:700}.no{color:#E54D42;font-weight:700}
.timeline{list-style:none;position:relative;padding-left:20px}
.timeline:before{content:"";position:absolute;left:5px;top:6px;bottom:6px;
  width:2px;background:#FFE0CC}
.timeline li{position:relative;padding:0 0 16px 12px;font-size:14px}
.timeline li:before{content:"";position:absolute;left:-17px;top:7px;width:10px;
  height:10px;border-radius:50%;background:#FF6900;
  box-shadow:0 0 0 3px #FFF3EB}
.timeline b{display:inline-block;min-width:56px;color:#FF6900}
.foot{color:#B0B4BA;font-size:12px;text-align:center;margin-top:26px}
.sec-note{color:#8C8C8C;font-size:13px;margin-top:-8px;margin-bottom:14px}
"""


def ring(score):
    r, c = 62, 2 * 3.14159 * 62
    done = c * score
    color = "#00A854" if score >= .6 else "#FF6900"
    return f"""
    <div class="ring">
      <svg width="150" height="150">
        <circle cx="75" cy="75" r="{r}" fill="none" stroke="#F0F0F0" stroke-width="12"/>
        <circle cx="75" cy="75" r="{r}" fill="none" stroke="{color}" stroke-width="12"
                stroke-linecap="round" stroke-dasharray="{done:.1f} {c:.1f}"/>
      </svg>
      <div class="val"><b>{score*100:.0f}%</b><span>综合匹配度</span></div>
    </div>"""


def metric(label, value, hint=""):
    if value is None:
        return f"""<div class="metric"><div class="row"><span>{label}</span>
                 <span>{hint or 'JD 未提要求'}</span></div>
                 <div class="bar"><i style="width:0"></i></div></div>"""
    cls = "ok" if value >= .75 else ("mid" if value >= .5 else "bad")
    return f"""<div class="metric"><div class="row"><span>{label}</span>
             <span>{value*100:.0f}%</span></div>
             <div class="bar"><i class="{cls}" style="width:{value*100:.0f}%"></i></div></div>"""


def _compute(resume, jd, out_path=None, matcher=None):
    m = matcher or Matcher()
    res = m.match(resume, jd)
    rep = analysis.analyze(resume, jd, res)
    d = rep["dims"]
    dp = deep.deep_report(res, d, rep["checks"], jd, rep["req"], resume)
    prof = dp["profile"]
    out = Path(out_path or (BASE / "报告.html"))

    hits = "".join(f'<span class="chip hit">{html.escape(s)}</span>'
                   for s, _, _ in res.matched) or '<span class="chip">无</span>'
    miss = "".join(f'<span class="chip miss">{html.escape(s)}</span>'
                   for s, _, _ in res.missing) or '<span class="chip">无</span>'

    tiers_html = ""
    for k in ("必须", "应该", "加分"):
        if k in dp["tiers"]:
            v = dp["tiers"][k]
            color = {"必须": "#E54D42", "应该": "#F59E0B", "加分": "#00A854"}[k]
            tiers_html += f"""
              <div class="metric">
                <div class="row"><span>{k}</span>
                  <span>{v['命中']}/{v['总数']}　{v['比例']*100:.0f}%</span></div>
                <div class="tier">
                  <i style="width:{v['比例']*100:.0f}%;background:{color}"></i>
                </div>
              </div>"""

    checks_html = "".join(
        f'<li><span class="{"ok" if ok else "no"}">{"✓" if ok else "✗"}</span>'
        f'<span><b>{html.escape(n)}</b>　{html.escape(note)}</span></li>'
        for n, ok, note in rep["checks"])

    qs_html = "".join(f"<li>{html.escape(q)}</li>" for q in dp["questions"]) \
        or "<li>JD 里没有技能要求，暂无预测</li>"

    plan_html = "".join(f"<li><b>{html.escape(w)}</b>{html.escape(t)}</li>"
                        for w, t in dp["plan"])

    suggestions = "".join(f"<li>{html.escape(s)}</li>" for s in rep["suggestions"])

    full = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>人岗匹配评估报告</title>
<style>{CSS}</style></head>
<body><div class="wrap">
  <div class="top">
    <h1>人岗匹配评估报告</h1>
    <p>简历 {len(resume)} 字　·　JD {len(jd)} 字　·　生成于 {datetime.now():%Y-%m-%d %H:%M}</p>
  </div>

  <div class="card">
    <div class="hero">
      {ring(res.score if res.has_skills else d['综合'])}
      <div class="hero-info">
        <span class="badge {dp['grade']}">竞争力 {dp['grade']}</span>
        <div class="verdict">{html.escape(dp['verdict'])}</div>
        <p class="sec-note" style="margin-top:10px">
          方向：{html.escape(prof['方向'])}　·　职级：{html.escape(prof['职级'])}　·
          学历门槛：{html.escape(prof['学历门槛'])}
        </p>
      </div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>分项评分</h2>
      {metric("技能匹配", d.get("技能匹配"))}
      {metric("经验", d.get("经验"))}
      {metric("学历", d.get("学历"))}
    </div>
    <div class="card">
      <h2>要求分级命中</h2>
      {tiers_html or '<p class="sec-note">JD 里没有技能要求</p>'}
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>已具备 {len(res.matched)} 项</h2>
      <div class="chips">{hits}</div>
    </div>
    <div class="card">
      <h2>缺失 {len(res.missing)} 项</h2>
      <div class="chips">{miss}</div>
    </div>
  </div>

  <div class="card">
    <h2>简历质量</h2>
    <ul class="plain">{checks_html}</ul>
  </div>

  <div class="grid">
    <div class="card">
      <h2>可能的面试问题</h2>
      <ul class="plain">{qs_html}</ul>
    </div>
    <div class="card">
      <h2>行动清单</h2>
      <ul class="timeline">{plan_html}</ul>
    </div>
  </div>

  <div class="card">
    <h2>改进建议</h2>
    <ul class="plain">{suggestions}</ul>
  </div>

  <p class="foot">由 resume_matcher 生成　·　纯规则、不联网、可解释</p>
</div></body></html>"""

    inner = full.split('<body><div class="wrap">')[1].rsplit("</div></body></html>")[0]
    out.write_text(full, encoding="utf-8")
    return inner, out, res, d, dp


def build(resume, jd, out_path=None):
    inner, out, res, d, dp = _compute(resume, jd, out_path)
    return out, res, d, dp


def render_inner(resume, jd, matcher=None):
    """给 Web 服务用：只返回仪表盘那一段 HTML。"""
    return _compute(resume, jd, matcher=matcher)[0]


if __name__ == "__main__":
    from cli import DEMO_JD, DEMO_RESUME
    p, res, d, dp = build(DEMO_RESUME, DEMO_JD)
    print(f"已生成：{p}（{p.stat().st_size/1024:.1f} KB）")
    print(f"匹配度 {res.score*100:.1f}%　评级 {dp['grade']}")
