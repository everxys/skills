# 节点文件

- 位置：`<clash目录>\nodes\<code>.yaml`，`<code>` 和 `FIXED_EXITS` 里的 code 一致（小写）。
- 格式：mihomo proxy-provider 文件，**顶层只需要 `proxies:`**，下面是和 profile 里一模一样的节点条目。没有 rules、proxy-groups，所以它**不是 profile**，别导入 Verge。
- 节点名在同一文件内唯一；界面上会显示为 `固定|<name>`（provider 加前缀），不会和 profile 自带的同名节点冲突。
- 文件含密钥：不要放进共享目录或版本库；读它时只看键名和节点名。
- 编码 UTF-8（无 BOM 也可），LF 或 CRLF 都行。

示例见 `examples/nodes-xx.example.yaml`（全是占位符）。

## 从 vps-<ip>.yaml 拷节点

`deploy-vless-reality` 生成的 `<clash目录>\vps-<ip>.yaml` 顶层有块状 `proxies:` 列表。

- 脚本：`scripts/add-node.ps1 -From <clash目录>\vps-<ip>.yaml -Code us [-Label 美国]`。会先备份目标文件（`.bak-<ts>`），查重名，追加，只打印节点名。
- 手工：用编辑器打开 `vps-<ip>.yaml`，复制 `proxies:` 下从 `- name:` 开始的整个条目（含 `reality-opts` 缩进块），粘到 `nodes\<code>.yaml` 的 `proxies:` 下面，缩进保持两个空格。
- 一个国家多个节点就往同一个文件里加多条；组里点选，或者以后把组 type 改成 `url-test`/`fallback`（改模板里的 `type: "select"`）。

删节点：删掉对应条目，保存，刷新 provider。如果被删的正是组里当前选中的，mihomo 会自动落到组里第一个节点。
