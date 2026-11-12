---
name: android-file-transfer
description: Transfer files between PC and Android phone (push files to phone, pull files from phone, install APKs) over wireless debugging (ADB Wi-Fi) or USB cable. Automatically locates ADB, discovers connected devices (e.g. PKH-110, OPPO, Xiaomi, OnePlus, Pixel, or IP endpoints), refreshes phone media storage, and manages wireless pairing/connecting. Use when the user asks to send/transfer files to phone, receive/pull files from phone, export photos/downloads, install APKs, or operate Android files via wireless debugging or ADB.
---

# Android File Transfer (ADB & Wireless Debugging)

This skill provides fast, reliable, bi-directional file transfer between a PC and Android mobile devices using ADB (USB or Wi-Fi Wireless Debugging).

## Core Capabilities

1. **Auto ADB & Device Discovery**: Automatically locates `adb.exe` (in PATH or Android SDK platform-tools) and targets active devices (e.g. `PKH-110` / `192.168.0.3:5555`).
2. **Push (Send to Phone)**: Send files or folders to the phone (defaults to `/sdcard/Download/`) and immediately triggers the Android Media Scanner so files appear in the phone's File Manager / Gallery without rebooting.
3. **Pull (Fetch from Phone)**: Fetch files, documents, screenshots, or camera photos from the phone to the PC.
4. **Wireless Debugging**: Connect (`adb connect`) and pair (`adb pair`) wireless debugging endpoints.
5. **APK Installation**: Install APK packages directly to the connected phone.

---

## Bundled Helper Script

The skill includes a pre-built PowerShell helper script at `scripts/transfer.ps1`.

### 1. View Connected Devices
```powershell
pwsh -File scripts/transfer.ps1 devices
```

### 2. Send Files to Phone (Push)
Default destination is `/sdcard/Download/`:
```powershell
# Send to default /sdcard/Download/
pwsh -File scripts/transfer.ps1 push "C:\path\to\file.yaml"

# Send to custom path on phone
pwsh -File scripts/transfer.ps1 push "C:\path\to\file.yaml" "/sdcard/Documents/"

# Target a specific device (by model or IP)
pwsh -File scripts/transfer.ps1 push "C:\path\to\file.yaml" -Device "PKH110"
```

### 3. Fetch Files from Phone (Pull)
Default destination is current directory:
```powershell
# Pull specific file to current folder
pwsh -File scripts/transfer.ps1 pull "/sdcard/Download/example.pdf"

# Pull file to specific local folder
pwsh -File scripts/transfer.ps1 pull "/sdcard/DCIM/Screenshots/screenshot.png" "C:\Users\everx\Downloads\"
```

### 4. Connect via Wireless Debugging
```powershell
# Connect to an IP on port 5555 (default port if omitted)
pwsh -File scripts/transfer.ps1 connect 192.168.0.3:5555

# Pair with a 6-digit code (Android 11+ wireless pairing)
pwsh -File scripts/transfer.ps1 pair 192.168.0.3:38475 123456
```

### 5. List Files on Phone
```powershell
# List /sdcard/Download/
pwsh -File scripts/transfer.ps1 ls

# List specific folder
pwsh -File scripts/transfer.ps1 ls "/sdcard/DCIM/Camera"
```

### 6. Install APK to Phone
```powershell
pwsh -File scripts/transfer.ps1 install "C:\path\to\app-release.apk"
```

---

## Common Android Paths Reference

| Storage Category | Standard Path |
| :--- | :--- |
| **Download / 下载** | `/sdcard/Download/` |
| **Camera Photos / 相机** | `/sdcard/DCIM/Camera/` |
| **Screenshots / 截屏** | `/sdcard/DCIM/Screenshots/` or `/sdcard/Pictures/Screenshots/` |
| **Documents / 文档** | `/sdcard/Documents/` |
| **WeChat Download / 微信下载** | `/sdcard/Android/data/com.tencent.mm/MicroMsg/Download/` or `/sdcard/Download/WeiXin/` |
| **Clash / Configs** | `/sdcard/Download/` (easiest for app file picker) |

---

## Troubleshooting Wireless Debugging

1. **Device Disconnected / Offline**:
   - Check if phone's Wi-Fi changed or disconnected.
   - On the phone: `Settings -> Developer Options -> Wireless Debugging` (设置 -> 开发者选项 -> 无线调试).
   - Ensure the IP address and port match: `pwsh -File scripts/transfer.ps1 connect <IP>:<PORT>`.
2. **Permission Denied / Unauthorized**:
   - Check phone screen for "Always allow debugging from this computer" prompt and tap **Allow**.
3. **File not showing up in File Manager**:
   - The script automatically triggers `am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE`. If the phone ROM restricts broadcasts, pull down to refresh in the phone's File Manager or restart the File Manager app.
