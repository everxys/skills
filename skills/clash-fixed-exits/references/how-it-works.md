# 原理

验证环境：Clash Verge Rev 2.5.10，服务模式，verge-mihomo 1.19.33，TUN 开，controller `127.0.0.1:9090`（2026-11-11）。

## 数据流

```
应用 --HTTP/SOCKS--> 127.0.0.1:<port>  (listener fixed-<code>-in, type mixed)
                        │ proxy: 固定<label>         ← 绕过 rules
                        ▼
                    组 固定<label> (select, use: [nodes-<code>])   ← Verge 界面点选
                        ▼
                    provider nodes-<code> (type file, path ./nodes/<code>.yaml,
                                           节点名加前缀 "固定|")
                        ▼
                    <内核home>\nodes  ==junction==>  <clash目录>\nodes\<code>.yaml
```

## 和 7897 的关系

- **7897** 是 Verge 的 `mixed-port`（系统代理 / 浏览器入口），流量**走规则**（GEOSITE cn 直连、其余进「节点选择」等）。TUN 接管的流量也走规则。
- **7901/7902/…** 是额外的 `listeners`。listener 指定了 `proxy: 固定<label>`，进来的流量**不看规则**，直接从该组当前选中的节点出去。
- **TUN 不拦截回环。** 应用把代理设为 `127.0.0.1:7902`（如 `HTTPS_PROXY=http://127.0.0.1:7902`）时，这条连接到本机 7902，不会被 TUN 再抓一次，出口就是美国节点。不认代理环境变量的程序仍走 TUN + 规则。
- 两者共用同一个内核、同一份节点连接池；改 profile、切 profile 不影响固定端口（脚本是全局的）。

## 为什么是全局 Script，不是 Merge

- **profile 级 Merge 不处理 `append-proxies`**（2.5.10 实测），节点进不去。
- **全局 Merge 写 `proxy-groups` 会整体覆盖 profile 的组**，订阅 profile 的组会丢。Script 可以"过滤同名再追加"，不影响原有组。
- Script 对每个 profile 都跑，换 profile 固定端口还在。

## 为什么要 junction

服务模式下内核由 `clash-verge-service` 以 SYSTEM 启动，home 是 `%ProgramData%\clash-verge-service\users\<sha256(用户SID)>\runtime`（**不是**服务根目录，也不是 `%APPDATA%` 下的 Verge 目录）。mihomo 只允许 provider `path` 落在 home 或 `SAFE_PATHS` 内，否则报 `path is not subpath of home directory or SAFE_PATHS`。`SAFE_PATHS` 是内核进程的环境变量，由服务决定，用户改不了。所以在 home 里建一个 `nodes` junction 指向用户目录，provider 写相对路径 `./nodes/<code>.yaml`。

home 目录名 = 用户 SID 字符串（如 `S-1-5-21-…-1001`）的 UTF-8 SHA-256 小写十六进制（2026-11-11 在 2.5.10 上核对一致）。普通用户进程列不了 `clash-verge-service\users`，只有管理员能看，所以 `make-junction.ps1` 先按 SID 算，提权后再确认目录存在；对不上时退回"唯一一个含 config.yaml 的 users\*\runtime"。
另一种探测：让内核加载一个 `path` 在 home 外的 file provider，controller 的报错里会带路径信息（当初就是这样发现的），但这需要一次配置重载，优先用 SID 计算。
