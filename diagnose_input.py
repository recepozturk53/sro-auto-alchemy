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

    print("Activating SRO_Client window ...")
    activated = bot._bring_window_to_front("SRO_Client")
    print(f"Window        : {'activated' if activated else 'NOT FOUND (game running?)'}")
    time.sleep(0.3)

    nx, ny = bot._to_virtual_desktop(fuse_x, fuse_y)
    moved = bot._send_mouse_input(
        MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny
    )
    time.sleep(0.05)
    position = bot._cursor_position()
    ok = moved and bot._cursor_near(fuse_x, fuse_y)
    print(f"SendInput move: {'OK' if ok else 'FAILED'} -> cursor at {position}")

    if not ok:
        print()
        print("[FAIL] The cursor could not be positioned.")
        if not bot._is_elevated():
            print("       This process is NOT elevated. SRO_Client most likely is,")
            print("       and Windows blocks synthetic input in that case.")
            print("       -> Close this window and open cmd/PowerShell 'as Administrator'.")
        else:
            print("       Elevated, yet the move was ignored. Make sure the game")
            print("       window is visible and not covered by a UAC prompt.")

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