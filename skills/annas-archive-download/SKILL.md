---
name: annas-archive-download
description: >-
  Searches and downloads ebooks from Anna's Archive (https://annas-archive.gl/).
  Supports automated one-command pipeline ('download_helper.py auto') and interactive
  Browser MCP. Prioritizes formats (EPUB > MOBI > AZW3 > PDF > TXT), filters exact
  volume/edition, handles DDoS-Guard & iframe captcha via OCR, manages server countdowns (>60s),
  cleans filenames to '<Title> -- <Author>.<ext>', and saves files to ~/Downloads.
---

# Anna's Archive Ebook Downloader

## Overview

This skill guides the agent in searching and downloading electronic books from Anna's Archive (`https://annas-archive.gl/`). To ensure maximum stability and prevent token-wasting trial-and-error, this skill features a **Dual-Track Architecture**:
- **Track 1 (Preferred / Most Efficient)**: Bundled all-in-one automation script (`download_helper.py auto`) powered by Playwright and local Chrome. Handles proxy detection, anti-bot bypass, candidate selection, multi-check countdown (>60s), link extraction, and download in a single step.
- **Track 2 (Interactive Browser MCP)**: Controls the user's active Chrome browser via Browser MCP. Used when the user explicitly requests browser interaction or when visually inspecting pages.

---

## Dependencies & Pre-flight Requirements

- **Python 3 / `uv`**: Required for executing `scripts/download_helper.py`.
- **Browser MCP / Node.js**: Optional (Track 2 only). When installed via `mise` on Windows, ensure `mcp_config.json` references `npx.exe` (e.g. `C:\Users\<user>\AppData\Local\mise\shims\npx.exe`) rather than `.cmd` scripts.
- **Local Proxy**: In regions where access to `annas-archive.gl` is disrupted by connection resets, ensure a local proxy (such as Clash / Mihomo on port `7897` or `7890`) or `HTTP_PROXY`/`HTTPS_PROXY` environment variables are active. `download_helper.py` auto-detects these ports automatically.
- **Terminal Execution**: When saving files to `~/Downloads` or running browser automation, always run terminal commands with **`BypassSandbox: true`**.

---

## Step 0: Pre-Flight Check & Track Decision (决策树)

Before taking any action, determine the execution track:
1. **Default Choice**: **Track 1 (`auto`)** is always the default and most token-efficient method.
2. **If Browser MCP is explicitly requested**:
   - Run `browser_list_tabs`.
   - **Success**: Proceed with **Track 2 (Browser MCP)**.
   - **Error / EOF / Client closing**: **Immediately switch to Track 1**. Do NOT write custom ad-hoc test scripts or make blind curl requests.

```text
User Request: "帮我下载《xxx》"
       │
       ▼
   Browser MCP explicitly requested?
     ├── No  ──► [Track 1: All-In-One Script (auto)] ──► Done (1 command, ~90% tokens saved)
     └── Yes ──► Pre-flight check (browser_list_tabs)
                   ├── Healthy ──► [Track 2: Browser MCP]
                   └── Failed  ──► [Track 1 Fallback]
```

---

## Track 1: All-In-One Automated Pipeline (Primary)

Run the bundled automation pipeline with `BypassSandbox: true`:

```bash
# Single book:
uv run --with playwright --with beautifulsoup4 --with ddddocr --with pillow python scripts/download_helper.py auto "<BOOK_TITLE>"

# Multiple books / Series volumes (automatically queued and downloaded sequentially, Concurrency=1):
# IMPORTANT: For multi-volume series, expand into explicit volume titles first!
uv run --with playwright --with beautifulsoup4 --with ddddocr --with pillow python scripts/download_helper.py auto "书名 卷1" "书名 卷2" "书名 卷3"
```

### Supported Parameters:
- `query`: Book title or search query (e.g. `"狂热分子 群众运动圣经"`).
- `--format`: Desired format priority override (e.g. `epub`, `mobi`, `azw3`, `pdf`, `txt`). Default is `EPUB > MOBI > AZW3 > PDF > TXT`.
- `--dest`: Destination folder (defaults to `~/Downloads`).
- `--max-wait`: Maximum countdown queue wait time in seconds (default `400` to comfortably handle server queues > 60s and captcha resets).
- `--proxy`: Custom proxy URL (e.g. `http://127.0.0.1:7897`). Auto-detected if omitted.
- `--headless`: Set flag for headless mode (omitted by default for maximum anti-bot success).

---

## Track 2: Interactive Browser MCP Workflow

Use this track only when operating through Browser MCP.

### Step 1: Open Search Page
1. Check existing tabs with `browser_list_tabs` and reuse if possible.
2. Navigate to:
   ```text
   https://annas-archive.gl/search?q=<ENCODED_BOOK_TITLE>
   ```

### Step 2: Handle DDoS-Guard Verification
1. Inspect page content using `browser_get_page_content` or `browser_screenshot`.
2. If DDoS-Guard challenge is present:
   - Notice that the checkbox is inside the iframe `#ddg-iframe`.
   - If `.ddg-captcha__checkbox` is visible, click it using `browser_click`.
   - If an image challenge or slider appears, use `browser_ask_user` to request quick user assistance in Chrome.
   - Wait 3–5 seconds for the page to redirect to the actual search results.

### Step 3: Parse and Select the Best Candidate
1. **Apply Volume Precision**:
   - Unless user asks for "2", "第二部", "续集", etc., exclude sequels (`2`, `Ⅱ`, `II`, `第二部`, `第2册`).
2. **Apply Format Priority**:
   - Check in strict order: `EPUB` -> `MOBI` -> `AZW3` -> `PDF`.
3. **Tie-Breaking**:
   - Among matching formats, pick the candidate with the highest download/view count. Ignore `0 B` entries.

### Step 4: Access Slow Download Page
1. Navigate to the selected book's detail page (`/md5/<hash>`).
2. Scroll to **Slow downloads** and click **Slow Partner Server #1** (or `#2`).

### Step 5: Multi-Check Countdown Waiting (>60s Queues)
> [!CAUTION]
> Slow Partner servers frequently assign queues longer than 60 seconds (e.g. 75s, 90s, 120s, 180s).
> **DO NOT REFRESH OR NAVIGATE AWAY** while the countdown is still ticking down.
1. Inspect the page text periodically (every 5~10s) using `browser_get_page_content` or `browser_screenshot`.
2. Extract remaining time from text (e.g. `Please wait 85 seconds...`).
3. Continue waiting until the remaining time reaches 0.
4. When the countdown completes, Anna's Archive will reload or display the `📚 Download now` button.
5. If the button has not appeared within 5 seconds after countdown hits 0, execute `window.location.reload()` once to retrieve the download ticket.
6. Extract the direct file URL from the `📚 Download now` button.

### Step 6: Download & Clean Filename
Download the extracted direct URL to `~/Downloads` via the helper script with `BypassSandbox: true`:
```bash
uv run python scripts/download_helper.py download "<DIRECT_DOWNLOAD_URL>" --referer "<PARTNER_PAGE_URL>"
```

### Step 7: Clean Up & Report
1. Close browser tabs using `browser_close_tab`.
2. Report the download outcome to the user:
   - Book Title & Author
   - Clean Filename (e.g. `狂热分子 群众运动圣经 -- 埃里克·霍弗.epub`)
   - Format chosen & reason
   - File Size
   - Saved Path in `~/Downloads`

---

## Core Rules & Policies

### 1. Title & Volume Precision (精准卷次过滤、系列展开与简繁归一化)
- **Series Expansion**: For multi-volume series, the agent MUST expand the series into explicit volume queries (e.g. `"书名 卷1"`, `"书名 卷2"`, etc.) before calling the download script.
- **Title & Metadata Relevance Scoring**: Every candidate is scored (Score 3: core title in candidate title; Score 2: query terms in candidate title; Score 1: query terms in metadata; Score 0: completely irrelevant). Candidates with Score 0 (e.g. yearbooks or unrelated manuals) are strictly rejected.
- **Traditional / Simplified Normalization (`normalize_zh`)**: Automatically bridges Traditional/Simplified script variations (e.g. `萬能鑑定士` ↔ `万能鉴定士`, `幾隻貓` ↔ `几只猫`).
- **Volume Precision Matching**: Supports Chinese volume conventions (`第X卷`, `第X部`, `第X册/冊`, `第X篇`, `卷X`, `Vol.X`, Roman numerals, spin-offs like `扉子篇`, `外传`, `番外`).
  - If the query does NOT ask for a spin-off, spin-offs are excluded.
  - If the query does NOT ask for a sequel, sequels (`卷 > 1`) are excluded unless the query explicitly matches that specific sub-title.
  - Single volume targets are strictly prioritized over giant omnibus collections so individual volumes are preserved.
  - If single volume candidates are unavailable, omnibus collections (`全集`/`合集`/`全X卷`) serve as automatic fallback.

### 2. Language Preference & Format Hierarchy
- **Language Preference**: When the search query contains Chinese characters, candidates marked `Chinese [zh]` are strictly prioritized over raw foreign editions (`Japanese [ja]`, `English [en]`).
- **Format Hierarchy**: `EPUB` (Highest) > `MOBI` > `AZW3` > `PDF` > `TXT` (Lowest).
- **Relative Size Preference**: Within the same format, larger file sizes are preferred (e.g. 250KB > 200KB > 100KB) to ensure full text, high-res covers, and typography illustrations are selected over bare-text scraper rips. Downloads count is used as secondary tie-breaker.

### 3. Filename Cleansing & Normalization
- Pattern: `<Title> -- <Author>.<ext>` (or `<Title>.<ext>` if author unknown).
- Strip out: publishing year, publisher, ISBN, MD5 hash, `-- Anna’s Archive` suffix, and secondary bilingual translations.

### 4. Countdown Safety & Dynamic Wait Extension (>60s Detection)
- Never refresh prematurely during active countdowns.
- Automatically handles DDoS-Guard captchas in a background loop via `ddddocr` and `Pillow`.
- If the countdown queue is still actively ticking down near the timeout limit, the wait time is dynamically extended by the remaining seconds to guarantee successful ticket acquisition.

### 5. Strict Concurrency = 1 Policy (多本书必须严格串行下载)
> [!IMPORTANT]
> Anna's Archive slow partner servers enforce a strict **Concurrency = 1** policy per IP/session. If two countdowns or downloads run in parallel, the server rejects or resets both with 429 Too Many Requests.
> - **NEVER parallelize subagents or background tasks**: If the user asks for multiple books (e.g. "帮我下载《书A》和《书B》"), the agent **MUST** process them sequentially one by one.
> - **Wait for completion**: Book 1 must be completely finished and saved to `~/Downloads` before Book 2 can begin.
> - **Multi-Book Batch Command**: Pass multiple book titles to `download_helper.py auto "书A" "书B" "书C"`. The script automatically processes them sequentially with an internal cooldown between books.

---

## Utility Script Reference (`scripts/download_helper.py`)

```bash
# 1. Full auto: Search, DDoS bypass with OCR, candidate selection, >60s countdown, and download
uv run --with playwright --with beautifulsoup4 --with ddddocr --with pillow python scripts/download_helper.py auto "书名"

# 2. Download direct URL with referer
uv run python scripts/download_helper.py download "<DIRECT_URL>" --referer "<REFERER>"

# 3. Custom title/author via environment variables
$env:BOOK_TITLE = "书名"; $env:BOOK_AUTHOR = "作者"; uv run python scripts/download_helper.py download "<URL>"

# 4. Normalize names of existing downloaded files
uv run python scripts/download_helper.py rename --dest "~/Downloads"

# 5. Test filename clean-up logic
uv run python scripts/download_helper.py clean-name "<RAW_FILENAME>"
```
