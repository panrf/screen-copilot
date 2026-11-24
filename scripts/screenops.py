#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""screenops.py - DPI-aware screen capture + mouse/keyboard automation CLI.

Single entry point for the screen-copilot skill. Every invocation re-applies
DPI awareness before importing pyautogui, so coordinates always match what
ImageGrab/PIL screenshots show (Windows 125%/150% scaling safe).

Commands
--------
  grab [--out PATH]                  capture full screen -> PNG (prints path + size)
  size                               print coordinate system info (diagnose DPI)
  windows                            list visible top-level window titles
  focus KEYWORD                      activate first window whose title contains KEYWORD
  click X Y [--double] [--right]     click at physical pixel coords
  move X Y
  scroll N [--at X Y]                N>0 up, N<0 down
  key NAME                           enter|tab|esc|space|backspace|up|down...
  hotkey K1 K2 ...                   e.g. hotkey ctrl v
  type TEXT                          ASCII only (use paste for CJK)
  paste [--file PATH] [--text TEXT] [--click X Y] [--enter] [--delay S]
                                     clipboard paste (CJK safe), optional click first
  testfocus X Y [--wait S]           click then press space -> probe if input focused
                                     (prints FOCUS_OK / FOCUS_FAIL after screenshot diff)
"""

import ctypes
import os
import sys
import time

# ---------------------------------------------------------------------------
# DPI awareness MUST run before pyautogui is imported, otherwise pyautogui
# reports a virtual 1280x800 viewport on a 1920x1200 @150% display and every
# click lands ~1.5x off target.
# ---------------------------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

SHOT_DIR = os.path.join(os.getcwd(), "screen_shots")


def _pg():
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.3
    return pyautogui


def _grab_image():
    from PIL import ImageGrab

    return ImageGrab.grab()


def cmd_grab(argv):
    out = None
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    img = _grab_image()
    if not out:
        os.makedirs(SHOT_DIR, exist_ok=True)
        out = os.path.join(SHOT_DIR, "shot_%s.png" % time.strftime("%H%M%S"))
    img.save(out)
    print("SHOT %s %dx%d" % (out, img.size[0], img.size[1]))


def cmd_size(argv):
    user32 = ctypes.windll.user32
    img = _grab_image()
    print("screenshot: %dx%d" % img.size)
    print("GetSystemMetrics: %dx%d" % (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)))
    try:
        print("GetDpiForSystem: %d" % user32.GetDpiForSystem())
    except Exception:
        pass
    print("OK if screenshot == GetSystemMetrics")


def cmd_windows(argv):
    user32 = ctypes.windll.user32
    results = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        results.append(buf.value)
        return True

    user32.EnumWindows(proc_type(cb), 0)
    for t in results:
        print(t)


def _find_windows(keyword):
    user32 = ctypes.windll.user32
    hits = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if keyword.lower() in buf.value.lower():
            hits.append((hwnd, buf.value))
        return True

    user32.EnumWindows(proc_type(cb), 0)
    return hits


def cmd_focus(argv):
    keyword = " ".join(argv)
    hits = _find_windows(keyword)
    if not hits:
        print("NOT_FOUND %r" % keyword)
        sys.exit(1)
    hwnd, title = hits[0]
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    print("FOCUSED %r" % title)


def cmd_click(argv):
    pg = _pg()
    double = "--double" in argv
    right = "--right" in argv
    nums = [a for a in argv if not a.startswith("--")]
    x, y = int(nums[0]), int(nums[1])
    pg.moveTo(x, y, duration=0.15)
    if right:
        pg.rightClick()
    elif double:
        pg.doubleClick()
    else:
        pg.click()
    print("CLICKED %d,%d%s" % (x, y, " right" if right else ""))


def cmd_move(argv):
    pg = _pg()
    pg.moveTo(int(argv[0]), int(argv[1]), duration=0.15)
    print("MOVED")


def cmd_scroll(argv):
    pg = _pg()
    amount = int(argv[0])
    if "--at" in argv:
        i = argv.index("--at")
        pg.moveTo(int(argv[i + 1]), int(argv[i + 2]))
        time.sleep(0.2)
    # send in chunks: one big scroll event is often ignored by web apps
    step = 1 if amount > 0 else -1
    for _ in range(abs(amount)):
        pg.scroll(step * 20)
        time.sleep(0.05)
    print("SCROLLED %d" % amount)


def cmd_key(argv):
    pg = _pg()
    pg.press(argv[0])
    print("KEY %s" % argv[0])


def cmd_hotkey(argv):
    pg = _pg()
    pg.hotkey(*argv)
    print("HOTKEY %s" % "+".join(argv))


def cmd_type(argv):
    pg = _pg()
    text = " ".join(argv)
    pg.typewrite(text, interval=0.02)
    print("TYPED %d chars" % len(text))


def cmd_paste(argv):
    pg = _pg()
    import pyperclip

    text = None
    if "--file" in argv:
        path = argv[argv.index("--file") + 1]
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    elif "--text" in argv:
        text = argv[argv.index("--text") + 1]
    if text is None:
        print("ERROR: need --file or --text")
        sys.exit(1)

    if "--click" in argv:
        i = argv.index("--click")
        pg.click(int(argv[i + 1]), int(argv[i + 2]))
        time.sleep(1.0)

    delay = 1.5
    if "--delay" in argv:
        delay = float(argv[argv.index("--delay") + 1])

    pyperclip.copy(text)
    time.sleep(0.2)
    pg.hotkey("ctrl", "v")
    time.sleep(delay)

    if "--enter" in argv:
        pg.press("enter")
        time.sleep(1.0)
        print("PASTED+SENT %d chars" % len(text))
    else:
        print("PASTED %d chars (not sent)" % len(text))


def cmd_testfocus(argv):
    """Click, press space, compare screenshots. A focused input shows a change."""
    pg = _pg()
    x, y = int(argv[0]), int(argv[1])
    wait = 0.8
    if "--wait" in argv:
        wait = float(argv[argv.index("--wait") + 1])

    before = _grab_image()
    pg.click(x, y)
    time.sleep(wait)
    pg.press("space")
    time.sleep(wait)
    after = _grab_image()

    from PIL import ImageChops

    diff = ImageChops.difference(before.convert("RGB"), after.convert("RGB"))
    bbox = diff.getbbox()
    if bbox:
        print("FOCUS_OK bbox=%s" % (bbox,))
    else:
        print("FOCUS_FAIL (no visual change - click missed the editable area)")


COMMANDS = {
    "grab": cmd_grab,
    "size": cmd_size,
    "windows": cmd_windows,
    "focus": cmd_focus,
    "click": cmd_click,
    "move": cmd_move,
    "scroll": cmd_scroll,
    "key": cmd_key,
    "hotkey": cmd_hotkey,
    "type": cmd_type,
    "paste": cmd_paste,
    "testfocus": cmd_testfocus,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
