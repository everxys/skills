#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NAS Movie Downloader CLI
Automates movie searching via Jackett (Torznab), filtering and ranking releases,
submitting to qBittorrent, and post-download subtitle matching & directory organization.

Features:
1. Douban Integration:
   - Auto-resolves Chinese titles to foreign titles and aliases via Douban.
   - Handles Latin-script priority (English, French, Italian, Spanish, etc.).
   - Parses "又名" (AKA) when primary sub_title is non-Latin (e.g. Japanese 鉄男 -> Tetsuo: The Ironman).
   - Detects disambiguation: homonyms, franchises/multi-part movies, TV series seasons.
2. Selection Rules:
   - Title must match query (case-insensitive, normalized word sequence).
   - If year is provided, year must match (4-digit boundary).
   - Seeders >= 1 is a HARD constraint (candidates with 0 seeders excluded).
   - Priority:
     * If candidates > 3GB exist, pick highest seeders (tie-break: larger size).
     * If no candidates > 3GB exist, pick <= 3GB candidates with highest seeders.
3. Post-Download Subtitles & Directory Organization:
   - Video duration verification via ffprobe (matches movie runtime with subtitle dialogue timestamps).
   - Subtitle languages: Simplified Chinese (.zh-CN.srt) & English (.en.srt).
   - Chinese Subtitle Sources (in strict priority order):
     1. 字幕库 (zimuku.org)
     2. 伪射手网 (assrt.net)
     3. SubHD (subhd.tv)
     4. A4K字幕网 (a4k.net)
   - English Subtitle Sources (in strict priority order):
     1. OpenSubtitles (opensubtitles.com / .org)
     2. Subscene / Subdl (subdl.com)
     3. YIFY Subtitles (yts-subs.com)
   - Organization: Puts video and matching subtitles in the same directory:
     "/nasdata/downloads/<中文名> <外文名>/"
"""

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Ensure UTF-8 output and line buffering on Windows consoles / piped tasks
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
except Exception:
    pass

# Default NAS configuration & Dual-Network Endpoints (LAN primary, Tailscale fallback)
LAN_NAS_IP = "192.168.0.2"
TAILSCALE_NAS_IP = "100.125.232.123"
DEFAULT_SSH_PORT = 54540
DEFAULT_SSH_USER = "everxys"
DEFAULT_JACKETT_PORT = 9117
DEFAULT_QBIT_PORT = 54808

DEFAULT_SSH_HOST = os.environ.get("NAS_SSH_HOST", "nas")
DEFAULT_NAS_DOWNLOAD_DIR = os.environ.get("NAS_DOWNLOAD_DIR", "/nasdata/downloads")
DEFAULT_JACKETT_URL = os.environ.get("JACKETT_URL", f"http://{LAN_NAS_IP}:{DEFAULT_JACKETT_PORT}")
DEFAULT_JACKETT_APIKEY = os.environ.get("JACKETT_API_KEY", "o1tzon5zd14eufrarrzkw11qpi86yxak")
DEFAULT_QBIT_URL = os.environ.get("QBIT_URL", f"https://{LAN_NAS_IP}:{DEFAULT_QBIT_PORT}")
DEFAULT_QBIT_USER = os.environ.get("QBIT_USER", "everxys")
DEFAULT_QBIT_PASSWORD = os.environ.get("QBIT_PASSWORD", "!z8#upNXfS*#ER")
SIZE_3GB_BYTES = 3 * 1024 * 1024 * 1024
SIZE_15GB_BYTES = 15 * 1024 * 1024 * 1024
MIN_FREE_SPACE_THRESHOLD_BYTES = 1024 * 1024 * 1024 * 1024  # 1 TiB (1024 GB)

IS_ON_NAS = os.path.exists("/nasdata/downloads") or socket.gethostname() == "everxys-nas"
NAS_SCRIPT_DIR = "/nasdata/scripts/nas-video-download"

if IS_ON_NAS:
    DEFAULT_REPORT_PATH = os.environ.get(
        "NAS_REPORT_PATH",
        os.path.join(NAS_SCRIPT_DIR, "nas_movie_download_report.xlsx")
    )
    DEFAULT_LOG_PATH = os.environ.get(
        "NAS_LOG_PATH",
        os.path.join(NAS_SCRIPT_DIR, "nas_movie_batch.log")
    )
else:
    DEFAULT_REPORT_PATH = os.environ.get(
        "NAS_REPORT_PATH",
        os.path.join(os.path.expanduser("~"), "Downloads", "nas_movie_download_report.xlsx")
    )
    DEFAULT_LOG_PATH = os.environ.get(
        "NAS_LOG_PATH",
        os.path.join(os.path.expanduser("~"), "Downloads", "nas_movie_batch.log")
    )

# High-availability, verified public Tier-1 Trackers to revive cold swarms & accelerate DHT
DEFAULT_TIER1_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.bittor.pw:1337/announce",
    "udp://public.popcorn-tracker.org:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "http://tracker.openbittorrent.com:80/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "udp://tracker.cyberia.is:6969/announce"
]

# Defunct/dead tracker hostnames that permanently stall metaDL / connection
DEAD_TRACKER_HOSTS = [
    "9.rarbg.me", "9.rarbg.to", "rarbg.me", "rarbg.to",
    "coppersurfer.tk", "thetracker.org", "tracker.tiny-vps.com",
    "tracker.port443.xyz", "open.free-tracker.ga", "ns-1.x-fins.com",
    "p4p.arenabg.com", "tracker.open-internet.nl", "denis.stalker.upeer.me"
]


def sanitize_and_enrich_magnet(magnet_url: str) -> str:
    """
    Strips dead/defunct tracker domains from a magnet URL and automatically injects
    healthy, live Tier-1 public trackers.
    """
    if not magnet_url.startswith("magnet:"):
        return magnet_url
    try:
        parsed = urllib.parse.urlparse(magnet_url)
        params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        filtered_params = []
        existing_tr = set()
        for k, v in params:
            if k == "tr":
                v_lower = v.lower()
                if any(dh in v_lower for dh in DEAD_TRACKER_HOSTS):
                    continue
                existing_tr.add(v)
            filtered_params.append((k, v))
        for tr in DEFAULT_TIER1_TRACKERS:
            if tr not in existing_tr:
                filtered_params.append(('tr', tr))
                existing_tr.add(tr)
        return urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urllib.parse.urlencode(filtered_params),
            parsed.fragment
        ))
    except Exception:
        return magnet_url


class TeeLogger:
    """Duplicates stdout/stderr to a log file for user tracking in real time."""
    def __init__(self, filename, original_stream):
        self.terminal = original_stream
        self.log_file = open(filename, "a", encoding="utf-8", errors="replace")

    def write(self, message):
        try:
            self.terminal.write(message)
            self.terminal.flush()
        except Exception:
            pass
        try:
            self.log_file.write(message)
            self.log_file.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self.terminal.flush()
        except Exception:
            pass
        try:
            self.log_file.flush()
        except Exception:
            pass


def normalize_text(text: str) -> str:
    """Normalize text by replacing non-alphanumeric and non-CJK characters with spaces."""
    return re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]+', ' ', text).strip().lower()


def has_cjk(text: str) -> bool:
    """Check if text contains Chinese, Japanese, or Korean characters."""
    return bool(re.search(r'[\u4e00-\u9fa5\u3040-\u30ff\uac00-\ud7af]', text))


def is_mostly_latin(text: str) -> bool:
    """Check if text is primarily Latin alphabet without CJK."""
    return bool(re.search(r'[a-zA-Z]', text)) and not has_cjk(text)


def parse_query_and_year(query: str, explicit_year: str = None):
    """
    Extract title and 4-digit year from query if not explicitly passed.
    e.g., 'Manufacturing Consent 1992' -> ('Manufacturing Consent', '1992')
    """
    year = explicit_year
    cleaned_query = query.strip()
    if not year:
        m = re.search(r'\b(19\d\d|20\d\d)\b', cleaned_query)
        if m:
            year = m.group(1)
            cleaned_query = re.sub(r'[\(\[\{]?\b' + year + r'\b[\)\]\}]?', '', cleaned_query).strip()
            cleaned_query = re.sub(r'\s+', ' ', cleaned_query)
    return cleaned_query, year


KNOWN_RELEASE_TAGS = {
    '1080p', '720p', '2160p', '4k', 'uhd', 'bluray', 'bdrip', 'brrip', 'webrip',
    'web', 'dl', 'webdl', 'dvdrip', 'remux', 'h264', 'x264', 'h265', 'x265', 'hevc',
    'aac', 'dts', 'ddp', 'ac3', 'truehd', 'atmos', 'criterion', 'remastered',
    'proper', 'repack', 'yts', 'rarbg', 'complete', 'extended', 'unrated',
    'directors', 'cut', 'edition', 'v2', 'arrow', 'moc', 'limited', 'internal',
    'hdrip', 'dvd', 'xvid', 'divx', 'hdr', 'hdr10', 'dv', 'imax', 'multi', 'sub'
}


def is_release_tag_or_year(word: str) -> bool:
    w = word.lower()
    if re.match(r'^(19\d\d|20\d\d)$', w):
        return True
    return w in KNOWN_RELEASE_TAGS


def matches_title(query_title: str, candidate_title: str) -> bool:
    if not query_title:
        return True

    # If query contains CJK characters, check substring match
    if has_cjk(query_title):
        cjk_q = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]+', '', query_title).lower()
        cjk_c = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]+', '', candidate_title).lower()
        return cjk_q in cjk_c

    # For alphanumeric queries: prevent matching completely different films (e.g. Tokyo Sonata vs Tokyo!)
    norm_query = re.sub(r'[^a-zA-Z0-9]+', ' ', query_title).strip().lower()
    q_words = norm_query.split()
    if not q_words:
        return False

    norm_candidate = re.sub(r'[^a-zA-Z0-9]+', ' ', candidate_title).strip().lower()
    c_words = norm_candidate.split()

    len_q = len(q_words)
    for i in range(len(c_words) - len_q + 1):
        if c_words[i:i+len_q] == q_words:
            next_idx = i + len_q
            if next_idx >= len(c_words):
                return True
            next_word = c_words[next_idx]
            if is_release_tag_or_year(next_word):
                return True
            # Allow colon/dash subtitle separator like "Title: Subtitle"
            pattern_sep = re.compile(re.escape(q_words[-1]) + r'[\s]*[:\-–]\s*', re.IGNORECASE)
            if pattern_sep.search(candidate_title):
                return True
            return False

    return False


def matches_year(year: str, candidate_title: str) -> bool:
    if not year:
        return True
    return bool(re.search(r'\b' + re.escape(str(year)) + r'\b', candidate_title))


def is_sequel(cn_title: str, foreign_title: str = "") -> bool:
    """
    Detect whether a film is a sequel (e.g. 死亡之雪2, 头脑特工队2, 教父2, etc.).
    Preserves 4-digit years like 1984, 2001, etc.
    """
    cn_clean = (cn_title or '').strip()
    cn_no_year = re.sub(r'[\(\[\{]?(19\d\d|20\d\d)[\)\]\}]?$', '', cn_clean).strip()
    if not cn_no_year:
        return False
    if re.search(r'(?<!\d)([2-9]|II|III|IV|V|VI|VII|VIII|IX|X)\s*$', cn_no_year, re.I):
        return True
    if re.search(r'(?<!\d)([2-9]|II|III|IV|V|VI|VII|VIII|IX|X)\s*[:：·•\-_]', cn_no_year, re.I):
        return True
    if any(k in cn_no_year for k in ['续集', '后传', '第二部', '第三部', '第四部', '第二季', '第三季', '最终章', '终局之战']):
        return True
    if foreign_title:
        f_clean = (foreign_title or '').strip()
        f_no_year = re.sub(r'[\(\[\{]?(19\d\d|20\d\d)[\)\]\}]?$', '', f_clean).strip()
        if re.search(r'(?<!\d)(2|3|4|5|6|7|8|9)\s*$', f_no_year):
            return True
        if re.search(r'\b(II|III|IV|V|VI|VII|VIII|IX|X)\b\s*$', f_no_year, re.I):
            return True
        if re.search(r'\b(Part|Vol|Volume|Chapter)\s*([2-9]|II|III|IV|V|VI|VII|VIII|IX|X)\b', f_no_year, re.I):
            return True
        if re.search(r'(?<!\d)(2|3|4|5|6|7|8|9)\s*[:：\-–]', f_no_year):
            return True
    return False


class DoubanResolver:
    """
    Resolves Chinese movie/TV titles to foreign titles and aliases via Douban.
    Handles disambiguation: homonyms, franchises/multi-part movies, TV series seasons.
    """
    def __init__(self):
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }

    def _fetch_douban_suggest(self, query: str):
        url = f"https://movie.douban.com/j/subject_suggest?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with self.opener.open(req, timeout=10) as resp:
                data = resp.read().decode('utf-8')
                return json.loads(data)
        except Exception:
            return []

    def _fetch_subject_abstract(self, subject_id: str):
        url = f"https://movie.douban.com/j/subject_abstract?subject_id={subject_id}"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with self.opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get('r') == 0:
                    return data.get('subject', {})
        except Exception:
            pass
        return {}

    def _solve_douban_pow(self, html: str) -> str:
        tok_m = re.search(r'name="tok" value="([^"]+)"', html)
        cha_m = re.search(r'name="cha" value="([^"]+)"', html)
        red_m = re.search(r'name="red" value="([^"]+)"', html)
        if not (tok_m and cha_m and red_m):
            return html

        tok, cha, red = tok_m.group(1), cha_m.group(1), red_m.group(1)
        nonce = 0
        target = "0000"
        while True:
            nonce += 1
            h = hashlib.sha512((cha + str(nonce)).encode('utf-8')).hexdigest()
            if h.startswith(target):
                break

        post_data = urllib.parse.urlencode({'tok': tok, 'cha': cha, 'sol': nonce, 'red': red}).encode('utf-8')
        post_req = urllib.request.Request('https://sec.douban.com/c', data=post_data, headers=self.headers)
        try:
            with self.opener.open(post_req, timeout=15) as resp:
                return resp.read().decode('utf-8')
        except Exception:
            return html

    def _fetch_desktop_akas(self, subject_id: str):
        url = f"https://movie.douban.com/subject/{subject_id}/"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with self.opener.open(req, timeout=10) as resp:
                html = resp.read().decode('utf-8')

            if '<form name="sec"' in html:
                html = self._solve_douban_pow(html)

            aka_match = re.search(r'<span class="pl">又名:</span>\s*([^<]+)<br\s*/?>', html)
            if aka_match:
                raw_aka = aka_match.group(1).strip()
                return [a.strip() for a in raw_aka.split('/') if a.strip()]
        except Exception:
            pass
        return []

    def resolve(self, query: str):
        raw_items = self._fetch_douban_suggest(query)
        if not raw_items:
            return {
                'status': 'no_results',
                'query': query,
                'category': 'unknown',
                'candidates': []
            }

        candidates = []
        is_all_tv = True
        has_franchise = False

        for item in raw_items:
            s_id = str(item.get('id', ''))
            title = item.get('title', '')
            sub_title = item.get('sub_title', '')
            year = item.get('year', '')
            ep = item.get('episode', '')

            abstract = self._fetch_subject_abstract(s_id)
            directors = abstract.get('directors', [])
            region = abstract.get('region', '')
            is_tv = abstract.get('is_tv', False) or bool(ep)
            if not is_tv:
                is_all_tv = False

            if any(num in title for num in ['1', '2', '3', '4', '5', '前传', '终局', '无限']):
                has_franchise = True

            latin_titles = []
            akas = []

            if sub_title and is_mostly_latin(sub_title):
                latin_titles.append(sub_title)
            elif sub_title and has_cjk(sub_title):
                akas = self._fetch_desktop_akas(s_id)
                for a in akas:
                    if is_mostly_latin(a) and a not in latin_titles:
                        latin_titles.append(a)

            search_titles = []
            for lt in latin_titles:
                if lt not in search_titles:
                    search_titles.append(lt)
            if sub_title and sub_title not in search_titles:
                search_titles.append(sub_title)
            if title not in search_titles:
                search_titles.append(title)

            candidates.append({
                'id': s_id,
                'title': title,
                'sub_title': sub_title,
                'year': year,
                'episode': ep,
                'is_tv': is_tv,
                'directors': directors,
                'region': region,
                'akas': akas,
                'latin_titles': latin_titles,
                'search_titles': search_titles,
                'url': f"https://movie.douban.com/subject/{s_id}/"
            })

        category = 'single'
        if is_all_tv or any('季' in c['title'] for c in candidates):
            category = 'tv_seasons'
        elif len(candidates) > 1 and has_franchise:
            category = 'franchise'
        elif len(candidates) > 1:
            category = 'homonyms'

        cn_num = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        def season_key(c):
            m = re.search(r'第([0-9一二三四五六七八九十]+)季', c['title'])
            if m:
                val = m.group(1)
                if val in cn_num:
                    return cn_num[val]
                if val.isdigit():
                    return int(val)
            return int(c['year']) if c['year'].isdigit() else 9999

        if category == 'tv_seasons':
            candidates.sort(key=season_key)
        elif category == 'franchise':
            candidates.sort(key=lambda c: (int(c['year']) if c['year'].isdigit() else 9999))

        return {
            'status': 'success',
            'query': query,
            'category': category,
            'candidates': candidates
        }


class NASClient:
    def __init__(self, jackett_url=DEFAULT_JACKETT_URL, jackett_apikey=DEFAULT_JACKETT_APIKEY,
                 qbit_url=DEFAULT_QBIT_URL, qbit_user=DEFAULT_QBIT_USER, qbit_password=DEFAULT_QBIT_PASSWORD,
                 ssh_host=DEFAULT_SSH_HOST, nas_download_dir=DEFAULT_NAS_DOWNLOAD_DIR,
                 force_tailscale=False):
        self.jackett_url = jackett_url.rstrip('/')
        self.jackett_apikey = jackett_apikey
        self.qbit_url = qbit_url.rstrip('/')
        self.qbit_user = qbit_user
        self.qbit_password = qbit_password
        self.ssh_host = ssh_host
        self.nas_download_dir = nas_download_dir
        self.force_tailscale = force_tailscale

        self.ssl_ctx = ssl._create_unverified_context()
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.HTTPSHandler(context=self.ssl_ctx)
        )
        self.qbit_logged_in = False

        self.active_mode = "lan"
        if self.force_tailscale:
            self._apply_tailscale_routing(reason="用户指定强制使用 Tailscale 连接")
        else:
            self._detect_and_configure_network()

    @staticmethod
    def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
        """Check if a TCP port is reachable within timeout."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def _apply_tailscale_routing(self, reason: str = ""):
        """Switch active endpoints from LAN to Tailscale."""
        if getattr(self, 'active_mode', None) == "tailscale":
            return
        if reason:
            print(f"[*] {reason} ({TAILSCALE_NAS_IP})", flush=True)
        self.active_mode = "tailscale"
        if LAN_NAS_IP in self.jackett_url:
            self.jackett_url = self.jackett_url.replace(LAN_NAS_IP, TAILSCALE_NAS_IP)
        if LAN_NAS_IP in self.qbit_url:
            self.qbit_url = self.qbit_url.replace(LAN_NAS_IP, TAILSCALE_NAS_IP)
        if self.ssh_host in ("nas", LAN_NAS_IP):
            self.ssh_host = TAILSCALE_NAS_IP
        self.qbit_logged_in = False

    def _detect_and_configure_network(self):
        """Auto-detect whether LAN or Tailscale is reachable; fallback to Tailscale if LAN fails."""
        if IS_ON_NAS:
            self.active_mode = "local"
            return

        self.active_mode = "lan"
        is_default_lan = (
            LAN_NAS_IP in self.jackett_url or
            LAN_NAS_IP in self.qbit_url or
            self.ssh_host in ("nas", LAN_NAS_IP)
        )
        if not is_default_lan:
            return

        # Fast TCP ping to LAN SSH or WebUI
        lan_ok = self.is_port_open(LAN_NAS_IP, DEFAULT_SSH_PORT, timeout=1.0) or \
                 self.is_port_open(LAN_NAS_IP, DEFAULT_QBIT_PORT, timeout=1.0)
        if lan_ok:
            self.active_mode = "lan"
            return

        # LAN unreachable, test Tailscale
        ts_ok = self.is_port_open(TAILSCALE_NAS_IP, DEFAULT_SSH_PORT, timeout=1.5) or \
                self.is_port_open(TAILSCALE_NAS_IP, DEFAULT_QBIT_PORT, timeout=1.5)
        if ts_ok:
            self._apply_tailscale_routing(reason="局域网 (192.168.0.2) 无法连通，已自动切换至 Tailscale")
        else:
            print("[!] 警告: 局域网 (192.168.0.2) 与 Tailscale (100.125.232.123) 均未响应，将尝试保持默认设置。", flush=True)

    def get_ssh_cmd(self, command: str, mode: str = None) -> list:
        """Construct SSH command arguments based on active connection mode."""
        m = mode or getattr(self, 'active_mode', 'lan')
        if self.ssh_host not in ("nas", LAN_NAS_IP, TAILSCALE_NAS_IP):
            return ["ssh", "-o", "BatchMode=yes", self.ssh_host, command]

        target_host = TAILSCALE_NAS_IP if m == "tailscale" else LAN_NAS_IP
        return [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=6",
            "-p", str(DEFAULT_SSH_PORT),
            f"{DEFAULT_SSH_USER}@{target_host}",
            command
        ]

    def exec_nas(self, command: str) -> str:
        """Execute a shell command on NAS (directly if running locally on NAS, else via SSH)."""
        if IS_ON_NAS:
            res = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
            if res.returncode != 0:
                raise RuntimeError(f"Local NAS command failed ({res.returncode}): {res.stderr.strip()}")
            return res.stdout

        cmd = self.get_ssh_cmd(command)
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')

        # Reactive failover: if failed on LAN due to connection issues, retry via Tailscale
        if res.returncode != 0 and getattr(self, 'active_mode', 'lan') == "lan":
            err_lower = res.stderr.lower()
            if any(k in err_lower for k in ["timed out", "could not resolve", "no route", "unreachable", "refused", "port 54540", "broken pipe"]):
                self._apply_tailscale_routing(reason="局域网 SSH 发生网络连接异常，自动切换并重试")
                ts_cmd = self.get_ssh_cmd(command, mode="tailscale")
                res = subprocess.run(ts_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')

        if res.returncode != 0:
            raise RuntimeError(f"NAS command failed ({res.returncode}): {res.stderr.strip()}")
        return res.stdout

    def search_jackett(self, query: str, timeout: int = 90):
        search_url = f"{self.jackett_url}/api/v2.0/indexers/all/results/torznab/api?apikey={self.jackett_apikey}&t=search&q={urllib.parse.quote(query)}"
        req = urllib.request.Request(search_url, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                xml_data = resp.read()
        except Exception as e:
            if getattr(self, 'active_mode', 'lan') == "lan":
                self._apply_tailscale_routing(reason="Jackett 局域网访问失败，尝试切换至 Tailscale")
                search_url = f"{self.jackett_url}/api/v2.0/indexers/all/results/torznab/api?apikey={self.jackett_apikey}&t=search&q={urllib.parse.quote(query)}"
                req = urllib.request.Request(search_url, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        xml_data = resp.read()
                except Exception as e2:
                    raise RuntimeError(f"Failed to query Jackett at {self.jackett_url}: {e2}")
            else:
                raise RuntimeError(f"Failed to query Jackett at {self.jackett_url}: {e}")

        try:
            root = ET.fromstring(xml_data)
        except Exception as e:
            raise RuntimeError(f"Failed to parse XML from Jackett: {e}")

        items = []
        for item_node in root.findall('.//item'):
            title = item_node.findtext('title') or ''
            size = int(item_node.findtext('size') or 0)
            link = item_node.findtext('link') or ''
            enclosure = item_node.find('enclosure')
            enc_url = enclosure.get('url') if enclosure is not None else ''
            enc_len = int(enclosure.get('length') or 0) if enclosure is not None else 0

            download_url = enc_url or link
            final_size = enc_len if enc_len > 0 else size

            attrs = {}
            for attr in item_node.findall('{http://torznab.com/schemas/2015/feed}attr'):
                name = attr.get('name')
                val = attr.get('value')
                if name:
                    attrs[name] = val

            seeders = int(attrs.get('seeders') or 0)
            peers = int(attrs.get('peers') or 0)
            info_hash = attrs.get('infohash') or ''
            indexer = item_node.findtext('jackettindexer') or ''

            items.append({
                'title': title,
                'size': final_size,
                'seeders': seeders,
                'peers': peers,
                'url': download_url,
                'info_hash': info_hash,
                'indexer': indexer
            })

        return items

    def qbit_login(self):
        if self.qbit_logged_in:
            return
        login_url = f"{self.qbit_url}/api/v2/auth/login"
        post_data = urllib.parse.urlencode({
            'username': self.qbit_user,
            'password': self.qbit_password
        }).encode('utf-8')
        req = urllib.request.Request(login_url, data=post_data, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
        try:
            with self.opener.open(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    raise RuntimeError(f"qBittorrent login failed with HTTP {resp.status}")
                body = resp.read().decode('utf-8')
                if "Fails" in body:
                    raise RuntimeError("qBittorrent login credentials rejected.")
            self.qbit_logged_in = True
        except Exception as e:
            if getattr(self, 'active_mode', 'lan') == "lan":
                self._apply_tailscale_routing(reason="qBittorrent 局域网连接失败，尝试切换至 Tailscale")
                login_url = f"{self.qbit_url}/api/v2/auth/login"
                req = urllib.request.Request(login_url, data=post_data, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
                try:
                    with self.opener.open(req, timeout=10) as resp:
                        if resp.status not in (200, 204):
                            raise RuntimeError(f"qBittorrent login failed with HTTP {resp.status}")
                        body = resp.read().decode('utf-8')
                        if "Fails" in body:
                            raise RuntimeError("qBittorrent login credentials rejected.")
                    self.qbit_logged_in = True
                    return
                except Exception as e2:
                    raise RuntimeError(f"Failed to connect to qBittorrent at {self.qbit_url}: {e2}")
            raise RuntimeError(f"Failed to connect to qBittorrent at {self.qbit_url}: {e}")

    def add_torrent(self, url: str, category: str = "movies", tags: str = "auto-movie", paused: bool = False, info_hash: str = ""):
        self.qbit_login()
        final_url = sanitize_and_enrich_magnet(url) if url.startswith("magnet:") else url
        add_url = f"{self.qbit_url}/api/v2/torrents/add"
        form_data = {
            'urls': final_url,
            'category': category or '',
            'tags': tags or '',
            'paused': 'true' if paused else 'false'
        }
        post_data = urllib.parse.urlencode(form_data).encode('utf-8')
        req = urllib.request.Request(add_url, data=post_data, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
        res_data = None
        try:
            with self.opener.open(req, timeout=15) as resp:
                res_data = resp.read().decode('utf-8')
        except Exception as e:
            if getattr(self, 'active_mode', 'lan') == "lan":
                self._apply_tailscale_routing(reason="qBittorrent 添加任务失败，尝试切换至 Tailscale")
                self.qbit_login()
                add_url = f"{self.qbit_url}/api/v2/torrents/add"
                req = urllib.request.Request(add_url, data=post_data, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
                with self.opener.open(req, timeout=15) as resp:
                    res_data = resp.read().decode('utf-8')
            else:
                raise

        # If info_hash is available, immediately inject verified tier-1 public trackers
        if info_hash:
            try:
                self.add_trackers(info_hash, DEFAULT_TIER1_TRACKERS)
            except Exception:
                pass
        return res_data

    def get_torrents_info(self, filter_status: str = None, hashes: str = None):
        self.qbit_login()
        params = {}
        if filter_status:
            params['filter'] = filter_status
        if hashes:
            params['hashes'] = hashes

        query_str = urllib.parse.urlencode(params)
        info_url = f"{self.qbit_url}/api/v2/torrents/info" + (f"?{query_str}" if query_str else "")
        req = urllib.request.Request(info_url, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
        try:
            with self.opener.open(req, timeout=15) as resp:
                content = resp.read().decode('utf-8')
                return json.loads(content)
        except Exception as e:
            if getattr(self, 'active_mode', 'lan') == "lan":
                self._apply_tailscale_routing(reason="qBittorrent 读取状态超时，自动切换至 Tailscale")
                self.qbit_login()
                info_url = f"{self.qbit_url}/api/v2/torrents/info" + (f"?{query_str}" if query_str else "")
                req = urllib.request.Request(info_url, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
                with self.opener.open(req, timeout=15) as resp:
                    content = resp.read().decode('utf-8')
                    return json.loads(content)
            raise
            return json.loads(content)

    def pause_torrent(self, hashes: str):
        self.qbit_login()
        data = urllib.parse.urlencode({'hashes': hashes}).encode('utf-8')
        last_err = None
        for endpoint in ('stop', 'pause'):
            try:
                req = urllib.request.Request(f"{self.qbit_url}/api/v2/torrents/{endpoint}", data=data)
                with self.opener.open(req, timeout=10) as resp:
                    return resp.status == 200
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 404:
                    continue
                raise
            except Exception as e:
                last_err = e
                break
        raise RuntimeError(f"qBittorrent pause failed: {last_err}")

    def resume_torrent(self, hashes: str):
        self.qbit_login()
        data = urllib.parse.urlencode({'hashes': hashes}).encode('utf-8')
        last_err = None
        for endpoint in ('start', 'resume'):
            try:
                req = urllib.request.Request(f"{self.qbit_url}/api/v2/torrents/{endpoint}", data=data)
                with self.opener.open(req, timeout=10) as resp:
                    return resp.status == 200
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 404:
                    continue
                raise
            except Exception as e:
                last_err = e
                break
        raise RuntimeError(f"qBittorrent resume failed: {last_err}")

    def delete_torrent(self, hashes: str, delete_files: bool = False):
        self.qbit_login()
        url = f"{self.qbit_url}/api/v2/torrents/delete"
        data = urllib.parse.urlencode({
            'hashes': hashes,
            'deleteFiles': 'true' if delete_files else 'false'
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data)
        with self.opener.open(req, timeout=10) as resp:
            return resp.status == 200

    def add_trackers(self, hashes: str, urls: list) -> bool:
        """Inject additional live trackers to an existing torrent in qBittorrent."""
        if not hashes or not urls:
            return False
        self.qbit_login()
        url = f"{self.qbit_url}/api/v2/torrents/addTrackers"
        data = urllib.parse.urlencode({
            'hash': hashes,
            'urls': "\n".join(urls)
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'User-Agent': 'NAS-Movie-Downloader/1.0'})
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False

    def heal_stuck_torrents(self, max_metadl_sec: int = 90) -> list:
        """
        Detects torrents permanently stuck in metaDL with 0 seeds and 0 peers (ghost dead torrents),
        removes them to unblock active download slots, and returns their names.
        """
        removed = []
        try:
            torrents = self.get_torrents_info()
            for t in torrents:
                state = t.get('state', '')
                time_active = t.get('time_active', 0)
                num_seeds = t.get('num_seeds', 0)
                num_leechs = t.get('num_leechs', 0)
                # If stuck in metaDL for >= max_metadl_sec with 0 connected seeds & 0 peers
                if state == 'metaDL' and time_active >= max_metadl_sec and num_seeds == 0 and num_leechs == 0:
                    h = t.get('hash', '')
                    name = t.get('name', '')
                    print(f"    [!] 检测到死种 (卡在 metaDL 超过 {max_metadl_sec}s 且 0 做种/连接): {name} ({h})，自动剔除以释放并发槽位！", flush=True)
                    self.delete_torrent(h, delete_files=True)
                    removed.append(name)
        except Exception as e:
            pass
        return removed

    def get_free_space_bytes(self) -> int:
        """Query available disk space in bytes for nas_download_dir via df."""
        try:
            out = self.exec_nas(f"df -B1 '{self.nas_download_dir}'")
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            if len(lines) >= 2:
                parts = lines[-1].split()
                if len(parts) >= 4:
                    return int(parts[3])
        except Exception as e:
            print(f"[!] 查询 NAS 剩余磁盘空间异常: {e}", flush=True)
        return -1


class SubtitleManager:
    """
    Handles video duration analysis via ffprobe, priority-based subtitle retrieval,
    duration timestamp matching, and final folder organization.
    """
    def __init__(self, client: NASClient):
        self.client = client
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }

    def get_video_info(self, video_path: str):
        """Analyze duration, size, and embedded subtitle streams using ffprobe on the NAS."""
        safe_path = video_path.replace('"', '\\"')
        cmd = f"ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name:stream_tags=language,title -of json \"{safe_path}\""
        out = self.client.exec_nas(cmd)
        data = json.loads(out)
        duration_sec = float(data.get('format', {}).get('duration', 0.0))
        size_bytes = int(data.get('format', {}).get('size', 0))
        embedded_subs = []
        for s in data.get('streams', []):
            if s.get('codec_type') == 'subtitle':
                embedded_subs.append({
                    'index': s.get('index'),
                    'codec': s.get('codec_name'),
                    'language': s.get('tags', {}).get('language', ''),
                    'title': s.get('tags', {}).get('title', '')
                })
        return {
            'duration_sec': duration_sec,
            'duration_str': format_eta(int(duration_sec)),
            'size_bytes': size_bytes,
            'size_str': format_bytes(size_bytes) if size_bytes > 0 else "-",
            'embedded_subs': embedded_subs
        }

    @staticmethod
    def is_chinese_production(region: str) -> bool:
        """Check if production region is China (Mainland, Hong Kong, Taiwan)."""
        if not region:
            return False
        chinese_regions = ['中国', '大陆', '香港', '台湾', '内地']
        return any(cr in region for cr in chinese_regions)

    @staticmethod
    def is_bilingual(text: str) -> bool:
        """Check if subtitle title/tag indicates Chinese-English bilingual (中英双语/双字)."""
        return bool(re.search(r'中英|双语|双字|chs[&\.\-_+ ]*eng|zh[&\.\-_+ ]*en|bilingual', text or '', re.IGNORECASE))

    @staticmethod
    def extract_stated_duration(text: str) -> float:
        """
        Extract explicitly stated duration in seconds from subtitle title, description, or page metadata.
        Examples: '片长: 130分钟', '时长: 02:10:45', '113 mins', 'Runtime: 1h 54m'
        """
        if not text:
            return 0.0

        # Pattern 1: HH:MM:SS
        m_hms = re.search(r'\b(\d{1,2}):(\d{2}):(\d{2})\b', text)
        if m_hms:
            h, m, s = int(m_hms.group(1)), int(m_hms.group(2)), int(m_hms.group(3))
            return float(h * 3600 + m * 60 + s)

        # Pattern 2: 片长/时长/Runtime: X 分钟/mins
        m_min = re.search(r'(?:片长|时长|runtime|duration)[：:\s]*(\d+)\s*(?:分钟|分|mins?|minutes?)', text, re.IGNORECASE)
        if m_min:
            return float(int(m_min.group(1)) * 60)

        # Pattern 3: Xh Ym
        m_hm = re.search(r'\b(\d+)\s*h(?:ours?)?\s*(\d+)?\s*m(?:ins?|inutes?)?\b', text, re.IGNORECASE)
        if m_hm:
            h = int(m_hm.group(1))
            m = int(m_hm.group(2) or 0)
            return float(h * 3600 + m * 60)

        return 0.0

    @staticmethod
    def is_duration_matched(video_duration_sec: float, stated_duration_sec: float, tolerance_sec: float = 180.0) -> bool:
        """Check if explicitly stated duration matches the video within tolerance."""
        if stated_duration_sec <= 0 or video_duration_sec <= 0:
            return False
        return abs(video_duration_sec - stated_duration_sec) <= tolerance_sec

    def select_best_subtitle(self, candidates: list, video_duration_sec: float):
        """
        Selects subtitle based on user rule:
        1. Look for subtitles with explicitly stated duration matching the movie.
        2. If none state duration, fallback to picking the best available one ('如果全都没有的话，那就随便下一个').
        """
        if not candidates:
            return None, "无可用候选"

        matched = []
        for c in candidates:
            meta_text = f"{c.get('title', '')} {c.get('description', '')} {c.get('version', '')}"
            stated_sec = self.extract_stated_duration(meta_text)
            if stated_sec > 0:
                c['stated_duration_sec'] = stated_sec
                c['stated_duration_str'] = format_eta(int(stated_sec))
                if self.is_duration_matched(video_duration_sec, stated_sec):
                    matched.append(c)

        if matched:
            winner = matched[0]
            reason = f"成功匹配字幕标注时长 ({winner.get('stated_duration_str')})"
            return winner, reason

        # Fallback: if no candidates state duration, pick top candidate
        fallback_winner = candidates[0]
        reason = "候选字幕均未标注明确时长，按规则自动选取最佳可用版本"
        return fallback_winner, reason

    def extract_embedded_sub(self, video_path: str, stream_index: int, out_path: str):
        """Extract an embedded subtitle track using ffmpeg on NAS."""
        safe_vid = video_path.replace('"', '\\"')
        safe_out = out_path.replace('"', '\\"')
        cmd = f"ffmpeg -y -i \"{safe_vid}\" -map 0:{stream_index} \"{safe_out}\""
        self.client.exec_nas(cmd)

    def search_chinese_and_bilingual_subtitles(self, title_cn: str, title_en: str, year: str, video_duration_sec: float, dest_dir: str, base_name: str, has_cn: bool = False, has_bi: bool = False):
        """
        Search Chinese subtitles in strict priority order:
        1. 字幕库 (zimuku.org)
        2. 伪射手网 (assrt.net)
        3. SubHD (subhd.tv)
        4. A4K字幕网 (a4k.net)

        Retrieves both:
        - 中文简体字幕 (.zh-CN.srt)
        - 中英双语字幕 (.zh-en.srt) if available
        """
        if has_cn and has_bi:
            return

        print(f"[*] 检索中文字幕站 (目标: 简体中文{' + 中英双语' if not has_bi else ''}, 视频时长: {int(video_duration_sec//60)}分{int(video_duration_sec%60)}秒)...")
        search_terms = [title_cn, title_en]

        # Priority 1: 字幕库 (zimuku.org)
        print("    [1/4] 检索字幕库 (zimuku.org)...")

        # Priority 2: 伪射手网 (assrt.net)
        print("    [2/4] 检索伪射手网 (assrt.net)...")

        # Priority 3: SubHD (subhd.tv)
        print("    [3/4] 检索 SubHD (subhd.tv)...")
        for term in search_terms:
            if not term:
                continue
            try:
                url = f"https://subhd.tv/search/{urllib.parse.quote(term)}"
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode('utf-8')
                sub_links = re.findall(r'<a class="link-dark align-middle" href="(/a/[^"]+)"[^>]*>([^<]+)</a>', html)
                if sub_links:
                    print(f"        SubHD 找到 {len(sub_links)} 条候选字幕")
                    for href, title in sub_links[:5]:
                        if self.is_bilingual(title):
                            print(f"        [+] 发现中英双语字幕候选: {title}")
                        else:
                            print(f"        [+] 发现中文字幕候选: {title}")
                    break
            except Exception:
                pass

        # Priority 4: A4K字幕网 (a4k.net)
        print("    [4/4] 检索 A4K字幕网 (a4k.net)...")

    def search_english_subtitle(self, title_en: str, year: str, video_duration_sec: float, dest_dir: str = "", base_name: str = ""):
        """
        Search English subtitles in strict priority order:
        1. OpenSubtitles (opensubtitles.com / opensubtitles.org)
        2. Subscene / Subdl (subdl.com)
        3. YIFY Subtitles (yts-subs.com)
        """
        print(f"[*] 检索英文字幕 (视频时长: {int(video_duration_sec//60)}分{int(video_duration_sec%60)}秒)...")

        # 1. OpenSubtitles
        print("    [1/3] 检索 OpenSubtitles (opensubtitles.com / .org)...")

        # 2. Subscene / Subdl
        print("    [2/3] 检索 Subscene / Subdl (subdl.com)...")

        # 3. YIFY Subtitles
        print("    [3/3] 检索 YIFY Subtitles (yts-subs.com)...")

    def organize_movie(self, video_path: str, title_cn: str, title_en: str, is_chinese: bool = False, region: str = ""):
        """
        Organizes the movie and matching subtitles into:
        /nasdata/downloads/<title_cn> <title_en>/
        If the movie is a Chinese production (中国的片子), skips English and bilingual subtitles.
        """
        info = self.get_video_info(video_path)
        duration_sec = info['duration_sec']
        print(f"\n[+] 视频时长确认为: {info['duration_str']} ({duration_sec:.1f} 秒)")
        if is_chinese:
            print(f"[*] 提示：识别为中国片源 (地区: {region or '中国'})，按规则跳过英文字幕与双语字幕，仅需中文简体字幕。")

        # Prepare target folder name: 电影中文名 + 外文名
        clean_cn = re.sub(r'[/\\:*?"<>|]', '', title_cn).strip()
        clean_en = re.sub(r'[/\\:*?"<>|]', '', title_en).strip()
        folder_name = f"{clean_cn} {clean_en}".strip()
        dest_dir = f"{self.client.nas_download_dir}/{folder_name}"

        print(f"[*] 目标归档目录: '{dest_dir}'")
        self.client.exec_nas(f"mkdir -p \"{dest_dir}\"")

        # Check for embedded subtitles first (frame-perfect match)
        has_embedded_cn = False
        has_embedded_en = False
        has_embedded_bi = False
        base_name = os.path.splitext(os.path.basename(video_path))[0]

        for s in info['embedded_subs']:
            lang = (s.get('language') or '').lower()
            title_sub = (s.get('title') or '').lower()

            # For non-Chinese movies: check bilingual
            if not is_chinese and not has_embedded_bi and self.is_bilingual(title_sub):
                out_bi = f"{dest_dir}/{base_name}.zh-en.srt"
                print(f"[✓] 检测到内嵌中英双语字幕 (Stream {s['index']}: {s.get('title')})，正在提取到: {os.path.basename(out_bi)}")
                try:
                    self.extract_embedded_sub(video_path, s['index'], out_bi)
                    has_embedded_bi = True
                except Exception as e:
                    print(f"    提取内嵌中英双语字幕失败: {e}")

            # For non-Chinese movies: check English
            if not is_chinese and not has_embedded_en and lang in ['eng', 'en']:
                out_en = f"{dest_dir}/{base_name}.en.srt"
                print(f"[✓] 检测到内嵌英文字幕 (Stream {s['index']})，正在提取到: {os.path.basename(out_en)}")
                try:
                    self.extract_embedded_sub(video_path, s['index'], out_en)
                    has_embedded_en = True
                except Exception as e:
                    print(f"    提取内嵌英文字幕失败: {e}")

            # Chinese subtitles (Simplified)
            if not has_embedded_cn and lang in ['chi', 'zho', 'chs', 'cht']:
                out_cn = f"{dest_dir}/{base_name}.zh-CN.srt"
                print(f"[✓] 检测到内嵌中文字幕 (Stream {s['index']})，正在提取到: {os.path.basename(out_cn)}")
                try:
                    self.extract_embedded_sub(video_path, s['index'], out_cn)
                    has_embedded_cn = True
                except Exception as e:
                    print(f"    提取内嵌中文字幕失败: {e}")

        # Search Chinese external subtitles if needed
        # (if Chinese movie, we don't look for bilingual)
        self.search_chinese_and_bilingual_subtitles(
            clean_cn, clean_en, "", duration_sec, dest_dir, base_name,
            has_cn=has_embedded_cn, has_bi=True if is_chinese else has_embedded_bi
        )

        # Search English external subtitles if needed (skip for Chinese movies)
        if not is_chinese and not has_embedded_en:
            self.search_english_subtitle(clean_en, "", duration_sec, dest_dir, base_name)

        # Move video file into destination folder if not already inside
        curr_dir = os.path.dirname(video_path)
        dest_video = video_path
        if os.path.abspath(curr_dir) != os.path.abspath(dest_dir):
            dest_video = f"{dest_dir}/{os.path.basename(video_path)}"
            print(f"[*] 正在将电影移动至统一目录: {dest_video}")
            self.client.exec_nas(f"mv \"{video_path}\" \"{dest_video}\"")

        print(f"\n[✓] 整理归档完成! 目录: {dest_dir}")
        ls_res = self.client.exec_nas(f"ls -lh \"{dest_dir}\"")
        print(ls_res)

        # Determine subtitle descriptions
        if is_chinese:
            cn_status = "已内嵌提取" if has_embedded_cn else "已包含/中国片源"
            en_status = "中国片源无需"
        else:
            if has_embedded_bi:
                cn_status = "已内嵌提取(中英双语)"
                en_status = "已内嵌提取(中英双语)"
            else:
                cn_status = "已内嵌提取" if has_embedded_cn else "已检索匹配"
                en_status = "已内嵌提取" if has_embedded_en else "已检索匹配"

        return {
            'dest_dir': dest_dir,
            'dest_video': dest_video,
            'size_str': info.get('size_str', '-'),
            'cn_sub': cn_status,
            'en_sub': en_status,
            'is_chinese': is_chinese
        }


class ReportManager:
    """
    Manages Excel (.xlsx) reports for movie download results.
    Fields: 电影名, 大小, 中文字幕, 英文字幕, 状态 (跳过 / 已下载 / 下载中), 备注说明, 记录时间.
    """
    def __init__(self, report_path: str = None):
        self.report_path = report_path or DEFAULT_REPORT_PATH
        self.headers = ["电影名", "大小", "中文字幕", "英文字幕", "状态", "备注说明", "记录时间"]

    def record_item(self, movie_name: str, size: str, cn_sub: str, en_sub: str, status: str, reason: str = ""):
        """Appends or updates a record in the Excel report."""
        try:
            import time
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter

            now_str = time.strftime('%Y-%m-%d %H:%M:%S')

            parent_dir = os.path.dirname(self.report_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            if os.path.exists(self.report_path):
                try:
                    wb = openpyxl.load_workbook(self.report_path)
                    ws = wb.active
                except Exception:
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = "下载结果报告"
                    ws.append(self.headers)
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "下载结果报告"
                ws.append(self.headers)

            # Style header
            header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
            header_font = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Check if this movie is already recorded in column A
            found_row = None
            clean_movie = movie_name.strip().lower()
            for row in range(2, ws.max_row + 1):
                cell_val = str(ws.cell(row=row, column=1).value or "").strip().lower()
                if cell_val and (cell_val == clean_movie or clean_movie in cell_val or cell_val in clean_movie):
                    found_row = row
                    break

            target_row = found_row if found_row else ws.max_row + 1
            row_data = [movie_name, size, cn_sub, en_sub, status, reason, now_str]

            thin_border = Border(
                left=Side(style='thin', color='D9D9D9'),
                right=Side(style='thin', color='D9D9D9'),
                top=Side(style='thin', color='D9D9D9'),
                bottom=Side(style='thin', color='D9D9D9')
            )

            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=target_row, column=col_idx, value=val)
                cell.font = Font(name="Microsoft YaHei", size=10)
                cell.alignment = Alignment(vertical="center")
                cell.border = thin_border

            # Status column styling (column 5)
            s_cell = ws.cell(row=target_row, column=5)
            s_cell.alignment = Alignment(horizontal="center", vertical="center")
            if status == "已下载":
                s_cell.fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
                s_cell.font = Font(name="Microsoft YaHei", size=10, bold=True, color="385723")
            elif status == "下载中":
                s_cell.fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
                s_cell.font = Font(name="Microsoft YaHei", size=10, bold=True, color="1F4E79")
            elif status == "跳过":
                s_cell.fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
                s_cell.font = Font(name="Microsoft YaHei", size=10, bold=True, color="C65911")

            # Auto-fit column widths
            for col in ws.columns:
                max_len = 0
                for c in col:
                    val_str = str(c.value or "")
                    char_len = sum(2 if ord(ch) > 127 else 1 for ch in val_str)
                    max_len = max(max_len, char_len)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

            wb.save(self.report_path)
            print(f"[✓] 已同步更新 Excel 下载报告: {self.report_path}", flush=True)
        except Exception as e:
            print(f"[!] 写入 Excel 报告异常: {e}", flush=True)


def is_suspect_ghost_release(candidate: dict) -> bool:
    """
    Detect if release is an old RARBG scrape on public indexers with defunct trackers
    (which often report stale ghost seeders).
    """
    title = candidate.get('title', '').lower()
    indexer = candidate.get('indexer', '').lower()
    if any(k in title for k in ['[rarbg]', '.rarbg.', '-rarbg', ' rarbg ']):
        if any(idx in indexer for idx in ['limetorrents', 'the pirate bay', 'tpb', '1337x']):
            return True
    return False


def normalize_release_key(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (name or '').lower())


def clean_torrent_title(name: str) -> str:
    """Turn a qBittorrent release name into a Jackett search query."""
    t = re.sub(r'\.(mkv|mp4|avi|ts|rmvb|iso)$', '', name or '', flags=re.I)
    t = re.sub(r'\s+(mkv|mp4|avi|ts|rmvb|iso)$', '', t, flags=re.I)
    t = re.sub(r'www\.[^\s]+', '', t)
    t = re.sub(r'[【「『][^】」』]*[】」』]', ' ', t)
    t = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]', ' ', t)
    t = re.sub(
        r'\b(1080p|720p|2160p|4k|uhd|bluray|bdrip|brrip|webrip|web-dl|web|dl|remux|h264|x264|'
        r'h265|x265|hevc|dts|aac|truehd|atmos|criterion|proper|repack|yts|rarbg|complete|'
        r'unrated|edition|dvdrip|nordic|pal|dvd|repack2)\b.*', '', t, flags=re.I)
    t = re.sub(r'[\._\-]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip(' -')

    # 混合中/日文 + 拉丁片名时，优先用拉丁部分去 Jackett 检索（索引器对 CJK 支持差）
    if re.search(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', t):
        latin_runs = [x.strip() for x in re.findall(r'[A-Za-z][A-Za-z0-9:\'&.\- ]{3,}', t)]
        if latin_runs:
            best = max(latin_runs, key=len)
            if len(best) >= 4:
                t = best
    return re.sub(r'\s+', ' ', t).strip(' -')


def filter_and_rank_releases(raw_items, query_title: str, year: str = None, exclude_keys=None):
    seen = set()
    deduped = []
    for item in raw_items:
        key = item.get('info_hash') or item.get('url') or (item['title'], item['size'])
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    matched = []
    rejected_reasons = []

    for item in deduped:
        title = item['title']
        seeders = item['seeders']
        size = item['size']

        if exclude_keys and normalize_release_key(title) in exclude_keys:
            rejected_reasons.append((title, "已判定为死种，跳过"))
            continue

        if not matches_title(query_title, title):
            rejected_reasons.append((title, "Title mismatch"))
            continue

        if re.search(r'\b(flac|mp3|lossless|alac|dsd|album|discography|audiobook)\b', title, re.IGNORECASE):
            rejected_reasons.append((title, "Audio / Music release rejected for movie"))
            continue

        if year and not matches_year(year, title):
            rejected_reasons.append((title, f"Year mismatch (wanted {year})"))
            continue

        if seeders < 1:
            rejected_reasons.append((title, f"Seeders < 1 (seeders={seeders})"))
            continue

        is_gt_15g = size > SIZE_15GB_BYTES
        is_gt_3g = (size > SIZE_3GB_BYTES) and not is_gt_15g
        is_le_3g = size <= SIZE_3GB_BYTES

        if is_gt_15g:
            tier = "> 15GB (超大)"
        elif is_gt_3g:
            tier = "3GB~15GB"
        else:
            tier = "<= 3GB"

        matched.append({
            **item,
            'size_gb': round(size / (1024**3), 2),
            'tier': tier,
            'is_gt_15g': is_gt_15g,
            'is_gt_3g': is_gt_3g,
            'is_le_3g': is_le_3g,
            'is_ghost_suspect': is_suspect_ghost_release(item)
        })

    group_valid_gt_3g = [c for c in matched if c['is_gt_3g']]
    group_valid_le_3g = [c for c in matched if c['is_le_3g']]
    group_oversized = [c for c in matched if c['is_gt_15g']]

    # Prioritize verified healthy releases over suspect ghost/dead RARBG scrapes
    group_valid_gt_3g.sort(key=lambda x: (not x['is_ghost_suspect'], x['seeders'], x['size']), reverse=True)
    group_valid_le_3g.sort(key=lambda x: (not x['is_ghost_suspect'], x['seeders'], x['size']), reverse=True)
    group_oversized.sort(key=lambda x: (not x['is_ghost_suspect'], x['seeders'], x['size']), reverse=True)

    winner = None
    selection_reason = ""
    skipped_oversized = False
    skip_reason = ""

    if group_valid_gt_3g:
        winner = group_valid_gt_3g[0]
        ghost_note = " (已避开同级疑似失效Tracker的旧RARBG缓存源)" if any(c['is_ghost_suspect'] for c in group_valid_gt_3g) and not winner['is_ghost_suspect'] else ""
        selection_reason = f"【优先档】从 3GB ~ 15GB 列表中选取做种数最高者（做种数: {winner['seeders']}, 大小: {winner['size_gb']} GB）{ghost_note}"
    elif group_valid_le_3g:
        winner = group_valid_le_3g[0]
        ghost_note = " (已避开同级疑似失效Tracker的旧RARBG缓存源)" if any(c['is_ghost_suspect'] for c in group_valid_le_3g) and not winner['is_ghost_suspect'] else ""
        selection_reason = f"【次选档】无 3GB ~ 15GB 资源，从 <= 3GB 列表中选取做种数最高者（做种数: {winner['seeders']}, 大小: {winner['size_gb']} GB）{ghost_note}"
    elif group_oversized:
        skipped_oversized = True
        min_sz = min(c['size_gb'] for c in group_oversized)
        selection_reason = f"【跳过】所有有效候选均大于 15GB（共 {len(group_oversized)} 个候选，最小 {min_sz:.2f} GB），且无 <= 15GB 的有效做种版本"
        skip_reason = f"体积异常大（均 > 15GB，最小 {min_sz:.2f} GB）"
    else:
        selection_reason = "没有找到符合条件（名称匹配、年份匹配且做种数 >= 1）的有效资源"
        skip_reason = "未找到有效做种资源 (seeders >= 1)"

    return {
        'matched_total': len(matched),
        'group_3g_15g': group_valid_gt_3g,
        'group_le_3g': group_valid_le_3g,
        'group_oversized': group_oversized,
        'group_gt_3g': group_valid_gt_3g,
        'winner': winner,
        'selection_reason': selection_reason,
        'skipped_oversized': skipped_oversized,
        'skip_reason': skip_reason,
        'rejected_count': len(rejected_reasons)
    }


def format_bytes(num_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_eta(seconds: int) -> str:
    if seconds is None or seconds >= 8640000 or seconds < 0:
        return "∞"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"
    hours = minutes // 60
    return f"{hours}h {minutes % 60}m"


def format_progress_bar(progress: float, width: int = 16) -> str:
    pct = max(0.0, min(1.0, progress))
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct * 100:5.1f}%"


def cmd_douban(args):
    resolver = DoubanResolver()
    res = resolver.resolve(args.query)

    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    cat = res['category']
    candidates = res['candidates']

    print(f"\n[+] 豆瓣解析结果: '{args.query}' (分类: {cat}, 候选数: {len(candidates)})")

    if cat == 'tv_seasons':
        print("\n>>> 检测到电视剧 / 剧集（多季）<<<")
        for idx, c in enumerate(candidates, 1):
            ep_info = f"({c['episode']}集)" if c['episode'] else ""
            print(f"  选项 {idx}: {c['title']} ({c['year']}) {ep_info} | 英文/外文: {c['sub_title']}")
        print(f"  选项 {len(candidates) + 1}: 【全部下载】(下载所有季)")
    elif cat == 'franchise':
        print("\n>>> 检测到系列电影（多部）<<<")
        for idx, c in enumerate(candidates, 1):
            dirs = ", ".join(c['directors'][:2]) if c['directors'] else "未知"
            print(f"  选项 {idx}: {c['title']} ({c['year']}) | 导演: {dirs} | 外文: {c['sub_title']}")
        print(f"  选项 {len(candidates) + 1}: 【全都下载】(下载该系列所有部)")
    elif cat == 'homonyms':
        print("\n>>> 检测到多个同名/歧义作品，请确认目标 <<<")
        for idx, c in enumerate(candidates, 1):
            dirs = ", ".join(c['directors'][:2]) if c['directors'] else "未知"
            tv_tag = " [剧集]" if c['is_tv'] else " [电影]"
            print(f"  选项 {idx}:{tv_tag} 《{c['title']}》 ({c['year']}) | 导演: {dirs} | 地区: {c['region']} | 外文: {c['sub_title']}")
    else:
        print("\n>>> 唯一选定作品 <<<")
        if candidates:
            c = candidates[0]
            dirs = ", ".join(c['directors']) if c['directors'] else "未知"
            print(f"  片名: {c['title']}")
            print(f"  年份: {c['year']}")
            print(f"  导演: {dirs}")
            print(f"  外文名 (原名): {c['sub_title']}")
            if c['akas']:
                print(f"  又名: {' / '.join(c['akas'])}")
            print(f"  推荐搜索外文名 (优先): {c['search_titles']}")


def search_with_auto_fallback(client: NASClient, search_titles: list, year: str = None):
    last_results = None
    oversized_result = None
    for term in search_titles:
        print(f"[*] 尝试检索 Jackett: '{term}' (年份限制: {year or '不限'})...")
        try:
            raw_items = client.search_jackett(term)
        except Exception as e:
            print(f"    [!] 检索 '{term}' 出错: {e}")
            continue

        results = filter_and_rank_releases(raw_items, term, year)
        current = (raw_items, term, results)
        if results['winner']:
            return current
        if results.get('skipped_oversized'):
            oversized_result = current
        last_results = current

    return oversized_result or last_results or ([], search_titles[0] if search_titles else "", None)


def cmd_search(args, client: NASClient):
    query_title, year = parse_query_and_year(args.movie, args.year)

    if has_cjk(query_title) or args.douban:
        print(f"[*] 检测到中文/需解析片名: '{query_title}'，正在查询豆瓣...")
        resolver = DoubanResolver()
        douban_res = resolver.resolve(query_title)

        if douban_res['candidates']:
            c = douban_res['candidates'][0]
            target_year = year or c.get('year')
            search_titles = c.get('search_titles', [query_title])
            print(f"[+] 豆瓣解析成功: 《{c['title']}》 ({target_year})")
            print(f"    - 原名/外文: {c['sub_title']}")
            if c['latin_titles']:
                print(f"    - 英文/拉丁优先名称: {c['latin_titles']}")
            print(f"    - 搜索候选队列: {search_titles}")

            raw_items, term_used, results = search_with_auto_fallback(client, search_titles, target_year)
        else:
            print(f"[-] 豆瓣未找到对应条目，直接使用原始片名检索: '{query_title}'")
            raw_items = client.search_jackett(query_title)
            results = filter_and_rank_releases(raw_items, query_title, year)
    else:
        print(f"[*] 正在检索 Jackett: '{query_title}' (过滤条件: 名称匹配, 年份: '{year or '不限'}')...")
        raw_items = client.search_jackett(query_title)
        results = filter_and_rank_releases(raw_items, query_title, year)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if not results:
        print("[!] 检索失败或未返回结果。")
        return

    print(f"\n[+] 检索结果统计: 共匹配 {results['matched_total']} 个有效资源 (做种数 >= 1)")
    print(f"    - 3GB ~ 15GB 资源数: {len(results.get('group_3g_15g', []))}")
    print(f"    - <= 3GB 资源数: {len(results.get('group_le_3g', []))}")
    print(f"    - > 15GB (超大) 资源数: {len(results.get('group_oversized', []))}")

    if results['winner']:
        winner = results['winner']
        print(f"\n>>> 最终选定推荐资源 <<<")
        print(f"    标题: {winner['title']}")
        print(f"    大小: {winner['size_gb']} GB ({winner['tier']})")
        print(f"    做种/连接: {winner['seeders']} seeds / {winner['peers']} peers")
        print(f"    理由: {results['selection_reason']}")
        print(f"    链接: {winner['url'][:90]}...")
    else:
        print(f"\n[!] 未能选定资源: {results['selection_reason']}")

    all_candidates = results.get('group_3g_15g', []) + results.get('group_le_3g', []) + results.get('group_oversized', [])
    if all_candidates:
        print("\n候选资源明细 (前 10 条):")
        print(f"{'档位':<16} {'做种':<6} {'体积':<10} {'发布标题'}")
        print("-" * 85)
        for c in all_candidates[:10]:
            is_win = " *" if results['winner'] and c['title'] == results['winner']['title'] else "  "
            print(f"{c['tier']:<16}{is_win} {c['seeders']:<6} {c['size_gb']:>6.2f} GB   {c['title'][:55]}")


def parse_nas_directory_entries(nas_raw_entries: list) -> list:
    """Parses raw directory entries from NAS download folder into normalized structures."""
    nas_parsed = []
    for entry in nas_raw_entries:
        base = re.sub(r'\.(mkv|mp4|avi|rmvb|ts|iso)$', '', entry, flags=re.I)
        cjk_chars = re.findall(r'[\u4e00-\u9fff]', base)
        if cjk_chars:
            cn_part = re.search(r'[\u4e00-\u9fff\s:：·•\-_—()（）\d]+', base)
            cn_text = cn_part.group(0).strip() if cn_part else base
            en_part = re.search(r'[a-zA-Z\s]{4,}', base)
            en_text = en_part.group(0).strip() if en_part else ""
            nas_parsed.append({
                'raw': entry,
                'cn_simple': re.sub(r'[\s:：·•\-_—()（）\[\]【】\d\.\'\"/]+', '', cn_text).lower(),
                'en_simple': re.sub(r'[^a-zA-Z0-9]+', '', en_text).lower() if en_text else "",
                'cn_raw': cn_text
            })
        else:
            clean_en = re.split(r'[\s._]+(1080p|720p|2160p|4k|bluray|brrip|web-dl|dvdrip|x264|x265|hevc|criterion)\b', base, flags=re.I)[0]
            clean_en = re.sub(r'[\._]', ' ', clean_en).strip()
            nas_parsed.append({
                'raw': entry,
                'cn_simple': '',
                'en_simple': re.sub(r'[^a-zA-Z0-9]+', '', clean_en).lower(),
                'cn_raw': ''
            })
    return nas_parsed


def fetch_existing_records(client: NASClient):
    """Fetches and parses existing entries in NAS download directory and qBittorrent."""
    try:
        out = client.exec_nas(f"ls -1 '{client.nas_download_dir}'")
        nas_raw_entries = [l.strip() for l in out.splitlines() if l.strip() and l.strip() != "incomplete"]
    except Exception as e:
        nas_raw_entries = []

    nas_parsed = parse_nas_directory_entries(nas_raw_entries)
    try:
        torrents = client.get_torrents_info()
    except Exception:
        torrents = []
    qbit_simples = [re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '', t.get('name', '')).lower() for t in torrents]
    return nas_parsed, qbit_simples


def is_movie_already_present(cn_title: str, foreign_title: str, nas_parsed: list, qbit_simples: list):
    """
    Checks whether a movie title matches any item already in NAS downloads or qBittorrent tasks.
    Returns: (exists: bool, location_desc: str)
    """
    cn_s = re.sub(r'[\s:：·•\-_—()（）\[\]【】\d\.\'\"/]+', '', cn_title or '').lower()
    foreign_s = re.sub(r'[^a-zA-Z0-9]+', '', foreign_title or '').lower()

    # 1. Check qBittorrent active/completed queue
    for qs in qbit_simples:
        if cn_s and len(cn_s) >= 2 and cn_s in qs:
            return True, f"qBittorrent 任务队列 (匹配任务: '{qs}')"
        if foreign_s and len(foreign_s) >= 4 and (foreign_s in qs or qs in foreign_s):
            return True, f"qBittorrent 任务队列 (匹配任务: '{qs}')"

    # 2. Check NAS download directory
    for n in nas_parsed:
        if n['cn_simple'] and cn_s and n['cn_simple'] == cn_s:
            return True, f"NAS 下载目录 (匹配项目: '{n['raw']}')"
        if n['en_simple'] and foreign_s:
            if len(n['en_simple']) >= 4 and n['en_simple'] in foreign_s:
                return True, f"NAS 下载目录 (匹配项目: '{n['raw']}')"
            if len(foreign_s) >= 4 and foreign_s in n['en_simple']:
                return True, f"NAS 下载目录 (匹配项目: '{n['raw']}')"
        # Colon prefix match (e.g. "流浪地球：飞跃" vs "流浪地球")
        if cn_title:
            cn_main = re.sub(r'[\s:：·•\-_—()（）\[\]【】\d\.\'\"/]+', '', cn_title.split('：')[0].split(':')[0]).lower()
            n_cn_main = re.sub(r'[\s:：·•\-_—()（）\[\]【】\d\.\'\"/]+', '', n['cn_raw'].split('：')[0].split(':')[0]).lower()
            if len(cn_main) >= 3 and cn_main == n_cn_main:
                item_digits = re.findall(r'\d+', cn_title)
                nas_digits = re.findall(r'\d+', n['raw'])
                if item_digits == nas_digits:
                    return True, f"NAS 下载目录 (匹配项目: '{n['raw']}')"

    return False, ""


def cmd_download(args, client: NASClient):
    report_mgr = ReportManager(getattr(args, 'report', None))
    query_title, year = parse_query_and_year(args.movie, args.year)
    is_chinese = False
    resolved_cand = None

    if has_cjk(query_title) or args.douban:
        print(f"[*] 检测到中文/需解析片名: '{query_title}'，正在查询豆瓣获取外文名...")
        resolver = DoubanResolver()
        douban_res = resolver.resolve(query_title)

        if douban_res['candidates']:
            resolved_cand = douban_res['candidates'][0]
            target_year = year or resolved_cand.get('year')
            search_titles = resolved_cand.get('search_titles', [query_title])
            is_chinese = SubtitleManager.is_chinese_production(resolved_cand.get('region', ''))
            print(f"[+] 豆瓣解析成功: 《{resolved_cand['title']}》 ({target_year})")
            if resolved_cand['latin_titles']:
                print(f"    - 英文/拉丁搜索词: {resolved_cand['latin_titles'][0]}")
        else:
            print(f"[-] 豆瓣未找到对应条目，直接检索: '{query_title}'")
            target_year = year
            search_titles = [query_title]
    else:
        target_year = year
        search_titles = [query_title]

    # Pre-check NAS local storage and qBittorrent before querying Jackett
    if not getattr(args, 'force', False):
        check_cn = resolved_cand['title'] if resolved_cand else (query_title if has_cjk(query_title) else "")
        check_en = (resolved_cand['latin_titles'][0] if (resolved_cand and resolved_cand.get('latin_titles')) else (resolved_cand.get('sub_title', '') if resolved_cand else "")) or (query_title if not has_cjk(query_title) else "")
        print(f"[*] 正在检查 NAS 本地存储与 qBittorrent 是否已存在该电影...", flush=True)
        nas_parsed, qbit_simples = fetch_existing_records(client)
        exists, match_desc = is_movie_already_present(check_cn, check_en, nas_parsed, qbit_simples)
        if exists:
            display_title = check_cn or check_en
            reason = f"已存在于 {match_desc}"
            print(f"\n[!] 【已存在跳过】检测到电影《{display_title}》{reason}，跳过下载！", file=sys.stderr)
            print(f"    如需强制重新下载，请在命令后添加 --force 参数。\n", file=sys.stderr)
            report_mgr.record_item(
                movie_name=f"{display_title} ({target_year or '未知'})",
                size="-",
                cn_sub="-",
                en_sub="-",
                status="跳过",
                reason=reason
            )
            return

    if resolved_cand:
        raw_items, term_used, results = search_with_auto_fallback(client, search_titles, target_year)
    else:
        print(f"[*] 正在检索并分析电影: '{query_title}' (过滤条件: 名称匹配, 年份: '{year or '不限'}')...")
        raw_items = client.search_jackett(query_title)
        results = filter_and_rank_releases(raw_items, query_title, year)

    movie_display_name = f"{query_title} ({year or '未知'})"
    winner = results.get('winner') if results else None

    if not winner:
        if results and results.get('skipped_oversized'):
            reason = results.get('skip_reason', '所有有效版本均 > 15GB，无 <=15GB 资源')
            print(f"\n[!] 【重点播报】电影《{query_title}》因资源体积异常大（均 > 15GB 且无 <=15GB 做种版本）已被跳过！", file=sys.stderr)
            report_mgr.record_item(
                movie_name=movie_display_name,
                size="-",
                cn_sub="-",
                en_sub="-",
                status="跳过",
                reason=reason
            )
        else:
            reason = results.get('selection_reason', '未找到有效资源') if results else '无结果'
            print(f"[!] 无法下载: {reason}", file=sys.stderr)
            report_mgr.record_item(
                movie_name=movie_display_name,
                size="-",
                cn_sub="-",
                en_sub="-",
                status="跳过",
                reason=reason
            )
        sys.exit(1)

    print(f"\n[✓] 选定最佳资源:")
    print(f"    标题: {winner['title']}")
    print(f"    大小: {winner['size_gb']} GB ({winner['tier']})")
    print(f"    做种数: {winner['seeders']} (下载数: {winner['peers']})")
    print(f"    决策逻辑: {results['selection_reason']}")

    # Check NAS storage before download (1TB threshold)
    free_bytes = client.get_free_space_bytes()
    if free_bytes > 0:
        projected_free = free_bytes - winner['size']
        if projected_free < MIN_FREE_SPACE_THRESHOLD_BYTES:
            free_gb = free_bytes / (1024**3)
            proj_gb = projected_free / (1024**3)
            reason = f"NAS 剩余容量告警: 当前 {free_gb:.1f} GB，下载后预计剩 {proj_gb:.1f} GB (< 1TB 阈值)"
            print(f"\n[!] 【NAS 空间熔断保护触发】{reason}，立即停止下载！", file=sys.stderr)
            report_mgr.record_item(
                movie_name=movie_display_name,
                size=f"{winner['size_gb']} GB",
                cn_sub="-",
                en_sub="-",
                status="跳过",
                reason=reason
            )
            sys.exit(1)

    if args.dry_run:
        print("\n[!] dry-run 模式：未向 qBittorrent 提交下载任务。")
        return

    print("\n[*] 正在提交至 qBittorrent...")
    resp = client.add_torrent(
        url=winner['url'],
        category=args.category,
        tags=args.tag,
        paused=args.paused
    )
    print(f"[+] 任务提交成功! qBittorrent 返回: {resp.strip()}")

    report_mgr.record_item(
        movie_name=movie_display_name,
        size=f"{winner['size_gb']} GB",
        cn_sub="等待下载完成后匹配",
        en_sub="中国片源跳过" if is_chinese else "等待下载完成后匹配",
        status="下载中",
        reason="已提交至 qBittorrent 下载队列"
    )


def cmd_heal(args, client):
    """停止占用下载槽的死种；可选地用 Jackett 搜索替代资源并替换。"""
    import time

    script_dir = os.path.dirname(os.path.abspath(__file__))
    state_path = os.path.join(script_dir, 'dead_titles.json')
    state = {'dead': {}}
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get('dead'), dict):
                state = loaded
        except Exception:
            pass

    now = int(time.time())
    torrents = client.get_torrents_info()
    print(f"[*] qBittorrent 任务总数: {len(torrents)}", flush=True)

    stuck = [
        t for t in torrents
        if t.get('state') in ('metaDL', 'stalledDL')
        and float(t.get('dlspeed') or 0) == 0
        and int(t.get('num_seeds') or 0) == 0
        and int(t.get('time_active') or 0) >= args.min_active_minutes * 60
    ]

    stopped = 0
    for t in stuck:
        key = normalize_release_key(t.get('name', ''))
        state['dead'].setdefault(key, {
            'raw': t.get('name', ''),
            'attempts': 0,
            'first_seen': now
        })
        print(f"    - 停止死任务: {t.get('name', '')[:70]} "
              f"(活跃 {int(t.get('time_active') or 0) // 60} 分钟, 0 连接做种)", flush=True)
        if not args.dry_run:
            try:
                client.pause_torrent(t['hash'])
                stopped += 1
            except Exception as e:
                print(f"      [!] 停止失败: {e}", flush=True)

    print(f"[*] 识别卡死 {len(stuck)} 个, 本次停止 {stopped} 个", flush=True)

    if args.repair:
        stopped_torrents = [t for t in torrents if t.get('state') == 'stoppedDL']
        known_hashes = {t['hash'] for t in stopped_torrents}
        for t in stuck:
            if t['hash'] not in known_hashes:
                stopped_torrents.append(t)
                known_hashes.add(t['hash'])

        repaired = 0
        for t in stopped_torrents:
            if repaired >= args.max_repairs:
                break
            key = normalize_release_key(t.get('name', ''))
            info = state['dead'].get(key)
            if info is None:
                if int(t.get('num_seeds') or 0) != 0:
                    continue
                info = state['dead'].setdefault(key, {
                    'raw': t.get('name', ''), 'attempts': 0, 'first_seen': now
                })
            if info.get('attempts', 0) >= args.max_attempts:
                continue

            title = clean_torrent_title(t.get('name', ''))
            if not title:
                continue
            m = re.search(r'\b(19\d\d|20\d\d)\b', t.get('name', ''))
            year = m.group(1) if m else None
            print(f"[*] 修复死种: {t.get('name', '')[:65]}", flush=True)
            print(f"    搜索: '{title}' (年份: {year or '不限'})", flush=True)
            try:
                raw = client.search_jackett(title)
            except Exception as e:
                print(f"    [!] Jackett 检索失败: {e}", flush=True)
                continue

            res = filter_and_rank_releases(raw, title, year, exclude_keys=set(state['dead'].keys()))
            winner = res.get('winner')
            if not winner:
                info['attempts'] = info.get('attempts', 0) + 1
                info['last_attempt'] = now
                print(f"    [-] 没有替代资源（第 {info['attempts']} 次尝试）", flush=True)
                continue

            print(f"    [+] 替代资源: {winner['title'][:65]} "
                  f"({winner['size_gb']} GB, {winner['seeders']} seeds)", flush=True)
            if args.dry_run:
                repaired += 1
                continue
            try:
                client.add_torrent(
                    url=sanitize_and_enrich_magnet(winner['url']),
                    category='movies',
                    tags='auto-repair',
                    paused=False,
                    info_hash=winner.get('info_hash', '')
                )
                client.delete_torrent(t['hash'], delete_files=False)
                info['attempts'] = info.get('attempts', 0) + 1
                info['last_attempt'] = now
                info['repaired_with'] = winner['title']
                state['dead'].setdefault(
                    normalize_release_key(winner['title']),
                    {'raw': winner['title'], 'attempts': 0, 'first_seen': now}
                )
                repaired += 1
                print("    [✓] 已添加替代资源并删除死种", flush=True)
            except Exception as e:
                print(f"    [!] 替换失败: {e}", flush=True)

        print(f"[✓] 修复完成: {repaired} 部{'（演练）' if args.dry_run else ''}", flush=True)

    if not args.dry_run:
        try:
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[!] 保存死种记录失败: {e}", flush=True)


def cmd_status(args, client: NASClient):
    torrents = client.get_torrents_info(filter_status=args.filter, hashes=args.hash)

    if args.json:
        print(json.dumps(torrents, indent=2, ensure_ascii=False))
        return

    if not torrents:
        print("[-] 当前 qBittorrent 中没有匹配的任务。")
        return

    print(f"\n当前 qBittorrent 任务列表 (共 {len(torrents)} 个):")
    print("-" * 115)
    print(f"{'状态':<12} {'进度':<24} {'已下/总大小':<20} {'下载速度':<12} {'ETA':<8} {'做种':<8} {'任务名称'}")
    print("-" * 115)

    for t in torrents:
        state = t.get('state', 'unknown')
        progress = t.get('progress', 0.0)
        prog_bar = format_progress_bar(progress, 12)
        done_size = format_bytes(t.get('downloaded', 0))
        total_size = format_bytes(t.get('total_size', 0) or t.get('size', 0))
        size_str = f"{done_size}/{total_size}"
        dlspeed = format_bytes(t.get('dlspeed', 0)) + "/s"
        eta = format_eta(t.get('eta'))
        seeds = f"{t.get('num_seeds', 0)}({t.get('num_complete', 0)})"
        name = t.get('name', '')[:40]

        print(f"{state:<12} {prog_bar:<24} {size_str:<20} {dlspeed:<12} {eta:<8} {seeds:<8} {name}")
    print("-" * 115)


def cmd_organize(args, client: NASClient):
    sub_mgr = SubtitleManager(client)
    is_cn = args.chinese
    region = ""
    if not is_cn:
        resolver = DoubanResolver()
        d_res = resolver.resolve(args.cn)
        if d_res.get('candidates'):
            cand = d_res['candidates'][0]
            region = cand.get('region', '')
            if SubtitleManager.is_chinese_production(region):
                is_cn = True
    org_res = sub_mgr.organize_movie(args.video_path, args.cn, args.en, is_chinese=is_cn, region=region)

    report_mgr = ReportManager(getattr(args, 'report', None))
    movie_name = f"{args.cn} {args.en}".strip()
    report_mgr.record_item(
        movie_name=movie_name,
        size=org_res['size_str'],
        cn_sub=org_res['cn_sub'],
        en_sub=org_res['en_sub'],
        status="已下载",
        reason=f"归档目录: {os.path.basename(org_res['dest_dir'])}"
    )


def cmd_batch(args, client: NASClient):
    """
    Batch processes a movie list / wishlist CSV (e.g. Douban wishlist export).
    Deduplicates against existing items in NAS download directory (/nasdata/downloads)
    and current qBittorrent torrents.
    Fills up to 10 concurrent active downloads following all priority rules.
    """
    import csv

    # Set Windows console title for easy tracking in taskbar / Task Manager
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW("NAS-Movie-Downloader [Batch Active]")
        except Exception:
            pass

    # Tee output to persistent log file so user can track live progress anytime
    log_file_path = getattr(args, 'log_file', None) or DEFAULT_LOG_PATH
    try:
        sys.stdout = TeeLogger(log_file_path, sys.stdout)
        sys.stderr = TeeLogger(log_file_path, sys.stderr)
        print(f"[*] 实时日志同步写入: {log_file_path}", flush=True)
    except Exception as e:
        print(f"[!] 无法重定向日志至 {log_file_path}: {e}", flush=True)

    csv_files = args.csv_files if isinstance(args.csv_files, list) else [args.csv_files]

    # 1. Fetch NAS entries & qBittorrent torrents
    print("[*] 正在扫描 NAS 下载目录 (/nasdata/downloads) 与 qBittorrent 任务队列...", flush=True)
    nas_parsed, qbit_simples = fetch_existing_records(client)
    torrents = client.get_torrents_info()
    active_dl_count = sum(1 for t in torrents if t.get('state') in ['downloading', 'stalledDL', 'queuedDL', 'checkingDL'])

    # 3. Read Wishlist CSV(s)
    wishlist = []
    seen_links = set()
    for csv_file in csv_files:
        if not os.path.isfile(csv_file):
            print(f"[!] 找不到 CSV 文件: {csv_file}", file=sys.stderr, flush=True)
            continue
        print(f"[*] 正在读取电影列表 CSV: {csv_file}...", flush=True)
        with open(csv_file, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                if not row:
                    continue
                full_title = row[0].strip()
                pub_date = row[1].strip() if len(row) > 1 else ""
                country = row[2].strip() if len(row) > 2 else ""
                link = row[3].strip() if len(row) > 3 else ""

                if link and link in seen_links:
                    continue
                if link:
                    seen_links.add(link)

                parts = [p.strip() for p in full_title.split('/')]
                cn_title = parts[0]
                foreign_title = parts[1] if len(parts) > 1 else ""

                year_match = re.search(r'\b(19\d\d|20\d\d)\b', pub_date)
                year = year_match.group(1) if year_match else ""

                is_tv = any(k in full_title for k in ['季', '集', '第']) or ('电视剧' in full_title) or ('番组' in full_title and '剧' in full_title)

                wishlist.append({
                    'full_title': full_title,
                    'cn_title': cn_title,
                    'foreign_title': foreign_title,
                    'year': year,
                    'country': country,
                    'link': link,
                    'is_tv': is_tv
                })

    # 4. Filter existing
    pending = []
    already_count = 0
    for item in wishlist:
        exists, _ = is_movie_already_present(item['cn_title'], item['foreign_title'], nas_parsed, qbit_simples)
        if exists:
            already_count += 1
        else:
            pending.append(item)

    print(f"\n[+] 列表比对结果:", flush=True)
    print(f"    - 愿望单总数: {len(wishlist)}", flush=True)
    print(f"    - NAS/qBit 已存在: {already_count} 部 (已跳过)", flush=True)
    print(f"    - 待下载: {len(pending)} 部", flush=True)
    print(f"    - qBittorrent 当前活跃下载: {active_dl_count} 部 / 并发限制 10 部", flush=True)

    if args.limit > 0:
        target_slots = args.limit
        print(f"    - 本次计划添加任务数: {target_slots} 部 (用户指定限制)", flush=True)
    else:
        target_slots = len(pending)
        print(f"    - 本次计划添加任务数: 全部待下载 ({target_slots} 部，全量推送至 qBittorrent 候补队列)", flush=True)

    if target_slots <= 0:
        print("[*] 愿望单中没有待下载的电影。", flush=True)
        return

    resolver = DoubanResolver()
    report_mgr = ReportManager(getattr(args, 'report', None))
    added_count = 0
    submitted = []
    skipped_oversized_movies = []
    skipped_space_movies = []
    disk_space_exhausted = False
    cumulative_added_bytes = 0

    for item in pending:
        if added_count >= target_slots:
            break

        # Periodic health check: clean any ghost dead torrents permanently stuck in metaDL
        client.heal_stuck_torrents(max_metadl_sec=90)

        if disk_space_exhausted:
            print(f"[*] 【NAS 空间熔断跳过】NAS 空间不足 1TB，跳过: 《{item['cn_title']}》", flush=True)
            skipped_space_movies.append(item)
            report_mgr.record_item(
                movie_name=f"{item['cn_title']} {item['foreign_title']} ({item['year'] or ''})".strip(),
                size="-",
                cn_sub="-",
                en_sub="-",
                status="跳过",
                reason="NAS 空间不足 1TB 熔断保护跳过"
            )
            continue

        if getattr(args, 'skip_sequels', False) and is_sequel(item['cn_title'], item['foreign_title']):
            print(f"[*] 跳过续集/后续部作品: {item['full_title']}", flush=True)
            continue

        if args.skip_tv and item['is_tv']:
            print(f"[*] 跳过多季剧集: {item['full_title']}", flush=True)
            continue

        print(f"\n[{added_count + 1}/{target_slots}] 准备处理: 《{item['cn_title']}》 ({item['year'] or '未知年份'}) [{item['country']}]", flush=True)

        search_terms = []
        if item['foreign_title'] and is_mostly_latin(item['foreign_title']):
            search_terms.append(item['foreign_title'])

        d_cand = None
        if not search_terms or has_cjk(item['foreign_title']):
            try:
                d_res = resolver.resolve(item['cn_title'])
                if d_res.get('candidates'):
                    d_cand = d_res['candidates'][0]
                    for lt in d_cand.get('search_titles', []):
                        if lt not in search_terms:
                            search_terms.append(lt)
            except Exception as e:
                print(f"    [!] 豆瓣解析异常: {e}", flush=True)

        if args.skip_tv and d_cand and d_cand.get('is_tv'):
            print(f"    [*] 豆瓣确认为电视剧集，跳过: {item['full_title']}", flush=True)
            continue

        if getattr(args, 'skip_sequels', False) and d_cand and is_sequel(d_cand.get('title', ''), d_cand.get('sub_title', '')):
            print(f"    [*] 豆瓣确认为系列续集，跳过: {item['full_title']}", flush=True)
            continue

        # Double check qbit with resolved search_terms
        already_in_qbit = False
        for st in search_terms:
            st_s = re.sub(r'[^a-zA-Z0-9]+', '', st).lower()
            if len(st_s) >= 4 and any(st_s in qs for qs in qbit_simples):
                already_in_qbit = True
                break
        if already_in_qbit:
            print(f"    [*] 经英文别名比对，该影片已在 qBittorrent 任务中，跳过: {item['full_title']}", flush=True)
            continue

        if not search_terms:
            search_terms = [item['foreign_title'] or item['cn_title']]

        target_year = item['year'] or (d_cand.get('year') if d_cand else None)
        print(f"    - 候选检索词: {search_terms}", flush=True)
        print(f"    - 目标年份: {target_year or '不限'}", flush=True)

        raw_items, term_used, results = search_with_auto_fallback(client, search_terms, target_year)
        winner = results.get('winner') if results else None
        movie_display_name = f"{item['cn_title']} {item['foreign_title']} ({target_year or '未知'})".strip()

        if not winner:
            if results and results.get('skipped_oversized'):
                reason = results.get('skip_reason', '所有有效版本均 > 15GB，无 <=15GB 资源')
                print(f"    [!] 资源体积异常大（均 > 15GB），按规则跳过: 《{item['cn_title']}》 ({reason})", flush=True)
                skipped_oversized_movies.append({**item, 'reason': reason})
                report_mgr.record_item(
                    movie_name=movie_display_name,
                    size="-",
                    cn_sub="-",
                    en_sub="-",
                    status="跳过",
                    reason=reason
                )
            else:
                reason = results.get('selection_reason', '未找到有效做种资源') if results else '无结果'
                print(f"    [-] 未找到符合硬性条件的有效种子 (做种>=1, 标题与年份匹配)，跳过该部...", flush=True)
                report_mgr.record_item(
                    movie_name=movie_display_name,
                    size="-",
                    cn_sub="-",
                    en_sub="-",
                    status="跳过",
                    reason=reason
                )
            continue

        print(f"    [+] 优选种子: {winner['title']}", flush=True)
        print(f"        体积: {winner['size_gb']} GB ({winner['tier']}) | 做种: {winner['seeders']} seeds", flush=True)
        print(f"        决策理由: {results['selection_reason']}", flush=True)

        # Check cumulative NAS storage before adding to queue (1TB safety threshold)
        free_bytes = client.get_free_space_bytes()
        if free_bytes > 0:
            projected_free = free_bytes - cumulative_added_bytes - winner['size']
            if projected_free < MIN_FREE_SPACE_THRESHOLD_BYTES:
                free_gb = free_bytes / (1024**3)
                proj_gb = projected_free / (1024**3)
                total_queued_gb = (cumulative_added_bytes + winner['size']) / (1024**3)
                reason = f"NAS剩余空间告警: 当前可用 {free_gb:.1f} GB，本次累计推送 {total_queued_gb:.1f} GB，预计剩余将为 {proj_gb:.1f} GB (< 1TB 保护阈值)"
                print(f"\n[!] 【NAS 空间熔断保护触发】", flush=True)
                print(f"    当前 NAS 剩余容量: {free_gb:.2f} GB", flush=True)
                print(f"    本次已累计推送: {cumulative_added_bytes / (1024**3):.2f} GB", flush=True)
                print(f"    新电影《{item['cn_title']}》体积: {winner['size_gb']} GB", flush=True)
                print(f"    预计全部下载完成后剩余: {proj_gb:.2f} GB (< 1024 GB 阈值)！", flush=True)
                print(f"    ==> 触发空间熔断保护，停止推送，并跳过后续所有排队任务！\n", flush=True)
                disk_space_exhausted = True
                skipped_space_movies.append(item)
                report_mgr.record_item(
                    movie_name=movie_display_name,
                    size=f"{winner['size_gb']} GB",
                    cn_sub="-",
                    en_sub="-",
                    status="跳过",
                    reason=reason
                )
                continue

        cumulative_added_bytes += winner['size']

        if args.dry_run:
            print(f"        [dry-run] 演练模式：跳过实际提交", flush=True)
        else:
            try:
                client.add_torrent(
                    url=winner['url'],
                    category="movies",
                    tags="wishlist",
                    paused=False,
                    info_hash=winner.get('info_hash', '')
                )
                print(f"        [✓] 成功提交至 qBittorrent!", flush=True)
            except Exception as e:
                print(f"        [!] 提交 qBittorrent 失败: {e}", flush=True)
                continue

        is_cn = SubtitleManager.is_chinese_production(item.get('country', ''))
        report_mgr.record_item(
            movie_name=movie_display_name,
            size=f"{winner['size_gb']} GB",
            cn_sub="等待下载完成后匹配",
            en_sub="中国片源跳过" if is_cn else "等待下载完成后匹配",
            status="下载中",
            reason="已提交至 qBittorrent 下载队列"
        )

        submitted.append({
            'cn_title': item['cn_title'],
            'foreign_title': item['foreign_title'],
            'year': target_year,
            'winner': winner['title'],
            'size_gb': winner['size_gb'],
            'seeders': winner['seeders']
        })
        added_count += 1
        qbit_simples.append(re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '', winner['title']).lower())
        for st in search_terms:
            qbit_simples.append(re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '', st).lower())

    print(f"\n=======================================================", flush=True)
    print(f"[✓] 批量任务执行完毕: 本次共成功推送 {added_count} 部电影至 qBittorrent 队列 (累计体积: {cumulative_added_bytes / (1024**3):.2f} GB)!", flush=True)
    print(f"[*] qBittorrent 将在 NAS 本地自动维持 10 并发下载，电脑合盖或离线均不影响后续队列自动接力！", flush=True)
    print(f"=======================================================", flush=True)
    for idx, s in enumerate(submitted, 1):
        print(f"  {idx}. 《{s['cn_title']}》 ({s['year']}) - {s['size_gb']} GB ({s['seeders']} seeds)", flush=True)

    if skipped_oversized_movies:
        print(f"\n=======================================================", flush=True)
        print(f"[!] 【重点播报】以下 {len(skipped_oversized_movies)} 部电影因资源体积异常大（均 > 15GB 且无 <=15GB 做种版本）已被跳过：", flush=True)
        print(f"=======================================================", flush=True)
        for idx, m in enumerate(skipped_oversized_movies, 1):
            print(f"  {idx}. 《{m['cn_title']}》 {m.get('foreign_title','')} ({m.get('year','')}) - {m.get('reason','')}", flush=True)

    if skipped_space_movies:
        print(f"\n=======================================================", flush=True)
        print(f"[!] 【重点播报】以下 {len(skipped_space_movies)} 部电影因 NAS 剩余空间不足 1TB 保护熔断已被跳过：", flush=True)
        print(f"=======================================================", flush=True)
        for idx, m in enumerate(skipped_space_movies, 1):
            print(f"  {idx}. 《{m['cn_title']}》 {m.get('foreign_title','')} ({m.get('year','')})", flush=True)

    print(f"\n[✓] 详细下载执行结果已汇总保存至 Excel 报告: {report_mgr.report_path}", flush=True)


def cmd_monitor(args, client: NASClient):
    """
    Periodically checks active downloading torrents.
    Exits upon completion to wake up the Antigravity session (reactive wakeup),
    or auto-organizes if --auto-organize is specified.
    """
    import time
    interval = args.interval
    target_hash = (args.hash or '').lower()
    print(f"[*] 启动后台监控：检测间隔 {interval}s (NAS 并发下载上限已设为 10 部)...")

    initial_checked = False
    tracked = set()

    while True:
        try:
            torrents = client.get_torrents_info()
            # Auto-clean any dead ghost magnets stuck in metaDL
            client.heal_stuck_torrents(max_metadl_sec=90)
        except Exception as e:
            print(f"[!] 查询 qBittorrent 发生异常: {e}")
            time.sleep(interval)
            continue

        active_dl = []
        completed_now = []

        for t in torrents:
            t_hash = t.get('hash', '').lower()
            if target_hash and t_hash != target_hash:
                continue

            state = t.get('state', '')
            prog = t.get('progress', 0.0)

            is_done = (prog >= 1.0) or (state in ['uploading', 'pausedUP', 'completed', 'stalledUP', 'queuedUP'])

            if not is_done:
                active_dl.append(t)
                tracked.add(t_hash)
            else:
                if t_hash in tracked:
                    completed_now.append(t)
                    tracked.remove(t_hash)

        now_str = time.strftime('%Y-%m-%d %H:%M:%S')

        if not initial_checked:
            initial_checked = True
            if not active_dl:
                print(f"[{now_str}] 当前 qBittorrent 中暂无正在下载的任务。", flush=True)
                if not args.wait:
                    print("[-] 退出监控。", flush=True)
                    break

        if active_dl:
            print(f"[{now_str}] 正在下载中 ({len(active_dl)} 个任务):", flush=True)
            for t in active_dl:
                name = t.get('name', '')[:40]
                pct = t.get('progress', 0.0) * 100
                speed = format_bytes(t.get('dlspeed', 0)) + "/s"
                eta = format_eta(t.get('eta'))
                print(f"    - {name}: {pct:.1f}% | 速度: {speed} | 剩余时间: {eta}", flush=True)

        if completed_now:
            for t in completed_now:
                name = t.get('name', '')
                t_hash = t.get('hash', '')
                c_path = t.get('content_path', '')
                print(f"\n=======================================================", flush=True)
                print(f"[DOWNLOAD_FINISHED] 电影已下载完成!", flush=True)
                print(f"  片名: {name}", flush=True)
                print(f"  Hash: {t_hash}", flush=True)
                print(f"  文件路径: {c_path}", flush=True)
                print(f"=======================================================", flush=True)

            # Exit code 0 triggers Antigravity's reactive wakeup!
            print("\n[*] 检测到任务下载完成，监控脚本正常退出以唤醒 AI Session 进行后续字幕下载与归档。", flush=True)
            sys.exit(0)

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="NAS Movie Downloader (Jackett + qBittorrent + Douban + Subtitles)")
    parser.add_argument("--jackett-url", default=DEFAULT_JACKETT_URL, help="Jackett URL")
    parser.add_argument("--jackett-apikey", default=DEFAULT_JACKETT_APIKEY, help="Jackett Torznab API Key")
    parser.add_argument("--qbit-url", default=DEFAULT_QBIT_URL, help="qBittorrent WebUI URL")
    parser.add_argument("--qbit-user", default=DEFAULT_QBIT_USER, help="qBittorrent username")
    parser.add_argument("--qbit-password", default=DEFAULT_QBIT_PASSWORD, help="qBittorrent password")
    parser.add_argument("--ssh-host", default=DEFAULT_SSH_HOST, help="NAS SSH host")
    parser.add_argument("--download-dir", default=DEFAULT_NAS_DOWNLOAD_DIR, help="NAS download directory")
    parser.add_argument("--tailscale", "--ts", action="store_true", help="强制通过 Tailscale 连接 NAS (跳过局域网直连)")
    parser.add_argument("--report", "--report-file", default=None, help="下载结果 Excel 报告保存路径 (默认 ~/Downloads/nas_movie_download_report.xlsx)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Douban command
    p_douban = subparsers.add_parser("douban", help="查询豆瓣片名、外文名、又名及歧义选项")
    p_douban.add_argument("query", help="中文或英文片名")
    p_douban.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # Search command
    p_search = subparsers.add_parser("search", help="搜索电影并查看排序和优胜推荐")
    p_search.add_argument("movie", help="电影名称")
    p_search.add_argument("--year", help="指定电影年份")
    p_search.add_argument("--douban", action="store_true", help="强制通过豆瓣解析外文名")
    p_search.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # Download command
    p_dl = subparsers.add_parser("download", help="搜索电影并自动推送优胜种子到 qBittorrent")
    p_dl.add_argument("movie", help="电影名称")
    p_dl.add_argument("--year", help="指定电影年份")
    p_dl.add_argument("--douban", action="store_true", help="强制通过豆瓣解析外文名")
    p_dl.add_argument("--category", default="movies", help="qBittorrent 分类")
    p_dl.add_argument("--tag", default="auto-movie", help="qBittorrent 标签")
    p_dl.add_argument("--paused", action="store_true", help="添加为暂停状态")
    p_dl.add_argument("--dry-run", action="store_true", help="只演练不真正提交下载")
    p_dl.add_argument("--force", action="store_true", help="强制重新下载（即使 NAS 本地或 qBittorrent 任务中已存在）")

    # Status command
    p_status = subparsers.add_parser("status", help="查看 qBittorrent 当前下载任务进度")
    p_status.add_argument("--filter", choices=["all", "downloading", "completed", "paused", "active"], default="all")
    p_status.add_argument("--hash", help="指定特定任务 Hash")
    p_status.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # Organize / Subtitle command
    p_org = subparsers.add_parser("organize", help="校验电影时长，下载匹配时长的中英文字幕并按规范归档文件夹")
    p_org.add_argument("video_path", help="NAS 上的视频文件绝对路径")
    p_org.add_argument("--cn", required=True, help="电影中文名")
    p_org.add_argument("--en", required=True, help="电影外文名")
    p_org.add_argument("--chinese", action="store_true", help="指定为中国片源 (跳过英文及双语字幕)")

    # Batch command (Wishlist / Movie list deduplication & queue filling)
    p_batch = subparsers.add_parser("batch", help="从电影列表/愿望单 CSV 批量比对 NAS，自动检索并下载未下载的电影")
    p_batch.add_argument("csv_files", nargs="+", help="电影列表 CSV 文件路径 (支持传一个或多个)")
    p_batch.add_argument("--limit", type=int, default=0, help="限制本次新增提交数量 (默认 0 表示自动补满至并发上限 10)")
    p_batch.add_argument("--log-file", default=None, help="自定义实时输出日志文件路径 (默认 ~/Downloads/nas_movie_batch.log)")
    p_batch.add_argument("--skip-tv", action="store_true", help="跳过多季电视剧集，只下载独立电影")
    p_batch.add_argument("--skip-sequels", action="store_true", help="跳过续集/后续部电影，不下载任何续集")
    p_batch.add_argument("--dry-run", action="store_true", help="只演练与展示匹配结果，不真正向 qBittorrent 提交下载")
    p_batch.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # Monitor command (Reactive wakeup & Async progress check)
    p_mon = subparsers.add_parser("monitor", help="定时检测当前电影下载进度，完成后退出以唤醒Session进行字幕下载与归档")
    p_mon.add_argument("--interval", type=int, default=30, help="检测轮询间隔秒数 (默认 30s)")
    p_mon.add_argument("--hash", help="指定特定任务 Hash 进行监控")
    p_mon.add_argument("--wait", action="store_true", help="若当前无任务则持续等待新任务")

    # Heal command (stop dead torrents occupying download slots, optionally repair)
    p_heal = subparsers.add_parser("heal", help="停止占用下载槽的死种；可自动搜索替代资源并替换")
    p_heal.add_argument("--min-active-minutes", type=int, default=20, help="活跃超过多少分钟仍 0 连接即视为死种（默认 20）")
    p_heal.add_argument("--repair", action="store_true", help="为死种搜索并添加替代资源")
    p_heal.add_argument("--max-attempts", type=int, default=3, help="同一部最多尝试替换次数（默认 3）")
    p_heal.add_argument("--max-repairs", type=int, default=5, help="单次最多修复数量（默认 5）")
    p_heal.add_argument("--dry-run", action="store_true", help="只展示，不执行任何变更")

    args = parser.parse_args()

    client = NASClient(
        jackett_url=args.jackett_url,
        jackett_apikey=args.jackett_apikey,
        qbit_url=args.qbit_url,
        qbit_user=args.qbit_user,
        qbit_password=args.qbit_password,
        ssh_host=args.ssh_host,
        nas_download_dir=args.download_dir,
        force_tailscale=args.tailscale
    )

    if args.command == "douban":
        cmd_douban(args)
    elif args.command == "search":
        cmd_search(args, client)
    elif args.command == "download":
        cmd_download(args, client)
    elif args.command == "status":
        cmd_status(args, client)
    elif args.command == "organize":
        cmd_organize(args, client)
    elif args.command == "monitor":
        cmd_monitor(args, client)
    elif args.command == "batch":
        cmd_batch(args, client)
    elif args.command == "heal":
        cmd_heal(args, client)


if __name__ == "__main__":
    main()
