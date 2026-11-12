# 坑与排错

| 症状 | 原因 | 处理 |
|---|---|---|
| provider 报 `path is not subpath of home directory or SAFE_PATHS` | provider `path` 在内核 home 外（例如写了 `C:\Users\…\nodes\us.yaml` 绝对路径） | path 用 `./nodes/<code>.yaml`，在 home 里建 junction |
| 建了 junction 还是找不到文件 | junction 建在服务根目录 `clash-verge-service\` 或 `users\<hash>\` 下 | home 是 `users\<hash>\runtime` 子目录，junction 必须是 `runtime\nodes` |
| 7901/7902 突然连不上，日志里 provider 读文件失败 | junction 被清掉（服务重装、Verge 升级可能重建 runtime；是否发生尚未实测确认） | 重跑 `make-junction.ps1`；常发生就装计划任务（用户同意后） |
| 端口能连但出口不对 | 组里选错节点，或节点文件改了没刷新 | 刷新 provider，组里重选；`verify.ps1` |
| 「固定<国家>」组是空的 | 节点文件不存在 / 格式错（顶层不是 `proxies:`）/ junction 不对 | 检查文件和 junction，刷新 provider |
| 把 `tr.yaml` 导入成订阅并激活后断网 | 节点文件不是 profile，没有规则和组 | 切回原 profile；那条订阅可以删，删订阅不会删 `nodes\tr.yaml` |
| 用全局 Merge 写组后订阅 profile 的组没了 | 全局 Merge 的 `proxy-groups` 整体覆盖 | 用全局 Script（过滤同名再追加） |
| profile Merge 里写 `append-proxies` 没效果 | Verge 2.5.10 profile 级 Merge 不处理它 | 节点放 provider 文件（本方案）或 profile 的 proxies 扩展 |
| `netstat` 只看到 UDP 7901 | 显示问题，TCP 实际在听 | 用 curl / `Test-NetConnection` 判断 |
| 改了 Script.js 没生效 | Verge 只在激活/重新生成时跑脚本 | 重新激活当前 profile |
| 端口冲突、内核起不来 | listener 端口和 mixed-port/controller/其他程序冲突 | 换端口，`Get-NetTCPConnection -LocalPort <port>` 先查 |
| `make-junction.ps1` 退出码 5 | 普通用户看不到 users 目录，或服务从没以此用户跑过 | 先在服务模式下开一次 Verge；或 `-RuntimeDir` 手工指定 |
| 列 `C:\ProgramData\clash-verge-service\users` 报不存在 | 非管理员没权限，不代表目录不存在 | 用 make-junction（会提权） |

## 读配置时的安全

- `profiles.yaml` 含订阅 URL 和 token：只用 `Select-String` 按键名看结构，不整份读。
- `clash-verge.yaml` 含 controller `secret` 和节点密钥：只读需要的标量（`mixed-port`、`external-controller`），secret 只放进请求头不打印。
- 节点文件、`vps-<ip>.yaml`：只列键名和 `name`。
- 万一密钥/token 出现在输出里：不保存、不复述，并建议用户重置（订阅后台重置链接；节点可用 deploy-vless-reality 轮换密钥）。
