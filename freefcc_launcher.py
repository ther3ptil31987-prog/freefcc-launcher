"""
FreeFCC Launcher — a Windows .exe that installs FreeFCC onto a DJI RC Pro 2
or RC Plus controller over USB, the same way the OpenFCC launcher does it.

Step 1: CONNECT    — detect DJI controller via adb devices -l
Step 2: USB DEBUG   — show per-model guide, auto-advance when ADB bridge is up
Step 3: INSTALL     — download FreeFCC APK + adb install -r + grant permissions
Step 4: DONE        — success screen

No server, no license, no terminal. Just plug in USB and click.
"""
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from tkinter import (
    Tk, ttk, StringVar, BooleanVar, IntVar, messagebox,
    scrolledtext, filedialog, DISABLED, NORMAL, END, INSERT
)

APP_VERSION = "1.0.0"
APP_NAME = "FreeFCC Launcher"

FREEFCC_GITHUB_URL = "https://github.com/doesthings/FreeFCC/releases/download/v1.1/FreeFCC.apk"
FREEFCC_PACKAGE = "com.freefcc.app"
FREEFCC_MAIN_ACTIVITY = "com.freefcc.app.MainActivity"

MODEL_MAP = {
    "rc520": "DJI RC Pro 2",
    "rm700": "DJI RC Plus",
    "RM700": "DJI RC Plus",
    "rc331": "DJI RC 2",
    "rm510": "DJI RC Pro",
    "rm500": "DJI Smart Controller",
    "rm330": "DJI RC",
}

DJI_CODE_RE = re.compile(r"^(rc|rm)[a-z]*\d", re.IGNORECASE)

# USB debugging guide steps (same as OpenFCC launcher)
USB_GUIDE_STEPS = [
    ("Open Settings",
     "Swipe down from the top of the controller screen and tap the gear (Settings) icon."),
    ("Open About",
     "Scroll down and tap 'About this device' (or 'About' / 'About tablet')."),
    ("Tap Build Number 7 times",
     "Find 'Build number' (or 'Build version') and tap it 7 times rapidly.\nYou'll see 'You are now a developer!' after the 7th tap."),
    ("Go back to Settings",
     "Press the back button to return to the main Settings screen."),
    ("Open Developer Options",
     "Scroll down — you'll now see 'Developer options' near the bottom. Tap it."),
    ("Enable USB Debugging",
     "Find 'USB debugging' and toggle it ON."),
    ("Accept the prompt",
     "A dialog appears on the controller: 'Allow USB debugging?'\nTick 'Always allow from this computer' and tap OK."),
]


def get_adb_path():
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    adb = base / "adb.exe"
    if not adb.exists():
        found = shutil.which("adb")
        if found:
            return found
    return str(adb)


def run_adb(args, timeout=30):
    adb = get_adb_path()
    cmd = [adb] + args
    flags = 0x08000000 if platform.system() == "Windows" else 0  # CREATE_NO_WINDOW
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=flags)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "adb timed out"
    except FileNotFoundError:
        return -2, "", f"adb binary not found: {adb}"
    except Exception as e:
        return -3, "", str(e)


def parse_devices(output):
    devices = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        model = ""
        manufacturer = ""
        brand = ""
        for part in parts[2:]:
            if "=" in part:
                key, _, val = part.partition("=")
                if key == "model":
                    model = val
                elif key == "manufacturer":
                    manufacturer = val
                elif key == "brand":
                    brand = val
        is_dji = ("dji" in manufacturer.lower() or "dji" in brand.lower()
                  or DJI_CODE_RE.match(model) is not None
                  or DJI_CODE_RE.match(serial) is not None)
        display = MODEL_MAP.get(model, model if model else "DJI Controller")
        if is_dji or model:
            devices.append({"serial": serial, "state": state, "model": model,
                           "display": display, "manufacturer": manufacturer})
    return devices


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_file(url, dest, on_progress=None, on_status=None):
    if on_status:
        on_status(f"Downloading...")
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = resp.headers.get("Content-Length")
        total = int(total) if total else 0
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress:
                    on_progress(downloaded / total if total > 0 else 0)
    if on_status:
        on_status(f"Downloaded {downloaded:,} bytes")


class LauncherApp:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} v{APP_VERSION}")
        root.minsize(720, 680)
        root.geometry("720x720")

        # State
        self.current_step = IntVar(value=0)  # 0=connect, 1=usb, 2=install, 3=done
        self.apk_path = StringVar()
        self.apk_ready = BooleanVar(value=False)
        self.apk_local = BooleanVar(value=False)
        self.device_serial = StringVar(value="")
        self.device_model = StringVar(value="")
        self.device_state = StringVar(value="—")
        self.is_busy = BooleanVar(value=False)
        self.progress_val = IntVar(value=0)
        self.progress_text = StringVar(value="")
        self.locked_serial = None
        self.expected_model = None
        self.polling = True

        self._build_ui()
        self._start_polling()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        # Header
        ttk.Label(main, text=APP_NAME, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(main, text="Install FreeFCC onto your DJI RC Pro 2 / RC Plus — no terminal, no adb, no server",
                  font=("Segoe UI", 10), foreground="#666").pack(anchor="w")
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=(8, 12))

        # Step badges
        self.step_frame = ttk.Frame(main)
        self.step_frame.pack(fill="x", pady=(0, 12))
        self.step_labels = []
        step_names = ["1. Connect", "2. USB Debug", "3. Install", "4. Done"]
        for i, name in enumerate(step_names):
            badge = ttk.Label(self.step_frame, text=f"  {name}  ", font=("Segoe UI", 10, "bold"),
                             relief="solid", padding=(12, 6))
            badge.grid(row=0, column=i, padx=4, sticky="ew")
            self.step_frame.columnconfigure(i, weight=1)
            self.step_labels.append(badge)
        self._update_step_badges()

        # Content area — one frame per step
        self.content = ttk.Frame(main)
        self.content.pack(fill="both", expand=True)

        # Step 0: Connect
        self.frame_connect = ttk.Frame(self.content)
        self._build_connect_step(self.frame_connect)

        # Step 1: USB Debug
        self.frame_usb = ttk.Frame(self.content)
        self._build_usb_step(self.frame_usb)

        # Step 2: Install
        self.frame_install = ttk.Frame(self.content)
        self._build_install_step(self.frame_install)

        # Step 3: Done
        self.frame_done = ttk.Frame(self.content)
        self._build_done_step(self.frame_done)

        self._show_step(0)

        # Progress + log at bottom (always visible)
        bottom = ttk.Frame(main)
        bottom.pack(fill="x", pady=(8, 0))
        self.progress_bar = ttk.Progressbar(bottom, variable=self.progress_val, maximum=100)
        self.progress_bar.pack(fill="x")
        ttk.Label(bottom, textvariable=self.progress_text, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 4))

        log_frame = ttk.LabelFrame(main, text="Activity Log", padding=4)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 9),
                                                     wrap="none", state=DISABLED)
        self.log_widget.pack(fill="both", expand=True)

    def _build_connect_step(self, frame):
        ttk.Label(frame, text="Connect Your Controller", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(4, 8))
        ttk.Label(frame, text="Plug your DJI RC Pro 2 or RC Plus into your computer using a USB cable.\n"
                  "The controller will appear here once it's connected.",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))

        info_box = ttk.LabelFrame(frame, text="Detected Controller", padding=10)
        info_box.pack(fill="x", pady=(0, 12))
        grid = ttk.Frame(info_box)
        grid.pack(fill="x")
        ttk.Label(grid, text="Model:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.lbl_model = ttk.Label(grid, textvariable=self.device_model, font=("Segoe UI", 12, "bold"), foreground="#2196F3")
        self.lbl_model.grid(row=0, column=1, sticky="w")
        ttk.Label(grid, text="Serial:", font=("Segoe UI", 10)).grid(row=0, column=2, sticky="w", padx=(16, 8))
        ttk.Label(grid, textvariable=self.device_serial, font=("Segoe UI", 9)).grid(row=0, column=3, sticky="w")
        ttk.Label(grid, text="Status:", font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(4, 0))
        self.lbl_state = ttk.Label(grid, textvariable=self.device_state, font=("Segoe UI", 10, "bold"), foreground="#FF9800")
        self.lbl_state.grid(row=1, column=1, sticky="w", pady=(4, 0))

        self.connect_hint = ttk.Label(frame, text="Waiting for a DJI controller...",
                                       font=("Segoe UI", 10), foreground="#888")
        self.connect_hint.pack(anchor="w", pady=(4, 0))

        self.btn_connect = ttk.Button(frame, text="Continue →", state=DISABLED, command=self._advance_to_usb)
        self.btn_connect.pack(anchor="e", pady=(12, 0))

    def _build_usb_step(self, frame):
        ttk.Label(frame, text="Enable USB Debugging", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(4, 8))
        self.usb_model_label = ttk.Label(frame, text="", font=("Segoe UI", 11, "bold"), foreground="#2196F3")
        self.usb_model_label.pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text="Follow these steps on your controller's screen:",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))

        steps_box = ttk.LabelFrame(frame, text="Steps", padding=12)
        steps_box.pack(fill="both", expand=True, pady=(0, 8))
        self.usb_step_labels = []
        for i, (title, body) in enumerate(USB_GUIDE_STEPS):
            num = ttk.Label(steps_box, text=str(i + 1), font=("Segoe UI", 14, "bold"),
                           foreground="#2196F3", width=3)
            num.grid(row=i, column=0, sticky="nw", pady=(0, 8))
            if i == 2:
                # Emphasis on the build-number step
                title_label = ttk.Label(steps_box, text=title, font=("Segoe UI", 11, "bold"), foreground="#E91E63")
                body_label = ttk.Label(steps_box, text=body, font=("Segoe UI", 10), foreground="#E91E63", wraplength=500, justify="left")
            else:
                title_label = ttk.Label(steps_box, text=title, font=("Segoe UI", 11, "bold"))
                body_label = ttk.Label(steps_box, text=body, font=("Segoe UI", 10), foreground="#666", wraplength=500, justify="left")
            title_label.grid(row=i, column=1, sticky="nw", pady=(0, 2))
            body_label.grid(row=i, column=2, sticky="nw", padx=(8, 0), pady=(0, 8))
            self.usb_step_labels.append((title_label, body_label))

        self.usb_status = ttk.Label(frame, text="Waiting for USB debugging to be enabled...",
                                     font=("Segoe UI", 10), foreground="#FF9800")
        self.usb_status.pack(anchor="w")

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="← Back", command=self._back_to_connect).pack(side="left")
        self.btn_usb_next = ttk.Button(btns, text="Continue →", state=DISABLED, command=self._advance_to_install)
        self.btn_usb_next.pack(side="right")

    def _build_install_step(self, frame):
        ttk.Label(frame, text="Install FreeFCC", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(4, 8))

        # APK source
        apk_box = ttk.LabelFrame(frame, text="FreeFCC APK", padding=10)
        apk_box.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(apk_box)
        row.pack(fill="x")
        self.apk_status_label = ttk.Label(apk_box, text="Click 'Download' to get FreeFCC from GitHub", font=("Segoe UI", 10))
        self.apk_status_label.pack(anchor="w", pady=(4, 0))
        btns = ttk.Frame(apk_box)
        btns.pack(fill="x", pady=(4, 0))
        self.btn_download = ttk.Button(btns, text="Download from GitHub", command=self._download_apk)
        self.btn_download.pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Browse local APK…", command=self._browse_apk).pack(side="left")

        # Install button
        self.btn_install = ttk.Button(frame, text="Install FreeFCC onto Controller", state=DISABLED,
                                       command=self._do_install)
        self.btn_install.pack(fill="x", pady=(8, 0))

        # Back/Next
        btns2 = ttk.Frame(frame)
        btns2.pack(fill="x", pady=(8, 0))
        ttk.Button(btns2, text="← Back", command=self._back_to_usb).pack(side="left")
        self.btn_install_next = ttk.Button(btns2, text="Done →", state=DISABLED, command=self._advance_to_done)
        self.btn_install_next.pack(side="right")

    def _build_done_step(self, frame):
        ttk.Label(frame, text="Setup Complete!", font=("Segoe UI", 18, "bold"), foreground="#4CAF50").pack(anchor="w", pady=(4, 8))
        ttk.Label(frame, text="FreeFCC has been installed on your controller.\n\n"
                  "To turn on FCC mode:\n"
                  "  1. Open FreeFCC on your controller's home screen\n"
                  "  2. Tap Connect\n"
                  "  3. Tap Enable FCC Mode\n"
                  "  4. Wait for the green checkmark\n\n"
                  "To verify: open DJI Fly, go to the Transmission tab,\n"
                  "and check the signal graph extends past 1km.",
                  font=("Segoe UI", 11), justify="left").pack(anchor="w", pady=(0, 12))
        ttk.Button(frame, text="Set up another controller", command=self._reset).pack(anchor="w")

    # --- Step management ---
    def _show_step(self, step):
        for f in [self.frame_connect, self.frame_usb, self.frame_install, self.frame_done]:
            f.pack_forget()
        frames = [self.frame_connect, self.frame_usb, self.frame_install, self.frame_done]
        frames[step].pack(fill="both", expand=True)
        self.current_step.set(step)
        self._update_step_badges()

    def _update_step_badges(self):
        step = self.current_step.get()
        for i, label in enumerate(self.step_labels):
            if i < step:
                label.config(foreground="#4CAF50", background="#1B5E20")
            elif i == step:
                label.config(foreground="#2196F3", background="#0D47A1")
            else:
                label.config(foreground="#888", background="#333")

    def _set_busy(self, busy):
        self.is_busy.set(busy)

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_widget.config(state=NORMAL)
        self.log_widget.insert(END, f"[{ts}] {msg}\n")
        self.log_widget.see(END)
        self.log_widget.config(state=DISABLED)

    def set_progress(self, pct, text=""):
        self.progress_val.set(int(pct))
        if text:
            self.progress_text.set(text)

    # --- Device polling ---
    def _start_polling(self):
        def poll():
            while self.polling:
                if not self.is_busy.get():
                    self.root.after(0, self._poll_devices)
                time.sleep(2)
        threading.Thread(target=poll, daemon=True).start()

    def _poll_devices(self):
        rc, out, err = run_adb(["devices", "-l"], timeout=10)
        if rc != 0:
            self.device_model.set("ADB not found")
            self.device_serial.set("")
            self.device_state.set("error")
            return
        devices = parse_devices(out)
        dji = [d for d in devices if d.get("model") or d.get("display")]
        if dji:
            dev = dji[0]
            self.device_serial.set(dev["serial"])
            self.device_model.set(dev["display"])
            self.device_state.set(dev["state"])
            self.expected_model = dev["model"]

            state_colors = {"device": "#4CAF50", "unauthorized": "#FF9800", "offline": "#F44336"}
            self.lbl_state.config(foreground=state_colors.get(dev["state"], "#888"))

            if dev["state"] == "device":
                if self.current_step.get() == 0:
                    self.connect_hint.config(text="✓ Controller connected and ready!", foreground="#4CAF50")
                    self.btn_connect.config(state=NORMAL)
                elif self.current_step.get() == 1:
                    self.usb_status.config(text="✓ USB debugging is enabled!", foreground="#4CAF50")
                    self.btn_usb_next.config(state=NORMAL)
            elif dev["state"] == "unauthorized":
                if self.current_step.get() == 0:
                    self.connect_hint.config(text="Controller detected. Tap 'Allow USB debugging' on the controller screen.", foreground="#FF9800")
                    self.btn_connect.config(state=DISABLED)
                elif self.current_step.get() == 1:
                    self.usb_status.config(text="Tap 'Allow USB debugging' on the controller screen...", foreground="#FF9800")
                    self.btn_usb_next.config(state=DISABLED)
            elif dev["state"] == "offline":
                if self.current_step.get() == 0:
                    self.connect_hint.config(text="Controller is offline. Try reconnecting the USB cable.", foreground="#F44336")
                    self.btn_connect.config(state=DISABLED)
        else:
            self.device_model.set("—")
            self.device_serial.set("")
            self.device_state.set("not connected")
            if self.current_step.get() == 0:
                self.connect_hint.config(text="Waiting for a DJI controller...", foreground="#888")
                self.btn_connect.config(state=DISABLED)

    # --- Step transitions ---
    def _advance_to_usb(self):
        self.locked_serial = self.device_serial.get()
        self.usb_model_label.config(text=f"{self.device_model.get()} — enable USB debugging")
        self._show_step(1)

    def _advance_to_install(self):
        self._show_step(2)

    def _advance_to_done(self):
        self._show_step(3)

    def _back_to_connect(self):
        self._show_step(0)

    def _back_to_usb(self):
        self._show_step(1)

    def _reset(self):
        self.locked_serial = None
        self.apk_ready.set(False)
        self.apk_status_label.config(text="Click 'Download' to get FreeFCC from GitHub", foreground="#888")
        self.btn_install.config(state=DISABLED)
        self.btn_install_next.config(state=DISABLED)
        self._show_step(0)

    # --- Download APK ---
    def _download_apk(self):
        if self.is_busy.get():
            return
        dest = str(Path(tempfile.gettempdir()) / "FreeFCC.apk")
        self.apk_path.set(dest)
        self._set_busy(True)
        self.btn_download.config(state=DISABLED)
        self.log("Downloading FreeFCC from GitHub...")

        def worker():
            try:
                download_file(FREEFCC_GITHUB_URL, dest,
                    on_progress=lambda p: self.root.after(0, lambda: self.set_progress(p * 100, f"Downloading… {p*100:.0f}%")),
                    on_status=lambda s: self.root.after(0, lambda: self.log(s)),
                )
                self.root.after(0, lambda: self.set_progress(100, "Download complete"))
                sha = sha256_file(dest)
                size_mb = Path(dest).stat().st_size / (1024*1024)
                self.root.after(0, lambda: self.log(f"Downloaded {size_mb:.1f} MB — SHA-256: {sha[:16]}…"))
                self.root.after(0, lambda: self.apk_status_label.config(
                    text=f"✓ Ready — {size_mb:.1f} MB", foreground="#4CAF50"))
                self.apk_path.set(dest)
                self.apk_ready.set(True)
                self.apk_local.set(False)
                self.root.after(0, self._check_install_ready)
                self.root.after(0, lambda: self._set_busy(False))
                self.root.after(0, lambda: self.btn_download.config(state=NORMAL))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Download failed: {e}"))
                self.root.after(0, lambda: self.set_progress(0, f"Failed: {e}"))
                self.root.after(0, lambda: self.apk_status_label.config(text=f"Download failed: {e}", foreground="#F44336"))
                self.root.after(0, lambda: self._set_busy(False))
                self.root.after(0, lambda: self.btn_download.config(state=NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _browse_apk(self):
        path = filedialog.askopenfilename(title="Select FreeFCC APK",
            filetypes=[("APK files", "*.apk"), ("All files", "*.*")])
        if path:
            self.apk_path.set(path)
            self._verify_local_apk(path)

    def _verify_local_apk(self, path):
        if not Path(path).exists():
            self.apk_status_label.config(text="File not found", foreground="#F44336")
            self.apk_ready.set(False)
            return
        try:
            with open(path, "rb") as f:
                magic = f.read(2)
            if magic != b"PK":
                self.apk_status_label.config(text="Not a valid APK", foreground="#F44336")
                self.apk_ready.set(False)
                return
        except Exception:
            pass
        size_mb = Path(path).stat().st_size / (1024*1024)
        sha = sha256_file(path)
        self.apk_status_label.config(text=f"✓ Ready — {size_mb:.1f} MB — SHA: {sha[:16]}…", foreground="#4CAF50")
        self.apk_ready.set(True)
        self.apk_local.set(True)
        self._check_install_ready()

    def _check_install_ready(self):
        if self.apk_ready.get() and self.device_state.get() == "device" and not self.is_busy.get():
            self.btn_install.config(state=NORMAL)

    # --- Install ---
    def _do_install(self):
        if self.is_busy.get():
            return
        serial = self.locked_serial or self.device_serial.get()
        if not serial or self.device_state.get() != "device":
            messagebox.showwarning(APP_NAME, "No controller connected. Go back and connect first.")
            return
        if not self.apk_ready.get():
            messagebox.showwarning(APP_NAME, "Download or browse for the FreeFCC APK first.")
            return

        self._set_busy(True)
        self.btn_install.config(state=DISABLED)
        self.log(f"Installing FreeFCC onto {self.device_model.get()} ({serial})...")

        def worker():
            try:
                self._install_worker(serial)
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Install error: {e}"))
                self.root.after(0, lambda: self.set_progress(0, f"Error: {e}"))
                self.root.after(0, lambda: self._set_busy(False))
                self.root.after(0, lambda: self.btn_install.config(state=NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _install_worker(self, serial):
        apk = self.apk_path.get()

        # Pre-check: is it already installed?
        self.root.after(0, lambda: self.set_progress(5, "Checking existing install..."))
        rc, out, err = run_adb(["-s", serial, "shell", "pm", "path", FREEFCC_PACKAGE], timeout=10)
        already = "package:" in out
        if already:
            self.root.after(0, lambda: self.log("FreeFCC already installed — will update"))

        # Install
        self.root.after(0, lambda: self.set_progress(20, "Installing APK on controller..."))
        self.root.after(0, lambda: self.log(f"adb -s {serial} install -r FreeFCC.apk"))
        rc, out, err = run_adb(["-s", serial, "install", "-r", apk], timeout=120)

        if rc != 0 and ("INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out or "signatures do not match" in (out+err).lower()):
            # Signature mismatch — uninstall old, then install fresh
            self.root.after(0, lambda: self.log("Signature mismatch — uninstalling old version..."))
            run_adb(["-s", serial, "uninstall", FREEFCC_PACKAGE], timeout=60)
            self.root.after(0, lambda: self.set_progress(40, "Reinstalling..."))
            rc, out, err = run_adb(["-s", serial, "install", apk], timeout=120)

        if rc == 0 and ("Success" in out or "success" in out.lower() or "Failure" not in out):
            self.root.after(0, lambda: self.log(f"✓ APK installed"))
        else:
            self.root.after(0, lambda: self.log(f"✗ Install failed: {out.strip()} {err.strip()}"))
            self.root.after(0, lambda: self.set_progress(0, "Install failed"))
            self.root.after(0, lambda: self._set_busy(False))
            self.root.after(0, lambda: self.btn_install.config(state=NORMAL))
            return

        # Verify
        self.root.after(0, lambda: self.set_progress(60, "Verifying install..."))
        rc, out, err = run_adb(["-s", serial, "shell", "pm", "path", FREEFCC_PACKAGE], timeout=10)
        if "package:" in out:
            self.root.after(0, lambda: self.log("✓ Verified: FreeFCC is installed"))

        # Grant permissions (same approach as OpenFCC launcher provisioner)
        self.root.after(0, lambda: self.set_progress(70, "Granting permissions..."))
        self._grant_permissions(serial)

        # Launch the app
        self.root.after(0, lambda: self.set_progress(90, "Launching FreeFCC..."))
        rc, out, err = run_adb(["-s", serial, "shell", "am", "start", "-n",
                                f"{FREEFCC_PACKAGE}/{FREEFCC_MAIN_ACTIVITY}"], timeout=10)
        if rc == 0:
            self.root.after(0, lambda: self.log("✓ FreeFCC launched on controller"))

        # Keep screen awake during FCC apply
        run_adb(["-s", serial, "shell", "settings", "put", "system", "screen_off_timeout", "600000"], timeout=10)

        self.root.after(0, lambda: self.set_progress(100, "Done!"))
        self.root.after(0, lambda: self.log("✓ FreeFCC installed successfully!"))
        self.root.after(0, lambda: self.log("Open FreeFCC on your controller → Connect → Enable FCC Mode"))
        self.root.after(0, lambda: self.btn_install_next.config(state=NORMAL))
        self.root.after(0, lambda: self._set_busy(False))
        self.root.after(0, lambda: self.btn_install.config(state=NORMAL))

    def _grant_permissions(self, serial):
        """Grant the permissions FreeFCC needs — same approach as OpenFCC provisioner."""
        pkg = FREEFCC_PACKAGE

        # pm grant (best-effort, logged but not fatal)
        pm_perms = [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.FOREGROUND_SERVICE",
            "android.permission.WAKE_LOCK",
        ]
        for perm in pm_perms:
            rc, out, err = run_adb(["-s", serial, "shell", "pm", "grant", pkg, perm], timeout=10)
            if rc == 0:
                self.root.after(0, lambda p=perm: self.log(f"  ✓ pm grant {p}"))
            else:
                self.root.after(0, lambda p=perm: self.log(f"  - skip {p} (not applicable)"))

        # appops set (must read back "allow")
        appops = ["FOREGROUND_SERVICE"]
        for op in appops:
            rc, out, err = run_adb(["-s", serial, "shell", "appops", "set", pkg, op, "allow"], timeout=10)
            if rc == 0:
                self.root.after(0, lambda o=op: self.log(f"  ✓ appops set {o} allow"))
                # Read back
                rc2, out2, err2 = run_adb(["-s", serial, "shell", "appops", "get", pkg, op], timeout=10)
                if "allow" in out2.lower():
                    self.root.after(0, lambda o=op: self.log(f"    read-back: allow ✓"))
                else:
                    self.root.after(0, lambda o=op, v=out2.strip(): self.log(f"    read-back: {v}"))

        self.root.after(0, lambda: self.log("  ✓ Screen timeout set to 10 min"))


def main():
    root = Tk()
    app = LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()