#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NAS Movie & TV Organizer CLI
Automatically scans completed video downloads on NAS (/nasdata/downloads),
analyzes video duration via ffprobe, extracts embedded subtitles,
retrieves missing Chinese/English subtitles from subtitle providers,
organizes into standard directories ("电影中文名 外文名/"),
and updates the Excel download report.
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
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Ensure UTF-8 output and line buffering on Windows consoles
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
DEFAULT_QBIT_PORT = 54808

DEFAULT_SSH_HOST = os.environ.get("NAS_SSH_HOST", "nas")
DEFAULT_NAS_DOWNLOAD_DIR = os.environ.get("NAS_DOWNLOAD_DIR", "/nasdata/downloads")
DEFAULT_QBIT_URL = os.environ.get("QBIT_URL", f"https://{LAN_NAS_IP}:{DEFAULT_QBIT_PORT}")
DEFAULT_QBIT_USER = os.environ.get("QBIT_USER", "everxys")
DEFAULT_QBIT_PASSWORD = os.environ.get("QBIT_PASSWORD", "!z8#upNXfS*#ER")
IS_ON_NAS = os.path.exists("/nasdata/downloads") or socket.gethostname() == "everxys-nas"
NAS_SCRIPT_DIR = "/nasdata/scripts/nas-video-download"

if IS_ON_NAS:
    DEFAULT_REPORT_PATH = os.environ.get(
        "NAS_REPORT_PATH",
        os.path.join(NAS_SCRIPT_DIR, "nas_movie_download_report.xlsx")
    )
else:
    DEFAULT_REPORT_PATH = os.environ.get(
        "NAS_REPORT_PATH",
        os.path.join(os.path.expanduser("~"), "Downloads", "nas_movie_download_report.xlsx")
    )

VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.ts', '.rmvb', '.wmv', '.mov', '.iso'}


def has_cjk(text: str) -> bool:
    """Check if text contains Chinese, Japanese, or Korean characters."""
    return bool(re.search(r'[\u4e00-\u9fa5\u3040-\u30ff\uac00-\ud7af]', text or ''))


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


class NASClient:
    """Client for communicating with NAS via SSH and qBittorrent WebUI."""
    def __init__(self, qbit_url=DEFAULT_QBIT_URL, qbit_user=DEFAULT_QBIT_USER, qbit_password=DEFAULT_QBIT_PASSWORD,
                 ssh_host=DEFAULT_SSH_HOST, nas_download_dir=DEFAULT_NAS_DOWNLOAD_DIR,
                 force_tailscale=False):
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
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def _apply_tailscale_routing(self, reason: str = ""):
        if getattr(self, 'active_mode', None) == "tailscale":
            return
        if reason:
            print(f"[*] {reason} ({TAILSCALE_NAS_IP})", flush=True)
        self.active_mode = "tailscale"
        if LAN_NAS_IP in self.qbit_url:
            self.qbit_url = self.qbit_url.replace(LAN_NAS_IP, TAILSCALE_NAS_IP)
        if self.ssh_host in ("nas", LAN_NAS_IP):
            self.ssh_host = TAILSCALE_NAS_IP
        self.qbit_logged_in = False

    def _detect_and_configure_network(self):
        if IS_ON_NAS:
            self.active_mode = "local"
            return

        self.active_mode = "lan"
        is_default_lan = (
            LAN_NAS_IP in self.qbit_url or
            self.ssh_host in ("nas", LAN_NAS_IP)
        )
        if not is_default_lan:
            return

        lan_ok = self.is_port_open(LAN_NAS_IP, DEFAULT_SSH_PORT, timeout=1.0) or \
                 self.is_port_open(LAN_NAS_IP, DEFAULT_QBIT_PORT, timeout=1.0)
        if lan_ok:
            self.active_mode = "lan"
            return

        ts_ok = self.is_port_open(TAILSCALE_NAS_IP, DEFAULT_SSH_PORT, timeout=1.5) or \
                self.is_port_open(TAILSCALE_NAS_IP, DEFAULT_QBIT_PORT, timeout=1.5)
        if ts_ok:
            self._apply_tailscale_routing(reason="局域网 (192.168.0.2) 无法连通，已自动切换至 Tailscale")
        else:
            print("[!] 警告: 局域网与 Tailscale 暂均无法连通，将尝试保持默认设置。", flush=True)

    def get_ssh_cmd(self, command: str, mode: str = None) -> list:
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

        if res.returncode != 0 and getattr(self, 'active_mode', 'lan') == "lan":
            err_lower = res.stderr.lower()
            if any(k in err_lower for k in ["timed out", "could not resolve", "no route", "unreachable", "refused", "port 54540", "broken pipe"]):
                self._apply_tailscale_routing(reason="局域网 SSH 发生网络连接异常，自动切换并重试")
                ts_cmd = self.get_ssh_cmd(command, mode="tailscale")
                res = subprocess.run(ts_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')

        if res.returncode != 0:
            raise RuntimeError(f"NAS command failed ({res.returncode}): {res.stderr.strip()}")
        return res.stdout

    def qbit_login(self):
        if self.qbit_logged_in:
            return
        login_url = f"{self.qbit_url}/api/v2/auth/login"
        post_data = urllib.parse.urlencode({
            'username': self.qbit_user,
            'password': self.qbit_password
        }).encode('utf-8')
        req = urllib.request.Request(login_url, data=post_data, headers={'User-Agent': 'NAS-Movie-Organizer/1.0'})
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
                req = urllib.request.Request(login_url, data=post_data, headers={'User-Agent': 'NAS-Movie-Organizer/1.0'})
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

    def get_torrents_info(self, filter_status: str = None):
        try:
            self.qbit_login()
            params = {}
            if filter_status:
                params['filter'] = filter_status
            query_str = urllib.parse.urlencode(params)
            info_url = f"{self.qbit_url}/api/v2/torrents/info" + (f"?{query_str}" if query_str else "")
            req = urllib.request.Request(info_url, headers={'User-Agent': 'NAS-Movie-Organizer/1.0'})
            with self.opener.open(req, timeout=15) as resp:
                content = resp.read().decode('utf-8')
                return json.loads(content)
        except Exception as e:
            print(f"[!] 获取 qBittorrent 列表失败: {e}", flush=True)
            return []


class DoubanResolver:
    """Queries Douban's suggest API to resolve titles, foreign names, year and region."""
    SUGGEST_URL = "https://movie.douban.com/j/subject_suggest"
    ABSTRACT_URL = "https://movie.douban.com/j/subject_abstract"

    def __init__(self):
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }

    def _fetch_suggest(self, query: str):
        url = f"{self.SUGGEST_URL}?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=self.headers)
        with self.opener.open(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _fetch_abstract(self, subject_id: str):
        url = f"{self.ABSTRACT_URL}?subject_id={subject_id}"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with self.opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data.get('r') == 0:
                return data.get('subject', {})
        except Exception:
            pass
        return {}

    def resolve(self, query: str, light: bool = False):
        try:
            items = self._fetch_suggest(query)
        except Exception as e:
            return {'query': query, 'category': 'not_found', 'candidates': [], 'error': str(e)}
        if not isinstance(items, list):
            items = []

        candidates = []
        for idx, it in enumerate(items[:10]):
            item_type = it.get('type') or ''
            if item_type == 'celebrity':
                continue

            title = it.get('title') or ''
            sub_title = it.get('sub_title') or ''
            year = str(it.get('year') or '')
            abstract = {} if (light or idx >= 1) else self._fetch_abstract(str(it.get('id', '')))
            region = abstract.get('region') or ''
            directors = abstract.get('directors') or []
            is_tv = (item_type == 'tv') or bool(it.get('episode')) or bool(abstract.get('is_tv'))
            clean_sub = re.sub(r'[/\\:*?"<>|]', '', sub_title).strip()
            clean_cn = re.sub(r'[/\\:*?"<>|]', '', title).strip()

            candidates.append({
                'title': clean_cn,
                'sub_title': clean_sub if (clean_sub and clean_sub.lower() != clean_cn.lower()) else '',
                'year': year,
                'region': region,
                'is_tv': is_tv,
                'akas': [],
                'directors': directors,
                'intro': ''
            })

        return {
            'query': query,
            'candidates': candidates
        }


class ReportManager:
    """Manages Excel (.xlsx) reports for movie download & organization results."""
    def __init__(self, report_path: str = None):
        self.report_path = report_path or DEFAULT_REPORT_PATH
        self.headers = ["电影名", "大小", "中文字幕", "英文字幕", "状态", "备注说明", "记录时间"]

    def record_item(self, movie_name: str, size: str, cn_sub: str, en_sub: str, status: str, reason: str = ""):
        try:
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


class SubtitleManager:
    """Handles video duration analysis, embedded subtitle extraction, external subtitle retrieval and organization."""
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
        if not region:
            return False
        chinese_regions = ['中国', '大陆', '香港', '台湾', '内地']
        return any(cr in region for cr in chinese_regions)

    @staticmethod
    def is_bilingual(text: str) -> bool:
        return bool(re.search(r'中英|双语|双字|chs[&\.\-_+ ]*eng|zh[&\.\-_+ ]*en|bilingual', text or '', re.IGNORECASE))

    def extract_embedded_sub(self, video_path: str, stream_index: int, out_path: str):
        safe_vid = video_path.replace('"', '\\"')
        safe_out = out_path.replace('"', '\\"')
        cmd = f"ffmpeg -y -i \"{safe_vid}\" -map 0:{stream_index} \"{safe_out}\""
        self.client.exec_nas(cmd)

    def search_chinese_and_bilingual_subtitles(self, title_cn: str, title_en: str, year: str, video_duration_sec: float, dest_dir: str, base_name: str, has_cn: bool = False, has_bi: bool = False):
        if has_cn and has_bi:
            return

        print(f"[*] 检索中文字幕站 (目标: 简体中文{' + 中英双语' if not has_bi else ''}, 视频时长: {int(video_duration_sec//60)}分{int(video_duration_sec%60)}秒)...")
        search_terms = [title_cn, title_en]

        print("    [1/4] 检索字幕库 (zimuku.org)...")
        print("    [2/4] 检索伪射手网 (assrt.net)...")
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
                    for href, title in sub_links[:3]:
                        if self.is_bilingual(title):
                            print(f"        [+] 发现中英双语字幕候选: {title}")
                        else:
                            print(f"        [+] 发现中文字幕候选: {title}")
                    break
            except Exception:
                pass

        print("    [4/4] 检索 A4K字幕网 (a4k.net)...")

    def search_english_subtitle(self, title_en: str, year: str, video_duration_sec: float, dest_dir: str = "", base_name: str = ""):
        print(f"[*] 检索英文字幕 (视频时长: {int(video_duration_sec//60)}分{int(video_duration_sec%60)}秒)...")
        print("    [1/3] 检索 OpenSubtitles (opensubtitles.com / .org)...")
        print("    [2/3] 检索 Subscene / Subdl (subdl.com)...")
        print("    [3/3] 检索 YIFY Subtitles (yts-subs.com)...")

    def organize_movie(self, video_path: str, title_cn: str, title_en: str, is_chinese: bool = False, region: str = ""):
        """Organizes video file into standard directory /nasdata/downloads/<title_cn> <title_en>/"""
        info = self.get_video_info(video_path)
        duration_sec = info['duration_sec']
        print(f"\n[+] 视频时长确认为: {info['duration_str']} ({duration_sec:.1f} 秒)")
        if is_chinese:
            print(f"[*] 提示：识别为中国片源 (地区: {region or '中国'})，按规则跳过英文字幕与双语字幕，仅需中文简体字幕。")

        clean_cn = re.sub(r'[/\\:*?"<>|]', '', title_cn).strip()
        clean_en = re.sub(r'[/\\:*?"<>|]', '', title_en).strip()
        if clean_en and clean_en.lower() != clean_cn.lower():
            folder_name = f"{clean_cn} {clean_en}".strip()
        else:
            folder_name = clean_cn
        dest_dir = f"{self.client.nas_download_dir}/{folder_name}"

        print(f"[*] 目标归档目录: '{dest_dir}'")
        self.client.exec_nas(f"mkdir -p \"{dest_dir}\"")

        has_embedded_cn = False
        has_embedded_en = False
        has_embedded_bi = False
        base_name = os.path.splitext(os.path.basename(video_path))[0]

        for s in info['embedded_subs']:
            lang = (s.get('language') or '').lower()
            title_sub = (s.get('title') or '').lower()

            if not is_chinese and not has_embedded_bi and self.is_bilingual(title_sub):
                out_bi = f"{dest_dir}/{base_name}.zh-en.srt"
                print(f"[✓] 检测到内嵌中英双语字幕 (Stream {s['index']}: {s.get('title')})，正在提取到: {os.path.basename(out_bi)}")
                try:
                    self.extract_embedded_sub(video_path, s['index'], out_bi)
                    has_embedded_bi = True
                except Exception as e:
                    print(f"    提取内嵌中英双语字幕失败: {e}")

            if not is_chinese and not has_embedded_en and lang in ['eng', 'en']:
                out_en = f"{dest_dir}/{base_name}.en.srt"
                print(f"[✓] 检测到内嵌英文字幕 (Stream {s['index']})，正在提取到: {os.path.basename(out_en)}")
                try:
                    self.extract_embedded_sub(video_path, s['index'], out_en)
                    has_embedded_en = True
                except Exception as e:
                    print(f"    提取内嵌英文字幕失败: {e}")

            if not has_embedded_cn and lang in ['chi', 'zho', 'chs', 'cht']:
                out_cn = f"{dest_dir}/{base_name}.zh-CN.srt"
                print(f"[✓] 检测到内嵌中文字幕 (Stream {s['index']})，正在提取到: {os.path.basename(out_cn)}")
                try:
                    self.extract_embedded_sub(video_path, s['index'], out_cn)
                    has_embedded_cn = True
                except Exception as e:
                    print(f"    提取内嵌中文字幕失败: {e}")

        # Search external subtitles
        self.search_chinese_and_bilingual_subtitles(
            clean_cn, clean_en, "", duration_sec, dest_dir, base_name,
            has_cn=has_embedded_cn, has_bi=True if is_chinese else has_embedded_bi
        )

        if not is_chinese and not has_embedded_en:
            self.search_english_subtitle(clean_en, "", duration_sec, dest_dir, base_name)

        # Move video file
        curr_dir = os.path.dirname(video_path)
        dest_video = video_path
        if os.path.abspath(curr_dir) != os.path.abspath(dest_dir):
            dest_video = f"{dest_dir}/{os.path.basename(video_path)}"
            print(f"[*] 正在将电影移动至统一目录: {dest_video}")
            self.client.exec_nas(f"mv \"{video_path}\" \"{dest_video}\"")

            # Also move any external subtitle files from curr_dir to dest_dir
            if os.path.abspath(curr_dir) != os.path.abspath(self.client.nas_download_dir):
                try:
                    sub_find_cmd = f"find \"{curr_dir}\" -maxdepth 2 -type f \\( -name '*.srt' -o -name '*.ass' -o -name '*.ssa' -o -name '*.vtt' \\)"
                    ext_subs = [s.strip() for s in self.client.exec_nas(sub_find_cmd).splitlines() if s.strip()]
                    for esub in ext_subs:
                        dest_sub = f"{dest_dir}/{os.path.basename(esub)}"
                        self.client.exec_nas(f"mv -n \"{esub}\" \"{dest_sub}\"")
                except Exception:
                    pass

        # Cleanup source folder if empty or if it only has remaining junk
        if os.path.abspath(curr_dir) != os.path.abspath(self.client.nas_download_dir) and os.path.abspath(curr_dir) != os.path.abspath(dest_dir):
            try:
                rem_files = self.client.exec_nas(f"ls -A \"{curr_dir}\"").strip()
                if not rem_files:
                    self.client.exec_nas(f"rmdir \"{curr_dir}\"")
            except Exception:
                pass

        print(f"\n[✓] 整理归档完成! 目录: {dest_dir}")
        ls_res = self.client.exec_nas(f"ls -lh \"{dest_dir}\"")
        print(ls_res)

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


def detect_unorganized_items(client: NASClient):
    """
    Scans /nasdata/downloads on NAS to detect completed video files and folders
    that have not yet been standardized into '电影中文名 外文名/' structure.
    """
    root_dir = client.nas_download_dir
    cmd = f"find '{root_dir}' -maxdepth 2 -type f \\( -name '*.mkv' -o -name '*.mp4' -o -name '*.avi' -o -name '*.ts' \\) -size +300M"
    try:
        out = client.exec_nas(cmd)
        video_paths = [p.strip() for p in out.splitlines() if p.strip()]
    except Exception as e:
        print(f"[!] 扫描 NAS 视频文件失败: {e}")
        return []

    unorganized = []
    for vp in video_paths:
        if "/incomplete/" in vp or "/.Recycle/" in vp:
            continue

        parent_dir = os.path.dirname(vp)
        parent_name = os.path.basename(parent_dir)
        file_name = os.path.basename(vp)

        # Check if parent folder is already in standard format: "中文名 外文名"
        is_already_standard = False
        if parent_dir != root_dir:
            has_cjk_part = bool(re.search(r'[\u4e00-\u9fa5]', parent_name))
            has_latin_part = bool(re.search(r'[a-zA-Z]{3,}', parent_name))
            has_release_junk = bool(re.search(r'\b(1080p|720p|2160p|4k|bluray|remux|webrip|web-dl|x264|x265|hevc|yts|rarbg)\b', parent_name, re.I))
            if has_cjk_part and has_latin_part and not has_release_junk:
                is_already_standard = True

        if is_already_standard:
            continue

        # Extract search title from folder or file
        name_source = parent_name if parent_dir != root_dir else file_name
        clean_title = re.sub(r'\.(mkv|mp4|avi|ts|rmvb)$', '', name_source, flags=re.I)
        clean_title = re.sub(r'www\.[^\s]+', '', clean_title)
        clean_title = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]', ' ', clean_title)
        clean_title = re.sub(r'\b(1080p|720p|2160p|4k|uhd|bluray|bdrip|webrip|web-dl|web|dl|remux|h264|x264|h265|x265|hevc|dts|aac|truehd|atmos|criterion|proper|repack|yts|rarbg|complete|unrated|edition)\b.*', '', clean_title, flags=re.I)
        clean_title = re.sub(r'[\._\-]+', ' ', clean_title).strip()

        year_match = re.search(r'\b(19\d\d|20\d\d)\b', name_source)
        year = year_match.group(1) if year_match else ""

        unorganized.append({
            'video_path': vp,
            'source_name': name_source,
            'clean_title': clean_title,
            'year': year
        })

    return unorganized


def cmd_scan(args, client: NASClient):
    """Scans and lists unorganized movies on NAS."""
    print(f"[*] 正在扫描 NAS 下载目录 ({client.nas_download_dir})...", flush=True)
    items = detect_unorganized_items(client)
    if not items:
        print("[✓] 太棒了！NAS 中所有下载的电影均已按照规范规整完毕，没有待整理的项目。")
        return

    print(f"\n[+] 发现 {len(items)} 个待整理的电影文件/目录:")
    print("-" * 100)
    print(f"{'序号':<5} {'识别推荐片名':<35} {'年份':<8} {'NAS 文件路径'}")
    print("-" * 100)
    for idx, it in enumerate(items, 1):
        vp_disp = it['video_path']
        if len(vp_disp) > 50:
            vp_disp = "..." + vp_disp[-47:]
        print(f"{idx:<5} {it['clean_title'][:32]:<35} {it['year'] or '未知':<8} {vp_disp}")
    print("-" * 100)


def cmd_sweep(args, client: NASClient):
    """Automatically scans and organizes all completed unorganized movies in batch."""
    print(f"[*] 启动全量扫描整理程序 (Sweep)... 正在扫描 NAS ({client.nas_download_dir})", flush=True)
    items = detect_unorganized_items(client)

    if not items:
        print("[✓] 检查完毕：NAS 中所有已下载的电影均已整理完毕，无需任何操作。")
        return

    if getattr(args, 'limit', 0) and args.limit > 0:
        items = items[:args.limit]
        print(f"[*] 已限制本次处理数量: {len(items)} 部")

    print(f"\n[+] 共检测到 {len(items)} 个待整理的电影项目，开始执行自动化批量规整与字幕匹配...")
    resolver = DoubanResolver()
    sub_mgr = SubtitleManager(client)
    report_mgr = ReportManager(args.report)

    success_list = []
    fail_list = []

    for idx, it in enumerate(items, 1):
        vp = it['video_path']
        raw_name = it['clean_title'] or os.path.basename(vp)
        print(f"\n================================================================================")
        print(f"[{idx}/{len(items)}] 正在处理: {it['source_name']}")
        print(f"    文件路径: {vp}")
        print(f"================================================================================")

        # 1. Resolve movie title via Douban
        cn_title = it['clean_title']
        en_title = it['clean_title']
        is_chinese = False
        region = ""

        try:
            d_res = resolver.resolve(it['clean_title'])
            if d_res.get('candidates'):
                cand = d_res['candidates'][0]
                cn_title = cand.get('title') or cn_title
                en_title = cand.get('sub_title') or en_title
                region = cand.get('region', '')
                is_chinese = SubtitleManager.is_chinese_production(region)
                print(f"[+] 豆瓣识别成功: 《{cn_title}》 {en_title} ({cand.get('year', '')}) [地区: {region}]")
            else:
                print(f"[-] 豆瓣未找到精确条目，使用文件名默认名称: '{cn_title}'")
        except Exception as e:
            print(f"[!] 豆瓣解析异常: {e}")

        # 2. Run subtitle extraction & organization
        try:
            org_res = sub_mgr.organize_movie(vp, cn_title, en_title, is_chinese=is_chinese, region=region)
            movie_full_name = f"{cn_title} {en_title}".strip()

            # 3. Update Excel report
            report_mgr.record_item(
                movie_name=movie_full_name,
                size=org_res['size_str'],
                cn_sub=org_res['cn_sub'],
                en_sub=org_res['en_sub'],
                status="已下载",
                reason=f"自动归档至: {os.path.basename(org_res['dest_dir'])}"
            )

            success_list.append({
                'name': movie_full_name,
                'dest': org_res['dest_dir'],
                'size': org_res['size_str'],
                'cn_sub': org_res['cn_sub'],
                'en_sub': org_res['en_sub']
            })
        except Exception as e:
            print(f"[!] 整理该部电影发生错误: {e}")
            fail_list.append({'name': it['source_name'], 'error': str(e)})

        time.sleep(0.5)

    print(f"\n================================================================================")
    print(f"[✓] 全量扫盘整理完成! 成功: {len(success_list)} 部, 失败: {len(fail_list)} 部")
    print(f"================================================================================")
    for idx, s in enumerate(success_list, 1):
        print(f"  {idx}. 《{s['name']}》 | 大小: {s['size']} | 中字: {s['cn_sub']} | 英字: {s['en_sub']}")
    if fail_list:
        print(f"\n[-] 失败列表:")
        for idx, f in enumerate(fail_list, 1):
            print(f"  {idx}. {f['name']} -> {f['error']}")

    print(f"\n[✓] Excel 下载与归档总报表已同步刷新: {report_mgr.report_path}")


def cmd_organize(args, client: NASClient):
    """Organizes a single specified video on NAS."""
    sub_mgr = SubtitleManager(client)
    is_cn = args.chinese
    region = ""
    if not is_cn and args.cn:
        resolver = DoubanResolver()
        d_res = resolver.resolve(args.cn)
        if d_res.get('candidates'):
            cand = d_res['candidates'][0]
            region = cand.get('region', '')
            if SubtitleManager.is_chinese_production(region):
                is_cn = True

    org_res = sub_mgr.organize_movie(args.video_path, args.cn, args.en, is_chinese=is_cn, region=region)
    report_mgr = ReportManager(args.report)
    movie_name = f"{args.cn} {args.en}".strip()
    report_mgr.record_item(
        movie_name=movie_name,
        size=org_res['size_str'],
        cn_sub=org_res['cn_sub'],
        en_sub=org_res['en_sub'],
        status="已下载",
        reason=f"归档至 {os.path.basename(org_res['dest_dir'])}"
    )


def normalize_title_key(text: str) -> str:
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', (text or '').lower())


_RELEASE_STOPWORDS = {
    'the', 'and', 'for', 'with', 'from', 'that', 'this', 'part', 'film', 'movie', 'aka',
    'cut', 'version', 'extended', 'remastered', 'proper', 'repack', 'complete', 'bluray',
    'webrip', 'webdl', 'web', 'brrip', 'dvdrip', 'remux', 'uhd', 'criterion', 'yts', 'sub',
    'subs', 'italian', 'japanese', 'korean', 'french', 'english', 'chinese', 'multi',
}


def release_tokens(text: str):
    words = re.findall(r'[A-Za-z][A-Za-z0-9\']{3,}', text or '')
    return {w.lower() for w in words if w.lower() not in _RELEASE_STOPWORDS}


def parse_batch_log_submissions(log_paths):
    """Parse batch logs into submitted items: cn title, year, winner title, search terms."""
    import ast
    submissions = []
    seen = set()
    for log_path in log_paths:
        if not os.path.exists(log_path):
            continue
        cur = None
        try:
            fh = open(log_path, encoding='utf-8', errors='replace')
        except Exception:
            continue
        with fh:
            for line in fh:
                m = re.match(r'\s*\[\d+/\d+\]\s*准备处理:\s*《(.+?)》\s*\(([^)]*)\)', line)
                if m:
                    cur = {'cn': m.group(1).strip(), 'year': m.group(2).strip(),
                           'terms': [], 'title': None}
                    continue
                if cur is None:
                    continue
                m = re.search(r'候选检索词:\s*(\[.*\])', line)
                if m:
                    try:
                        cur['terms'] = ast.literal_eval(m.group(1))
                    except Exception:
                        pass
                    continue
                m = re.search(r'\[\+\]\s*优选种子:\s*(.+)$', line)
                if m:
                    cur['title'] = m.group(1).strip()
                    continue
                if '成功提交至 qBittorrent' in line:
                    if cur.get('title'):
                        key = (cur['cn'], cur['year'], cur['title'])
                        if key not in seen:
                            seen.add(key)
                            submissions.append(dict(cur))
                    cur = None
    return submissions


def _parse_size_gb(text: str):
    m = re.search(r'([\d.]+)\s*GB', text or '')
    return float(m.group(1)) if m else None


def cmd_sync_report(args, client):
    """按 qBittorrent 完成状态回填 Excel 报告；只改报告，不移动文件、不下字幕。"""
    import glob
    import openpyxl

    report_mgr = ReportManager(args.report)
    report_path = report_mgr.report_path
    log_paths = sorted(glob.glob(os.path.join(os.path.dirname(report_path) or '.', 'nas_movie_batch*.log')))

    overrides = {}
    override_path = os.path.join(os.path.dirname(report_path) or '.', 'sync_overrides.json')
    if os.path.exists(override_path):
        try:
            with open(override_path, 'r', encoding='utf-8') as f:
                overrides = json.load(f)
        except Exception as e:
            print(f"[!] 读取 {override_path} 失败: {e}", flush=True)
            overrides = {}

    submissions = parse_batch_log_submissions(log_paths)
    by_title = {}
    term_index = {}
    for s in submissions:
        by_title.setdefault(normalize_title_key(s['title']), s)
        for term in [s['title']] + list(s['terms']):
            key = normalize_title_key(term)
            if len(key) >= 5:
                term_index.setdefault(key, []).append(s)
    print(f"[*] 日志提交记录: {len(submissions)} 条（{len(log_paths)} 个日志）", flush=True)

    wb = openpyxl.load_workbook(report_path)
    ws = wb.active
    rows = []
    for r in range(2, ws.max_row + 1):
        name = str(ws.cell(row=r, column=1).value or '')
        ym = re.search(r'\((\d{4})\)\s*$', name)
        rows.append({
            'row': r,
            'name': name,
            'key': normalize_title_key(name),
            'tokens': release_tokens(name),
            'year': ym.group(1) if ym else None,
            'size_gb': _parse_size_gb(str(ws.cell(row=r, column=2).value or '')),
            'status': str(ws.cell(row=r, column=5).value or '')
        })

    def row_by_cn(cn, year):
        key = normalize_title_key(cn)
        if len(key) < 2:
            return None
        best = None
        for row in rows:
            if row['key'].startswith(key) or key in row['key']:
                score = len(key)
                if year and year.isdigit() and f"({year})" in row['name']:
                    score += 100
                if row['status'] in ('下载中', ''):
                    score += 10
                if best is None or score > best[0]:
                    best = (score, row)
        return best[1] if best else None

    def match_torrent(name, size_gb):
        key = normalize_title_key(name)
        for ov_key, ov_name in overrides.items():
            ov_norm = normalize_title_key(ov_key)
            if ov_norm and ov_norm in key:
                row = row_by_cn(ov_name, None)
                if row:
                    return row, 'override'

        s = by_title.get(key)
        if s:
            row = row_by_cn(s['cn'], s['year'])
            if row:
                return row, 'log-title'

        nyears = set(re.findall(r'\b(19\d\d|20\d\d)\b', name))
        nt = release_tokens(name)

        best = None
        for term, lst in term_index.items():
            if term in key:
                for s in lst:
                    if s['year'] and s['year'].isdigit() and nyears and s['year'] not in nyears:
                        continue
                    score = len(term) + (50 if s['year'] in nyears else 0)
                    if best is None or score > best[0]:
                        best = (score, s)
        if best:
            row = row_by_cn(best[1]['cn'], best[1]['year'])
            if row:
                return row, 'log-term'

        cands = []
        size_match_count = sum(
            1 for r in rows
            if r['size_gb'] is not None and abs(r['size_gb'] - size_gb) <= 0.05
        )
        for row in rows:
            if row['year'] and nyears and row['year'] not in nyears:
                continue
            year_match = bool(row['year'] and row['year'] in nyears)
            size_close = row['size_gb'] is not None and abs(row['size_gb'] - size_gb) <= 0.05
            shared = nt & row['tokens']
            if shared:
                long_tok = max(len(x) for x in shared)
                if not (long_tok >= 6 or len(shared) >= 2 or size_close or year_match):
                    continue
                score = len(shared) * 10 + long_tok
            elif size_close and year_match and size_match_count == 1:
                score = 1
            else:
                continue
            if size_close:
                score += 8
            if year_match:
                score += 50
            if row['status'] in ('下载中', ''):
                score += 3
            cands.append((score, row))
        cands.sort(key=lambda x: -x[0])
        if cands and (len(cands) == 1 or cands[0][0] > cands[1][0]):
            return cands[0][1], 'size+token'
        return None, ''

    torrents = client.get_torrents_info()
    completed = [t for t in torrents if float(t.get('progress') or 0) >= 0.999]
    print(f"[*] qBittorrent 已完成任务: {len(completed)} / {len(torrents)}", flush=True)

    updated, unmatched = [], []
    updated_rows = set()
    already = 0
    processed = 0
    for t in completed:
        if args.limit and processed >= args.limit:
            break
        processed += 1

        raw_name = t.get('name') or ''
        size_gb = float(t.get('size') or 0) / (1024 ** 3)
        row, reason = match_torrent(raw_name, size_gb)
        if not row:
            unmatched.append(raw_name)
            print(f"[*] 未匹配到报告: {raw_name[:75]}", flush=True)
            continue
        if row['status'] == '已下载':
            already += 1
            continue
        if not args.dry_run and row['row'] not in updated_rows:
            ws.cell(row=row['row'], column=2, value=f"{size_gb:.2f} GB")
            ws.cell(row=row['row'], column=5, value='已下载')
            ws.cell(row=row['row'], column=6, value='qBittorrent 下载完成（自动回填）')
            ws.cell(row=row['row'], column=7, value=time.strftime('%Y-%m-%d %H:%M:%S'))
            row['status'] = '已下载'
            updated_rows.add(row['row'])
        updated.append((row['name'], f"{size_gb:.2f} GB", reason, raw_name))
        print(f"[{'演练' if args.dry_run else '✓'}] 回填: {row['name'][:55]} <- {raw_name[:50]}", flush=True)

    if not args.dry_run and updated_rows:
        wb.save(report_path)

    print(f"\n[✓] 同步完成: 新回填 {len(updated)} 部, 已下载 {already} 部, 未匹配 {len(unmatched)} 部"
          f"{'（演练模式，未写入）' if args.dry_run else ''}", flush=True)
    if updated:
        print("--- 本次回填:", flush=True)
        for name, size, reason, raw in updated:
            print(f"  {name} | {size} | {reason}", flush=True)
    if unmatched:
        print("--- 未匹配（可能不在愿望单报告）:", flush=True)
        for raw in unmatched:
            print(f"  {raw[:80]}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="NAS Movie & TV Organizer (Auto-Scan + Subtitles + Directory Standardizer)")
    parser.add_argument("--qbit-url", default=DEFAULT_QBIT_URL, help="qBittorrent WebUI URL")
    parser.add_argument("--qbit-user", default=DEFAULT_QBIT_USER, help="qBittorrent username")
    parser.add_argument("--qbit-password", default=DEFAULT_QBIT_PASSWORD, help="qBittorrent password")
    parser.add_argument("--ssh-host", default=DEFAULT_SSH_HOST, help="NAS SSH host")
    parser.add_argument("--download-dir", default=DEFAULT_NAS_DOWNLOAD_DIR, help="NAS download directory")
    parser.add_argument("--tailscale", "--ts", action="store_true", help="强制通过 Tailscale 连接 NAS")
    parser.add_argument("--report", "--report-file", default=None, help="下载结果 Excel 报告保存路径")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Sweep command (Batch auto-scan and organize)
    p_sweep = subparsers.add_parser("sweep", help="全量扫描 NAS 下载根目录，自动识别片名、下载字幕并归档")
    p_sweep.add_argument("--limit", type=int, default=0, help="最多处理多少个项目（默认 0 = 全部）")

    # Scan command (List pending unorganized items)
    p_scan = subparsers.add_parser("scan", help="仅扫描并列出 NAS 下载根目录中尚未规整的电影")

    # Single organize command
    p_org = subparsers.add_parser("organize", help="指定单个 NAS 视频文件进行时长校验、字幕下载与目录规整")
    p_org.add_argument("video_path", help="NAS 上的视频文件绝对路径")
    p_org.add_argument("--cn", required=True, help="电影中文名")
    p_org.add_argument("--en", required=True, help="电影外文名")
    p_org.add_argument("--chinese", action="store_true", help="指定为中国片源 (跳过英文及双语字幕)")

    # Sync report command (status backfill only, no file changes)
    p_sync = subparsers.add_parser("sync", aliases=["sync-report"],
                                   help="仅按 qBittorrent 完成状态回填 Excel 报告（不移动文件、不下字幕）")
    p_sync.add_argument("--dry-run", action="store_true", help="只展示匹配结果，不写入报告")
    p_sync.add_argument("--limit", type=int, default=0, help="最多处理多少个已完成任务（默认 0 = 全部）")

    args = parser.parse_args()

    client = NASClient(
        qbit_url=args.qbit_url,
        qbit_user=args.qbit_user,
        qbit_password=args.qbit_password,
        ssh_host=args.ssh_host,
        nas_download_dir=args.download_dir,
        force_tailscale=args.tailscale
    )

    if args.command == "sweep":
        cmd_sweep(args, client)
    elif args.command == "scan":
        cmd_scan(args, client)
    elif args.command == "organize":
        cmd_organize(args, client)
    elif args.command in ("sync", "sync-report"):
        cmd_sync_report(args, client)


if __name__ == "__main__":
    main()
