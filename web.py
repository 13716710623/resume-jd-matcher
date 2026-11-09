"""
本地 Web 应用：浏览器里用人岗匹配器。

为什么不再用 tkinter：卡片、阴影、圆角、环形进度、动效，
这些是 CSS 几行的事，tkinter 要几百行 Canvas 自绘还画不好。

启动：
    python web.py            # 自动打开 http://127.0.0.1:8765
    python web.py --port 9000 --no-browser
"""
import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import export_html
from matcher import Matcher

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
MATCHER = Matcher()

PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>人岗匹配 · 智能评估</title>
<style>
__CSS__
/* ---- 输入区 ---- */
.inputs{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
@media(max-width:820px){.inputs{grid-template-columns:1fr}}
.inbox{background:#fff;border-radius:16px;padding:16px 18px;
  box-shadow:0 1px 3px rgba(0,0,0,.06),0 8px 24px rgba(0,0,0,.04)}
.inbox label{display:block;font-size:13px;color:#8C8C8C;margin-bottom:8px;
  letter-spacing:.5px}
.inbox textarea{width:100%;height:170px;border:1px solid #EFEFEF;border-radius:10px;
  background:#FAFAFA;padding:12px;font:13.5px/1.7 inherit;color:#191919;
  resize:vertical;outline:none}
.inbox textarea:focus{border-color:#FF6900;background:#fff}
.actions{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.btn{border:0;border-radius:99px;padding:13px 34px;font-size:15px;font-weight:600;
  cursor:pointer;background:#FF6900;color:#fff;transition:.18s}
.btn:hover{background:#E85D00;transform:translateY(-1px)}
.btn:active{transform:none}
.btn:disabled{background:#FFC299;cursor:not-allowed;transform:none}
.btn.ghost{background:#fff;color:#191919;border:1px solid #E6E6E6}
.btn.ghost:hover{background:#F5F6F7}
.hint{color:#8C8C8C;font-size:13px}
#result{margin-top:6px}
.skel{color:#B0B4BA;text-align:center;padding:50px 0;font-size:14px}
.spin{display:inline-block;width:16px;height:16px;border:2px solid #FFD9BF;
  border-top-color:#FF6900;border-radius:50%;animation:sp .7s linear infinite;
  vertical-align:-3px;margin-right:8px}
@keyframes sp{to{transform:rotate(360deg)}}
</style></head>
<body><div class="wrap">
  <div class="top">
    <h1>人岗匹配 · 智能评估</h1>
    <p>粘贴简历和 JD，10 秒内拿到一份可解释的评估报告</p>
  </div>

  <div class="inputs">
    <div class="inbox">
      <label>① 你的简历</label>
      <textarea id="resume" placeholder="粘贴简历正文，或只要关键经历…"></textarea>
    </div>
    <div class="inbox">
      <label>② 岗位 JD</label>
      <textarea id="jd" placeholder="粘贴招聘要求原文…"></textarea>
    </div>
  </div>

  <div class="actions">
    <button class="btn" id="go">开始分析</button>
    <button class="btn ghost" id="demo">加载示例</button>
    <span class="hint" id="hint"></span>
  </div>

  <div id="result"><div class="skel">填入内容后点「开始分析」</div></div>
</div>

<script>
const $ = s => document.querySelector(s);
const btn = $('#go'), hint = $('#hint'), box = $('#result');

$('#demo').onclick = async () => {
  hint.textContent = '载入示例…';
  const r = await fetch('/api/demo');
  const d = await r.json();
  $('#resume').value = d.resume;
  $('#jd').value = d.jd;
  hint.textContent = '';
  go();
};

btn.onclick = go;
async function go(){
  const resume = $('#resume').value.trim();
  const jd = $('#jd').value.trim();
  if(!resume || !jd){ hint.textContent = '简历和 JD 都要填'; return; }

  btn.disabled = true;
  btn.textContent = '分析中…';
  hint.textContent = '';
  box.innerHTML = '<div class="skel"><span class="spin"></span>正在分析…</div>';

  const t0 = performance.now();
  try{
    const r = await fetch('/api/analyze', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({resume, jd})
    });
    const d = await r.json();
    if(!r.ok){ throw new Error(d.error || '分析失败'); }
    box.innerHTML = d.html;
    hint.textContent = `完成 · ${Math.round(performance.now()-t0)} ms`;
  }catch(e){
    box.innerHTML = `<div class="card"><p style="color:#E54D42">${e.message}</p></div>`;
    hint.textContent = '';
  }finally{
    btn.disabled = false;
    btn.textContent = '开始分析';
  }
}

// 带 ?demo=1 打开时自动跑一遍（截图 / 演示用）
if (new URLSearchParams(location.search).has('demo')) {
  window.addEventListener('load', () => $('#demo').click());
}
</script>
</body></html>"""


def analyze_payload(resume, jd):
    """跑一遍分析，返回仪表盘 HTML 片段。"""
    if not resume.strip() or not jd.strip():
        raise ValueError("简历和 JD 都要填")
    return export_html.render_inner(resume, jd, MATCHER)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass                                  # 不刷屏

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path          # 去掉 ?demo=1 之类的查询串
        if path in ("/", "/index.html"):
            self._send(200, PAGE.replace("__CSS__", export_html.CSS))
        elif path == "/api/demo":
            from cli import DEMO_JD, DEMO_RESUME
            self._send(200, json.dumps({"resume": DEMO_RESUME, "jd": DEMO_JD},
                                       ensure_ascii=False),
                       "application/json; charset=utf-8")
        else:
            self._send(404, "not found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/analyze":
            self._send(404, "not found")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            html = analyze_payload(payload.get("resume", ""), payload.get("jd", ""))
            self._send(200, json.dumps({"html": html}, ensure_ascii=False),
                       "application/json; charset=utf-8")
        except ValueError as e:
            self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False),
                       "application/json; charset=utf-8")
        except Exception as e:                # noqa: BLE001
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"},
                                       ensure_ascii=False),
                       "application/json; charset=utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"✓ 服务已启动：{url}")
    print("  按 Ctrl+C 停止")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        srv.shutdown()


if __name__ == "__main__":
    main()
