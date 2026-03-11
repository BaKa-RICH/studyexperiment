#!/usr/bin/env python3
"""
将 task_forum JSON 转换为可读的 HTML 讨论面板。

用法：
    python build_forum.py                  # 读 task_forum.json → task_forum.html
    python build_forum.py acc_bug          # 读 acc_bug.json    → acc_bug.html
    python build_forum.py forum/my_task    # 读 forum/my_task.json → forum/my_task.html

规则：
    - 参数为不带扩展名的路径（或带 .json 的完整路径都可以）
    - 输出 HTML 与输入 JSON 同目录同名，仅扩展名改为 .html
"""
import json
import html
import sys
from pathlib import Path

AGENT_AVATAR = {"Sonnet": "S", "GPT": "G", "Opus": "O", "Gemini": "G"}
AGENT_CLASS  = {"Sonnet": "sonnet", "GPT": "gpt", "Opus": "opus", "Gemini": "gemini"}


def resolve_paths(arg: str | None) -> tuple[Path, Path]:
    """根据命令行参数解析 JSON / HTML 路径对。"""
    base = Path(arg) if arg else Path("task_forum")
    if base.suffix.lower() == ".json":
        json_path = base
    else:
        json_path = base.with_suffix(".json")
    html_path = json_path.with_suffix(".html")
    return json_path, html_path


def escape_html(text: str) -> str:
    return html.escape(text).replace("\n", "<br>\n")


def render_message(msg: dict) -> str:
    agent   = msg.get("agent", "Unknown")
    mtype   = msg.get("type", "MSG")
    ts      = msg.get("time", "")
    content = msg.get("content", "")

    agent_cls = AGENT_CLASS.get(agent, "sonnet")
    avatar    = AGENT_AVATAR.get(agent, "?")

    # 粗体渲染
    parts = content.split("**")
    buf = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            buf.append("<strong>")
        buf.append(html.escape(p))
        if i % 2 == 1:
            buf.append("</strong>")
    content_html = "".join(buf).replace("\n", "<br>\n")

    # 消息边框颜色：type 优先，否则按 agent
    type_css_map = {
        "PROPOSAL":       "proposal",
        "VOTE":           "vote",
        "EXECUTION":      "execution",
        "QA":             "qa",
        "REPLY":          "reply",
        "CONTEXT_SHARE":  "context-share",
        "SUBTASK_RESULT": "subtask-result",
    }
    type_cls = type_css_map.get(mtype, agent_cls)

    return f'''    <div class="msg {type_cls} {agent_cls}">
      <div class="msg-avatar">{avatar}</div>
      <div class="msg-body">
        <div class="msg-head">
          <span class="msg-user">{html.escape(agent)}</span>
          <span class="msg-tag">{html.escape(mtype)}</span>
          <span class="msg-time">{html.escape(ts)}</span>
        </div>
        <div class="msg-content">{content_html}</div>
      </div>
    </div>'''


HTML_TMPL = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forum · {title}</title>
<style>
  :root {{
    --bg:#f0f2f5; --card:#fff; --border:#dadce0; --text:#202124; --sec:#5f6368;
    --sonnet:#5c6bc0; --sonnet-bg:#e8eaf6;
    --gpt:#00897b;   --gpt-bg:#e0f2f1;
    --opus:#7b1fa2;  --opus-bg:#f3e5f5;
    --gemini:#f57c00;--gemini-bg:#fff3e0;
    --mono:'SFMono-Regular',Consolas,monospace;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
    background:var(--bg);color:var(--text);line-height:1.65;font-size:15px}}
  .page{{max-width:920px;margin:0 auto;padding:24px 20px 60px}}
  .header{{background:var(--card);border-radius:12px;padding:24px 28px;
    margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.06);border:1px solid var(--border)}}
  .header h1{{font-size:1.45rem}}
  .header .meta{{color:var(--sec);font-size:13px;margin-top:8px}}
  .legend{{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:16px;
    padding:10px 16px;background:var(--card);border-radius:8px;
    border:1px solid var(--border);font-size:13px}}
  .legend span{{display:flex;align-items:center;gap:6px}}
  .dot{{width:10px;height:10px;border-radius:50%;display:inline-block}}
  .thread{{display:flex;flex-direction:column;gap:14px}}
  .msg{{display:flex;gap:16px;background:var(--card);border-radius:12px;
    padding:18px 22px;box-shadow:0 1px 4px rgba(0,0,0,.06);
    border:1px solid var(--border);border-left:4px solid var(--border)}}
  /* 左侧色条：type 优先 */
  .msg.proposal       {{border-left-color:#1a73e8}}
  .msg.context-share  {{border-left-color:#26a69a;background:#f0fffe}}
  .msg.subtask-result {{border-left-color:#8d6e63;background:#fdf8f5}}
  .msg.reply          {{border-left-color:#9e9e9e}}
  .msg.vote           {{border-left-color:#78909c}}
  .msg.execution      {{border-left-color:#43a047}}
  .msg.qa             {{border-left-color:#fb8c00}}
  /* 兜底按 agent */
  .msg.sonnet {{border-left-color:var(--sonnet)}}
  .msg.gpt    {{border-left-color:var(--gpt)}}
  .msg.opus   {{border-left-color:var(--opus)}}
  .msg.gemini {{border-left-color:var(--gemini)}}
  .msg-avatar{{flex-shrink:0;width:42px;height:42px;border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    font-weight:700;font-size:13px;color:#fff}}
  .msg.sonnet .msg-avatar{{background:var(--sonnet)}}
  .msg.gpt    .msg-avatar{{background:var(--gpt)}}
  .msg.opus   .msg-avatar{{background:var(--opus)}}
  .msg.gemini .msg-avatar{{background:var(--gemini)}}
  .msg.context-share  .msg-avatar{{background:#26a69a}}
  .msg.subtask-result .msg-avatar{{background:#8d6e63}}
  .msg-body{{flex:1;min-width:0}}
  .msg-head{{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}}
  .msg-user{{font-weight:700;font-size:14px}}
  .msg.sonnet .msg-user{{color:var(--sonnet)}}
  .msg.gpt    .msg-user{{color:var(--gpt)}}
  .msg.opus   .msg-user{{color:var(--opus)}}
  .msg.gemini .msg-user{{color:var(--gemini)}}
  .msg-tag{{font-size:11px;padding:2px 8px;border-radius:10px;
    background:#f1f3f4;color:var(--sec)}}
  .msg.context-share  .msg-tag{{background:#e0f2f1;color:#00695c}}
  .msg.subtask-result .msg-tag{{background:#efebe9;color:#4e342e}}
  .msg.execution      .msg-tag{{background:#e8f5e9;color:#2e7d32}}
  .msg.qa             .msg-tag{{background:#fff3e0;color:#e65100}}
  .msg.proposal       .msg-tag{{background:#e8f0fe;color:#1557b0}}
  .msg-time{{font-size:12px;color:var(--sec);margin-left:auto}}
  .msg-content{{font-size:14px;line-height:1.7;white-space:pre-wrap;word-break:break-word}}
  .msg-content strong{{font-weight:600}}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>📋 {title}</h1>
    <div class="meta">
      🗓 {created} &nbsp;·&nbsp; 主 Agent: {main_agent} &nbsp;·&nbsp; 审阅: {reviewers}
      &nbsp;·&nbsp; 📄 {json_name}
    </div>
  </div>
  <div class="legend">
    <span><span class="dot" style="background:var(--sonnet)"></span>Sonnet</span>
    <span><span class="dot" style="background:var(--gpt)"></span>GPT</span>
    <span><span class="dot" style="background:var(--opus)"></span>Opus</span>
    <span><span class="dot" style="background:var(--gemini)"></span>Gemini</span>
    <span><span class="dot" style="background:#26a69a"></span>CONTEXT_SHARE</span>
    <span><span class="dot" style="background:#8d6e63"></span>SUBTASK_RESULT</span>
    <span><span class="dot" style="background:#1a73e8"></span>PROPOSAL</span>
    <span><span class="dot" style="background:#43a047"></span>EXECUTION</span>
    <span><span class="dot" style="background:#fb8c00"></span>QA</span>
  </div>
  <div class="thread">
{messages}
  </div>
</div>
</body>
</html>"""


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    json_path, html_path = resolve_paths(arg)

    if not json_path.exists():
        print(f"Error: {json_path} not found", file=sys.stderr)
        print(f"  Usage: python build_forum.py [task_slug]", file=sys.stderr)
        print(f"  Example: python build_forum.py acc_bug  → reads acc_bug.json", file=sys.stderr)
        return 1

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages_html = "\n".join(render_message(m) for m in data.get("messages", []))

    content = HTML_TMPL.format(
        title     = html.escape(data.get("title", "Task Forum")),
        created   = html.escape(data.get("created", "")),
        main_agent= html.escape(data.get("main_agent", "Sonnet")),
        reviewers = html.escape(", ".join(data.get("reviewers", []))),
        json_name = html.escape(json_path.name),
        messages  = messages_html,
    )

    html_path.parent.mkdir(parents=True, exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Generated {html_path}  (from {json_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
