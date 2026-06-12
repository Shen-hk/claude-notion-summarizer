# claude-notion-summarizer

Claude Code Stop hook，在每次对话结束时自动总结内容并写入 Notion —— 包括按项目分类的总结页面，以及按优先级排序的 Weekly To-do List。

## 功能介绍

每次在 Claude Code 中输入 `/exit` 结束对话，hook 会自动：

1. 读取本次对话的 transcript（`.jsonl` 文件）
2. 调用 Claude API，以「10年经验的Android老司机带新人」视角生成结构化总结
3. 在 Notion 的 **AI对话总结 → [项目文件夹]** 下创建总结页面
4. 将可执行的 Todo 条目追加到 **Weekly To-do List** 页面，按模块分组、按优先级排序

### 总结格式

```
## 一、工作概要
本次对话做了什么事（1-3句）

## 二、知识点总结
### 1. 知识点         — 本次涉及的技术知识点
### 2. 工作经验       — 可复用的工作方法
### 3. AI 错误教训    — 使用AI走弯路的地方
### 4. 欠缺知识点     — 知识盲区 + 学习规划（表格）
### 5. 额外建议       — 值得补充的建议
```

### Notion 结构

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
│   │   ├── 🔴 [紧急] 任务A
│   │   └── 🟡 [重要] 任务B
│   └── 实操
│       └── 🟢 [一般] 任务C
└── 🎯 业余
    └── 工具配置
        └── 🟡 [重要] 任务D
```

### 项目自动识别

脚本根据对话关键词自动判断项目名：

| 关键词 | 项目名 |
|---|---|
| `notion` + `知识库` | 知识库搭建 |
| `android`、`ufs`、`adb` | Android开发 |
| `seeway` | Seeway |
| `fishmemory` | FishMemory |
| *(默认)* | 日常对话 |

---

## 安装配置

### 前置条件

- Python 3.10+（脚本使用了 `dict | None` 类型语法）
- Claude Code CLI
- Notion 账号 + Integration Token
- Anthropic API Key（或兼容代理）

### 第一步 — 创建 Notion Integration

1. 打开 [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. 点击 **New integration**，随意起个名字（如 "Claude Summarizer"）
3. 复制 **Internal Integration Token**（以 `ntn_` 或 `secret_` 开头）
4. 打开 Notion 中的 **AI对话总结** 页面 → 点击右上角 `...` → **Add connections** → 选择刚创建的 Integration
5. 对 **Weekly To-do List** 页面重复上一步

### 第二步 — 获取 Notion 页面 ID

在 Notion 中打开对应页面，从 URL 中复制页面 ID：
```
https://notion.so/your-workspace/Page-Title-<这串就是ID>
```
ID 是 URL 末尾的 32 位十六进制字符串（带不带短横线都可以）。

### 第三步 — 部署 hook 脚本

将 `hooks/summarize_conversation.py` 复制到 Claude hooks 目录：

**Windows：**
```
C:\Users\你的用户名\.claude\hooks\summarize_conversation.py
```

**macOS / Linux：**
```
~/.claude/hooks/summarize_conversation.py
```

### 第四步 — 配置 `settings.json`

编辑 `~/.claude/settings.json`（参考 `settings.json.example`）：

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "你的API Key",
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
    "NOTION_TOKEN": "ntn_你的Notion Token",
    "NOTION_PARENT_PAGE_ID": "AI对话总结页面的ID",
    "WEEKLY_TODO_PAGE_ID": "Weekly To-do List页面的ID"
  },
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"C:\\Users\\你的用户名\\.claude\\hooks\\summarize_conversation.py\""
          }
        ]
      }
    ]
  }
}
```

> **使用自定义 API 代理？** 将 `ANTHROPIC_BASE_URL` 改为你的代理地址。脚本使用 `Authorization: Bearer <token>` 请求头，兼容大多数 OpenAI 格式的代理。

### 第五步 — 自定义项目识别（可选）

修改脚本中的 `infer_project()` 函数，按你自己的项目关键词来识别：

```python
def infer_project(conversation_text: str) -> str:
    text_lower = conversation_text.lower()
    if "你的关键词" in text_lower:
        return "你的项目名"
    ...
    return "日常对话"  # 默认值
```

同时注意修改 `main()` 中的 `base` 路径，改成你本地实际的 Claude projects 目录。Windows 默认路径是：
```python
base = Path.home() / ".claude" / "projects" / "C--Users----"
```

---

## 使用方法

在 Claude Code 中输入：
```
/exit
```

hook 会在后台自动运行，约 30 秒后在 Notion 中出现新的总结页面。

### 手动触发

也可以直接对任意 transcript 文件手动运行：
```bash
python summarize_conversation.py /path/to/session.jsonl
```

---

## 自定义总结风格

总结的人设和格式由 `call_claude()` 中的 `system_prompt` 变量控制。默认是「10年Android老司机带新人」的视角。可以按自己的领域和偏好自由修改。

Todo 输出采用哨兵字符串方案 —— LLM 在同一次响应中同时输出 Markdown 总结和 JSON Todo，以 `## __TODO_JSON__` 分隔，避免额外的 API 调用。

---

## 常见问题

**hook 没有自动触发**
- Stop hook 只在 `/exit` 时触发，关闭窗口或强制退出不会触发。这是有意为之，方便你有选择性地保存对话。
- 检查 `~/.claude/settings.json` 是否是合法 JSON。

**Notion 没有生成新页面**
- 手动带 transcript 路径运行脚本，查看 stderr 输出定位问题。
- 确认 Notion Integration 已经添加到对应页面的 connections 中。
- 检查 `NOTION_PARENT_PAGE_ID` 和 `WEEKLY_TODO_PAGE_ID` 是否填写正确。

**日志中出现 `stdin path not received`**
- Windows 上属于正常现象。脚本会自动 fallback，查找最近 10 分钟内修改过的 `.jsonl` 文件。

**Windows 编码报错**
- 脚本启动时已调用 `sys.stdout.reconfigure(encoding="utf-8")`。如仍报错，可设置环境变量 `PYTHONIOENCODING=utf-8` 再运行。

---

## 文件结构

```
claude-notion-summarizer/
├── hooks/
│   └── summarize_conversation.py   # 主 hook 脚本
├── settings.json.example           # Claude Code 配置模板
├── README.md                       # 英文文档
└── README.zh.md                    # 中文文档（本文件）
```

---

## License

MIT
