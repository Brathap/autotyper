# AutoTyper

A universal, cross-platform automated keyboard typer that simulates real hardware keystrokes across Windows, macOS, and Linux.

## Features
- **Universal Zero-Dependency Support**:
  - **Windows**: Built-in native Win32 `user32.dll` ctypes driver (no pip packages needed).
  - **macOS**: Built-in AppleScript `osascript` driver (no pip packages needed).
  - **Linux**: Auto-detects Wayland (`wtype`) and X11 (`xdotool`), with seamless fallback to `pynput`.
- **Smart Typist Modes**:
  - `Smart`: Sends raw input without newline complications.
  - `Raw`: Standard direct simulation.
  - `Trim`: Automatically calculates indentation changes and uses backspaces to fix IDE auto-indent laddering.
- **Microsecond Stop Responsiveness**: Halts countdowns and typing loops immediately upon clicking Stop.
- **Voice Typing**: Optional Speech-to-Text input.
- **Adjustable Typing Speed**: From 1ms up to 1000ms delay per key.

## Run directly with Python
```bash
python autotyper.py
```

## Automated Builds
Native standalone executable applications for **Windows (`.exe`)**, **macOS**, and **Linux** are automatically built on every commit via GitHub Actions.
Check the [Actions tab](https://github.com/Brathap/autotyper/actions) or Releases to download the latest executable for your OS.
