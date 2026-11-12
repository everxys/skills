---
name: toolbox-tauri-app
description: Use when working in the toolbox repo (Tauri + React + Rust).
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [tauri, react, rust, desktop, android]
    related_skills: [implement, code-review, tdd]
---

# toolbox（Tauri v2 + React + Rust）工作规范

仓库根：`C:\Users\everx\dev\toolbox`。桌面与安卓共用同一份 Rust 核心，前端按 tool 目录自动注册。

## When to Use

在 `C:\Users\everx\dev\toolbox` 里做任何改动时（新增/修改 tool、记账与抖音后端、桌面与安卓共用核心、删掉某个功能），开工前加载本技能；它给出验证门、删功能收尾清单和记账专项约定。修改 Hermes 自身配置或与本仓库无关的通用重构，不适用。

## 先读什么

- `AGENTS.md` 是硬契约：Tauri 命令名/参数名、camelCase JSON 形状、`toolbox.db` 表结构、用户数据位置、抖音 `douyin://` 代理与 vendor 子模块只读。改动前读它，**不要**在技能里重抄这些地图。
- 一个 tool 只碰自己的三处文件（`src/plugins/<id>/tool.manifest.tsx`、`src-tauri/src/<id>/mod.rs`、`src-tauri/src/commands/<id>.rs`），共享文件（registry、build.rs、SwitchBar）不该为新增 tool 而改。

## 验证门（改完按顺序跑，别只跑一条）

```bash
cd /c/Users/everx/dev/toolbox
export PATH="/c/Users/everx/AppData/Local/mise/installs/node/26.7.0:$PATH"   # mise 的 node/npm 不在全局 PATH
node --test src/plugins/<tool>/*.test.ts    # 最快的一轮反馈，先跑这个
npx tsc --noEmit
npm test && npm run build
cargo test --manifest-path src-tauri/Cargo.toml --all-targets --locked
```

- 前端纯逻辑测试走裸 `node --test`；不要 import `src/toolbox/registry.ts`（`import.meta.glob` 是 Vite 专属，裸 node 不认）。
- `cargo test` 会把 `src-tauri` 的所有 bin（含 `accounting_mcp`）一起编译，所以“命令被删/签名改了但别处还在调”这类断裂会在这一步暴露，不必单独 build 再验。
- `npx tsc --noEmit` 的报错可能来自你没碰的文件（例如并行改的 `plugins/library`）。先按路径分清归属，再决定是不是自己的锅，别顺手去修别人的半成品。

## 安卓真机

安装/拉起/验证的完整流程（设备 serial、锁屏码、无线重连、logcat、截图）在 `android-adb-devices` 技能，所有安卓 APP 通用，这里不重写。本仓库只多两条：

- 产物：`src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release.apk`，package `com.toolbox.app`。
- 真机验证前先跑 `android-adb-devices` 的 `adb-pick.sh` 看哪台在线（两台都可能不在），谁在线用谁；别写死 IP、也别默认某台一定可用。

## 编辑工具的坑

- 用 `execute_code` 里的 python 改过文件之后，`write_file` 可能以 `stale_write_blocked` 拒绝整文件重写（读取记账与磁盘不一致，即使刚刚 read 过）。此时：小改用 `patch`；要整文件重写就继续在 execute_code 里 `open(p, 'w', encoding='utf-8', newline='\n').write(s)`。
- 写盘统一 UTF-8 + LF，跟仓库既有风格一致。

## 删除 / 收敛一个功能的收尾清单

命令层 `#[tauri::command]` → 移动端补 `// @mobile`（或反注册）→ MCP 工具（`src-tauri/src/bin/*_mcp.rs`）→ Rust 类型与仓储 → 前端 api 函数/类型/调用点 → 测试 → `README.md` 的能力描述 → `src/toolbox/toolRegistration.test.ts`。

删完要证明它真的不在了：跑 MCP `tools/list` 看工具清单，而不是“编译过了就算”。残余的手写调用点（api.ts 里的 invoke、移动端页面）比编译错误更常见，用 `search_files` 全仓搜函数名兜底。

## 设计偏好（这个用户的取舍标准）

- **单一真相源**：同一件事只能在一个地方改。发现产品的两个控件在改同一件事（例如“跟踪币种”与账户币种下拉、手动覆盖与自动汇率）就会要求删掉冗余的那个。新增设置前先问：有没有第二处能改同一件事？有就先合并。
- 设置项要管到底：一处“启用 X”应当同时决定下拉选项、列表展示、后台抓取三处行为，否则算没做完。
- 停用/缺失要当面说清（“缺汇率”“这些账户的币种没有启用”），不要静默按 0 或按 1 折算。

## 记账（accounting）专项

- 设置存 `accounting_settings(key, value)` 键值表，汇率在 `accounting_rates`。**改设置键名时必须读旧键迁移**（旧值写入新键 + 删旧键），并补一个“旧库只有旧键时行为不变”的单测；历史库不能因为改名读崩。
- 币种不变量：主币种永远启用（由 `activeCurrencies(settings)` 并入）。前端下拉/汇率表/后端抓取读的必须是同一个启用集合，否则会出现“表里没有但后台在拉”的错位。
- 新增币种代码要补 `currencyLabel` 中文名（下拉显示 `BTC · 比特币`），统一过 `normalizeCurrency`（大小写/空白归一）。
- 后端联调不开 GUI：见 `references/accounting-backend-probe.md`（临时库 + JSON-RPC 管道，几十秒确认抓取集合、设置迁移、工具清单）。
