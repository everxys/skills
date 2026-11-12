# 完整部署流程

适用：新电脑、重装 Verge、或第一次搭固定出口。每一步只打印结构和结果，不打印密钥。

## 0. 前提

- Clash Verge Rev 以**服务模式**运行（设置里"服务模式"开），内核 verge-mihomo。非服务模式（sidecar）时内核 home 就是 `<verge目录>`，可以不用 junction，直接在 `<verge目录>` 下建 `nodes` 目录或 junction（同样要过 SAFE_PATHS 检查）。
- 已有每个国家至少一个能用的节点，通常是 `<clash目录>\vps-<ip>.yaml`。
- `node` 在 PATH 里（用于离线模拟），否则跳过第 5 步模拟，靠 `-t` 和实测。

## 1. 探测（只读）

```powershell
$V = "$env:APPDATA\io.github.clash-verge-rev.clash-verge-rev"
Test-Path "$V\profiles\Script.js"; (Get-Item "$V\profiles\Script.js").Length   # 全局脚本是否已有内容
Select-String "$V\clash-verge.yaml" -Pattern '^(mixed-port|external-controller):'  # 不要匹配 secret
Get-NetTCPConnection -State Listen -LocalPort 7901,7902 -ErrorAction SilentlyContinue  # 端口是否被占
.\scripts\make-junction.ps1 -WhatIf -NodesDir <clash目录>\nodes            # 预期的内核 home
```

全局 Script 在 `profiles.yaml` 里是 uid `Script` 的条目（文件 `profiles\Script.js`）；只用 `Select-String -Pattern '^\s*(uid|type):'` 看结构，别整份读 profiles.yaml（有订阅 token）。

## 2. 备份

```powershell
$B = "<clash目录>\backups\$(Get-Date -Format yyyyMMdd-HHmmss)"; New-Item -ItemType Directory $B | Out-Null
Copy-Item "$V\profiles\Script.js","$V\clash-verge.yaml" $B
```
动到哪个 profile 扩展（`profiles\<uid>.yaml`）也一起备份。告诉用户备份路径。

## 3. 节点文件

```powershell
New-Item -ItemType Directory -Force <clash目录>\nodes | Out-Null
.\scripts\add-node.ps1 -From <clash目录>\vps-<ip-tr>.yaml -Code tr -Label 土耳其
.\scripts\add-node.ps1 -From <clash目录>\vps-<ip-us>.yaml -Code us -Label 美国
```
见 [node-files.md](node-files.md)。

## 4. 建 junction

```powershell
.\scripts\make-junction.ps1 -NodesDir <clash目录>\nodes
```
弹一次 UAC，用户点「是」。日志 `%TEMP%\clash-fixed-exits-junction.log`，看到 `junction created` / `OK junction already present` 和 `visible through junction: tr.yaml,us.yaml` 即成功。退出码：3 UAC 被拒，4 nodes 目录不存在，5 找不到内核 home（先在服务模式下启动一次 Verge），6 `runtime\nodes` 已存在但不是指向这里的 junction（不会动它，人工判断）。

## 5. 写/合并全局 Script.js

- **全局 Script.js 是空模板**（只有 `function main(config, profileName) { return config; }` 一类）：直接用 `scripts/Script.js`，按需改 `FIXED_EXITS`。
- **已有其他逻辑**：不要覆盖。把模板里 `FIXED_EXITS`…`applyFixedExits` 整段（`==== clash-fixed-exits` 注释之间、`main` 之前的部分）粘到原文件顶部，在原 `main()` 的 `return config` 前加 `config = applyFixedExits(config);`。如果原 main 返回的是别的变量名，就对那个变量调用。
- **旧版固定出口脚本**（写死节点或写死组名）：用模板替换前先 `node scripts/simulate.js --compare <旧> <新>`，`EQUIVALENT` 才替换（组在界面上的顺序可能不同，只影响显示）。
- 端口别和 `mixed-port`（默认 7897）、`external-controller`（默认 9090）及已有 listener 冲突。
- 写回时 UTF-8 编码（组名是中文）。

## 6. 离线校验

```powershell
node .\scripts\simulate.js "$V\profiles\Script.js"
```
应看到每个 code 一个 `nodes-<code>`（type file，path `./nodes/<code>.yaml`，health-check generate_204 600s，`additional-prefix: 固定|`），一个 `固定<label>` select 组（`use: [nodes-<code>]`），一个 `fixed-<code>-in` mixed listener（127.0.0.1:<port>，proxy `固定<label>`），原有组/listener/provider 保留。

需要的话再做内核语法检查：把应用后的配置写到临时目录，并在临时目录里放一个指向 `<clash目录>\nodes` 的 junction 或副本，然后
`& "C:\Program Files\Clash Verge\verge-mihomo.exe" -t -d <临时目录> -f <临时目录>\config.yaml`，只报告通过/失败，结束后删掉临时目录（里面有密钥）。

## 7. 应用

- **首选**：Verge「订阅」页重新点一下当前 profile（重新激活），Verge 会重跑全局脚本、写 `clash-verge.yaml` 并重载内核。新加国家/改端口也是这样。只改节点文件不需要这一步。
- **备选（不想动界面时）**：把同样的 providers/组/listeners 改进 `<verge目录>\clash-verge.yaml`（先备份），`-t` 通过后
  `PUT http://<controller>/configs?force=true`，头 `Authorization: Bearer <clash-verge.yaml 里的 secret，不打印>`，body `{"path":"","payload":"<clash-verge.yaml 全文>"}`。`path` 不能用（服务模式下同样会报 not subpath of home directory）。注意这只是临时生效，下次 Verge 重新生成时以 Script.js 为准，所以 Script.js 必须已经写好。

## 8. 验证

```powershell
.\scripts\verify.ps1            # 或 -Refresh 先刷新 provider
```
通过标准：
- 每个 `nodes-<code>`：`vehicleType=File`，节点数和文件一致（名字带 `固定|`）。
- 每个固定端口：`tcp=True`，`exit=` 是该国节点的出口 IP（NAT 机器出口可能和拨号 IP 不同，以 deploy 时记录的出口为准）。
- `127.0.0.1:7897` 仍正常（出口按规则，可能是别的节点）。
- 手工单测：`curl.exe -s --proxy http://127.0.0.1:<port> https://api.ipify.org`。

`netstat -ano | findstr :790` 有时只列出 UDP 行，TCP 其实在监听，以 curl / `Test-NetConnection` 为准。

## 9. 交付

告诉用户：节点文件路径、端口↔国家对照、在「代理」页「代理集合」刷新、在「固定<国家>」组选节点、备份路径、junction 可能丢失时怎么修（以及可选的自动修复计划任务，需要他同意才装）。
