#!/usr/bin/env python3
"""
Claude Code stop hook: auto-summarize conversation and write to Notion
Triggered on conversation end (/exit), generates structured summary and stores
it under AI > AI对话总结 directory in Notion.
"""

import os
import sys
import json
import re
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Force stdout/stderr to use UTF-8 (important on Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── Configuration ─────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")

# The Notion page ID of your "AI对话总结" parent page
# Find it in the page URL: notion.so/your-workspace/PAGE-TITLE-<THIS_ID>
NOTION_PARENT_PAGE_ID = os.environ.get("NOTION_PARENT_PAGE_ID", "YOUR_NOTION_PARENT_PAGE_ID")

# The Notion page ID of your Weekly To-do List page
WEEKLY_TODO_PAGE_ID = os.environ.get("WEEKLY_TODO_PAGE_ID", "YOUR_WEEKLY_TODO_PAGE_ID")

# Max number of recent messages to include in summary (prevents token overflow)
MAX_MESSAGES = 60
# ─────────────────────────────────────────────────────────────────────────────


def read_jsonl(path: str) -> list[dict]:
    messages = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"[summarize] Failed to read jsonl: {e}", file=sys.stderr)
    return messages


def extract_conversation(records: list[dict]) -> str:
    """Extract readable conversation text from jsonl records"""
    lines = []
    for rec in records:
        msg = rec.get("message", {})
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role not in ("user", "assistant"):
            continue

        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        c = item.get("content", "")
                        if isinstance(c, list):
                            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                        parts.append(f"[Tool Result] {str(c)[:200]}")
            text = "\n".join(parts).strip()
        else:
            continue

        if not text:
            continue

        tag = "User" if role == "user" else "Claude"
        lines.append(f"[{tag}] {text[:800]}")  # Truncate each message to 800 chars

    return "\n\n".join(lines[-MAX_MESSAGES:])


def call_claude(conversation_text: str) -> tuple[str, list]:
    """Call Claude API to generate summary. Returns (markdown_text, todo_list)"""
    system_prompt = """You are a senior Android engineer with 10 years of experience, with keen industry insight and a passion for technology.
You are mentoring a junior developer and need to distill key learnings from conversation records.

Output in the following format. Output content only, no extra explanations:

## 一、工作概要
[Brief description of what was done in this conversation, 1-3 sentences]

## 二、知识点总结

### 1. 知识点
[Technical knowledge points covered, bullet list. Omit if none]

### 2. 工作经验
[Reusable work methods and experience, bullet list. Omit if none]

### 3. 使用 AI 的错误总结与教训
[Detours taken when using AI, bullet list. Omit if none]

### 4. 欠缺的知识点 & 学习规划
[Knowledge gaps discovered, table format: | # | 欠缺点 | 建议行动 |. Omit if none]

### 5. 额外建议
[Additional suggestions worth adding. Omit if none]

---

## 学习 To-Do

- [ ] [specific actionable learning task]
[Omit if no learning tasks]

---

## __TODO_JSON__
[Output only the following JSON, no explanations. Output empty array [] if no todos]
[
  {
    "task": "task description",
    "module": "安卓" or "业余",
    "category": "知识点学习" or "实操" or "工具配置" or "项目实践",
    "priority": "紧急" or "重要" or "一般"
  }
]

Note: If the conversation doesn't involve a section at all, skip it entirely. Don't write "N/A" or "not applicable". The __TODO_JSON__ section MUST always be output."""

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 2500,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": f"Please summarize the following conversation:\n\n{conversation_text}"
            }
        ]
    }

    url = f"{ANTHROPIC_BASE_URL}/v1/messages"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ANTHROPIC_API_KEY}",
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    full_text = result["content"][0]["text"]

    # Split markdown summary and todo JSON
    todo_items = []
    if "## __TODO_JSON__" in full_text:
        parts = full_text.split("## __TODO_JSON__")
        summary_md = parts[0].strip()
        json_block = parts[1].strip()
        match = re.search(r'\[.*\]', json_block, re.DOTALL)
        if match:
            try:
                todo_items = json.loads(match.group())
            except Exception:
                pass
    else:
        summary_md = full_text

    return summary_md, todo_items


def notion_api(method: str, endpoint: str, body: dict | None = None) -> dict:
    url = f"https://api.notion.com/v1/{endpoint}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        method=method
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def markdown_to_notion_blocks(md: str) -> list[dict]:
    """Convert Markdown text to Notion block list (simplified)"""
    blocks = []
    lines = md.split("\n")
    i = 0
    in_table = False
    table_rows = []

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            in_table = False
            if table_rows:
                for row in table_rows:
                    cells = [c.strip() for c in row.strip("|").split("|")]
                    text = " | ".join(cells)
                    blocks.append({"object": "block", "type": "bulleted_list_item",
                                   "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]}})
                table_rows = []
            i += 1
            continue

        if line.startswith("## "):
            text = line[3:].strip()
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}})
            i += 1
            continue

        if line.startswith("### "):
            text = line[4:].strip()
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]}})
            i += 1
            continue

        if re.match(r"^---+$", line.strip()):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.match(r"^[-:]+$", c) for c in cells if c):
                i += 1
                continue
            table_rows.append(line)
            i += 1
            continue

        if line.startswith("- [ ] "):
            text = line[6:].strip()
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": [{"type": "text", "text": {"content": text}}], "checked": False}})
            i += 1
            continue

        if line.startswith("- [x] ") or line.startswith("- [X] "):
            text = line[6:].strip()
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": [{"type": "text", "text": {"content": text}}], "checked": True}})
            i += 1
            continue

        if line.startswith("- ") or line.startswith("* "):
            text = line[2:].strip()
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]}})
            i += 1
            continue

        text = line.strip()
        if text:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}})
        i += 1

    return blocks


def get_or_create_project_folder(project: str) -> str:
    """Find or create project subfolder under AI对话总结, return page_id"""
    result = notion_api("GET", f"blocks/{NOTION_PARENT_PAGE_ID}/children?page_size=100")
    blocks = result.get("results", [])

    for block in blocks:
        if block.get("type") == "child_page":
            page_title = block.get("child_page", {}).get("title", "")
            if page_title == project:
                return block["id"]

    # Not found — create new project folder page
    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "icon": {"type": "emoji", "emoji": "📁"},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": project}}]
            }
        }
    }
    result = notion_api("POST", "pages", payload)
    return result["id"]


def create_notion_page(title: str, summary_md: str, project: str) -> str:
    """Create summary page under project subfolder in Notion, return page URL"""
    parent_id = get_or_create_project_folder(project)
    blocks = markdown_to_notion_blocks(summary_md)

    first_batch = blocks[:100]

    payload = {
        "parent": {"page_id": parent_id},
        "icon": {"type": "emoji", "emoji": "📝"},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": first_batch
    }

    result = notion_api("POST", "pages", payload)
    page_id = result["id"]
    page_url = result.get("url", "")

    if len(blocks) > 100:
        notion_api("PATCH", f"blocks/{page_id}/children", {"children": blocks[100:200]})

    return page_url


PRIORITY_EMOJI = {"紧急": "🔴", "重要": "🟡", "一般": "🟢"}
PRIORITY_ORDER = {"紧急": 0, "重要": 1, "一般": 2}


def get_page_blocks(page_id: str) -> list:
    result = notion_api("GET", f"blocks/{page_id}/children?page_size=100")
    return result.get("results", [])


def find_heading_text(blocks: list, heading_text: str) -> bool:
    """Check if any heading block in blocks contains the specified text"""
    for block in blocks:
        btype = block.get("type", "")
        if btype in ("heading_1", "heading_2", "heading_3"):
            rich = block.get(btype, {}).get("rich_text", [])
            text = "".join(r.get("text", {}).get("content", "") for r in rich)
            if heading_text in text:
                return True
    return False


def append_blocks(parent_id: str, children: list):
    notion_api("PATCH", f"blocks/{parent_id}/children", {"children": children})


def update_weekly_todo(todo_items: list):
    """Append todo items to Weekly To-do List, grouped by module/category/priority"""
    if not todo_items:
        return

    sorted_items = sorted(todo_items, key=lambda x: (
        x.get("module", ""),
        x.get("category", ""),
        PRIORITY_ORDER.get(x.get("priority", "一般"), 2)
    ))

    grouped = {}
    for item in sorted_items:
        m = item.get("module", "业余")
        c = item.get("category", "其他")
        grouped.setdefault(m, {}).setdefault(c, []).append(item)

    existing = get_page_blocks(WEEKLY_TODO_PAGE_ID)

    new_blocks = []
    for module, categories in grouped.items():
        emoji_m = "📱" if module == "安卓" else "🎯"
        module_label = f"{emoji_m} {module}"
        if not find_heading_text(existing, module):
            new_blocks.append({
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": module_label}}]}
            })

        for category, items in categories.items():
            if not find_heading_text(existing, category):
                new_blocks.append({
                    "object": "block", "type": "heading_3",
                    "heading_3": {"rich_text": [{"type": "text", "text": {"content": category}}]}
                })

            for item in items:
                priority = item.get("priority", "一般")
                ep = PRIORITY_EMOJI.get(priority, "🟢")
                task_text = f"{ep} [{priority}] {item['task']}"
                new_blocks.append({
                    "object": "block", "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": task_text}}],
                        "checked": False
                    }
                })

    if new_blocks:
        append_blocks(WEEKLY_TODO_PAGE_ID, new_blocks)


def infer_project(conversation_text: str) -> str:
    """Infer project name from conversation content"""
    text_lower = conversation_text.lower()
    if "notion" in text_lower and "知识库" in conversation_text:
        return "知识库搭建"
    if "android" in text_lower or "ufs" in text_lower or "adb" in text_lower:
        return "Android开发"
    if "seeway" in text_lower:
        return "Seeway"
    if "fishmemory" in text_lower:
        return "FishMemory"
    return "日常对话"


def main():
    # Hook passes JSON context via stdin; also supports command-line argument
    hook_input = {}
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        if raw.strip():
            hook_input = json.loads(raw)
    except Exception:
        pass

    # Command-line args take priority: python script.py <transcript_path> [session_id]
    if len(sys.argv) > 1:
        hook_input["transcript_path"] = sys.argv[1]
    if len(sys.argv) > 2:
        hook_input["session_id"] = sys.argv[2]

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")

    if not transcript_path:
        if session_id:
            base = Path.home() / ".claude" / "projects" / "C--Users----"
            transcript_path = str(base / f"{session_id}.jsonl")
        else:
            # Fallback: find most recently modified .jsonl within the last 10 minutes
            # Adjust the path below to match your Claude projects directory
            base = Path.home() / ".claude" / "projects" / "C--Users----"
            import time
            candidates = list(base.glob("*.jsonl")) if base.exists() else []
            now = time.time()
            recent = [p for p in candidates if (now - p.stat().st_mtime) < 600]
            if recent:
                transcript_path = str(max(recent, key=lambda p: p.stat().st_mtime))
                print(f"[summarize] stdin path not received, using recent file: {transcript_path}", file=sys.stderr)
            else:
                print("[summarize] No transcript_path found, skipping", file=sys.stderr)
                sys.exit(0)

    if not Path(transcript_path).exists():
        print(f"[summarize] Conversation file not found: {transcript_path}", file=sys.stderr)
        sys.exit(0)

    if not ANTHROPIC_API_KEY:
        print("[summarize] ANTHROPIC_AUTH_TOKEN not set, skipping", file=sys.stderr)
        sys.exit(0)

    if not NOTION_TOKEN:
        print("[summarize] NOTION_TOKEN not set, skipping", file=sys.stderr)
        sys.exit(0)

    print(f"[summarize] Reading conversation: {transcript_path}", file=sys.stderr)
    records = read_jsonl(transcript_path)
    if not records:
        print("[summarize] Empty conversation, skipping", file=sys.stderr)
        sys.exit(0)

    conversation_text = extract_conversation(records)
    if len(conversation_text) < 100:
        print("[summarize] Conversation too short, skipping", file=sys.stderr)
        sys.exit(0)

    print("[summarize] Calling Claude to generate summary...", file=sys.stderr)
    try:
        summary_md, todo_items = call_claude(conversation_text)
    except Exception as e:
        print(f"[summarize] Claude API call failed: {e}", file=sys.stderr)
        sys.exit(0)

    project = infer_project(conversation_text)
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Extract short description from first non-heading line of summary
    short_desc = ""
    lines = summary_md.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            continue
        text = re.sub(r"\*+", "", stripped)
        short_desc = text[:18].strip()
        break
    if not short_desc:
        short_desc = "对话总结"

    title = f"{project} {short_desc} {date_str} by Claude"

    print(f"[summarize] Writing to Notion: {title}", file=sys.stderr)
    try:
        page_url = create_notion_page(title, summary_md, project)
        print(f"[summarize] Written: {page_url}", file=sys.stderr)
    except Exception as e:
        print(f"[summarize] Failed to write to Notion: {e}", file=sys.stderr)

    if todo_items:
        print(f"[summarize] Writing {len(todo_items)} items to Weekly To-do", file=sys.stderr)
        try:
            update_weekly_todo(todo_items)
            print("[summarize] Weekly To-do updated", file=sys.stderr)
        except Exception as e:
            print(f"[summarize] Failed to write Weekly To-do: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
