#!/usr/bin/env python3
"""
download_helper.py: Helper script for searching, downloading, and verifying ebooks from Anna's Archive.
Writes files by default to ~/Downloads.
Cleans raw filenames to strictly follow the pattern: '<Title> -- <Author>.<ext>' (or '<Title>.<ext>').
Supports all-in-one automated pipeline ('auto') via Playwright with proxy auto-detection,
DDoS-Guard bypass, volume precision filtering, multi-check countdown (>60s), and direct download.
"""

import argparse
import asyncio
import json
import os
import re
import ssl
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def get_downloads_dir() -> Path:
    """Returns the user's Downloads directory across platforms."""
    return Path(os.path.expanduser("~/Downloads")).resolve()


def sanitize_filename(name: str) -> str:
    """
    Removes or replaces invalid filesystem characters while preserving Unicode semantics.
    Replaces Windows-forbidden punctuation with fullwidth or clean equivalents.
    """
    replacements = {
        '?': '？',
        ':': '：',
        '"': "''",
        '*': '·',
        '<': '《',
        '>': '》',
        '|': '_',
        '/': '_',
        '\\': '_',
    }
    for char, rep in replacements.items():
        name = name.replace(char, rep)

    clean = re.sub(r'\s+', ' ', name).strip().strip('.')
    return clean or "downloaded_ebook"


def clean_annas_filename(raw_name: str, title: str = None, author: str = None, ext: str = None) -> str:
    """
    Cleans Anna's Archive filenames to strictly retain only '<Title> -- <Author>.<ext>'
    or '<Title>.<ext>', removing years, publishers, ISBNs, MD5 hashes, and 'Anna’s Archive' suffixes.
    Also strips secondary bilingual title markers (e.g. ' = English Title') and author noise (' 著').
    """
    if title and '\ufffd' in title:
        title = None
    if author and '\ufffd' in author:
        author = None

    if not title:
        env_t = os.environ.get("BOOK_TITLE")
        if env_t and '\ufffd' not in env_t:
            title = env_t.strip()
    if not author:
        env_a = os.environ.get("BOOK_AUTHOR")
        if env_a and '\ufffd' not in env_a:
            author = env_a.strip()

    path = Path(raw_name)
    raw_ext = path.suffix if path.suffix else ".epub"
    if ext and ext.lower() not in [".other", "other"]:
        file_ext = ext if ext.startswith(".") else f".{ext}"
    else:
        file_ext = raw_ext

    if title:
        title_clean = sanitize_filename(title.strip())
        if author:
            author_clean = re.sub(r'\s*(?:著|编著|等著)$', '', author.strip())
            author_clean = sanitize_filename(author_clean)
            return f"{title_clean} -- {author_clean}{file_ext}"
        return f"{title_clean}{file_ext}"

    stem = path.stem

    if " -- " in stem:
        parts = [p.strip() for p in stem.split(" -- ") if p.strip()]
        if len(parts) >= 2:
            p0 = parts[0]
            p1 = parts[1]

            p0 = re.split(r'\s+=\s+[A-Za-z]', p0)[0].strip()

            is_p1_non_author = (
                re.fullmatch(r'\d{4}', p1) or
                re.match(r'^(?:isbn|doi|asin|md5|anna)', p1, re.I) or
                re.fullmatch(r'[a-f0-9]{32}', p1, re.I)
            )
            if not is_p1_non_author:
                p1_clean = re.sub(r'\s*(?:著|编著|等著)$', '', p1)
                return f"{sanitize_filename(p0)} -- {sanitize_filename(p1_clean)}{file_ext}"
            return f"{sanitize_filename(p0)}{file_ext}"
        elif len(parts) == 1:
            p0 = re.split(r'\s+=\s+[A-Za-z]', parts[0])[0].strip()
            return f"{sanitize_filename(p0)}{file_ext}"

    cleaned = re.sub(r'\s*--\s*Anna[’\']s\s*Archive.*$', '', stem, flags=re.I)
    cleaned = re.sub(r'\s*--\s*[a-f0-9]{32}', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s*--\s*isbn\S*\s*[\d\-xX]+', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s*--\s*\d{4}', '', cleaned)
    cleaned = re.split(r'\s+=\s+[A-Za-z]', cleaned)[0].strip()
    return f"{sanitize_filename(cleaned)}{file_ext}"


def detect_local_proxy() -> str | None:
    """Detects proxy from environment or active local proxy listeners (e.g. Clash 7897/7890)."""
    for k in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"]:
        val = os.environ.get(k)
        if val:
            return val
    import socket
    for port in [7897, 7890, 10808, 10809, 2080]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return f"http://127.0.0.1:{port}"
        except Exception:
            pass
    return None


def find_browser_executable() -> str | None:
    """Finds installed Chrome or Edge executable on Windows."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def build_opener(proxy: str = None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    effective_proxy = proxy or detect_local_proxy()
    if effective_proxy:
        handlers.append(
            urllib.request.ProxyHandler({
                "http": effective_proxy,
                "https": effective_proxy,
            })
        )
    return urllib.request.build_opener(*handlers)


def download_file(url: str, referer: str = None, dest_dir: Path = None, title: str = None,
                  author: str = None, fmt: str = None, timeout: int = 60, proxy: str = None) -> dict:
    """Streams a file from URL to dest_dir with clean filename normalization and retries."""
    import time
    dest_dir = dest_dir or get_downloads_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    opener = build_opener(proxy=proxy)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Connection": "close",
    }
    if referer:
        headers["Referer"] = referer

    last_exc = None
    for attempt in range(1, 6):
        target_path = None
        try:
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=timeout) as resp:
                content_disposition = resp.headers.get("Content-Disposition", "")
                raw_filename = None

                if content_disposition:
                    m = re.search(r"filename\*=UTF-8''([^;\s]+)", content_disposition, re.I)
                    if m:
                        raw_filename = urllib.parse.unquote(m.group(1))
                    else:
                        m2 = re.search(r'filename="?([^";]+)"?', content_disposition)
                        if m2:
                            raw_filename = m2.group(1)

                if not raw_filename:
                    parsed = urllib.parse.urlparse(url)
                    base = os.path.basename(parsed.path)
                    raw_filename = urllib.parse.unquote(base) if base else "ebook.epub"

                final_filename = clean_annas_filename(
                    raw_filename,
                    title=title,
                    author=author,
                    ext=f".{fmt}" if fmt else None
                )

                target_path = dest_dir / final_filename
                counter = 1
                stem = target_path.stem
                suffix = target_path.suffix
                while target_path.exists():
                    target_path = dest_dir / f"{stem} ({counter}){suffix}"
                    counter += 1

                total_bytes = 0
                is_html = False
                first_chunk = True

                with open(target_path, "wb") as out_f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        if first_chunk:
                            first_chunk = False
                            sample = chunk[:512].lower()
                            if b"<!doctype html" in sample or b"<html" in sample or b"<head" in sample:
                                is_html = True
                        out_f.write(chunk)
                        total_bytes += len(chunk)

                if is_html and total_bytes < 50000:
                    target_path.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"Received HTML content instead of ebook binary ({total_bytes} bytes). Link may have expired."
                    )

                return {
                    "status": "success",
                    "file_name": target_path.name,
                    "file_path": str(target_path),
                    "size_bytes": total_bytes,
                    "dest_dir": str(dest_dir),
                }
        except Exception as ex:
            last_exc = ex
            if target_path and target_path.exists():
                try:
                    target_path.unlink(missing_ok=True)
                except Exception:
                    pass
            print(f"[*] Download attempt {attempt} encountered error: {ex}. Retrying...", flush=True)
            time.sleep(attempt * 3)

    raise RuntimeError(f"Download failed after 5 attempts: {last_exc}")


def cmd_download(args):
    try:
        res = download_file(
            url=args.url,
            referer=args.referer,
            dest_dir=Path(args.dest).resolve() if args.dest else None,
            title=args.title or args.filename,
            author=args.author,
            fmt=args.format,
            timeout=args.timeout,
            proxy=args.proxy,
        )
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    except Exception as e:
        err = {"status": "error", "message": str(e), "url": args.url}
        print(json.dumps(err, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


_OCR_INSTANCE = None


def get_ocr_instance():
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        try:
            import ddddocr
            _OCR_INSTANCE = ddddocr.DdddOcr(show_ad=False)
            try:
                _OCR_INSTANCE.set_ranges("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
            except Exception:
                pass
        except Exception as e:
            print(f"[!] ddddocr not available or failed to initialize: {e}", flush=True)
            return None
    return _OCR_INSTANCE


def recognize_captcha(img_bytes: bytes) -> str | None:
    ocr = get_ocr_instance()
    if not ocr:
        return None
    try:
        raw_code = ocr.classification(img_bytes).strip()
        code = re.sub(r'[^a-zA-Z0-9]', '', raw_code)
        if len(code) >= 4:
            return code

        import io
        from PIL import Image
        im = Image.open(io.BytesIO(img_bytes)).convert("L")
        thresh = im.point(lambda p: 255 if p > 180 else 0)
        out = io.BytesIO()
        thresh.save(out, format="PNG")
        raw_code2 = ocr.classification(out.getvalue()).strip()
        code2 = re.sub(r'[^a-zA-Z0-9]', '', raw_code2)
        if len(code2) >= 4:
            return code2
        return code or code2
    except Exception as e:
        print(f"[!] Captcha recognition error: {e}", flush=True)
        return None


def parse_size_bytes(size_str: str) -> int:
    """Parses a size string like '250 KB', '1.2 MB' into an integer of bytes."""
    if not size_str or size_str == "0 B" or "Unknown" in size_str:
        return 0
    m = re.search(r'([\d\.]+)\s*(KB|MB|GB|B)', size_str, re.I)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).upper()
    if unit == 'KB':
        return int(val * 1024)
    elif unit == 'MB':
        return int(val * 1024 * 1024)
    elif unit == 'GB':
        return int(val * 1024 * 1024 * 1024)
    return int(val)


CN_NUMS = {
    '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
    'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
    'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
    'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15,
    'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3, 'Ⅳ': 4, 'Ⅴ': 5,
    'Ⅵ': 6, 'Ⅶ': 7, 'Ⅷ': 8, 'Ⅸ': 9, 'Ⅹ': 10,
}

SPINOFF_KEYWORDS = ['扉子', '外传', '外傳', '番外', '特别篇', '特別篇', '前传', '前傳', '后传', '後傳', '短篇集']


def parse_chinese_num(s: str) -> int | None:
    if not s:
        return None
    s = s.strip()
    if s.isdigit():
        return int(s)
    return CN_NUMS.get(s.upper(), None)


def normalize_zh(s: str) -> str:
    """Translates common Traditional Chinese characters to Simplified for matching."""
    TRANS = str.maketrans({
        '萬': '万', '鑑': '鉴', '冊': '册', '與': '与', '門': '门',
        '誌': '志', '貓': '猫', '偵': '侦', '探': '探', '華': '华',
        '學': '学', '園': '园', '繪': '绘', '貴': '贵', '婦': '妇',
        '後': '后', '話': '话', '體': '体', '點': '点', '銀': '银',
    })
    return s.translate(TRANS)


def extract_volume_info(text: str) -> dict:
    """
    Extracts volume number, spin-off flag, and omnibus flag from a string.
    Handles '第X卷', '第X部', '第X册', '第X篇', '卷X', 'Vol.X', Roman numerals, etc.
    """
    norm_text = normalize_zh(text)
    has_spinoff = any(k in norm_text for k in SPINOFF_KEYWORDS)
    spinoff_name = next((k for k in SPINOFF_KEYWORDS if k in norm_text), None)
    is_omnibus = bool(re.search(r'(?:全集|合集|全\s*\d+\s*[卷部册篇]|\d+[-~～]\d+\s*[卷部册篇])', norm_text))

    vol = None
    # 1. '第X卷' / '第X部' / '第X册' / '第X篇'
    m = re.search(r'第\s*([0-9]+|[一二两三四五六七八九十]+)\s*[卷部册篇]', norm_text)
    if m:
        vol = parse_chinese_num(m.group(1))

    # 2. '卷X' / '册X'
    if vol is None:
        m = re.search(r'[卷部册篇]\s*([0-9]+|[一二两三四五六七八九十]+)', norm_text)
        if m:
            vol = parse_chinese_num(m.group(1))

    # 3. 'Vol. X' / 'Volume X'
    if vol is None:
        m = re.search(r'(?:vol|volume)\.?\s*([0-9]+)', norm_text, re.I)
        if m:
            vol = int(m.group(1))

    # 4. Enclosed in brackets/parentheses e.g. (2), （2）, [2], 【2】
    if vol is None:
        m = re.search(r'[\(（\[【]\s*([0-9]+|[一二两三四五六七八九十]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])\s*[\)）\]】]', norm_text)
        if m:
            vol = parse_chinese_num(m.group(1))

    # 5. Roman numerals isolated e.g. ' II ', ' Ⅲ '
    if vol is None:
        m = re.search(r'(?:^|[\s_—\-])(II|III|IV|VI{0,3}|IX|X|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])(?:[\s_—\-]|$)', norm_text)
        if m:
            vol = parse_chinese_num(m.group(1))

    # 6. Attached digit to book title or punctuation, e.g. '手帖1:', '手帖 2', '事件簿12', '事件簿 01'
    if vol is None:
        cleaned_text = re.sub(r'\b(?:19|20)\d{2}\b', '', norm_text)
        m = re.search(r'(?:^|[^\d])([0-9]{1,2})(?:[：:\s_—\-\.]|$|[^\d])', cleaned_text)
        if m:
            vol = int(m.group(1))

    if is_omnibus:
        vol = None

    return {
        "volume": vol,
        "has_spinoff": has_spinoff,
        "spinoff_name": spinoff_name,
        "is_omnibus": is_omnibus,
    }


def clean_query_core(query: str) -> str:
    """Extracts core book title from query by stripping volume patterns, author tokens, and punctuation."""
    q = normalize_zh(query.strip())
    q = re.sub(r'第\s*([0-9]+|[一二两三四五六七八九十]+)\s*[卷部册篇]', '', q)
    q = re.sub(r'(?:vol|volume)\.?\s*[0-9]+', '', q, flags=re.I)
    q = re.sub(r'[\(（\[【]\s*([0-9]+|[一二两三四五六七八九十]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])\s*[\)）\]】]', '', q)
    q = re.sub(r'\s+[0-9]{1,2}$', '', q).strip()
    return q


def compute_candidate_relevance(cand_title: str, cand_card: str, query: str) -> int:
    """Computes relevance score of candidate to query: 3=core in title, 2=term in title, 1=term in card, 0=irrelevant."""
    core = clean_query_core(query)
    terms = [normalize_zh(t.strip()) for t in re.split(r'[\s:：·—\-]+', query) if len(t.strip()) >= 2]
    cand_title_norm = normalize_zh(cand_title).lower()
    cand_full = normalize_zh(f"{cand_title} {cand_card}").lower()

    if core and core.lower() in cand_title_norm:
        return 3
    if any(t.lower() in cand_title_norm for t in terms):
        return 2
    if any(t.lower() in cand_full for t in terms):
        return 1
    return 0


async def solve_ddos_guard_if_present(page, timeout: int = 90) -> bool:
    """Detects and automatically solves DDoS-Guard checkbox & captcha if present."""
    has_ddg = False
    clicked_cb = False
    captcha_img_path = Path(tempfile.gettempdir()) / "annas_captcha_to_solve.png"
    code_override_path = Path(tempfile.gettempdir()) / "annas_captcha_code.txt"

    for s in range(timeout):
        try:
            title = await page.title()
            url = page.url
        except Exception:
            await page.wait_for_timeout(1000)
            continue

        # Check if actual Anna's Archive content is present
        try:
            has_results = await page.locator("a[href^='/md5/'], .js-aarecord-list-outer, main, footer").count() > 0
            if has_results and "check=1" not in url and "ddos-guard" not in title.lower():
                if has_ddg:
                    print(f"[*] Successfully bypassed DDoS-Guard at {s}s.", flush=True)
                return True
        except Exception:
            pass

        if has_ddg:
            if "check=1" not in url and "ddos-guard" not in title.lower():
                print(f"[*] Successfully bypassed DDoS-Guard at {s}s.", flush=True)
                return True

        if "check=1" in url or "ddos-guard" in title.lower():
            has_ddg = True
        try:
            iframe_loc = page.locator("#ddg-iframe")
            count = await iframe_loc.count()
            if count == 0:
                await page.wait_for_timeout(1000)
                continue

            iframe = page.frame_locator("#ddg-iframe")
            cb = iframe.locator(".ddg-captcha__checkbox")
            if not clicked_cb and await cb.count() > 0 and await cb.is_visible():
                print("[*] DDoS-Guard checkbox detected. Clicking...", flush=True)
                try:
                    await cb.click()
                    clicked_cb = True
                except Exception as ex:
                    print(f"[*] Error clicking checkbox: {ex}", flush=True)
                await page.wait_for_timeout(2000)

            captcha_img = iframe.locator(".ddg-modal__captcha-image")
            captcha_input = iframe.locator("input[name='captcha']")
            verify_btn = iframe.locator(".ddg-modal__submit")

            if await captcha_img.count() > 0 and await captcha_img.is_visible():
                code = None
                if code_override_path.exists():
                    try:
                        code = code_override_path.read_text(encoding="utf-8").strip()
                        code_override_path.unlink(missing_ok=True)
                        print(f"[*] Read captcha override code: '{code}'", flush=True)
                    except Exception:
                        pass

                if not code:
                    try:
                        img_bytes = await captcha_img.screenshot()
                        try:
                            captcha_img_path.write_bytes(img_bytes)
                        except Exception:
                            pass
                        code = recognize_captcha(img_bytes)
                        if code:
                            print(f"[*] OCR recognized code: '{code}'", flush=True)
                        else:
                            print("[*] OCR returned no valid code.", flush=True)
                    except Exception as ex:
                        print(f"[!] Captcha handling exception: {ex}", flush=True)

                if code and len(code) >= 4:
                    await captcha_input.fill(code)
                    await page.wait_for_timeout(300)
                    try:
                        await captcha_input.press("Enter")
                    except Exception:
                        pass
                    if await verify_btn.is_visible():
                        await verify_btn.click()
                    print("[*] Submitted captcha code. Waiting for response...", flush=True)
                    for _ in range(8):
                        await page.wait_for_timeout(1000)
                        t = await page.title()
                        u = page.url
                        if "check=1" not in u and "ddos-guard" not in t.lower():
                            print("[*] Successfully bypassed DDoS-Guard after captcha submission!", flush=True)
                            return True
                else:
                    print("[*] Code length < 4 or recognition failed, clicking refresh...", flush=True)
                    refresh_btn = iframe.locator(".img-refresh, button:has-text('Refresh'), .ddg-modal__refresh")
                    if await refresh_btn.count() > 0:
                        try:
                            await refresh_btn.first.click()
                        except Exception:
                            pass
                    await page.wait_for_timeout(2000)
        except Exception:
            pass

        await page.wait_for_timeout(1000)

    return False


async def auto_search_and_download(query: str, dest_dir: Path, requested_format: str = None,
                                  max_wait: int = 400, proxy: str = None, headless: bool = False) -> dict:
    """Automated search, DDoS bypass, candidate selection, multi-turn countdown (>60s), and download."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("Playwright is required for 'auto'. Run with: uv run --with playwright python scripts/download_helper.py auto ...")

    browser_exe = find_browser_executable()
    effective_proxy = proxy or detect_local_proxy()
    profile_dir = Path(tempfile.gettempdir()) / "annas_archive_browser_profile"

    print(f"[*] Starting auto download for query: '{query}'", flush=True)
    if effective_proxy:
        print(f"[*] Using proxy: {effective_proxy}", flush=True)
    if browser_exe:
        print(f"[*] Using browser: {browser_exe}", flush=True)

    try:
        async with async_playwright() as p:
            launch_args = {
                "user_data_dir": str(profile_dir),
                "headless": headless,
                "ignore_default_args": ["--enable-automation"],
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars"
                ],
                "viewport": {"width": 1280, "height": 800},
                "locale": "zh-CN"
            }
            if browser_exe:
                launch_args["executable_path"] = browser_exe
            if effective_proxy:
                launch_args["proxy"] = {"server": effective_proxy}

            context = await p.chromium.launch_persistent_context(**launch_args)
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'zh-CN'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)
            page = context.pages[0] if context.pages else await context.new_page()

            # 1. Search page
            search_url = f"https://annas-archive.gl/search?q={urllib.parse.quote(query)}"
            if requested_format:
                search_url += f"&ext={urllib.parse.quote(requested_format.lower())}"
            for _attempt in range(3):
                try:
                    await page.goto(search_url, timeout=60000)
                    break
                except Exception as ex:
                    if _attempt == 2:
                        raise
                    print(f"[*] Search page navigation retry ({ex})...", flush=True)
                    await page.wait_for_timeout(3000)

            # 2. Wait for search results, continuously solving DDoS-Guard if present
            print("[*] Waiting for search results to render (max 180s)...", flush=True)
            results_ready = False
            for s in range(180):
                await page.wait_for_timeout(1500)
                if s % 10 == 0 and s > 0:
                    print(f"[*] [{s}s/180s] Waiting for catalog entries (you can complete verification directly in Chrome window if needed)...", flush=True)

                # Check if catalog entries are already available
                try:
                    md5_count = await page.locator("a[href^='/md5/']").count()
                    if md5_count > 0:
                        results_ready = True
                        print(f"[*] Found {md5_count} catalog entries at {s}s.", flush=True)
                        break
                except Exception:
                    pass

                # Check if DDoS-Guard challenge is present
                try:
                    iframe_loc = page.locator("#ddg-iframe")
                    if await iframe_loc.count() > 0:
                        frame = page.frame_locator("#ddg-iframe")
                        cb = frame.locator(".ddg-captcha__checkbox")
                        if await cb.count() > 0 and await cb.is_visible():
                            print(f"[*] DDoS-Guard checkbox detected at {s}s. Clicking...", flush=True)
                            try:
                                await cb.click()
                            except Exception as ex:
                                print(f"[*] Error clicking checkbox: {ex}", flush=True)
                            await page.wait_for_timeout(2000)

                        captcha_img = frame.locator(".ddg-modal__captcha-image")
                        if await captcha_img.count() > 0 and await captcha_img.is_visible():
                            try:
                                img_bytes = await captcha_img.screenshot()
                                code = recognize_captcha(img_bytes)
                                if code:
                                    print(f"[*] OCR recognized code: '{code}'", flush=True)
                                else:
                                    print("[*] OCR returned no valid code.", flush=True)

                                if code and len(code) >= 4:
                                    inp = frame.locator("input[name='captcha']")
                                    await inp.fill(code)
                                    await page.wait_for_timeout(300)
                                    btn = frame.locator(".ddg-modal__submit")
                                    if await btn.is_visible():
                                        print("[*] Submitting captcha via submit button...", flush=True)
                                        await btn.click()
                                    else:
                                        print("[*] Submitting captcha via Enter key...", flush=True)
                                        await inp.press("Enter")
                                    await page.wait_for_timeout(3000)
                                else:
                                    print("[*] Code length < 4, clicking refresh...", flush=True)
                                    refresh_btn = frame.locator(".img-refresh, button:has-text('Refresh')")
                                    if await refresh_btn.count() > 0:
                                        await refresh_btn.first.click()
                                    await page.wait_for_timeout(2000)
                            except Exception as ex:
                                print(f"[!] Captcha handling exception: {ex}", flush=True)
                except Exception:
                    pass

            if not results_ready:
                await context.close()
                raise RuntimeError("Timed out waiting for search results. DDoS-Guard or network block.")

            # 3. Parse candidates
            content = await page.content()
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, "html.parser")
            except ImportError:
                soup = None

            candidates = []
            processed_md5 = set()
            if soup:
                # Remove ticker if present
                for ticker in soup.find_all("div", class_=re.compile(r"recent-downloads")):
                    ticker.decompose()

                outer = soup.find("div", class_="js-aarecord-list-outer")
                items = outer.find_all("div", recursive=False) if outer else []

                if items:
                    for item in items:
                        link = item.find("a", href=re.compile(r"/md5/([a-f0-9]{32})"))
                        if not link:
                            continue
                        md5 = re.search(r"/md5/([a-f0-9]{32})", link["href"]).group(1)
                        if md5 in processed_md5:
                            continue
                        processed_md5.add(md5)

                        card_text = " ".join(item.get_text().split())
                        fmt_match = re.search(r'·\s*(EPUB|MOBI|AZW3|PDF|DJVU|TXT)\s*·', card_text, re.I)
                        fmt = fmt_match.group(1).upper() if fmt_match else "OTHER"
                        if fmt == "OTHER":
                            for f in ["EPUB", "MOBI", "AZW3", "PDF", "TXT"]:
                                if re.search(r'\b' + f + r'\b', card_text, re.I):
                                    fmt = f
                                    break

                        size_match = re.search(r'·\s*([\d\.]+\s*(?:KB|MB|GB))\s*·', card_text, re.I)
                        if not size_match:
                            size_match = re.search(r'([\d\.]+\s*(?:KB|MB|GB))\b', card_text, re.I)
                        size_str = size_match.group(1) if size_match else "0 B"

                        dl_match = re.search(r'(?:Downloads|downloads|下载)?:?\s*(\d+)', card_text)
                        dl_count = int(dl_match.group(1)) if dl_match else 0

                        title_el = item.find("a", class_=re.compile(r"text-\[#2563eb\]"))
                        item_title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

                        candidates.append({
                            "md5": md5,
                            "title": item_title,
                            "format": fmt,
                            "size": size_str,
                            "size_bytes": parse_size_bytes(size_str),
                            "downloads": dl_count,
                            "card_text": card_text
                        })
                else:
                    for a in soup.find_all("a", href=True):
                        m = re.search(r"/md5/([a-f0-9]{32})", a["href"])
                        if not m:
                            continue
                        md5 = m.group(1)
                        if md5 in processed_md5:
                            continue
                        processed_md5.add(md5)

                        container = a
                        while container.parent and container.parent.name not in ['body', 'html']:
                            if 'relative' in container.get('class', []) or 'border' in container.get('class', []):
                                if len(container.get_text()) > 80:
                                    break
                            container = container.parent

                        card_text = container.get_text(" | ", strip=True)

                        fmt = "OTHER"
                        for f in ["EPUB", "MOBI", "AZW3", "PDF"]:
                            if re.search(r'\b' + f + r'\b', card_text, re.I):
                                fmt = f
                                break

                        size_match = re.search(r'([\d\.]+\s*(?:KB|MB|GB))\b', card_text, re.I)
                        size_str = size_match.group(1) if size_match else "0 B"

                        dl_match = re.search(r'(?:Downloads|downloads|下载)?:?\s*(\d+)', card_text)
                        dl_count = int(dl_match.group(1)) if dl_match else 0

                        h3 = container.find("h3")
                        item_title = h3.get_text(strip=True) if h3 else a.get_text(strip=True)

                        candidates.append({
                            "md5": md5,
                            "title": item_title,
                            "format": fmt,
                            "size": size_str,
                            "size_bytes": parse_size_bytes(size_str),
                            "downloads": dl_count,
                            "card_text": card_text
                        })
            else:
                # Fallback regex extraction if bs4 is missing
                raw_md5s = re.findall(r'/md5/([a-f0-9]{32})', content)
                for md5 in raw_md5s:
                    if md5 not in processed_md5:
                        processed_md5.add(md5)
                        candidates.append({
                            "md5": md5,
                            "title": query,
                            "format": "EPUB",
                            "size": "Unknown",
                            "size_bytes": 0,
                            "downloads": 0,
                            "card_text": ""
                        })

            print(f"[*] Parsed {len(candidates)} distinct book candidates.", flush=True)
            if not candidates:
                await context.close()
                raise RuntimeError(f"No matching books found for query '{query}'.")

            # 1. Title & Metadata Relevance Scoring
            for c in candidates:
                c["relevance"] = compute_candidate_relevance(c["title"], c["card_text"], query)

            max_rel = max((c["relevance"] for c in candidates), default=0)
            if max_rel >= 2:
                candidates = [c for c in candidates if c["relevance"] >= 2]
                print(f"[*] Retained {len(candidates)} candidate(s) with high title relevance (Score >= 2).", flush=True)
            elif max_rel == 1:
                candidates = [c for c in candidates if c["relevance"] >= 1]
                print(f"[*] Retained {len(candidates)} candidate(s) with metadata relevance (Score >= 1).", flush=True)

            # 2. Enhanced Volume Precision: robust extraction for volume number & spin-offs
            query_info = extract_volume_info(query)
            target_vol = query_info["volume"]
            wants_spinoff = query_info["has_spinoff"]
            core_query = clean_query_core(query)

            filtered = []
            exact_vol_matches = []
            omnibus_matches = []
            for c in candidates:
                cand_info = extract_volume_info(c["title"])
                if cand_info["volume"] is None:
                    card_cand_info = extract_volume_info(c["card_text"])
                    if card_cand_info["volume"] is not None:
                        cand_info["volume"] = card_cand_info["volume"]
                cand_vol = cand_info["volume"]
                cand_spinoff = cand_info["has_spinoff"] or extract_volume_info(c["card_text"])["has_spinoff"]

                # If query does NOT want spin-off (e.g. 扉子篇 / 外传), but candidate has it, reject
                if not wants_spinoff and cand_spinoff:
                    continue

                # If query specified target volume (e.g. 2):
                if target_vol is not None:
                    if cand_vol == target_vol:
                        exact_vol_matches.append(c)
                    elif cand_info["is_omnibus"]:
                        omnibus_matches.append(c)
                    elif cand_vol is not None and cand_vol != target_vol:
                        # Conflicting volume (e.g. vol 1 when asking for vol 2), reject!
                        continue
                    else:
                        filtered.append(c)
                else:
                    # If query didn't specify volume, reject sequels (vol > 1) UNLESS query is a specific title
                    # E.g., if query is "黑贵妇", candidate "匠千晓系列08:黑贵妇" has "黑贵妇" in title, so keep it!
                    core_in_title = bool(core_query and len(core_query) >= 2 and core_query.lower() in c["title"].lower())
                    if not core_in_title:
                        if cand_vol is not None and cand_vol > 1:
                            continue
                        if re.search(r'(?:续集|后篇|下册|第二部)', f"{c['title']} {c['card_text']}"):
                            continue
                    filtered.append(c)

            if target_vol is not None:
                if exact_vol_matches:
                    filtered = exact_vol_matches
                elif omnibus_matches:
                    print(f"[*] Single volume {target_vol} not found separately; falling back to omnibus edition.", flush=True)
                    filtered = omnibus_matches

            if query_info.get("is_omnibus"):
                omni_cands = [c for c in filtered if extract_volume_info(c["title"])["is_omnibus"] or extract_volume_info(c["card_text"])["is_omnibus"]]
                if omni_cands:
                    filtered = omni_cands

            if not filtered:
                print(f"[*] Volume precision filter yielded 0 candidates; falling back to all {len(candidates)} candidates.", flush=True)
                filtered = candidates

            # Language Filter: If query contains Chinese characters, prefer Chinese [zh] over Japanese [ja] or English [en]
            has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in query)
            if has_cjk:
                zh_cands = [c for c in filtered if re.search(r'\bChinese\s*\[zh\]', c.get("card_text", ""), re.I) or 'Chinese' in c.get("card_text", "")]
                if zh_cands:
                    print(f"[*] Filtered {len(zh_cands)} Chinese [zh] edition candidate(s).", flush=True)
                    filtered = zh_cands

            # Format priority & Size comparison (larger size preferred, e.g. 250KB > 200KB > 100KB)
            format_priority = [requested_format.upper()] if requested_format else ["EPUB", "MOBI", "AZW3", "PDF", "TXT"]
            best_candidate = None
            for fmt in format_priority:
                matching = [c for c in filtered if c["format"] == fmt and c.get("size_bytes", 0) > 0]
                if matching:
                    # Sort primarily by size descending, then by download count descending
                    matching.sort(key=lambda x: (x.get("size_bytes", 0), x.get("downloads", 0)), reverse=True)
                    best_candidate = matching[0]
                    break

            if not best_candidate:
                # Fallback to any candidate with size > 0
                candidates_with_size = [c for c in filtered if c.get("size_bytes", 0) > 0]
                if candidates_with_size:
                    candidates_with_size.sort(key=lambda x: (x.get("size_bytes", 0), x.get("downloads", 0)), reverse=True)
                    best_candidate = candidates_with_size[0]
                else:
                    best_candidate = filtered[0]

            print(f"[*] Selected best candidate: MD5={best_candidate['md5']}, Format={best_candidate['format']}, Size={best_candidate['size']} ({best_candidate.get('size_bytes', 0)} bytes), Title={best_candidate.get('title')}", flush=True)

            candidate_pool = [best_candidate]
            if matching:
                for c in matching:
                    if c['md5'] != best_candidate['md5']:
                        candidate_pool.append(c)

            target_slow_url = None
            selected_candidate = best_candidate

            for cand in candidate_pool[:4]:
                selected_candidate = cand
                detail_url = f"https://annas-archive.gl/md5/{cand['md5']}"
                print(f"[*] Navigating to detail page: {detail_url}", flush=True)
                for _attempt in range(2):
                    try:
                        await page.goto(detail_url, timeout=60000)
                        break
                    except Exception:
                        await page.wait_for_timeout(3000)
                await solve_ddos_guard_if_present(page, timeout=30)
                await page.wait_for_timeout(2000)

                slow_links = await page.eval_on_selector_all(
                    "a",
                    """elements => elements
                        .filter(e => e.innerText.includes('Slow Partner Server') || e.href.includes('/slow_download/'))
                        .map(e => ({ href: e.href, text: e.innerText.trim() }))
                    """
                )
                if slow_links:
                    target_slow_url = slow_links[0]["href"]
                    print(f"[*] Selected candidate with active slow download server: MD5={cand['md5']}, Title={cand.get('title')}", flush=True)
                    break
                else:
                    fallback_slow = f"https://annas-archive.gl/slow_download/{cand['md5']}/0/0"
                    print(f"[*] Using direct slow download URL format: {fallback_slow}", flush=True)
                    target_slow_url = fallback_slow
                    break

            if not target_slow_url:
                await context.close()
                raise RuntimeError(f"No slow download server found on any candidate detail page for query '{query}'.")

            # 5. Access slow download page & Multi-turn Countdown Detection
            print(f"[*] Accessing slow download server: {target_slow_url}", flush=True)
            await page.goto(target_slow_url, timeout=60000)
            await solve_ddos_guard_if_present(page, timeout=30)

            direct_download_url = None
            print(f"[*] Monitoring countdown (max {max_wait}s)...", flush=True)

            for elapsed in range(max_wait):
                await page.wait_for_timeout(1000)
                try:
                    # Check if DDoS-Guard reappeared
                    if await page.locator("#ddg-iframe").count() > 0:
                        await solve_ddos_guard_if_present(page, timeout=10)

                    dl_btn = await page.eval_on_selector_all(
                        "a",
                        """elements => elements
                            .filter(e => e.innerText.includes('Download now') || e.innerText.includes('download now') || e.innerText.includes('📚'))
                            .map(e => ({ href: e.href, text: e.innerText.trim() }))
                        """
                    )
                    if dl_btn:
                        direct_download_url = dl_btn[0]["href"]
                        print(f"[*] Download button appeared at {elapsed}s: {direct_download_url}", flush=True)
                        break

                    # Periodic countdown status check every 3 seconds (supports >60s queues)
                    if elapsed % 3 == 0:
                        body_text = await page.eval_on_selector("body", "e => e.innerText")
                        m = re.search(r'(?:wait|waiting|等待)\s*(\d+)\s*(?:seconds?|秒)', body_text, re.I)
                        if m:
                            print(f"[*] [{elapsed}s] Server queue countdown: {m.group(1)}s remaining...", flush=True)
                        else:
                            if elapsed % 15 == 0:
                                clean_snippet = ' '.join(body_text.split()[:20])
                                print(f"[*] [{elapsed}s] Waiting for server ticket... (Snippet: '{clean_snippet}')", flush=True)

                    # If stalled with no countdown for 25s, reload once to kickstart the queue
                    if elapsed == 25 and not direct_download_url:
                        body_text = await page.eval_on_selector("body", "e => e.innerText")
                        if not re.search(r'(?:wait|waiting|等待)\s*(\d+)\s*(?:seconds?|秒)', body_text, re.I):
                            print("[*] Stalled without active countdown; reloading page once to trigger server ticket...", flush=True)
                            await page.reload()
                            await page.wait_for_timeout(3000)

                    # If elapsed reached near end and countdown is still ticking, dynamically extend
                    if elapsed == max_wait - 1 and not direct_download_url:
                        try:
                            body_text = await page.eval_on_selector("body", "e => e.innerText")
                            m = re.search(r'(?:wait|waiting|等待)\s*(\d+)\s*(?:seconds?|秒)', body_text, re.I)
                            if m and int(m.group(1)) > 0:
                                rem = int(m.group(1))
                                print(f"[*] Queue still has {rem}s remaining, extending wait by {rem + 20}s...", flush=True)
                                for extra in range(rem + 20):
                                    await page.wait_for_timeout(1000)
                                    dl_btn = await page.eval_on_selector_all(
                                        "a",
                                        """elements => elements
                                            .filter(e => e.innerText.includes('Download now') || e.innerText.includes('download now') || e.innerText.includes('📚'))
                                            .map(e => ({ href: e.href, text: e.innerText.trim() }))
                                        """
                                    )
                                    if dl_btn:
                                        direct_download_url = dl_btn[0]["href"]
                                        print(f"[*] Download button appeared during extension at +{extra}s: {direct_download_url}", flush=True)
                                        break
                        except Exception:
                            pass

                except Exception:
                    await page.wait_for_timeout(1000)
                    continue

            # Reload if countdown passed but button didn't appear
            if not direct_download_url:
                print("[*] Countdown completed; reloading page to retrieve download ticket...", flush=True)
                await page.reload()
                await page.wait_for_timeout(4000)
                try:
                    dl_btn = await page.eval_on_selector_all(
                        "a",
                        """elements => elements
                            .filter(e => e.innerText.includes('Download now') || e.innerText.includes('download now') || e.innerText.includes('📚'))
                            .map(e => ({ href: e.href, text: e.innerText.trim() }))
                        """
                    )
                    if dl_btn:
                        direct_download_url = dl_btn[0]["href"]
                        print(f"[*] Download button found after reload: {direct_download_url}", flush=True)
                except Exception as e:
                    print(f"[*] Warning checking download button after reload: {e}", flush=True)

            await context.close()

            if not direct_download_url:
                raise RuntimeError(f"Failed to obtain direct download link after waiting {max_wait}s.")

            # 6. Stream file to ~/Downloads with clean filename
            print(f"[*] Downloading file from direct URL...", flush=True)
            res = download_file(
                url=direct_download_url,
                referer=target_slow_url,
                dest_dir=dest_dir,
                title=selected_candidate.get("title"),
                fmt=selected_candidate.get("format").lower(),
                proxy=effective_proxy
            )
            return res

    except Exception as e:
        raise RuntimeError(f"Auto download pipeline failed: {e}")


def cmd_auto(args):
    dest_dir = Path(args.dest).resolve() if args.dest else get_downloads_dir()
    results = []
    total = len(args.queries)

    for idx, q in enumerate(args.queries, 1):
        if total > 1:
            print(
                f"\n{'='*60}\n[*] Processing book {idx}/{total}: '{q}' (Strict Sequential Download - Concurrency: 1)\n{'='*60}",
                flush=True,
            )
        try:
            res = asyncio.run(auto_search_and_download(
                query=q,
                dest_dir=dest_dir,
                requested_format=args.format,
                max_wait=args.max_wait,
                proxy=args.proxy,
                headless=args.headless,
            ))
            results.append(res)
        except Exception as e:
            print(f"[!] Error downloading '{q}': {e}", file=sys.stderr, flush=True)
            results.append({"status": "error", "query": q, "message": str(e)})

        # Enforce cooldown before starting next book so server-side concurrency slot frees up
        if idx < total:
            print("[*] Pausing 5 seconds before starting next download to respect Anna's Archive concurrency=1 limit...", flush=True)
            import time
            time.sleep(5)

    output_data = results[0] if total == 1 else {
        "status": "success" if any(r.get("status") == "success" for r in results) else "error",
        "total_requested": total,
        "successful_downloads": sum(1 for r in results if r.get("status") == "success"),
        "books": results,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(json.dumps(output_data, ensure_ascii=False, indent=2))
    if total == 1 and results[0].get("status") != "success":
        sys.exit(1)


def cmd_clean_name(args):
    """Utility subcommand to preview or test filename cleaning logic."""
    cleaned = clean_annas_filename(args.raw_name, title=args.title, author=args.author, ext=args.format)
    print(cleaned)


def cmd_rename_local(args):
    """Renames existing local ebook file(s) in dest directory to '<Title> -- <Author>.<ext>'."""
    dest_dir = Path(args.dest).resolve() if args.dest else get_downloads_dir()
    target_file = Path(args.file).resolve() if args.file else None

    if target_file:
        files = [target_file]
    else:
        files = []
        for ext in ("*.epub", "*.mobi", "*.azw3", "*.pdf"):
            files.extend(dest_dir.glob(ext))

    renamed = []
    for f in files:
        if not f.exists() or not f.is_file():
            continue
        new_name = clean_annas_filename(f.name, title=args.title, author=args.author, ext=f.suffix)
        if new_name != f.name:
            new_path = f.parent / new_name
            counter = 1
            stem = new_path.stem
            suffix = new_path.suffix
            while new_path.exists() and new_path != f:
                new_path = f.parent / f"{stem} ({counter}){suffix}"
                counter += 1
            f.rename(new_path)
            renamed.append({"old": f.name, "new": new_path.name, "path": str(new_path)})

    res = {"status": "success", "renamed_files": renamed}
    print(json.dumps(res, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Ebook search, download, and verification helper for Anna's Archive")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Auto all-in-one command
    auto_parser = subparsers.add_parser("auto", help="Automated search, DDoS bypass, candidate selection, countdown, and download")
    auto_parser.add_argument("queries", nargs="+", help="One or more book titles to download sequentially (concurrency=1)")
    auto_parser.add_argument("--format", help="Target format (epub, mobi, azw3, pdf)")
    auto_parser.add_argument("--dest", help="Destination folder (defaults to ~/Downloads)")
    auto_parser.add_argument("--max-wait", type=int, default=400, help="Maximum countdown wait time in seconds (supports >60s queues)")
    auto_parser.add_argument("--proxy", help="Custom proxy URL (defaults to auto-detected local proxy e.g. 127.0.0.1:7897)")
    auto_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (default: False for anti-bot reliability)")
    auto_parser.add_argument("--output", help="Write JSON summary to file")
    auto_parser.set_defaults(func=cmd_auto)

    # Download command
    dl_parser = subparsers.add_parser("download", help="Download a direct URL to dest directory")
    dl_parser.add_argument("url", help="Direct download URL")
    dl_parser.add_argument("--title", help="Explicit book title (used to format '<Title> -- <Author>.<ext>')")
    dl_parser.add_argument("--author", help="Explicit book author (used to format '<Title> -- <Author>.<ext>')")
    dl_parser.add_argument("--filename", help="Fallback / custom filename")
    dl_parser.add_argument("--format", help="File extension / format (e.g. epub, mobi, azw3, pdf)")
    dl_parser.add_argument("--dest", help="Destination folder (defaults to ~/Downloads)")
    dl_parser.add_argument("--referer", help="HTTP Referer header")
    dl_parser.add_argument("--proxy", help="Custom proxy URL")
    dl_parser.add_argument("--timeout", type=int, default=60, help="Request timeout in seconds")
    dl_parser.add_argument("--output", help="Write JSON summary to file")
    dl_parser.set_defaults(func=cmd_download)

    # Clean name command
    clean_parser = subparsers.add_parser("clean-name", help="Clean an Anna's Archive raw filename")
    clean_parser.add_argument("raw_name", help="Raw filename to clean")
    clean_parser.add_argument("--title", help="Explicit book title")
    clean_parser.add_argument("--author", help="Explicit book author")
    clean_parser.add_argument("--format", help="File extension")
    clean_parser.set_defaults(func=cmd_clean_name)

    # Rename local command
    rename_parser = subparsers.add_parser("rename", help="Normalize filenames of existing downloaded files in ~/Downloads")
    rename_parser.add_argument("--file", help="Specific file path to rename")
    rename_parser.add_argument("--dest", help="Directory containing downloaded files (defaults to ~/Downloads)")
    rename_parser.add_argument("--title", help="Explicit book title")
    rename_parser.add_argument("--author", help="Explicit book author")
    rename_parser.set_defaults(func=cmd_rename_local)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
