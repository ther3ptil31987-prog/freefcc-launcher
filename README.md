<div align="center">

[![GitHub release](https://img.shields.io/github/v/release/doesthings/freefcc-launcher?style=flat-square)](https://github.com/doesthings/freefcc-launcher/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/doesthings/freefcc-launcher?style=flat-square)](https://github.com/doesthings/freefcc-launcher/stargazers)

# FreeFCC Launcher

### One click installer to put FreeFCC onto your DJI RC Pro 2 or RC Plus

This is just a launcher. It installs the [FreeFCC](https://github.com/doesthings/FreeFCC) app onto your DJI controller over USB. That is all it does. FreeFCC does the actual FCC unlock. This just saves you from having to use a terminal.

[![Star on GitHub](https://img.shields.io/badge/Star%20on%20GitHub-%E2%AD%90-yellow?style=for-the-badge&logo=github)](https://github.com/doesthings/freefcc-launcher)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/freefcc)

</div>

---

> **STATUS: COMPLETELY UNTESTED.** This has not been tested on real hardware yet. It is built to work with the [FreeFCC](https://github.com/doesthings/FreeFCC) app and the DJI RC Pro 2 / RC Plus controllers, but nothing has been verified on an actual device. Use at your own risk. If you test it, please [open an issue](https://github.com/doesthings/freefcc-launcher/issues) with the result.

---

## What This Is

This is a desktop launcher app for Windows. It does one thing: it installs the [FreeFCC](https://github.com/doesthings/FreeFCC) Android app onto your DJI RC Pro 2 or RC Plus controller over a USB cable.

FreeFCC is the app that actually unlocks FCC mode on your drone. It is free and open source, made by the same author. Go to the [FreeFCC repo](https://github.com/doesthings/FreeFCC) for that.

This launcher exists because the RC Pro 2 and RC Plus do not have a memory card slot for sideloading apps like the RC 2 does. You have to install apps over USB using adb. Most people do not want to install the Android SDK and type commands into a terminal just to put an app on their controller. So this launcher does it for you with a click through wizard.

No terminal. No adb to install. No command line. Just plug in, click, and fly.

<div align="center">

| | |
|---|---|
| **Platform** | Windows 64 bit |
| **Size** | ~16 MB single exe, no install needed |
| **Requires** | A USB cable and a DJI RC Pro 2 or RC Plus |
| **Downloads** | FreeFCC APK automatically from GitHub |
| **Status** | COMPLETELY UNTESTED |

</div>

---

## How To Use

### 1. Download the launcher

Download `FreeFCC-Launcher.exe` from the [releases page](https://github.com/doesthings/freefcc-launcher/releases). Save it anywhere on your computer. Double click to run. No installation needed.

### 2. Connect your controller

Plug your DJI RC Pro 2 or RC Plus into your computer using a USB cable. The launcher will detect it automatically within a couple of seconds.

### 3. Enable USB debugging

The launcher shows you step by step how to enable USB debugging on your controller's screen:

1. Open Settings on the controller
2. Go to About
3. Tap Build Number 7 times to unlock Developer Options
4. Go back to Settings
5. Open Developer Options
6. Turn on USB Debugging
7. Accept the "Allow USB debugging" prompt on the controller

The launcher detects when USB debugging is enabled and moves to the next step automatically.

### 4. Install FreeFCC

Click "Download from GitHub" to get the FreeFCC APK. Then click "Install FreeFCC onto Controller". The launcher:

- Downloads the FreeFCC APK from the official GitHub release
- Installs it onto the controller silently, no terminal visible
- Grants the permissions FreeFCC needs
- Launches FreeFCC on the controller
- Sets the screen to stay awake for 10 minutes so the FCC apply does not get interrupted

### 5. Turn on FCC mode

FreeFCC opens on your controller. Tap **Connect**, then tap **Enable FCC Mode**. Wait for the green checkmark.

To verify it worked, open DJI Fly on the controller, go to the Transmission tab, and look at the signal graph. If the signal bar extends past the 1km mark, your drone is in FCC mode. If it barely reaches 1km, you are still in CE mode.

### To undo

Tap **Stop FCC Mode** in FreeFCC to restore CE mode. Or just reboot the controller. The radio reverts to the factory region on every reboot.

---

## Compatibility

| Controller | Status |
|------------|--------|
| DJI RC Pro 2 | COMPLETELY UNTESTED |
| DJI RC Plus | COMPLETELY UNTESTED |
| DJI RC 2 | Use the SD card method instead, see the [FreeFCC readme](https://github.com/doesthings/FreeFCC#install-guide) |

FreeFCC itself works on the RC 2 and has been tested there. This launcher targets the RC Pro 2 and RC Plus which install apps over USB instead of SD card. Neither the launcher nor FreeFCC have been tested on the RC Pro 2 or RC Plus yet.

---

## How It Works

The launcher bundles the Android Debug Bridge (adb) binary inside the exe. When you run it, the exe extracts adb to a temporary folder and uses it to talk to the controller over USB. Every adb command runs silently with no visible terminal window.

### FCC Mode Install

The installation process:

1. **Detect** the controller by polling adb devices every 2 seconds
2. **Guide** the user through enabling USB debugging on the controller screen
3. **Download** the FreeFCC APK from the official GitHub release
4. **Install** the APK on the controller with adb install
5. **Grant** the runtime permissions FreeFCC needs (pm grant + appops set)
6. **Launch** FreeFCC on the controller

After that, FreeFCC runs on the controller and does the FCC unlock itself by sending 21 DUMPL command frames to the controller's local TCP socket at 127.0.0.1:40009. The frames enter service mode, set the radio region to FCC, write channel maps and power limits, commit the change, and exit service mode. See the [FreeFCC readme](https://github.com/doesthings/FreeFCC#how-it-works) for the full DUMPL protocol details.

### 4G Firmware Swap (Optional, RC Pro 2 Only)

4G mode on the RC Pro 2 requires a controller firmware update that opens the 4G hardware path. Without it, the 4G activation frames have nothing to talk to. The launcher can do this swap for you:

1. **Download** a 937 MB DJI signed OTA firmware package (update.zip) from the GitHub release
2. **Verify** the SHA 256 hash (182e459b...) against the expected value
3. **Push** the firmware to /sdcard/update.zip on the controller via adb
4. **Verify** the on device copy by hashing it with sha256sum (or size + ZIP magic check if no hasher)
5. **Flash** via update_engine_client --path=/sdcard/update.zip --update (up to 12 attempts, 25 min total timeout, resumes from checkpoint on interruption)
6. **Reboot** the controller and wait for it to come back online
7. **Cleanup** the temporary update.zip files

After the firmware swap, open FreeFCC on the controller and tap "Turn 4G ON". FreeFCC sends 128 DUMPL frames to the 4G module via a Unix domain socket at /duss/mb/0x205 (abstract namespace). Each frame carries the aircraft serial number in its payload.

Supported aircraft for 4G: Mavic 4 Pro, Air 3S, Air 3, Mini 4 Pro.

The firmware swap is optional. If you only want FCC mode, skip it entirely.

### What Gets Installed

| Component | What | Size |
|-----------|------|------|
| FreeFCC APK | The FCC unlock app (from GitHub) | ~19 MB |
| 4G Firmware | DJI signed OTA for RC Pro 2 (optional) | ~937 MB |

### ADB Commands Used

The launcher runs these adb commands silently (no terminal visible to the user):

```
adb devices -l                              # detect controller
adb -s <serial> install -r FreeFCC.apk      # install the app
adb -s <serial> shell pm grant <perm>      # grant permissions
adb -s <serial> shell appops set <op> allow # grant appops
adb -s <serial> shell am start -n <activity> # launch the app
adb -s <serial> push update.zip /sdcard/    # push firmware (4G swap)
adb -s <serial> shell update_engine_client --update  # flash (4G swap)
adb -s <serial> shell reboot                # reboot (4G swap)
```

---

## Building From Source

Requirements: Python 3.12+, [PyInstaller](https://pyinstaller.org/).

```powershell
cd C:\path\to\freefcc-launcher

# Put adb.exe, AdbWinApi.dll, AdbWinUsbApi.dll in the folder
# (from Android platform-tools)

python -m PyInstaller freefcc_launcher.spec --noconfirm --clean
```

Output is in `dist/FreeFCC-Launcher.exe`.

---

## FreeFCC

This launcher is just an installer. The actual FCC unlock is done by [FreeFCC](https://github.com/doesthings/FreeFCC):

- Free and open source (AGPL 3.0)
- No server, no license, no subscription, no tracking
- Sends raw DUMPL commands from plain JSON profile files
- Works offline, everything runs locally on the controller
- FCC profile is universal, works on every DJI aircraft model tested

Go star the [FreeFCC repo](https://github.com/doesthings/FreeFCC) if this helped you.

---

## Support

If this launcher helped you out, please consider starring the repo. It helps others find it.

<div align="center">

[![Star on GitHub](https://img.shields.io/badge/Star%20on%20GitHub-%E2%AD%90-yellow?style=for-the-badge&logo=github)](https://github.com/doesthings/freefcc-launcher)

[![Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/freefcc)

</div>

Every contribution helps cover development costs. Thank you.

---

## Disclaimer

This software is provided for educational and research purposes only. Modifying radio transmission parameters may violate laws and regulations in your country or region. In most places, increasing radio power beyond what is legally permitted for your area requires authorization from the relevant regulatory authority.

You are solely responsible for ensuring that your use of this software complies with all applicable local, regional, and national laws. The author of this project accepts no liability for any damage, legal consequences, or regulatory action arising from the use of this tool.

This project is not affiliated with, endorsed by, or sponsored by DJI. Using this tool may void your warranty and DJI Care Refresh coverage.

---

## License

AGPL-3.0. See [LICENSE](LICENSE).