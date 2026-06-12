# claude-notion-summarizer

[中文文档](README.zh.md)

A Claude Code Stop hook that automatically summarizes your conversations and writes structured notes to Notion — including a project-organized summary page and a prioritized Weekly To-do List.

## What It Does

Every time you type `/exit` to end a Claude Code session, this hook:

1. Reads the conversation transcript (`.jsonl` file)
2. Calls Claude API to generate a structured summary from the perspective of a senior Android engineer mentoring a junior dev
3. Creates a Notion page under **AI对话总结 → [Project Folder]** with the summary
4. Appends actionable to-do items to your **Weekly To-do List** page, grouped by module and sorted by priority

### Summary Format

```
## 一、工作概要
Brief overview of what was done

## 二、知识点总结
### 1. 知识点         — Technical knowledge points
### 2. 工作经验       — Reusable work experience
### 3. AI 错误教训    — Mistakes made when using AI
### 4. 欠缺知识点     — Knowledge gaps + study plan (table)
### 5. 额外建议       — Extra suggestions
```

### Notion Structure

```
AI对话总结/
├── 📁 Android开发/
│   └── 📝 Android开发 xxx描述 2025-01-15 by Claude
├── 📁 知识库搭建/
│   └── 📝 知识库搭建 xxx描述 2025-01-16 by Claude
└── 📁 日常对话/
    └── ...

Weekly To-do List
├── 📱 安卓
│   ├── 知识点学习
│   │   ├── 🔴 [紧急] Task A
│   │   └── 🟡 [重要] Task B
│   └── 实操
│       └── 🟢 [一般] Task C
└── 🎯 业余
    └── 工具配置
        └── 🟡 [重要] Task D
```

### Project Auto-detection

The hook infers the project name from conversation keywords:

| Keywords | Project |
|---|---|
| `notion` + `知识库` | 知识库搭建 |
| `android`, `ufs`, `adb` | Android开发 |
| `seeway` | Seeway |
| `fishmemory` | FishMemory |
| *(default)* | 日常对话 |

---

## Setup

### Prerequisites

- Python 3.10+ (uses `dict | None` type union syntax)
- Claude Code CLI
- A Notion account with an Integration token
- An Anthropic API key (or compatible proxy)

### Step 1 — Create a Notion Integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **New integration**, give it a name (e.g. "Claude Summarizer")
3. Copy the **Internal Integration Token** (starts with `ntn_` or `secret_`)
4. Open your **AI对话总结** page in Notion → click `...` → **Add connections** → select your integration
5. Do the same for your **Weekly To-do List** page

### Step 2 — Get Notion Page IDs

Open each page in Notion and copy the ID from the URL:
```
https://notion.so/your-workspace/Page-Title-<THIS_IS_THE_ID>
```
The ID is the 32-character hex string at the end (with or without dashes).

### Step 3 — Install the Hook

Copy `hooks/summarize_conversation.py` to your Claude hooks directory:

**Windows:**
```
C:\Users\YOUR_USERNAME\.claude\hooks\summarize_conversation.py
```

**macOS/Linux:**
```
~/.claude/hooks/summarize_conversation.py
```

### Step 4 — Configure `settings.json`

Edit `~/.claude/settings.json` (copy from `settings.json.example`):

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-api-key-here",
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
    "NOTION_TOKEN": "ntn_your_notion_token",
    "NOTION_PARENT_PAGE_ID": "your-ai-summary-page-id",
    "WEEKLY_TODO_PAGE_ID": "your-weekly-todo-page-id"
  },
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\Users\\YOUR_USERNAME\\.claude\\hooks\\summarize_conversation.py\""
          }
        ]
      }
    ]
  }
}
```

> **Using a custom API proxy?** Set `ANTHROPIC_BASE_URL` to your proxy URL. The script uses `Authorization: Bearer <token>` header (not `x-api-key`), which is compatible with most OpenAI-compatible proxies.

### Step 5 — Adjust Project Detection (Optional)

Edit the `infer_project()` function in the script to match your own projects:

```python
def infer_project(conversation_text: str) -> str:
    text_lower = conversation_text.lower()
    if "your_keyword" in text_lower:
        return "YourProjectName"
    ...
    return "日常对话"  # default
```

Also update the `base` path in `main()` to match your Claude projects directory. On Windows the default path is:
```python
base = Path.home() / ".claude" / "projects" / "C--Users----"
```

---

## Usage

End any Claude Code session with:
```
/exit
```

The hook runs automatically in the background. Check your Notion pages — a new summary page should appear within ~30 seconds.

### Manual Trigger

You can also run the script manually against any transcript file:
```bash
python summarize_conversation.py /path/to/session.jsonl
```

---

## Customizing the Summary Style

The summary persona and format are defined in `call_claude()` via the `system_prompt` variable. The default prompt frames Claude as a 10-year Android veteran mentoring a junior engineer. Edit it to match your domain or preferred summary style.

The structured todo output uses a sentinel-based approach — the LLM outputs both Markdown and JSON in a single response, split by `## __TODO_JSON__`. This avoids an extra API call.

---

## Troubleshooting

**Hook doesn't trigger**
- The Stop hook only fires on `/exit`, not on window close or force-quit. This is by design so you can selectively save sessions.
- Check `~/.claude/settings.json` is valid JSON.

**No Notion page created**
- Run the script manually with a transcript path to see stderr output.
- Verify your Notion integration has access to both pages (Add connections in Notion UI).
- Make sure `NOTION_PARENT_PAGE_ID` and `WEEKLY_TODO_PAGE_ID` are correct.

**`stdin path not received` in logs**
- This is normal on Windows. The script automatically falls back to finding the most recently modified `.jsonl` file in the last 10 minutes.

**Encoding errors on Windows**
- The script calls `sys.stdout.reconfigure(encoding="utf-8")` at startup. If you still see errors, run Python with `PYTHONIOENCODING=utf-8`.

---

## File Structure

```
claude-notion-summarizer/
├── hooks/
│   └── summarize_conversation.py   # Main hook script
├── settings.json.example           # Claude Code settings template
└── README.md
```

---

## License

MIT
