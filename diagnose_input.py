"""
Diagnostic tool: check whether synthetic mouse input reaches SRO_Client.

Windows blocks synthetic input from a non-elevated process to an elevated
foreground window (UIPI), and DirectInput games only see SendInput. Run this
from an Administrator prompt to confirm clicking works BEFORE starting the bot:

    python diagnose_input.py            # move the cursor only (never clicks)
    python diagnose_input.py --click    # also click the configured fuse button

Exit code 0 when the cursor could be positioned, 1 otherwise.
"""

import sys
import time
import ctypes
from ctypes import wintypes
from pathlib import Path

# Make the src package importable no matter which folder the prompt is in.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.core.bot_base import (
    BotBase,
    MOUSEEVENTF_ABSOLUTE,
    MOUSEEVENTF_MOVE,
    MOUSEEVENTF_VIRTUALDESK,
)
from src.core.config import config_manager


class _DiagnosticBot(BotBase):
    """BotBase needs a concrete subclass to expose its Win32 helpers."""

    def _run_loop(self) -> None:
        pass

    def _perform_iteration(self) -> bool:
        return False


def game_is_elevated(bot: _DiagnosticBot):
    """Read the game's TokenElevation flag without changing its process."""
    hwnd = bot._find_game_window()
    if not hwnd:
        return None
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    if not process:
        return None
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(process, 0x0008, ctypes.byref(token)):
            return None
        elevated = wintypes.DWORD()
        returned = wintypes.DWORD()
        if not advapi32.GetTokenInformation(token, 20, ctypes.byref(elevated),
                                            ctypes.sizeof(elevated), ctypes.byref(returned)):
            return None
        return bool(elevated.value)
    finally:
        if token.value:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(process)


def run(click: bool) -> int:
    """Run the diagnostic. Returns the process exit code."""
    bot = _DiagnosticBot()

    print("=" * 62)
    print("SRO Auto-Alchemy - input diagnostic")
    print("=" * 62)
    print(f"Administrator : {bot._is_elevated()}")

    fuse_x, fuse_y = config_manager.get_fuse_button()
    print(f"Fuse button   : ({fuse_x}, {fuse_y})")
    if fuse_x <= 0 or fuse_y <= 0:
        print("[FAIL] Fuse button is not configured.")
        print("       Start the GUI, use 'Pick Fuse Button', then retry.")
        return 1

    original = bot._cursor_position()
    print(f"Cursor before : {original}")
    game_elevated = game_is_elevated(bot)
    print(f"Game elevated : {game_elevated}")

    clip = wintypes.RECT()
    if ctypes.windll.user32.GetClipCursor(ctypes.byref(clip)):
        print(f"Cursor area   : ({clip.left}, {clip.top}) - ({clip.right}, {clip.bottom})")
        inside = clip.left <= fuse_x < clip.right and clip.top <= fuse_y < clip.bottom
        print(f"Fuse in area  : {inside}")
    else:
        print("Cursor area   : unavailable")

    print("Testing movement before activating the game ...")
    nx, ny = bot._to_virtual_desktop(fuse_x, fuse_y)
    pre_move = bot._send_mouse_input(
        MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny
    )
    time.sleep(0.05)
    pre_position = bot._cursor_position()
    pre_ok = pre_move and bot._cursor_near(fuse_x, fuse_y)
    print(f"Before game   : {'OK' if pre_ok else 'FAILED'}"
          f" -> cursor at {pre_position}")
    if original and pre_position != original:
        bot._set_cursor_pos(*original)

    print("Activating SRO_Client window ...")
    activated = bot._bring_window_to_front("SRO_Client")
    print(f"Window        : {'activated' if activated else 'NOT FOUND (game running?)'}")
    time.sleep(0.3)

    moved = bot._send_mouse_input(
        MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny
    )
    time.sleep(0.05)
    position = bot._cursor_position()
    ok = moved and bot._cursor_near(fuse_x, fuse_y)
    print(f"SendInput move: {'OK' if ok else 'FAILED'} -> cursor at {position}")

    if not ok:
        fallback = bot._set_cursor_pos(fuse_x, fuse_y)
        time.sleep(0.05)
        fallback_position = bot._cursor_position()
        print(f"SetCursorPos  : {'OK' if fallback and bot._cursor_near(fuse_x, fuse_y) else 'FAILED'}"
              f" -> cursor at {fallback_position}")

    if not ok:
        print()
        print("[FAIL] The cursor could not be positioned.")
        if game_elevated is True and not bot._is_elevated() and pre_ok:
            print("       CONFIRMED: the game is elevated but this Python process is not.")
            print("       Start PowerShell as Administrator, then run the same")
            print("       .venv\\Scripts\\python.exe main.py command from that window.")
        else:
            print("       Check whether the fuse point is inside the cursor area and")
            print("       whether Windows allowed this process to control the game.")

    result = 0 if ok else 1

    if click and ok:
        print()
        print("Clicking the fuse button (game must be focused) ...")
        bot._bring_window_to_front("SRO_Client")
        time.sleep(0.3)
        bot._click_at(fuse_x, fuse_y, delay_ms=50)
        print("Done - watch the game log: a new line should appear.")

    if original:
        bot._set_cursor_pos(*original)
        print(f"Cursor restored: {bot._cursor_position()}")

    return result


def main() -> int:
    """Entry point."""
    click = "--click" in sys.argv[1:]
    if click:
        print("NOTE: --click will really press the left mouse button at the")
        print("      configured fuse coordinates. Make sure the game is open.")
        print()
    return run(click)


if __name__ == "__main__":
    raise SystemExit(main())
