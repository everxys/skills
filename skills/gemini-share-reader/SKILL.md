---
name: gemini-share-reader
description: >-
  Extracts and reads full conversation transcripts from Google Gemini share links
  (https://share.gemini.google/<slug> or https://gemini.google.com/share/<id>).
  Automatically resolves shortlink redirects, renders the Single Page Application (SPA) DOM via
  local headless Chrome/Edge, parses multi-turn dialogue into structured Markdown/JSON, and bypasses
  client-side hydration barriers. Use when the user asks "查看gemini分享链接", "提取gemini对话",
  "看看这个gemini对话说了什么", "read gemini share", "gemini share link", or provides a Gemini share link
  and wants its contents analyzed or summarized.
---

# Gemini Share Reader

自动化读取并解析 Google Gemini 公开分享链接（`share.gemini.google` 或 `gemini.google.com/share`）中的全部对话内容。

---

## 背景与技术原理

Google Gemini 的分享页面属于纯客户端单页应用（SPA）：
1. **普通 HTTP 请求失效**：直接通过 `curl` 或纯 HTTP GET 请求只能拉取到 HTML 空壳和元数据，对话正文是由前端 JavaScript 异步向 Google 私有 RPC 接口加载渲染的。
2. **自动化无头渲染方案**：本 Skill 利用本机已安装的 Chrome / Edge 浏览器，以 `--headless=new --dump-dom` 模式完成页面 JavaScript 的执行与 DOM 水合，然后由专用解析脚本提取对话树与多轮问答，还原为清晰易读的结构化 Markdown 或 JSON。

---

## 核心脚本位置

- **脚本路径**：`C:\Users\everx\.agents\skills\gemini-share-reader\scripts\gemini_share_reader.py`
- **依赖要求**：
  - Python 3.x（推荐使用 `mise` 托管的 Python）
  - 本机已安装 Google Chrome（`C:\Program Files\Google\Chrome\Application\chrome.exe`）或 Microsoft Edge
  - 本地代理（如 Clash Verge 端口 `7897` 或 `7890`，脚本会自动检测并附加 `--proxy-server`）

---

## 执行步骤与常用命令

### 1. 直接输出 Markdown 对话内容至终端
```powershell
python "C:\Users\everx\.agents\skills\gemini-share-reader\scripts\gemini_share_reader.py" "https://share.gemini.google/WztEliUejto6"
```

### 2. 导出对话为本地 Markdown 文件
```powershell
python "C:\Users\everx\.agents\skills\gemini-share-reader\scripts\gemini_share_reader.py" "https://share.gemini.google/WztEliUejto6" -o "conversation.md"
```

### 3. 以 JSON 格式输出（供自动化工具消费）
```powershell
python "C:\Users\everx\.agents\skills\gemini-share-reader\scripts\gemini_share_reader.py" "https://share.gemini.google/WztEliUejto6" --json
```

---

## 参数说明

| 参数 | 说明 |
|---|---|
| `url` | 必填。Gemini 分享链接（支持短链 `share.gemini.google/...` 或长链 `gemini.google.com/share/...`） |
| `-o, --output` | 可选。将对话 Markdown 输出写入指定文件 |
| `--json` | 可选。以结构化 JSON 对象返回对话标题、轮次与每轮的问答文本 |
| `--proxy` | 可选。指定代理地址，如 `http://127.0.0.1:7897`（默认自动探测） |
| `--timeout` | 可选。无头浏览器页面加载与水合超时时间（单位秒，默认 60） |
| `--browser` | 可选。自定义指定 Chrome / Edge 可执行文件路径 |

---

## 典型工作流

当用户发送一个 Gemini 分享链接并要求查看或总结内容时：
1. 调用本 Skill 的脚本抓取对话完整文本；
2. 读取解析输出的多轮问答结构；
3. 根据用户的具体诉求，提供对话完整转录、要点摘要、或针对该对话展开后续答疑。
