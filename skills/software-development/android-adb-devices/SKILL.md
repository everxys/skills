---
name: android-adb-devices
description: Use when testing an Android app on real phones via adb.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [android, adb, device, testing, install]
    related_skills: [toolbox-tauri-app, dogfood]
---

# 安卓真机调试（ADB）

## When to Use

在真机上装/跑/验任何安卓 APP（Tauri、Compose、React Native、Flutter 都算）、需要看 logcat 或截图、或者无线 adb 断了需要重连时加载本技能。代码层面的构建问题（Gradle、Rust、JS 报错）不属于这里。

用户是 Windows + git-bash 环境，手上两部安卓真机通过无线/USB 连到这台电脑。开发**任何**安卓 APP（Tauri、Compose、React Native、Flutter……）并在真机上验证时都走本技能的流程，不绑定某个项目。

## 设备（用型号/硬件序列号认，别用 IP）

IP 是 DHCP 分的，会变；无线调试重开端口也会变；USB 连着时 transport serial 又变成硬件序列号。唯一稳定的身份是 `ro.product.model` + `ro.serialno`。

- **PJE110**（Android 16）硬件序列号 `b7c63663`。
- **PKH110**（Android 17，用户主力机）硬件序列号 `e919fca2`。
- **两台都不保证在线**：可能被带走、关机、断开无线调试，也可能只插了一台 USB。别默认哪台能用——每次先跑 `adb-pick.sh` 看谁在，谁在线就用谁验证。
- 两台锁屏密码都是 `305786`，远程点安装确认框、授权弹窗、或需要点亮解锁时用。密码只存在本技能里：不要写进 memory，不要在聊天里复述。

## 找设备（每次现查，别背 IP）

```bash
S="$HOME/.agents/skills/software-development/android-adb-devices/scripts"
read -r MODEL SERIAL <<< "$(bash "$S/adb-pick.sh")"        # 默认按 PJE110 → PKH110 顺序，返回第一台真在线的
[ -n "${SERIAL:-}" ] || echo '一台都没在线，找用户确认'
"$ADB" -s "$SERIAL" install -r <apk>
```

- `adb-pick.sh [model...]`：不传参数就按 PJE110、PKH110 顺序试，输出 `<model> <serial>`；全都不在线就 exit 1 并打印提示。两台都在线时默认用 PJE110，想指定就 `adb-pick.sh PKH110 PJE110`。
- `adb-find.sh <model> [hw-serial]`：单台解析。先看 `adb devices`，逐个读 `ro.product.model` / `ro.serialno` 匹配；没命中就 `adb mdns services` 取 `_adb._tcp` 端点，依次 `adb connect` 重试几次读属性，命中就打印 transport serial，不匹配的自动 disconnect。只用 `_adb._tcp`，`_adb-tls-connect._tcp` 需要先 `adb pair`。

用户桌面上还有两个 PowerShell 快捷方式（`Toolbox 安装 - PJE110（无线调试）.lnk` / `PKH110`），调 `~/dev/toolbox/scripts/install-android-wireless.ps1 -Model <model>`，同一套 mDNS 发现逻辑，给用户手点用；我这边用上面的 bash 脚本。

## 基础命令

```bash
ADB="C:/Users/everx/AppData/Local/Android/Sdk/platform-tools/adb.exe"   # 不在 PATH，用正斜杠 native 路径
"$ADB" devices -l
```

- 安装/覆盖：`"$ADB" -s <serial> install -r <apk>` —— 多于一台设备时**必须** `-s`。
- 版本核对：`"$ADB" -s <serial> shell dumpsys package <pkg> | grep -E 'versionName|lastUpdateTime'`
- 拉起：`"$ADB" -s <serial> shell am start -W -n <pkg>/.MainActivity`（不确定入口：`cmd package resolve-activity --brief <pkg>`）
- 存活/前台：`pidof <pkg>`、`dumpsys activity activities | grep -m2 topResumedActivity`
- 日志：先 `logcat -c`，再复现，然后 `logcat -d -t 300 | grep -iE '<pkg>|FATAL|AndroidRuntime'`
- 截图：`shell screencap -p /sdcard/s.png` + `pull /sdcard/s.png`，落地后用 `vision_analyze` 看
- 卸载：`"$ADB" -s <serial> uninstall <pkg>`

## 坑

- 同一台手机可能同时以 USB serial 和 `ip:port` 出现（两条 transport），装前先确认是不是同一台，别装两遍。
- 不要写死 IP：`adb connect 192.168.x.x:5555` 只在当下有效，隔天/重启/换网就废。认设备只认型号 + `ro.serialno`。
- 手机上挂着悬浮窗（例如 PKH110 常年挂 Discord）时 `topResumedActivity` 可能不是被测应用，焦点 `false` **不等于**崩溃；用 `pidof` + logcat 判断。
- 重新打开无线调试后端口会变，旧 `ip:5555` 连不上就先 `adb connect`；需要配对码时用 `adb pair <ip:port> <code>`，码在手机屏幕上，我拿不到 —— 直接问用户。
- `adb tcpip 5555` 的老模式重启失效；无线调试重开后端口也会变，所以永远走 mDNS 发现（`adb-find.sh`）或 `adb mdns services` 现查。
- 原生 adb.exe 不认 MSYS 的 `/c/...` 路径，APK 路径也传 `C:/...` 形式。

## 手机锁着时会假装“应用没装”

锁屏（安全锁、重启后未解锁）时，非 directBootAware 的应用无法解析，`am start` 会报 `Error type 3: Activity class does not exist`、`cmd package resolve-activity` 说 `No activity found`，但 `dumpsys package` 里明明有该 activity —— 不是安装坏了，是手机没解锁。

锁定状态与解锁（ColorOS/OnePlus 实测有效）：

```bash
"$ADB" -s $S shell svc power stayon true          # 插着 USB 时别让屏幕又睡下去，否则后面的 tap 全落到息屏上
"$ADB" -s $S shell input keyevent 224             # 亮屏
"$ADB" -s $S shell input keyevent 82              # ColorOS：直接拉起 PIN 键盘（swipe 有时不生效）
"$ADB" -s $S shell dumpsys display | grep -m1 mScreenState   # 必须是 ON，Dozing/OFF 时 tap 无效
"$ADB" -s $S shell uiautomator dump /data/local/tmp/ui.xml && "$ADB" -s $S shell cat /data/local/tmp/ui.xml
```

- 安全锁屏下 `screencap` 截图是纯黑，别拿截图判断屏幕状态 —— 用 `uiautomator dump` 读 UI（能看到 `pinColorNumericKeyboard` 和每个数字键的 bounds）。
- ColorOS 的数字键盘不认 `input text`，按 dump 里的 bounds 逐个 `input tap <x> <y>`（3×4 网格，0 在底行中间）。6 位输完自动提交。
- 验证解锁成功：`dumpsys window | grep -E 'isKeyguardShowing|mCurrentFocus'` → `isKeyguardShowing=false` 且焦点是 launcher。
- 锁屏下 `/sdcard` 不可写，截图/临时文件放 `/data/local/tmp/`。
- 手机输密码失败次数多了会锁死，只能在手机上解锁 —— 试过一次不对就停手问用户。

## 装完要看什么

装成功 ≠ 跑得起来，而且**先解锁手机**（见上一节，否则会误判成“activity 不存在”）。固定顺序：安装 → 版本号核对 → 拉起 → `pidof`/前台 activity → 截图或 logcat 确认无 FATAL。四步都过了才算验证完成。
