import tkinter as tk
from tkinter import ttk
import subprocess
import time
import threading
import shutil
import sys
import math
import platform

# --- CROSS-PLATFORM KEYBOARD ENGINE ---
try:
    from pynput.keyboard import Key, Controller as KeyboardController
    keyboard = KeyboardController()
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

# --- SPEECH LIBRARY ---
try:
    import speech_recognition as sr
    HAS_SPEECH = True
except ImportError:
    HAS_SPEECH = False

# --- THEME CONFIGURATION ---
THEME = {
    "bg_app": "#1e1e1e",
    "bg_card": "#2b2b2b",
    "accent": "#4da6ff",
    "success": "#00d26a",
    "danger": "#ff4d4d",
    "text_main": "#ffffff",
    "text_sub": "#aaaaaa",
    "btn_fg": "#ffffff"
}

FONT_HEADER = ("Segoe UI", 12, "bold")
FONT_LABEL = ("Segoe UI", 9)
FONT_BTN = ("Segoe UI", 10, "bold")

class AutoTyperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Universal AutoTyper")
        self.root.geometry("340x620") 
        self.root.configure(bg=THEME["bg_app"])
        self.root.attributes('-topmost', True)

        # Linux native tools check
        self.tool = None
        if shutil.which("wtype"): 
            self.tool = "wtype"
        elif shutil.which("xdotool"): 
            self.tool = "xdotool"

        self.stop_event = threading.Event()
        
        # Set a default manual OS to start with
        self.selected_os = "Linux" 
        self.setup_ui()
        self.set_os(self.selected_os) # Initialize colors

    def setup_ui(self):
        tk.Label(self.root, text="CODE TYPER", bg=THEME["bg_app"], fg=THEME["success"], font=FONT_HEADER).pack(pady=(15, 2))
        
        # --- OS SELECTION BUTTONS (FULLY MANUAL) ---
        os_card = tk.Frame(self.root, bg=THEME["bg_card"], padx=10, pady=8)
        os_card.pack(fill="x", padx=15, pady=(5, 10))

        tk.Label(os_card, text="MANUAL OS SELECTION", bg=THEME["bg_card"], fg="#888", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 5))
        
        f_os_btns = tk.Frame(os_card, bg=THEME["bg_card"])
        f_os_btns.pack(fill="x")

        self.btn_win = tk.Button(f_os_btns, text="Windows", bg="#333", fg="white", font=("Segoe UI", 8, "bold"),
                                 relief="flat", cursor="hand2", command=lambda: self.set_os("Windows"))
        self.btn_win.pack(side="left", expand=True, fill="x", padx=2)

        self.btn_mac = tk.Button(f_os_btns, text="macOS", bg="#333", fg="white", font=("Segoe UI", 8, "bold"),
                                 relief="flat", cursor="hand2", command=lambda: self.set_os("macOS"))
        self.btn_mac.pack(side="left", expand=True, fill="x", padx=2)

        self.btn_linux = tk.Button(f_os_btns, text="Linux", bg="#333", fg="white", font=("Segoe UI", 8, "bold"),
                                   relief="flat", cursor="hand2", command=lambda: self.set_os("Linux"))
        self.btn_linux.pack(side="left", expand=True, fill="x", padx=2)

        card = tk.Frame(self.root, bg=THEME["bg_card"], padx=15, pady=12)
        card.pack(fill="x", padx=15)

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

        tk.Frame(card, height=1, bg="#444").pack(fill="x", pady=8)

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
        self.lbl_status.pack(pady=(15, 10))

        BTN_WIDTH = 22
        
        self.btn_start = tk.Button(self.root, text="START TYPING", bg=THEME["success"], fg="#111",
                                   font=FONT_BTN, command=self.start_process, relief="flat", width=BTN_WIDTH, cursor="hand2")
        self.btn_start.pack(pady=4)

        txt_speak = "🎤 SPEAK" if HAS_SPEECH else "NO SPEECH LIB"
        self.btn_speak = tk.Button(self.root, text=txt_speak, bg=THEME["accent"], fg="#111",
                                   font=FONT_BTN, command=self.start_speak, relief="flat", width=BTN_WIDTH, cursor="hand2")
        if not HAS_SPEECH: self.btn_speak.config(state="disabled", bg="#333")
        self.btn_speak.pack(pady=4)

        self.btn_stop = tk.Button(self.root, text="STOP", bg="#333", fg="#666", font=FONT_BTN, command=self.stop_process, relief="flat", width=BTN_WIDTH, state="disabled")
        self.btn_stop.pack(pady=4)

    def set_os(self, os_name):
        """Manually sets the OS and updates the UI button colors"""
        self.selected_os = os_name
        
        self.btn_win.config(bg="#333", fg="#aaa")
        self.btn_mac.config(bg="#333", fg="#aaa")
        self.btn_linux.config(bg="#333", fg="#aaa")

        if self.selected_os == "Windows":
            self.btn_win.config(bg=THEME["accent"], fg="#111")
        elif self.selected_os == "macOS":
            self.btn_mac.config(bg=THEME["accent"], fg="#111")
        elif self.selected_os == "Linux":
            self.btn_linux.config(bg=THEME["accent"], fg="#111")

    def check_os_mismatch(self):
        """Strictly blocks typing if the manual selection doesn't match reality"""
        actual_system = platform.system()
        
        # Map Python's platform.system() names to our button names
        if actual_system == "Windows": mapped_os = "Windows"
        elif actual_system == "Darwin": mapped_os = "macOS"
        else: mapped_os = "Linux"

        if self.selected_os != mapped_os:
            return True # There IS a mismatch
        return False

    def start_process(self):
        # 1. First, check if the manual choice is actually valid for this computer
        if self.check_os_mismatch():
            self.lbl_status.config(text=f"ERROR: NOT {self.selected_os.upper()}", fg=THEME["danger"])
            return

        # 2. Then, check the clipboard
        try: text = self.root.clipboard_get()
        except: 
            self.lbl_status.config(text="CLIPBOARD EMPTY", fg=THEME["danger"])
            return
        
        self.start_generic(self.run_logic, (text,))

    def start_speak(self):
        if self.check_os_mismatch():
            self.lbl_status.config(text=f"ERROR: NOT {self.selected_os.upper()}", fg=THEME["danger"])
            return
            
        self.lbl_status.config(text="LISTENING...", fg=THEME["accent"])
        self.start_generic(self.listen_logic, ())

    def start_generic(self, target, args):
        self.stop_event.clear()
        self.toggle_ui(True)
        threading.Thread(target=target, args=args).start()

    def stop_process(self):
        self.stop_event.set()
        self.lbl_status.config(text="STOPPED", fg=THEME["danger"])

    def toggle_ui(self, is_running):
        if is_running:
            self.btn_stop.config(state="normal", bg=THEME["danger"], fg="white")
            self.btn_start.config(state="disabled", bg="#333", fg="#555")
            self.btn_speak.config(state="disabled", bg="#333", fg="#555")
        else:
            self.btn_stop.config(state="disabled", bg="#333", fg="#666")
            self.btn_start.config(state="normal", bg=THEME["success"], fg="#111")
            if HAS_SPEECH: self.btn_speak.config(state="normal", bg=THEME["accent"], fg="#111")

    def listen_logic(self):
        r = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                self.lbl_status.config(text="SPEAK NOW...", fg=THEME["accent"])
                audio = r.listen(source, timeout=5, phrase_time_limit=15)
                
            self.lbl_status.config(text="PROCESSING...", fg="yellow")
            text = r.recognize_google(audio)
            
            self.lbl_status.config(text="TYPING...", fg=THEME["success"])
            time.sleep(1) 
            self.type_loop(text)
            self.lbl_status.config(text="DONE", fg="white")
        except:
            self.lbl_status.config(text="NO SPEECH", fg=THEME["danger"])
        self.toggle_ui(False)

    def run_logic(self, text):
        for i in range(5, 0, -1):
            if self.stop_event.is_set(): break
            self.lbl_status.config(text=f"STARTING IN {i}...", fg="yellow")
            time.sleep(1)
        if not self.stop_event.is_set():
            self.lbl_status.config(text="TYPING...", fg=THEME["success"])
            
            if self.selected_os == "Linux" and self.tool:
                try:
                    if self.tool == "wtype": subprocess.run(["wtype", "-m", "ctrl", "-m", "shift", "-m", "alt", "-m", "logo"])
                    else: subprocess.run(["xdotool", "keyup", "ctrl", "shift", "alt", "super"])
                except: pass
            elif HAS_PYNPUT:
                for m in [Key.shift, Key.ctrl, Key.alt, Key.cmd]:
                    keyboard.release(m)

            self.type_loop(text)
            self.lbl_status.config(text="DONE", fg="white")
        self.toggle_ui(False)

    def send_key(self, key_name):
        if self.selected_os == "Linux" and self.tool:
            try:
                if self.tool == "wtype":
                    if key_name == "Shift+Return":
                        subprocess.run(["wtype", "-M", "shift", "-k", "Return", "-m", "shift"])
                    else:
                        subprocess.run(["wtype", "-k", key_name])
                elif self.tool == "xdotool":
                    if key_name == "Shift+Return":
                        subprocess.run(["xdotool", "key", "Shift+Return"])
                    else:
                        subprocess.run(["xdotool", "key", key_name])
            except: pass
        
        elif HAS_PYNPUT:
            if key_name == "BackSpace":
                keyboard.press(Key.backspace)
                keyboard.release(Key.backspace)
            elif key_name == "Return":
                keyboard.press(Key.enter)
                keyboard.release(Key.enter)
            elif key_name == "Shift+Return":
                with keyboard.pressed(Key.shift):
                    keyboard.press(Key.enter)
                    keyboard.release(Key.enter)

    def type_text_chunk(self, content_to_type, delay_ms):
        delay_sec = delay_ms / 1000.0

        if self.selected_os == "Linux" and self.tool:
            try:
                if self.tool == "wtype":
                    subprocess.run(["wtype", "-d", str(delay_ms), "-"], input=content_to_type.encode('utf-8'))
                elif self.tool == "xdotool":
                    subprocess.run(["xdotool", "type", "--delay", str(delay_ms), "--clearmodifiers", "--file", "-"], input=content_to_type.encode('utf-8'))
            except Exception as e:
                print(f"Linux Typing Error: {e}")
                
        elif HAS_PYNPUT:
            for char in content_to_type:
                if self.stop_event.is_set(): break
                keyboard.type(char)
                if delay_sec > 0:
                    time.sleep(delay_sec)

    def type_loop(self, text):
        delay_ms = int(self.speed_scale.get())
        mode = self.mode_var.get()

        text = text.replace('\xa0', ' ').replace('\u00a0', ' ').replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
        text = text.encode('ascii', 'ignore').decode('ascii')

        if self.selected_os == "Windows":
            lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        else:
            lines = text.split('\n')
            
        total_lines = len(lines)
        last_indent = 0
        last_line_ended_colon = False

        for i, line in enumerate(lines):
            if self.stop_event.is_set(): break
            
            content_to_type = line
            
            if mode == "Trim":
                clean_line = line.expandtabs(4)
                curr_indent = len(clean_line) - len(clean_line.lstrip())
                content_to_type = line.lstrip()

                expected_ide_indent = last_indent + (4 if last_line_ended_colon else 0)
                
                if curr_indent < expected_ide_indent:
                    diff = expected_ide_indent - curr_indent
                    backspaces_needed = max(0, math.ceil(diff / 4))
                    for _ in range(backspaces_needed):
                        self.send_key("BackSpace")
                        time.sleep(delay_ms / 2000)

                last_indent = curr_indent
                last_line_ended_colon = content_to_type.strip().endswith(":")

            if content_to_type:
                self.type_text_chunk(content_to_type, delay_ms)

            if i < total_lines - 1:
                if mode == "Smart":
                    self.send_key("Shift+Return")
                else:
                    self.send_key("Return")
                time.sleep(0.05)

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoTyperApp(root)
    root.mainloop()