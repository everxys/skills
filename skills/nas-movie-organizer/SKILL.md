---
name: nas-movie-organizer
description: 整理 NAS 已下载完成的电影并自动补齐中英文字幕。当用户提到“整理电影”、“整理NAS电影”、“整理已下载”、“电影归档”、“下载字幕”、“匹配字幕”、“nas movie organize”、“nas organize”、“把已下载的电影整理一下”、“扫描并整理电影”时触发本 skill。全自动扫描 NAS 下载目录或 qBittorrent 已完成任务，提取视频时长、提取内嵌中英文字幕、通过字幕站（字幕库/伪射手/SubHD/A4K/OpenSubtitles等）检索补齐缺失字幕，按“电影中文名 外文名”规整目录归档，并增量更新 Excel 结果报告。
---

# NAS Movie & TV Organizer (影视自动整理与字幕补齐)

本 Skill 用于全面接管家庭 NAS（Debian，局域网 `192.168.0.2` / Tailscale `100.125.232.123`）已下载电影的**后处理全自动化工作流**：
与下载阶段彻底解耦，无论电影是在电脑离线期间由 qBittorrent 自主下载完成，还是历史遗留的散乱资源，均可随时随地通过本 Skill **一键全量扫盘整理（Sweep）** 或 **按指定路径归档**。

---

## 核心功能与工作流

### 1. 全盘扫盘识别（Sweep / Scan）
* 自动扫描 NAS 下载目录（`/nasdata/downloads`）中的散落视频文件及未经标准化的发布子目录。
* 过滤未下载完成的任务（`incomplete/`）与系统临时目录。
* 自动通过豆瓣（Douban）解析规范的中文译名、外文原名、发行年份与制片国家/地区。

### 2. 精确时长核验与内嵌字幕提取
* 使用 NAS 原生 `/usr/bin/ffprobe` 确认视频准确总秒数（精确到毫秒级）。
* 分析视频流容器（MKV/MP4），自动将原视频内部封装的高清简体中文字幕（`.zh-CN.srt`）、英文字幕（`.en.srt`）或双语字幕（`.zh-en.srt`）无损提取为外挂独立字幕。

### 3. 差异化字幕智能匹配（片源区分与优先级检索）
根据影片出品地区执行严格策略：

* **中国片源（中国大陆、香港、台湾）**：
  * **硬性规则**：**不下载英文字幕，也不下载中英双语字幕**。
  * 仅寻找**中文简体字幕**。
  * 检索顺序：1. 字幕库 (`zimuku.org`) $\to$ 2. 伪射手网 (`assrt.net`) $\to$ 3. SubHD (`subhd.tv`) $\to$ 4. A4K字幕网 (`a4k.net`)。

* **外国片源（欧美、日韩、拉美等海外影片）**：
  * **中文与中英双语字幕**：字幕库 $\to$ 伪射手网 $\to$ SubHD $\to$ A4K字幕网。
  * **英文字幕**：OpenSubtitles $\to$ Subscene / Subdl $\to$ YIFY Subtitles。
  * **时长匹配与容差兜底**：
    * 优先选择标注片长与实际时长相吻合（容差 $\le$ 3 分钟）的精准字幕。
    * 若无明确时长标注，绝不报错中断，按版本匹配度自动下载首选可用字幕作为兜底。

### 4. 规范化目录归档
* 在 NAS 下载根目录（`/nasdata/downloads/`）下创建标准目录：
  **`目录名 = 电影中文名 + " " + 外文名`**（如 `/nasdata/downloads/奇美拉 La Chimera/`）。
* 将主视频文件及所有匹配的外挂中英字幕一并移入该专属目录。
* 自动清理整理后的空残余文件夹。

### 5. Excel 总报告实时回填
* 自动读取并增量更新下载报告：
  * NAS 上执行：`/nasdata/scripts/nas-video-download/nas_movie_download_report.xlsx`
  * 本机执行：`~/Downloads/nas_movie_download_report.xlsx`
* 状态流转为 **“已下载”**（软绿色高亮），并详细回填中文字幕（已内嵌提取 / 已匹配下载 / 中国片源无需）与英文字幕的具体匹配情况。

---

## 报表状态自动回填（sync，NAS 常驻）

qBittorrent 下载完成后，由 `sync` 命令把报告里的 `下载中` 回填为 `已下载`。它**只改报告**，不移动文件、不下载字幕，因此可以安全地高频运行。

### 部署与定时
* **脚本**: `/nasdata/scripts/nas-video-download/nas_organize.py`
* **启动器**: `/nasdata/scripts/nas-video-download/run_sync.sh`（`flock` 防重入）
* **报告**: `/nasdata/scripts/nas-video-download/nas_movie_download_report.xlsx`
* **日志**: `/nasdata/scripts/nas-video-download/nas_movie_sync.log`
* **定时任务**: `crontab` 每 15 分钟自动执行一次
  ```bash
  */15 * * * * /nasdata/scripts/nas-video-download/run_sync.sh >> /nasdata/scripts/nas-video-download/nas_movie_sync.log 2>&1
  ```

### 匹配逻辑（纯本地，不依赖豆瓣）
1. 解析 `nas_movie_batch*.log` 里的提交记录（准备处理片名 / 精选种子标题 / 候选检索词），按中文名精确对应报告行。
2. 兜底使用报告中的 **体积（±0.05 GB）+ 年份 + 片名词元** 匹配；同名或歧义无法唯一确定时**宁可不更新**，避免写错行。
3. 仅把 `下载中` / `跳过` 更新为 `已下载`，保留电影名、字幕列，不覆盖已有 `已下载` 行。
4. 个别片名差异过大的，可在同目录 `sync_overrides.json` 里手动指定映射：
   ```json
   { "种子名归一化片段": "报告中的中文名" }
   ```
   键会与归一化后的种子名做包含匹配，优先于自动匹配。

### 手动执行
```bash
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_organize.py sync --dry-run"   # 预览
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_organize.py sync"             # 正式回填
```

> [!NOTE]
> 若日志中出现“未匹配到报告”，说明该任务不在愿望单里，或片名与报告差异过大。可以用下面的单部 `organize` 手动归档并回填。

---

## 常用 CLI 命令

脚本路径：`<SKILL_DIR>/scripts/nas_organize.py`

### 1. 全量扫描并自动归档（Sweep - 推荐日常使用）
```powershell
# 一键扫描 NAS 下载根目录所有已完成电影，自动查询豆瓣、匹配字幕、移动目录并更新 Excel 报告
python <SKILL_DIR>/scripts/nas_organize.py sweep

# 若人在外地，可强制走 Tailscale 隧道执行
python <SKILL_DIR>/scripts/nas_organize.py --ts sweep
```

### 2. 仅扫描待整理清单（Scan - 预览模式）
```powershell
# 仅列出当前 NAS 上有哪些电影尚未规范整理，不执行文件移动与字幕下载
python <SKILL_DIR>/scripts/nas_organize.py scan
```

### 3. 指定单个文件手动归档（Organize）
```powershell
# 指定单个视频文件归档
python <SKILL_DIR>/scripts/nas_organize.py organize "/nasdata/downloads/some_movie.mkv" --cn "电影中文名" --en "Foreign Title"

# 中国片源显式指定（跳过英文及双语字幕）
python <SKILL_DIR>/scripts/nas_organize.py organize "/nasdata/downloads/some_movie.mkv" --cn "大话西游" --en "A Chinese Odyssey" --chinese
```

### 4. 仅回填下载状态（Sync - 不改动文件）
```powershell
# 预览哪些已完成任务会被回填为“已下载”
python <SKILL_DIR>/scripts/nas_organize.py sync --dry-run

# 正式回填报告
python <SKILL_DIR>/scripts/nas_organize.py sync
```

---

## NAS 配置与网络端点

* **NAS 主机**: `ssh nas` (`192.168.0.2:54540`, user `everxys`)
* **Tailscale 节点**: `ssh nas-ts` (`100.125.232.123:54540`, user `everxys`)
* **下载根目录**: `/nasdata/downloads`
* **视频与音频处理工具**: NAS 已就绪 `/usr/bin/ffprobe` 与 `/usr/bin/ffmpeg`
* **双通道自愈**: 默认优先直连家庭局域网；局域网不可达时自动无缝降级走 Tailscale 专网。
