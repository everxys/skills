# 日常维护

## 加 / 删节点（最常见）

1. 改 `<clash目录>\nodes\<code>.yaml`：加节点用 `scripts/add-node.ps1 -From <clash目录>\vps-<ip>.yaml -Code <code>`，或手工粘贴条目；删节点就删掉整个条目。先备份（add-node 会自动备份）。
2. 刷新 provider，三选一：
   - Verge「代理」页顶部「代理集合」（Proxy Provider）→ `nodes-<code>` 旁边的刷新按钮；
   - `scripts/verify.ps1 -Refresh`（顺带验证）；
   - `PUT http://<controller>/providers/proxies/nodes-<code>`（带 Bearer secret，不打印）。
3. 在「代理」页「固定<label>」组里选中新节点。
4. 不需要重新激活 profile，不需要重启。

## 加一个新国家

1. 选 code（小写，如 `jp`）、中文名（如 `日本`）、空闲端口（如 `7903`）。
2. 建 `nodes\jp.yaml`（add-node.ps1 会自动建）。
3. 在全局 `Script.js` 的 `FIXED_EXITS` 加一行 `{ code: "jp", label: "日本", port: 7903 },`（先备份）。
4. `node scripts/simulate.js <Script.js>` 看一眼，然后在 Verge 里重新激活当前 profile。
5. `scripts/verify.ps1` 确认 7903 出口。

删国家：表里删行 → 重新激活 profile → 节点文件可留可删。

## 换电脑

把 `<clash目录>\nodes\` 和 skill 一起带过去（节点文件含密钥，用私有方式拷），按 [deploy.md](deploy.md) 从第 1 步走。内核 home 哈希跟用户 SID 走，新电脑一定不同，别复制旧的 make-junction 日志里的路径。

## Verge 升级 / 重装 / 服务重装后

先跑 `scripts/verify.ps1`。端口不通、provider 报错 → `scripts/make-junction.ps1`（一次 UAC）→ 再 verify。频繁丢失的话，征得用户同意后装 `scripts/install-junction-task.ps1`。
