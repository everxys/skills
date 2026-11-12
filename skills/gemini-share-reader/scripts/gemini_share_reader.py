#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemini Share Reader - Extract full multi-turn conversations from Google Gemini share links.
Works across Windows, macOS, and Linux by leveraging headless Chrome/Edge DOM rendering.
"""

import sys
import os
import re
import json
import socket
import argparse
import shutil
import subprocess
import urllib.request
from typing import List, Dict, Optional, Tuple

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def is_port_open(port: int, host: str = '127.0.0.1') -> bool:
    """Check if a local port is open (e.g. Clash Verge 7897 or 7890)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def get_default_proxy() -> Optional[str]:
    """Detect active local HTTP proxy."""
    for env in ['HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy']:
        val = os.environ.get(env)
        if val:
            return val

    for port in [7897, 7890, 10809]:
        if is_port_open(port):
            return f"http://127.0.0.1:{port}"

    return None


def find_browser_executable() -> Optional[str]:
    """Find local Chrome, Chromium, or Edge executable."""
    env_browser = os.environ.get('CHROME_PATH') or os.environ.get('BROWSER_PATH')
    if env_browser and os.path.isfile(env_browser):
        return env_browser

    if sys.platform == 'win32':
        candidates = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\Application\chrome.exe'),
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                return path

    if sys.platform == 'darwin':
        candidates = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

    for name in ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'msedge', 'chrome']:
        found = shutil.which(name)
        if found:
            return found

    return None


def resolve_canonical_url(url: str) -> str:
    """Follow redirects (e.g. share.gemini.google/xyz -> gemini.google.com/share/abc)."""
    clean_url = url.strip()
    if not clean_url.startswith('http://') and not clean_url.startswith('https://'):
        clean_url = 'https://' + clean_url

    match = re.search(r'gemini\.google\.com/share/([a-zA-Z0-9_-]+)', clean_url)
    if match:
        return f"https://gemini.google.com/share/{match.group(1)}"

    if shutil.which('curl') or shutil.which('curl.exe'):
        try:
            res = subprocess.run(
                ['curl.exe' if sys.platform == 'win32' else 'curl', '-ILs', clean_url],
                capture_output=True,
                text=True,
                timeout=10,
            )
            loc_match = re.search(r'Location:\s*https?://gemini\.google\.com/share/([a-zA-Z0-9_-]+)', res.stdout, re.IGNORECASE)
            if loc_match:
                return f"https://gemini.google.com/share/{loc_match.group(1)}"
        except Exception:
            pass

    try:
        req = urllib.request.Request(
            clean_url,
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
                )
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            final_url = resp.geturl()
            loc_match = re.search(r'gemini\.google\.com/share/([a-zA-Z0-9_-]+)', final_url)
            if loc_match:
                return f"https://gemini.google.com/share/{loc_match.group(1)}"
            return final_url
    except Exception:
        return clean_url


def render_page_dom(browser_path: str, url: str, proxy: Optional[str] = None, timeout_sec: int = 60) -> str:
    """Launch headless Chrome to render JavaScript SPA and dump the full DOM."""
    cmd = [
        browser_path,
        '--headless=new',
        '--disable-gpu',
        '--no-sandbox',
        '--disable-dev-shm-usage',
    ]

    if proxy:
        cmd.append(f'--proxy-server={proxy}')

    cmd.extend([
        '--dump-dom',
        url,
    ])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=timeout_sec,
        )
        return result.stdout or ''
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Browser rendering timed out after {timeout_sec}s for URL: {url}")
    except Exception as e:
        raise RuntimeError(f"Failed to launch browser ({browser_path}): {e}")


def parse_conversation_turns(dom_html: str) -> Tuple[str, List[Dict[str, str]]]:
    """Parse title and multi-turn dialogue from rendered Gemini HTML."""
    title = 'Gemini 对话'

    # 1. Prefer og:title (which holds the exact user chat title)
    og_match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', dom_html, re.IGNORECASE)
    if not og_match:
        og_match = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:title["\']', dom_html, re.IGNORECASE)

    if og_match:
        raw_title = og_match.group(1).strip()
        raw_title = re.sub(r'^[\u200e\s]*Gemini\s*[-–—]\s*', '', raw_title)
        if raw_title and raw_title != "direct access to Google AI":
            title = raw_title
    else:
        title_match = re.search(r'<title>(.*?)</title>', dom_html, re.IGNORECASE)
        if title_match:
            raw_title = title_match.group(1).strip()
            raw_title = re.sub(r'^[\u200e\s]*Gemini\s*[-–—]\s*', '', raw_title)
            if raw_title and raw_title != "direct access to Google AI":
                title = raw_title

    turns: List[Dict[str, str]] = []

    try:
        from lxml import html
        tree = html.fromstring(dom_html)

        turn_nodes = tree.xpath('//div[contains(@class, "share-turn-viewer")]')
        for i, turn_node in enumerate(turn_nodes):
            user_paragraphs = turn_node.xpath('.//div[contains(@class, "user-query-container")]//p[contains(@class, "query-text-line")]')
            if user_paragraphs:
                user_text = '\n'.join([p.text_content().strip() for p in user_paragraphs if p.text_content().strip()])
            else:
                uq = turn_node.xpath('.//div[contains(@class, "user-query-container")]')
                user_text = uq[0].text_content().strip() if uq else ''

            resp_node = turn_node.xpath('.//div[contains(@class, "response-container")]//message-content')
            if not resp_node:
                resp_node = turn_node.xpath('.//div[contains(@class, "response-container")]')

            gemini_text = resp_node[0].text_content().strip() if resp_node else ''
            gemini_text = re.sub(r'\n{3,}', '\n\n', gemini_text)

            turns.append({
                'turn': i + 1,
                'user': user_text,
                'gemini': gemini_text,
            })

        if turns:
            return title, turns
    except ImportError:
        pass

    # Regex fallback
    turn_blocks = re.findall(r'<div[^>]*class="[^"]*share-turn-viewer[^"]*"[^>]*>(.*?)</div>\s*(?=<div[^>]*class="[^"]*share-turn-viewer|$)', dom_html, re.DOTALL)
    for i, block in enumerate(turn_blocks):
        user_matches = re.findall(r'<p[^>]*class="[^"]*query-text-line[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
        user_text = '\n'.join([re.sub(r'<[^>]+>', '', m).strip() for m in user_matches if m.strip()])
        if not user_text:
            u_block = re.search(r'<div[^>]*class="[^"]*user-query-container[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
            if u_block:
                user_text = re.sub(r'<[^>]+>', '', u_block.group(1)).strip()

        m_block = re.search(r'<message-content[^>]*>(.*?)</message-content>', block, re.DOTALL)
        if m_block:
            resp_html = m_block.group(1)
            resp_html = re.sub(r'<br\s*/?>', '\n', resp_html)
            resp_html = re.sub(r'</p>', '\n\n', resp_html)
            resp_text = re.sub(r'<[^>]+>', '', resp_html).strip()
        else:
            resp_text = ''

        resp_text = re.sub(r'\n{3,}', '\n\n', resp_text)
        turns.append({
            'turn': i + 1,
            'user': user_text,
            'gemini': resp_text,
        })

    return title, turns


def format_markdown(url: str, title: str, turns: List[Dict[str, str]]) -> str:
    """Format dialogue turns into clean, readable Markdown."""
    lines = [
        f"# {title}",
        "",
        f"> **来源链接**: [{url}]({url})",
        f"> **对话轮次**: 共 {len(turns)} 轮",
        "",
        "---",
        "",
    ]

    for t in turns:
        lines.append(f"## 👤 用户（第 {t['turn']} 轮）")
        lines.append("")
        lines.append(t['user'] or "*(无文本输入)*")
        lines.append("")
        lines.append(f"## 🤖 Gemini 回答")
        lines.append("")
        lines.append(t['gemini'] or "*(无回答内容)*")
        lines.append("")
        lines.append("---")
        lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract full conversation transcript from Google Gemini share links."
    )
    parser.add_argument("url", help="Gemini share URL (e.g. https://share.gemini.google/WztEliUejto6)")
    parser.add_argument("-o", "--output", help="Write Markdown result to specified file")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    parser.add_argument("--browser", help="Custom path to Chrome or Edge executable")
    parser.add_argument("--proxy", help="Custom proxy URL (e.g. http://127.0.0.1:7897)")
    parser.add_argument("--timeout", type=int, default=60, help="Browser render timeout in seconds (default: 60)")

    args = parser.parse_args()

    browser = args.browser or find_browser_executable()
    if not browser:
        sys.stderr.write("错误: 未找到可用的 Chrome / Edge 浏览器可执行文件。\n")
        sys.stderr.write("请安装 Google Chrome 或通过 --browser 指定可执行文件路径。\n")
        sys.exit(1)

    proxy = args.proxy or get_default_proxy()

    canonical_url = resolve_canonical_url(args.url)

    try:
        dom = render_page_dom(browser, canonical_url, proxy=proxy, timeout_sec=args.timeout)
    except Exception as e:
        sys.stderr.write(f"页面渲染失败: {e}\n")
        sys.exit(1)

    if not dom:
        sys.stderr.write("错误: 浏览器未能渲染出有效 HTML。\n")
        sys.exit(1)

    title, turns = parse_conversation_turns(dom)
    if not turns:
        sys.stderr.write(f"未能解析出对话轮次。标题: {title}，HTML 长度: {len(dom)}\n")
        sys.exit(1)

    if args.json:
        result_obj = {
            "title": title,
            "url": args.url,
            "canonicalUrl": canonical_url,
            "turnCount": len(turns),
            "turns": turns,
        }
        output_str = json.dumps(result_obj, ensure_ascii=False, indent=2)
    else:
        output_str = format_markdown(args.url, title, turns)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_str)
        print(f"成功导出对话内容至: {args.output} (共 {len(turns)} 轮)")
    else:
        print(output_str)


if __name__ == '__main__':
    main()
