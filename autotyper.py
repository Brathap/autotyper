import tkinter as tk
from tkinter import ttk
import subprocess
import time
import threading
import shutil
import sys
import math
import platform
import queue
import ctypes
import random

# --- CHECK FOR OPTIONAL SPEECH LIBRARY ---
try:
    import speech_recognition as sr
    HAS_SPEECH = True
except ImportError:
    HAS_SPEECH = False

# --- CHECK FOR OPTIONAL PYNPUT LIBRARY ---
try:
    from pynput.keyboard import Key, Controller, Listener
    keyboard = Controller()
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

# --- THEME CONFIGURATION ---
THEME = {
    "bg_app": "#1e1e1e",
    "bg_card": "#2b2b2b",
    "accent": "#4da6ff",
    "success": "#00d26a",
    "stealth": "#bd93f9",
    "danger": "#ff4d4d",
    "text_main": "#ffffff",
    "text_sub": "#aaaaaa",
    "btn_fg": "#ffffff"
}

FONT_HEADER = ("Segoe UI", 12, "bold")
FONT_LABEL = ("Segoe UI", 9)
FONT_BTN = ("Segoe UI", 10, "bold")

# --- ZERO-DEPENDENCY NATIVE TYPERS (Standard Library Only) ---
class NativeKeyboard:
    """Provides pure standard-library keyboard simulation for Windows and macOS when pynput is not installed."""

    @staticmethod
    def is_windows():
        return platform.system() == "Windows"

    @staticmethod
    def is_mac():
        return platform.system() == "Darwin"

    # --- Windows Native Win32 API Implementation via ctypes ---
    @staticmethod
    def win32_send_unicode_char(char):
        if not hasattr(ctypes, 'windll'):
            return False
        user32 = ctypes.windll.user32
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002

        # Send UTF-16 character code
        for unit in char.encode('utf-16-le'):
            pass  # UTF-16 code units
        code = ord(char)
        if code > 0xFFFF:
            # Surrogate pair
            high = 0xD800 + ((code - 0x10000) >> 10)
            low = 0xDC00 + ((code - 0x10000) & 0x3FF)
            user32.keybd_event(0, high, KEYEVENTF_UNICODE, 0)
            user32.keybd_event(0, high, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
            user32.keybd_event(0, low, KEYEVENTF_UNICODE, 0)
            user32.keybd_event(0, low, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
        else:
            user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
            user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
        return True

    @staticmethod
    def win32_send_key(vk_code, shift=False):
        if not hasattr(ctypes, 'windll'):
            return False
        user32 = ctypes.windll.user32
        VK_SHIFT = 0x10
        KEYEVENTF_KEYUP = 0x0002

        if shift:
            user32.keybd_event(VK_SHIFT, 0, 0, 0)
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        if shift:
            user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        return True

    # --- macOS Native AppleScript Implementation via osascript ---
    @staticmethod
    def mac_send_text(text):
        if not shutil.which("osascript"):
            return False
        # Escape quotes and backslashes for AppleScript string literal
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        subprocess.run(["osascript", "-e", script], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    @staticmethod
    def mac_send_key(key, shift=False):
        if not shutil.which("osascript"):
            return False
        # key code 36 = Return, key code 51 = Delete/Backspace
        code = 36 if key == "Return" else (51 if key == "BackSpace" else None)
        if code is None:
            return False
        if shift:
            script = f'tell application "System Events" to key code {code} using shift down'
        else:
            script = f'tell application "System Events" to key code {code}'
        subprocess.run(["osascript", "-e", script], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True


class UniversalGlobalEscListener:
    """Listens globally for ESC key presses across Wayland, X11, Windows, and macOS without requiring pynput."""
    def __init__(self, callback):
        self.callback = callback
        self.running = True
        self.threads = []
        self._start()

    def _start(self):
        sys_name = platform.system()
        if sys_name == "Windows":
            t = threading.Thread(target=self._win_loop, daemon=True)
            t.start()
            self.threads.append(t)
        elif sys_name == "Linux":
            # 1. Direct /dev/input raw hardware listener (works 100% on Wayland/Hyprland)
            t_input = threading.Thread(target=self._linux_evdev_loop, daemon=True)
            t_input.start()
            self.threads.append(t_input)
            # 2. Pynput fallback if available
            if HAS_PYNPUT:
                try:
                    def _on_press(key):
                        if key == Key.esc:
                            self.callback()
                    l = Listener(on_press=_on_press)
                    l.daemon = True
                    l.start()
                except Exception:
                    pass

    def _win_loop(self):
        if not hasattr(ctypes, 'windll'):
            return
        user32 = ctypes.windll.user32
        VK_ESCAPE = 0x1B
        while self.running:
            # Check most significant bit of GetAsyncKeyState
            if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                self.callback()
                time.sleep(0.3)  # Debounce
            time.sleep(0.015)

    def _linux_evdev_loop(self):
        """Reads raw keyboard evdev packets for KEY_ESC (code 1) across all keyboard devices."""
        import glob
        import select
        import struct
        import os

        KEY_ESC = 1
        EV_KEY = 1
        EVENT_SIZE = 24
        EVENT_FORMAT = 'qqHHi'

        device_fds = []
        # Find keyboard event nodes
        for ev_path in glob.glob('/dev/input/event*'):
            try:
                fd = os.open(ev_path, os.O_RDONLY | os.O_NONBLOCK)
                device_fds.append(fd)
            except Exception:
                continue

        if not device_fds:
            return

        try:
            while self.running:
                try:
                    r, _, _ = select.select(device_fds, [], [], 0.1)
                except Exception:
                    break
                for fd in r:
                    try:
                        while True:
                            data = os.read(fd, EVENT_SIZE * 16)
                            if not data:
                                break
                            # Parse all 24-byte event structs in chunk
                            for offset in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
                                chunk = data[offset:offset + EVENT_SIZE]
                                _, _, ev_type, ev_code, ev_value = struct.unpack(EVENT_FORMAT, chunk)
                                # EV_KEY event, KEY_ESC, and press (value == 1 or 2)
                                if ev_type == EV_KEY and ev_code == KEY_ESC and ev_value in (1, 2):
                                    self.callback()
                    except BlockingIOError:
                        pass
                    except Exception:
                        pass
        finally:
            for fd in device_fds:
                try:
                    os.close(fd)
                except Exception:
                    pass

    def stop(self):
        self.running = False


class AutoTyperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Typer")
        self.root.geometry("300x600") 
        self.root.configure(bg=THEME["bg_app"])
        self.root.attributes('-topmost', True)

        # Thread-safe UI update queue
        self.ui_queue = queue.Queue()
        self.root.after(40, self.process_ui_queue)

        # Autodetect OS
        current_sys = platform.system()
        if current_sys == "Darwin":
            detected_os = "macOS"
        elif current_sys == "Windows":
            detected_os = "Windows"
        else:
            detected_os = "Linux"

        self.selected_os = detected_os

        # Detect Linux typing backend based on active display server
        self.tool = None
        self.backend_name = "Universal"
        session_type = sys.platform
        is_wayland = bool(platform.system() == "Linux" and (subprocess.os.environ.get("WAYLAND_DISPLAY") or subprocess.os.environ.get("XDG_SESSION_TYPE") == "wayland"))
        
        if is_wayland:
            if shutil.which("wtype"):
                self.tool = "wtype"
                self.backend_name = "Wayland"
            elif shutil.which("xdotool"):
                self.tool = "xdotool"
                self.backend_name = "XWayland"
        else:
            if shutil.which("xdotool"):
                self.tool = "xdotool"
                self.backend_name = "X11"
            elif shutil.which("wtype"):
                self.tool = "wtype"
                self.backend_name = "Wayland"

        if not self.tool and HAS_PYNPUT:
            self.tool = "pynput"
            self.backend_name = "Pynput"
        elif not self.tool and platform.system() == "Linux":
            self.backend_name = "Need wtype/xdotool"

        self.stop_event = threading.Event()
        self.current_subprocess = None
        self.subprocess_lock = threading.Lock()

        # Universal Global hotkey listener (ESC key) for instant emergency abort across all apps
        self.esc_listener = UniversalGlobalEscListener(self.stop_process)

        # Local window binding for ESC key
        self.root.bind("<Escape>", lambda e: self.stop_process())

        self.setup_ui()
        self.set_os(self.selected_os)

    def process_ui_queue(self):
        while not self.ui_queue.empty():
            try:
                fn = self.ui_queue.get_nowait()
                fn()
            except queue.Empty:
                break
            except Exception as e:
                print(f"UI Queue Error: {e}")
        self.root.after(40, self.process_ui_queue)

    def ui_call(self, fn):
        self.ui_queue.put(fn)

    def sleep_interruptible(self, duration_sec):
        """Sleeps for duration_sec unless stop_event is set. Returns True if completed, False if stopped."""
        return not self.stop_event.wait(max(0.0, duration_sec))

    def setup_ui(self):
        tk.Label(self.root, text="CODE TYPER", bg=THEME["bg_app"], fg=THEME["success"], font=FONT_HEADER).pack(pady=(20, 5))
        self.lbl_backend = tk.Label(self.root, text=f"[{self.backend_name}]", bg=THEME["bg_app"], fg="#555", font=("Segoe UI", 8))
        self.lbl_backend.pack(pady=(0, 10))

        # --- OS SELECTION BUTTONS ---
        f_os = tk.Frame(self.root, bg=THEME["bg_app"])
        f_os.pack(fill="x", padx=20, pady=(0, 10))
        self.btn_win = tk.Button(f_os, text="Win", bg="#333", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", command=lambda: self.set_os("Windows"))
        self.btn_win.pack(side="left", expand=True, fill="x", padx=2)
        self.btn_mac = tk.Button(f_os, text="Mac", bg="#333", fg="white", font=("Segoe UI", 8, "bold"), relief="flat", command=lambda: self.set_os("macOS"))
        self.btn_mac.pack(side="left", expand=True, fill="x", padx=2)
        self.btn_linux = tk.Button(f_os, text="Linux", bg=THEME["accent"], fg="#111", font=("Segoe UI", 8, "bold"), relief="flat", command=lambda: self.set_os("Linux"))
        self.btn_linux.pack(side="left", expand=True, fill="x", padx=2)
        # ----------------------------

        card = tk.Frame(self.root, bg=THEME["bg_card"], padx=15, pady=15)
        card.pack(fill="x", padx=20)

        tk.Label(card, text="Mode", bg=THEME["bg_card"], fg="#888", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        
        self.mode_var = tk.StringVar(value="Raw") 
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TRadiobutton", background=THEME["bg_card"], foreground="white", font=("Segoe UI", 9), focuscolor=THEME["bg_card"])
        style.map("TRadiobutton", background=[('active', THEME["bg_card"])])

        f_modes = tk.Frame(card, bg=THEME["bg_card"])
        f_modes.pack(fill="x", pady=5)
        ttk.Radiobutton(f_modes, text="Smart (Raw Input)", variable=self.mode_var, value="Smart").pack(anchor="w")
        ttk.Radiobutton(f_modes, text="Raw (Simple)", variable=self.mode_var, value="Raw").pack(anchor="w")
        ttk.Radiobutton(f_modes, text="Trim (Auto-Fix Indent)", variable=self.mode_var, value="Trim").pack(anchor="w")

        tk.Frame(card, height=1, bg="#444").pack(fill="x", pady=10)

        speed_header = tk.Frame(card, bg=THEME["bg_card"])
        speed_header.pack(fill="x")
        tk.Label(speed_header, text="Speed", bg=THEME["bg_card"], fg="#888", font=("Segoe UI", 8, "bold")).pack(side="left")
        
        self.lbl_speed = tk.Label(speed_header, text="80ms", bg=THEME["bg_card"], fg=THEME["accent"], font=("Segoe UI", 9, "bold"))
        self.lbl_speed.pack(side="right")

        style.configure("Horizontal.TScale", background=THEME["bg_card"], troughcolor="#444", bordercolor=THEME["bg_card"], darkcolor=THEME["bg_card"], lightcolor=THEME["bg_card"])
        
        self.speed_scale = ttk.Scale(card, from_=1, to=1000, value=80, orient="horizontal", style="Horizontal.TScale")
        self.speed_scale.pack(fill="x", pady=(5,0))
        self.speed_scale.configure(command=lambda v: self.lbl_speed.config(text=f"{int(float(v))}ms"))

        self.lbl_status = tk.Label(self.root, text="READY", bg=THEME["bg_app"], fg="#666", font=("Segoe UI", 11, "bold"))
        self.lbl_status.pack(pady=(20, 10))

        BTN_WIDTH = 22
        
        self.btn_start = tk.Button(self.root, text="START TYPING", bg=THEME["success"], fg="#111",
                                   font=FONT_BTN, command=self.start_process, relief="flat", width=BTN_WIDTH, cursor="hand2")
        self.btn_start.pack(pady=5)

        self.btn_stealth = tk.Button(self.root, text="🛡️ STEALTH (HUMANIZED)", bg=THEME["stealth"], fg="#111",
                                     font=FONT_BTN, command=self.start_stealth_process, relief="flat", width=BTN_WIDTH, cursor="hand2")
        self.btn_stealth.pack(pady=5)

        txt_speak = "🎤 SPEAK" if HAS_SPEECH else "NO SPEECH LIB"
        self.btn_speak = tk.Button(self.root, text=txt_speak, bg=THEME["accent"], fg="#111",
                                   font=FONT_BTN, command=self.start_speak, relief="flat", width=BTN_WIDTH, cursor="hand2")
        if not HAS_SPEECH: self.btn_speak.config(state="disabled", bg="#333")
        self.btn_speak.pack(pady=5)

        self.btn_stop = tk.Button(self.root, text="⏹ STOP (ESC)", bg="#333", fg="#666", font=FONT_BTN, command=self.stop_process, relief="flat", width=BTN_WIDTH, state="disabled")
        self.btn_stop.pack(pady=5)

    # --- OS LOGIC ---
    def set_os(self, os_name):
        self.selected_os = os_name
        self.btn_win.config(bg="#333", fg="#aaa")
        self.btn_mac.config(bg="#333", fg="#aaa")
        self.btn_linux.config(bg="#333", fg="#aaa")
        if os_name == "Windows": 
            self.btn_win.config(bg=THEME["accent"], fg="#111")
            backend_label = "[Pynput / Win]" if HAS_PYNPUT else "[Native Win32]"
            self.lbl_backend.config(text=backend_label)
        elif os_name == "macOS": 
            self.btn_mac.config(bg=THEME["accent"], fg="#111")
            backend_label = "[Pynput / macOS]" if HAS_PYNPUT else "[Native AppleScript]"
            self.lbl_backend.config(text=backend_label)
        elif os_name == "Linux": 
            self.btn_linux.config(bg=THEME["accent"], fg="#111")
            self.lbl_backend.config(text=f"[{self.backend_name}]")

    def set_status(self, text, fg):
        self.ui_call(lambda: self.lbl_status.config(text=text, fg=fg))

    def start_process(self):
        try: 
            text = self.root.clipboard_get()
        except Exception: 
            self.set_status("CLIPBOARD EMPTY", THEME["danger"])
            return

        if not text:
            self.set_status("CLIPBOARD EMPTY", THEME["danger"])
            return

        self.start_generic(self.run_logic, (text, False))

    def start_stealth_process(self):
        try: 
            text = self.root.clipboard_get()
        except Exception: 
            self.set_status("CLIPBOARD EMPTY", THEME["danger"])
            return

        if not text:
            self.set_status("CLIPBOARD EMPTY", THEME["danger"])
            return

        self.start_generic(self.run_logic, (text, True))

    def start_speak(self):
        if not HAS_SPEECH:
            self.set_status("NO SPEECH LIB", THEME["danger"])
            return
        self.set_status("LISTENING...", THEME["accent"])
        self.start_generic(self.listen_logic, ())

    def start_generic(self, target, args):
        self.stop_event.clear()
        self.toggle_ui(True)
        threading.Thread(target=target, args=args, daemon=True).start()

    def stop_process(self):
        self.stop_event.set()
        # Immediately terminate any active typing subprocess (wtype / xdotool)
        with self.subprocess_lock:
            if self.current_subprocess and self.current_subprocess.poll() is None:
                try:
                    self.current_subprocess.terminate()
                    self.current_subprocess.kill()
                except Exception:
                    pass
                self.current_subprocess = None
        self.toggle_ui(False)
        self.set_status("STOPPED", THEME["danger"])

    def toggle_ui(self, is_running):
        def _apply():
            if is_running:
                self.btn_stop.config(state="normal", bg=THEME["danger"], fg="white")
                self.btn_start.config(state="disabled", bg="#333", fg="#555")
                self.btn_stealth.config(state="disabled", bg="#333", fg="#555")
                self.btn_speak.config(state="disabled", bg="#333", fg="#555")
            else:
                self.btn_stop.config(state="disabled", bg="#333", fg="#666")
                self.btn_start.config(state="normal", bg=THEME["success"], fg="#111")
                self.btn_stealth.config(state="normal", bg=THEME["stealth"], fg="#111")
                if HAS_SPEECH: self.btn_speak.config(state="normal", bg=THEME["accent"], fg="#111")
        self.ui_call(_apply)

    def listen_logic(self):
        try:
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                self.set_status("SPEAK NOW...", THEME["accent"])
                audio = r.listen(source, timeout=5, phrase_time_limit=15)
                
            self.set_status("PROCESSING...", "yellow")
            text = r.recognize_google(audio)
            
            self.set_status("TYPING...", THEME["success"])
            if not self.sleep_interruptible(1.0):
                return
            self.type_loop(text)
            if not self.stop_event.is_set():
                self.set_status("DONE", "white")
        except sr.WaitTimeoutError:
            self.set_status("TIMEOUT", THEME["danger"])
        except sr.UnknownValueError:
            self.set_status("UNRECOGNIZED", THEME["danger"])
        except Exception as e:
            print(f"Speech error: {e}")
            self.set_status("NO SPEECH", THEME["danger"])
        finally:
            if not self.stop_event.is_set():
                self.toggle_ui(False)

    def run_logic(self, text, is_stealth=False):
        for i in range(5, 0, -1):
            if self.stop_event.is_set(): break
            status_text = f"STEALTH IN {i}..." if is_stealth else f"STARTING IN {i}..."
            status_color = THEME["stealth"] if is_stealth else "yellow"
            self.set_status(status_text, status_color)
            if not self.sleep_interruptible(1.0):
                break
            
        if not self.stop_event.is_set():
            active_status = "TYPING (STEALTH)..." if is_stealth else "TYPING..."
            active_color = THEME["stealth"] if is_stealth else THEME["success"]
            self.set_status(active_status, active_color)
            
            if self.selected_os == "Linux":
                try:
                    if self.tool == "wtype": 
                        subprocess.run(["wtype", "-m", "ctrl", "-m", "shift", "-m", "alt", "-m", "logo"], check=False)
                    elif self.tool == "xdotool": 
                        subprocess.run(["xdotool", "keyup", "ctrl", "shift", "alt", "super"], check=False)
                except Exception: 
                    pass
            
            self.type_loop(text, is_stealth=is_stealth)
            if not self.stop_event.is_set():
                self.set_status("DONE", "white")
        if not self.stop_event.is_set():
            self.toggle_ui(False)

    def send_key(self, key):
        if self.selected_os == "Linux":
            try:
                if self.tool == "wtype": 
                    subprocess.run(["wtype", "-k", key], check=False)
                elif self.tool == "xdotool": 
                    subprocess.run(["xdotool", "key", key], check=False)
                elif HAS_PYNPUT:
                    self._send_pynput_key(key)
            except Exception: 
                pass
        elif HAS_PYNPUT:
            self._send_pynput_key(key)
        elif self.selected_os == "Windows":
            # Native Windows without pynput
            VK_RETURN = 0x0D
            VK_BACK = 0x08
            vk = VK_RETURN if key == "Return" else (VK_BACK if key == "BackSpace" else None)
            if vk is not None:
                NativeKeyboard.win32_send_key(vk)
        elif self.selected_os == "macOS":
            # Native macOS without pynput
            NativeKeyboard.mac_send_key(key)

    def _send_pynput_key(self, key):
        try:
            if key == "BackSpace":
                keyboard.press(Key.backspace)
                keyboard.release(Key.backspace)
            elif key == "Return":
                keyboard.press(Key.enter)
                keyboard.release(Key.enter)
        except Exception: 
            pass

    def _get_keystroke_delay(self, base_delay_ms, is_stealth):
        if not is_stealth:
            return base_delay_ms / 1000.0
        # Humanized random jitter: 40ms to 90ms with Gaussian-like variance
        jitter_ms = random.uniform(40.0, 90.0)
        # 4% chance of subtle human micro-pause (pondering/word-transition) between 120ms and 220ms
        if random.random() < 0.04:
            jitter_ms += random.uniform(80.0, 150.0)
        return jitter_ms / 1000.0

    def type_loop(self, text, is_stealth=False):
        base_delay_ms = int(self.speed_scale.get())
        mode = self.mode_var.get()

        # Sanitize smart quotes and non-breaking spaces
        text = text.replace('\xa0', ' ').replace('\u00a0', ' ').replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        if text.endswith('\n') and lines and lines[-1] == '':
            lines.pop()

        total_lines = len(lines)

        last_indent = 0
        last_line_ended_colon = False

        for i, line in enumerate(lines):
            if self.stop_event.is_set(): 
                break
            
            clean_line = line.expandtabs(4)
            has_content = bool(clean_line.strip())
            content_to_type = line.lstrip() if mode == "Trim" else line
            
            if mode == "Trim":
                curr_indent = len(clean_line) - len(clean_line.lstrip()) if has_content else last_indent
                expected_ide_indent = last_indent + (4 if last_line_ended_colon else 0)
                
                if has_content and curr_indent < expected_ide_indent:
                    diff = expected_ide_indent - curr_indent
                    backspaces_needed = max(0, math.ceil(diff / 4))
                    for _ in range(backspaces_needed):
                        if self.stop_event.is_set(): 
                            break
                        self.send_key("BackSpace")
                        backspace_delay = self._get_keystroke_delay(base_delay_ms, is_stealth) / 2.0
                        if not self.sleep_interruptible(backspace_delay):
                            break

                if has_content:
                    last_indent = curr_indent
                    last_line_ended_colon = content_to_type.strip().endswith(":")

            if content_to_type:
                # Per-character typing loop with humanized jitter or native batch
                if is_stealth:
                    # Stealth mode: individual humanized keystrokes across all platforms
                    for char in content_to_type:
                        if self.stop_event.is_set():
                            break
                        self._send_single_char(char)
                        char_delay = self._get_keystroke_delay(base_delay_ms, is_stealth=True)
                        if not self.sleep_interruptible(char_delay):
                            break
                else:
                    # Standard fast batch / configured speed typing
                    if self.selected_os == "Linux":
                        try:
                            delay_sec = base_delay_ms / 1000.0
                            for char in content_to_type:
                                if self.stop_event.is_set():
                                    break
                                self._send_single_char(char)
                                if delay_sec > 0 and not self.sleep_interruptible(delay_sec):
                                    break
                        except Exception as e: 
                            print(f"Typing Error: {e}")
                    elif HAS_PYNPUT:
                        self._type_via_pynput(content_to_type, base_delay_ms)
                    elif self.selected_os == "Windows":
                        delay_sec = base_delay_ms / 1000.0
                        for char in content_to_type:
                            if self.stop_event.is_set():
                                break
                            NativeKeyboard.win32_send_unicode_char(char)
                            if delay_sec > 0 and not self.sleep_interruptible(delay_sec):
                                break
                    elif self.selected_os == "macOS":
                        delay_sec = base_delay_ms / 1000.0
                        if delay_sec > 0.05:
                            for char in content_to_type:
                                if self.stop_event.is_set():
                                    break
                                NativeKeyboard.mac_send_text(char)
                                if not self.sleep_interruptible(delay_sec):
                                    break
                        else:
                            NativeKeyboard.mac_send_text(content_to_type)

            if i < total_lines - 1 and not self.stop_event.is_set():
                if self.selected_os == "Linux":
                    try:
                        if mode == "Smart":
                            if self.tool == "wtype": 
                                subprocess.run(["wtype", "-M", "shift", "-k", "Return", "-m", "shift"], check=False)
                            elif self.tool == "xdotool": 
                                subprocess.run(["xdotool", "key", "Shift+Return"], check=False)
                            elif HAS_PYNPUT:
                                with keyboard.pressed(Key.shift):
                                    keyboard.press(Key.enter)
                                    keyboard.release(Key.enter)
                        else:
                            if self.tool == "wtype": 
                                subprocess.run(["wtype", "-k", "Return"], check=False)
                            elif self.tool == "xdotool": 
                                subprocess.run(["xdotool", "key", "Return"], check=False)
                            elif HAS_PYNPUT:
                                keyboard.press(Key.enter)
                                keyboard.release(Key.enter)
                        self.sleep_interruptible(0.1)
                    except Exception: 
                        pass
                elif HAS_PYNPUT:
                    try:
                        if mode == "Smart":
                            with keyboard.pressed(Key.shift):
                                keyboard.press(Key.enter)
                                keyboard.release(Key.enter)
                        else:
                            keyboard.press(Key.enter)
                            keyboard.release(Key.enter)
                        self.sleep_interruptible(0.1)
                    except Exception: 
                        pass
                elif self.selected_os == "Windows":
                    VK_RETURN = 0x0D
                    shift_pressed = (mode == "Smart")
                    NativeKeyboard.win32_send_key(VK_RETURN, shift=shift_pressed)
                    self.sleep_interruptible(0.1)
                elif self.selected_os == "macOS":
                    shift_pressed = (mode == "Smart")
                    NativeKeyboard.mac_send_key("Return", shift=shift_pressed)
                    self.sleep_interruptible(0.1)

    def _send_single_char(self, char):
        """Sends a single character using the active platform driver (zero-dependency compatible)."""
        if self.selected_os == "Linux":
            try:
                if self.tool == "wtype":
                    subprocess.run(["wtype", "-"], input=char.encode('utf-8'), check=False)
                elif self.tool == "xdotool":
                    subprocess.run(["xdotool", "type", "--clearmodifiers", "--file", "-"], input=char.encode('utf-8'), check=False)
                elif HAS_PYNPUT:
                    keyboard.type(char)
            except Exception:
                pass
        elif HAS_PYNPUT:
            keyboard.type(char)
        elif self.selected_os == "Windows":
            NativeKeyboard.win32_send_unicode_char(char)
        elif self.selected_os == "macOS":
            NativeKeyboard.mac_send_text(char)

    def _type_via_pynput(self, content, delay_ms):
        delay_sec = delay_ms / 1000.0
        for char in content:
            if self.stop_event.is_set(): 
                break
            keyboard.type(char)
            if delay_sec > 0 and not self.sleep_interruptible(delay_sec):
                break

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoTyperApp(root)
    root.mainloop()