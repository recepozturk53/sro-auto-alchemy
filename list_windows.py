"""
Script to list all window titles for finding SRO window name.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

# EnumWindows callback
hwnd_list = []

def enum_windows_callback(hwnd, lparam):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if title.strip():  # Only non-empty titles
            hwnd_list.append((hwnd, title))
    return True

# Define callback type
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# Enumerate windows
user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

print("=" * 60)
print("All Window Titles:")
print("=" * 60)
for hwnd, title in sorted(hwnd_list, key=lambda x: x[1].lower()):
    print(f"[{hwnd}] {title}")
print("=" * 60)

# Look for potential SRO windows
print("\nPotential SRO windows (containing 'silk', 'sro', 'road'):")
print("-" * 60)
for hwnd, title in hwnd_list:
    title_lower = title.lower()
    if 'silk' in title_lower or 'sro' in title_lower or 'road' in title_lower:
        print(f"[{hwnd}] {title}")
