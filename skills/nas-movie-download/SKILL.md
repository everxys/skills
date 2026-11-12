---
name: nas-movie-download
description: 控制 NAS 自动化检索、优选并下载电影与剧集至 qBittorrent，并在下载完成后校验视频时长、按严格优先级匹配下载中英文字幕，最后自动按“中文名+外文名”归档至同一目录。支持通过豆瓣（Douban）解析外文原名与拉丁又名（接口不可用时自动回退到 CSV 外文名）。严格遵循用户交互决策流（同名电影列出年份与导演供用户选择、多部系列电影列出各部加“全都下载”选项、影视剧按季列出加“全部下载”选项），并在种子优选时强制执行“名字匹配、年份匹配、做种数 seeders >= 1 铁律、大于3GB优先选做种最高（否则小于等于3GB选做种最高）”。脚本可常驻 NAS（tmux + cron）：批量入队、每 15 分钟自动回填下载完成状态、每 20 分钟巡检并替换卡在 metaDL 的死种。当用户提到“下载电影”、“下载剧集”、“帮我下载《xxx》”、“在NAS上下部电影”、“nas movie download”、“搜一下电影并下载”、“下载字幕”、“查看NAS下载进度”、“下载到多少了”、“卡在 downloading metadata”、“死种怎么办”、“更新下载报告”时触发本 skill。
---

# NAS Movie & TV Downloader & Organizer

本 Skill 用于全面接管家庭 NAS（Debian，局域网 `192.168.0.2` / Tailscale `100.125.232.123`）的影视工作流：
1. **豆瓣（Douban）前置解析**：中外文名自动转换、非拉丁语种别名提权、歧义作品多选交互。
2. **Jackett 严格优选**：硬性做种数约束（`seeders >= 1`）、体积大者优先（> 3GB 优选）。
3. **qBittorrent 下载管理**：任务推送与实时下载进度追踪。
4. **时长校验与字幕匹配**：使用 `ffprobe` 确认视频准确时长，按先后优先级检索下载匹配时长的**中文简体字幕**与**英文字幕**。
5. **规范化自动归档**：将电影文件与中英文字幕归档放置在同一目录下，目录命名统一为 **`电影中文名 + 外文名`**（如 `/nasdata/downloads/奇美拉 La Chimera/`）。

---

## NAS 端常驻运行（推荐，电脑关机不中断）

批量下载脚本不依赖本机：它常驻在 NAS 的 `/nasdata/scripts/nas-video-download/` 下运行，带电脑出门也不影响任务推进。

### 部署目录与文件
* **脚本**: `/nasdata/scripts/nas-video-download/nas_movie.py`
* **启动器**: `/nasdata/scripts/nas-video-download/run_batch.sh`（默认跳过剧集与续集，并防止重复启动）
* **死种巡检器**: `/nasdata/scripts/nas-video-download/run_heal.sh`（每 20 分钟，`flock` 防重入）
* **死种记录**: `/nasdata/scripts/nas-video-download/dead_titles.json`（已判定失效的发布名，避免重复添加）
* **愿望单 CSV**: `/nasdata/scripts/nas-video-download/db-movie-wishlist-20261025.csv`
* **进度报告**: `/nasdata/scripts/nas-video-download/nas_movie_download_report.xlsx`
* **实时日志**: `/nasdata/scripts/nas-video-download/nas_movie_batch.log`
* **巡检日志**: `/nasdata/scripts/nas-video-download/nas_movie_heal.log`
* **历史日志归档**: `/nasdata/scripts/nas-video-download/nas_movie_batch.windows-legacy-20261026.log`

脚本内置 `IS_ON_NAS` 判定：在 NAS 上执行时，报告与日志默认路径会自动指向上述目录，无需额外传 `--report` / `--log-file`。

### 启动（tmux 常驻）
```bash
ssh nas
tmux new -d -s nas-movie "bash /nasdata/scripts/nas-video-download/run_batch.sh"
```

### 查看 / 停止
```bash
tmux attach -t nas-movie          # 查看实时输出（Ctrl+B D 脱离）
ssh nas "tail -f /nasdata/scripts/nas-video-download/nas_movie_batch.log"
ssh nas "tmux kill-session -t nas-movie"    # 停止任务
scp nas:/nasdata/scripts/nas-video-download/nas_movie_download_report.xlsx ~/Downloads/   # 拉取最新报告到本机
```

### 重新部署（本机 → NAS）
```powershell
scp <SKILL_DIR>/scripts/nas_movie.py <SKILL_DIR>/scripts/run_batch.sh <SKILL_DIR>/scripts/run_heal.sh nas:/nasdata/scripts/nas-video-download/
scp "C:\Users\everx\Downloads\db-movie-wishlist-20261025.csv" nas:/nasdata/scripts/nas-video-download/
```
```bash
ssh nas "chmod +x /nasdata/scripts/nas-video-download/run_batch.sh /nasdata/scripts/nas-video-download/run_heal.sh"
```

`nas_organize.py` 与 `run_sync.sh` 属于 `nas-movie-organizer` 技能，同样部署在该目录。重建 crontab（幂等，可重复执行）：
```bash
ssh nas '( crontab -l 2>/dev/null | grep -v run_sync.sh | grep -v run_heal.sh; \
  echo "*/15 * * * * /nasdata/scripts/nas-video-download/run_sync.sh >> /nasdata/scripts/nas-video-download/nas_movie_sync.log 2>&1"; \
  echo "*/20 * * * * /nasdata/scripts/nas-video-download/run_heal.sh >> /nasdata/scripts/nas-video-download/nas_movie_heal.log 2>&1" ) | crontab -'
```

### 中断与恢复
`batch` 每次启动都会重新扫描 NAS 下载目录与 qBittorrent 队列做去重，**中断后直接重新执行 `run_batch.sh` 即可无损续跑**：已入队或已下载完的条目会自动跳过。

### 卡在 downloading metadata / 死种处理
**症状**：qBittorrent 里任务长期停在 `metaDL`（downloading metadata），速度为 0。这些磁力链的做种者已经消失，却仍占着 `max_active_downloads=10` 的并发槽，导致后面排队的任务一直不开始。

**自动巡检**：`run_heal.sh` 每 20 分钟执行：
1. 找出 `metaDL` / `stalledDL` 且 **0 连接做种、0 速度、活跃超过 20 分钟** 的任务；
2. 暂停它们，立即释放下载槽；
3. 用 Jackett 重新搜索该片名（排除 `dead_titles.json` 里已判定失效的发布），按同一套优选规则选替代资源，添加新种子并删除死种；
4. 同一部最多尝试 3 次；确实没有替代资源的保持暂停（记录在 `dead_titles.json`，可稍后重试）。

> [!NOTE]
> 如果某个高画质版本是死种、只有低画质版本还活着，替换会按“有做种优先”原则选低画质版本；不想降画质的话，可以删除 `dead_titles.json` 中对应条目后再试，或手动指定资源。

**手动执行**：
```bash
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py heal --repair --dry-run"   # 预览
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py heal --repair"             # 执行
```

---

## 完整执行流程与操作规范

### 第一步：片名解析与外文名确认（Douban）

国外 PT/BT 索引器（Jackett）主要使用英文、法文、西班牙文等拉丁字母标题。
1. **优先提取外文原名**：优先提取豆瓣 `sub_title`（如《奇美拉》 $\to$ `La Chimera`）。
2. **非拉丁语种（日文/韩文等）别名提权**：
   - 若原名为日韩等非拉丁文字（如《铁男1：金属兽 鉄男》），自动解析豆瓣“又名”（AKA），提取其中的拉丁/英文别名（如 `Tetsuo: The Ironman` / `The Ironman`）作为**第一优先搜索词**；若搜不到再回退尝试原名。
3. **豆瓣接口不可用时的回退**：
   - 豆瓣 suggest 接口可能整体返回空（2026-10 实测，PC 与 NAS 均如此）。此时不要卡住，直接使用 CSV / 愿望单里的外文名检索，或使用下载报告里已有的中外文名。批量场景下 CSV 的外文名列通常已足够。

---

### 第二步：交互歧义消除（Disambiguation & User Choice）

运行 `python <SKILL_DIR>/scripts/nas_movie.py douban "<query>" --json` 判断分类：

#### 分支 A：同名 / 歧义作品（Homonyms）
* 若检索到多部不同年份或不同导演的同名作品（且用户未指定年份）：
* **必须主动停下来询问用户**，逐项列出：
  - 【片名】+【年份】+【导演】+【地区】+【类型（电影/电视剧）】供用户选择。

#### 分支 B：系列电影（Franchise / 多部系列）
* 若为系列电影（如《复仇者联盟》、《教父》、《黑客帝国》、《指环王》）：
* **必须给出选项，按上映顺序从第一部列到最后一部**，且**最后一个选项必须是【全都下载】**：
  - 选项 1: 《复仇者联盟》(2012)
  - 选项 2: 《复仇者联盟2：奥创纪元》(2015)
  - 选项 3: 《复仇者联盟3：无限战争》(2018)
  - 选项 4: 《复仇者联盟4：终局之战》(2019)
  - 选项 5: **【全都下载】**（依次下载该系列所有部）

#### 分支 C：电视剧 / 影视剧（TV Series / 多季）
* 若目标是剧集或包含多个季（如《绝命毒师》、《权力的游戏》）：
* **必须询问用户要下载第几季**，按第一季到最后一季列出选项，且**最后一个选项必须是【全部下载】**：
  - 选项 1: 第一季 (Season 1, 2008, 7集)
  - 选项 2: 第二季 (Season 2, 2009, 13集)
  - ...
  - 选项 N: **【全部下载】**（下载全套所有季）

---

### 第三步：资源筛选与优选（硬性约束与安全熔断）

在 Jackett 检索结果中严格执行：
1. **名称匹配（Title Match）**：发布标题必须完整包含搜索词。
2. **年份匹配（Year Match）**：若已知年份，发布标题**必须匹配该 4 位年份**。
3. **做种数硬性约束（`seeders >= 1`）**：**硬性规定**，做种数为 0 的死种必须直接过滤淘汰。
4. **体积优选与异常大（> 15GB）规避规则**：
   - **异常大规避与优先档（3GB ~ 15GB）**：若存在 > 15GB 的超大版本，主动避开，优先从 **3GB ~ 15GB** 的候选列表中选出 **seeders 最高** 的版本。
   - **次选档（<= 3GB）**：若无 3GB ~ 15GB 且做种 >= 1 的候选，退而在 **<= 3GB** 列表中选取 **seeders 最高** 的版本。
   - **超大跳过与重点播报**：若**所有**做种 >= 1 的候选均大于 15GB（且无 <= 15GB 可选版本），则**跳过该电影**，并在最后向用户重点播报！
5. **NAS 剩余容量保护（1TB 熔断机制）**：
   - 任何下载任务提交前，必须探查 NAS `/nasdata/downloads` 实时可用磁盘空间。
   - 若下载该电影后预计 NAS 剩余空间将**不足 1TB（< 1024 GB）**，立即**停止下载**并**跳过后续所有电影任务**，触发全局容量熔断保护！
6. **Excel 结果报告导出**：
   - 所有单部及批量电影下载，均自动输出并增量更新 Excel 报告（本机执行为 `~/Downloads/nas_movie_download_report.xlsx`；NAS 上执行为 `/nasdata/scripts/nas-video-download/nas_movie_download_report.xlsx`）。
   - 报告规范包含 7 大字段：`电影名`、`大小`、`中文字幕`、`英文字幕`、`状态（跳过、已下载、下载中）`、`备注说明`、`记录时间`。
7. **本地与任务队列前置查重（NAS & qBit Deduplication）**：
   - 无论是单部电影下载（`download`）还是愿望单批量导入（`batch`），在向 Jackett 检索或推送到下载器前，**系统均会自动先扫描 NAS 下载目录（`/nasdata/downloads`）与 qBittorrent 当前全部任务**。
   - 对中文名、外文名、标点符号与数字进行多重归一化比对；若 NAS 本地已存在或任务队列中已有，**自动跳过下载**，避免带宽浪费与文件覆盖（单部下载可通过 `--force` 强制重新下载）。

---

### 第四步：下载完成后的时长校验、字幕匹配与目录归档

电影下载完成（100%）后，执行自动化归档程序：

#### 1. 确认视频精确时长
* 通过 `ffprobe` 获取视频文件的精确总秒数（如 `10053.2` 秒，即 `02:47:33`）。
* 同时检查视频容器（MKV/MP4）内部是否已携带原生封装的英文字幕或简体中文字幕。

#### 2. 字幕检索（按片源地区区分）
根据电影制作国家/地区进行差异化检索：

* **中国片源（中国的片子：中国大陆、香港、台湾）**：
  - **重要规则**：**不下载英文字幕，也不下载中英双语字幕**。
  - 仅检索**中文简体字幕**（若视频未内嵌硬字幕或需外挂字幕）。
  - 中文字幕检索顺序：
    1. **字幕库** (`zimuku.org` 及镜像)
    2. **伪射手网** (`assrt.net`)
    3. **SubHD** (`subhd.tv`)
    4. **A4K字幕网** (`a4k.net`)

* **外国片源（欧美、日韩等海外影片）**：
  - **中文字幕检索顺序**（寻找**中文简体**与**中英双语**）：
    1. **字幕库** (`zimuku.org` 及镜像)
    2. **伪射手网** (`assrt.net`)
    3. **SubHD** (`subhd.tv`)
    4. **A4K字幕网** (`a4k.net`)
    * **中英双语扩展**：若发现中英双语/双字字幕，一并下载并保存为独立双语字幕。
  - **英文字幕检索顺序**：
    1. **OpenSubtitles** (`opensubtitles.com` / `opensubtitles.org`)
    2. **Subscene / Subdl** (`subdl.com`)
    3. **YIFY Subtitles** (`yts-subs.com`)

#### 3. 时长匹配与优选规则（以标注时长为准，无标注则兜底下载）
* **优先匹配标注时长**：许多字幕平台（如 SubHD、OpenSubtitles、Subdl、伪射手等）会在字幕标题、说明或元数据中明确标注该字幕所适配的**片长/时长**（例如 `片长: 130分钟`、`时长: 02:10:45` 或 `113 mins`）。
  - 若候选字幕明确标注了时长，自动与视频时长（`ffprobe` 获取）比对，优先选取**时长吻合（容差 <= 3分钟）**的精准版本。
* **无时长标注时的兜底原则（“如果全都没有的话，那就随便下一个”）**：
  - 许多电影片尾有长达数分钟的纯配乐、黑幕或静默制作人员名单而无台词，**绝不以最后一句台词的时间戳强行卡死过滤**。
  - 若候选字幕页面均未提供明确时长标注，**坚决不报错放弃**，直接在当前优先级最高的字幕站中按版本匹配度（如 BluRay / WEB-DL，或下载量最高/最新版本）**自动下载首选可用字幕**！

#### 4. 目录创建与文件归档
* 在 NAS 下载根目录（`/nasdata/downloads/`）下创建规范目录：
  **`目录名 = 电影中文名 + " " + 外文名`**
  例如：`/nasdata/downloads/制造共识 Manufacturing Consent/` 或 `/nasdata/downloads/流浪地球 The Wandering Earth/`
* 将电影主视频文件移入该目录。
* 字幕同级归档规范：
  - **中国片源**：
    - 中文简体字幕：`<电影名>.zh-CN.srt`（或 `.ass`，如需要）
    - *(无需下载任何英文或双语字幕)*
  - **外国片源**：
    - 中文简体字幕：`<电影名>.zh-CN.srt`（或 `.ass`）
    - 英文字幕：`<电影名>.en.srt`（或 `.ass`）
    - 中英双语字幕：`<电影名>.zh-en.srt`（或 `.ass`，如有找到一并保存）

---

### 5. 并发队列与常驻运行机制

* **10部并发下载队列配置**：
  - NAS 上的 qBittorrent 已配置并发下载队列上限为 `max_active_downloads = 10`（最大活动任务数 20）。
  - 用户批量提交多部电影时，qBittorrent 会自动按 10 部并发跑满，超出部分排队顺延。

* **下载完成状态自动回填**：
  - batch 只在入队时写 `下载中`；完成状态由 `nas-movie-organizer` 的 `sync` 命令回填。
  - NAS 上已配置 crontab，每 15 分钟运行一次 `run_sync.sh`，只更新报告、不移动文件、不下字幕。
  - 回填日志：`/nasdata/scripts/nas-video-download/nas_movie_sync.log`
  - 手动查看/执行：
    - `ssh nas "tail -n 30 /nasdata/scripts/nas-video-download/nas_movie_sync.log"`
    - `ssh nas "python3 /nasdata/scripts/nas-video-download/nas_organize.py sync --dry-run"`
  - 完整归档（移动文件 + 字幕匹配）仍由 `nas-movie-organizer` 的 `sweep` 手动执行。

---

## 常用 CLI 命令

脚本路径：本机 `<SKILL_DIR>/scripts/nas_movie.py`；NAS 常驻副本 `/nasdata/scripts/nas-video-download/nas_movie.py`。
在 NAS 上执行时把 `python` 换成 `python3`，并通过 `ssh nas "..."` 调用。

### 1. 豆瓣信息与分类查询
```powershell
python <SKILL_DIR>/scripts/nas_movie.py douban "奇美拉"
python <SKILL_DIR>/scripts/nas_movie.py douban "铁男1：金属兽"
python <SKILL_DIR>/scripts/nas_movie.py douban "复仇者联盟"
python <SKILL_DIR>/scripts/nas_movie.py douban "绝命毒师"
```

### 2. 检索并自动提交下载
```powershell
# 自动调用豆瓣解析外文名检索并推送到 qBittorrent
python <SKILL_DIR>/scripts/nas_movie.py download "奇美拉" --year 2023
```

### 3. 查看下载进度
```powershell
# 即时查看当前任务状态（NAS 上执行）
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py status"

# 或直接看报告（状态由 sync 每 15 分钟回填）
scp nas:/nasdata/scripts/nas-video-download/nas_movie_download_report.xlsx ~/Downloads/
```
> NAS 常驻批量下载**不需要**用 `monitor` 轮询，也不依赖聊天 Session。`monitor --interval 30` 仅保留给本机单部下载后等待完成使用。

### 4. 归档与字幕处理（时长校验 + 字幕匹配 + 目录移动）
```powershell
# 对已下载完成的视频进行自动时长校验、字幕下载与目录规整
python <SKILL_DIR>/scripts/nas_movie.py organize "/nasdata/downloads/some_movie.mkv" --cn "电影中文名" --en "Foreign Title"
```

### 5. 死种巡检与自动替换（metaDL 卡死）
```powershell
# 停止 0 连接的 metaDL/stalledDL 任务并尝试替换（NAS 上每 20 分钟自动执行）
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py heal --repair"

# 只预览，不改动
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py heal --repair --dry-run"
```

### 6. 愿望单/批量电影列表对比与下载 (Batch 全量入队)
```powershell
# 在 NAS 上常驻运行（推荐，电脑关机不中断）
ssh nas "tmux new -d -s nas-movie 'bash /nasdata/scripts/nas-video-download/run_batch.sh'"

# 若要在本机执行：从 CSV 列表读取，对比 NAS 与 qBittorrent 自动去重，在不超过 1TB 剩余保护的前提下一次性全量推入 qBittorrent 队列
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py batch /nasdata/scripts/nas-video-download/db-movie-wishlist-20261025.csv --skip-tv --skip-sequels"

# 演练模式（仅比对和展示优胜资源，不向 qBittorrent 提交下载）
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py batch /nasdata/scripts/nas-video-download/db-movie-wishlist-20261025.csv --dry-run --limit 5"

# 跳过多季电视剧集，只下载独立电影
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py batch /nasdata/scripts/nas-video-download/db-movie-wishlist-20261025.csv --skip-tv"

# 跳过续集与系列后续作品，不下载任何续集
ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py batch /nasdata/scripts/nas-video-download/db-movie-wishlist-20261025.csv --skip-sequels"
```

> [!NOTE]
> 下载与字幕归档已全面解耦：qBittorrent 接收全部电影后在 NAS 本地全天候维持 10 并发下载，电脑离线不影响任务自动轮转接力。下载完成后的批量字幕匹配与目录整理交由专有技能 `nas-movie-organizer` 随时扫盘执行。

---

## 日常运维速查

| 目的 | 命令 |
| --- | --- |
| 看下载速度/状态 | `ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py status"` |
| 拉取最新报告 | `scp nas:/nasdata/scripts/nas-video-download/nas_movie_download_report.xlsx ~/Downloads/` |
| 进度回填日志 | `ssh nas "tail -30 /nasdata/scripts/nas-video-download/nas_movie_sync.log"` |
| 死种巡检日志 | `ssh nas "tail -30 /nasdata/scripts/nas-video-download/nas_movie_heal.log"` |
| 手动回填报告 | `ssh nas "python3 /nasdata/scripts/nas-video-download/nas_organize.py sync"` |
| 手动死种巡检 | `ssh nas "python3 /nasdata/scripts/nas-video-download/nas_movie.py heal --repair"` |
| 查看定时任务 | `ssh nas "crontab -l"` |
| 停止批量任务 | `ssh nas "tmux kill-session -t nas-movie"` |
| 磁盘余量 | `ssh nas "df -h /nasdata"` |

---

## NAS 配置与端点说明（双通道自动容灾）

脚本内置网络探活与自动降级机制：优先直连家庭局域网；当不在家中或局域网不可达时，自动无缝切换至 Tailscale 通道。

### 1. 局域网通道（LAN - 优先）
* **NAS 主机**: `ssh nas` (`192.168.0.2:54540`, user `everxys`)
* **Jackett**: `http://192.168.0.2:9117` (API Key: `o1tzon5zd14eufrarrzkw11qpi86yxak`)
* **qBittorrent**: `https://192.168.0.2:54808` (User: `everxys`, Pass: `!z8#upNXfS*#ER`)

### 2. Tailscale 互联通道（自动兜底 / 异地访问）
* **NAS 主机**: `ssh nas-ts` (`100.125.232.123:54540`, user `everxys`)
* **Jackett**: `http://100.125.232.123:9117`
* **qBittorrent**: `https://100.125.232.123:54808`
* **命令行强制指定**: 在执行任意 CLI 命令时附带 `--tailscale` 或 `--ts` 即可强制走 Tailscale 通道。

### 3. 系统环境
* **下载根目录**: `/nasdata/downloads`
* **常驻脚本目录**: `/nasdata/scripts/nas-video-download`（脚本、CSV、Excel 报告、日志均在此）
* **常驻会话**: tmux 会话名 `nas-movie`
* **定时任务**:
  * 每 15 分钟：`run_sync.sh` → 回填下载完成状态
  * 每 20 分钟：`run_heal.sh --repair` → 死种巡检与替代
* **视频处理工具**: NAS 已就绪 `/usr/bin/ffprobe` 与 `/usr/bin/ffmpeg`。
