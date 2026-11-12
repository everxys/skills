---
name: clash-fixed-exits
description: 在 Clash Verge Rev（服务模式、mihomo 内核）里为每个国家搭一个"固定出口"本地端口（如 127.0.0.1:7901 土耳其、7902 美国），全局对所有 profile 生效；节点按国家放在 <clash目录>\nodes\<code>.yaml，由全局 Script.js 自动生成 proxy-provider nodes-<code>、select 组 固定<国家>、mixed listener。用于新电脑重建、加节点/删节点、加新国家、排查 7901/7902 不通或 provider 报 "not subpath of home directory or SAFE_PATHS"。Fixed-exit ports, per-country node files, Verge global script, junction into the service core home.
---

# Clash 固定出口（按国家节点文件 + 固定端口）

给每个国家一个永远走该国节点的本地端口，节点按国家放在普通 yaml 文件里，选哪个节点在 Verge 界面点。三件事各管各的：

| 关心什么 | 改哪里 | 以后要不要动 |
|---|---|---|
| 有哪些节点 | `<clash目录>\nodes\<code>.yaml`（顶层 `proxies:`） | 加/删节点时改，改完刷新 provider |
| 端口 ↔ 国家 | 全局 `profiles\Script.js` 顶部 `FIXED_EXITS` 表 | 只有加国家时加一行 |
| 当前用哪个节点 | Verge「代理」页里的「固定<国家>」组 | 日常点选 |

原理、和 7897 的关系见 [how-it-works.md](references/how-it-works.md)。

## 硬规则

- **密钥不出用户文件。** 绝不回显、记录或写进 skill / 日志 / 报告：UUID、Reality 公钥/私钥、short-id、vless:// 分享链接、controller `secret`、订阅链接和 token。读文件只看结构（键名、节点名）。不要整份打印 `profiles.yaml`、`clash-verge.yaml`、节点文件或 profile（profiles.yaml 里有订阅 URL/token）。脚本出错只打印异常类型。
- **改 Verge 文件前先备份**到 `<clash目录>\backups\<yyyyMMdd-HHmmss>\`（Script.js、clash-verge.yaml、相关 profile 扩展），并告诉用户路径。Verge 设置属于用户：改之前要用户同意。
- **不碰用户点名不让动的文件**（例如 `vps.yaml`、`blocklist.yaml`）。
- **全局 Script.js 已有内容时合并，不覆盖**（见 [deploy.md](references/deploy.md#5-写合并全局-scriptjs)）。
- **节点文件不是 profile**：不要把 `nodes\*.yaml` 当订阅导入或激活，会断网。
- 开机自修复计划任务（`scripts/install-junction-task.ps1`）**只在用户明确同意后安装**。
- 不写死用户名、SID 哈希、IP；用下面的占位符并现场探测。

占位符：`<clash目录>` 用户放 profile 的目录（例：`C:\Users\<user>\dev\clash`）；`<verge目录>` = `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev`；`<内核home>` = `%ProgramData%\clash-verge-service\users\<sha256(用户SID)>\runtime`；`<code>` 国家代码小写（tr、us、jp…）。

## 流程（新电脑 / 首次搭建）

详见 [deploy.md](references/deploy.md)。

1. **探测**：Verge 版本、服务模式、controller 地址、`<内核home>`（`scripts/make-junction.ps1 -WhatIf`）、全局 Script.js 现状、已占用端口。
2. **备份**要动的文件。
3. **建节点文件**：`<clash目录>\nodes\<code>.yaml`，用 `scripts/add-node.ps1 -From <clash目录>\vps-<ip>.yaml -Code <code>` 从现有 profile 拷节点（只打印节点名）。格式见 [node-files.md](references/node-files.md)。
4. **建 junction** `<内核home>\nodes → <clash目录>\nodes`：`scripts/make-junction.ps1`（需管理员，弹一次 UAC）。
5. **写/合并全局 Script.js**：以 `scripts/Script.js` 为模板，只改 `FIXED_EXITS` 表。
6. **离线校验**：`node scripts/simulate.js <Script.js>` 看生成的 provider/组/listener；有旧版脚本时 `--compare`。必要时 `verge-mihomo -t`。
7. **应用**：Verge 里重新激活当前 profile（首选），或写 clash-verge.yaml + `PUT /configs?force=true`。
8. **验证**：`scripts/verify.ps1`：每个 provider `vehicleType=File` 且节点数正确，每个端口出口 IP = 该国节点出口，7897 仍按规则分流。

## 日常维护

见 [maintain.md](references/maintain.md)：加/删节点 → 改 `nodes\<code>.yaml` → 刷新 `nodes-<code>`（Verge「代理」页「代理集合」，或 `verify.ps1 -Refresh` / `PUT /providers/proxies/nodes-<code>`）→ 在「固定<国家>」组里选。加国家 → 表里加一行 + 建文件 + 重新激活 profile。

## 排错

见 [troubleshooting.md](references/troubleshooting.md)。最常见：端口不通 + provider 报错 = junction 没了，重跑 `make-junction.ps1`。

## 文件

| 路径 | 用途 |
|---|---|
| `scripts/Script.js` | 全局扩展脚本模板：`FIXED_EXITS` 表驱动，生成 provider/组/listener；可合并进已有脚本 |
| `scripts/simulate.js` | Node 离线模拟 Verge 跑脚本，打印结构；`--compare a.js b.js` 比较两版效果 |
| `scripts/make-junction.ps1` | 由用户 SID 算出内核 home，建 `runtime\nodes` junction；非管理员时自提权一次；`-WhatIf` 只探测 |
| `scripts/install-junction-task.ps1` | 可选：SYSTEM 计划任务，开机及每 30 分钟检查并重建 junction；`-Uninstall` 移除。需用户同意 |
| `scripts/add-node.ps1` | 把 `vps-<ip>.yaml` 的 `proxies:` 条目追加到 `nodes\<code>.yaml`，先备份、查重名、只打印节点名 |
| `scripts/verify.ps1` | 只读验证：provider 状态 + 每个端口出口 IP；`-Refresh` 先刷新 provider；不打印 secret |
| `examples/nodes-xx.example.yaml` | 占位符示例节点文件（无真实密钥） |
| `references/*.md` | 原理、部署、维护、排错 |

PowerShell 脚本兼容 Windows PowerShell 5.1 和 pwsh 7，保存为 UTF-8 with BOM。
