# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Silkroad Online Auto-Alchemy Bot.
Creates a single executable file with all dependencies bundled.
"""

import sys
from pathlib import Path

# Get the project root
project_root = Path(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # Include customtkinter assets
        ('src', 'src'),
    ],
    hiddenimports=[
        'customtkinter',
        'mss',
        'pytesseract',
        'cv2',
        'PIL',
        'numpy',
        'ctypes',
        'threading',
        'json',
        'dataclasses',
        'abc',
        'enum',
        're',
        'logging',
        'pathlib',
        'typing',
        'winsound',
        'win32api',
        'win32con',
        'win32gui',
        'pygetwindow',
        'pyrect',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'unittest',
        'pydoc',
        'distutils',
        'setuptools',
        'pip',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SROAutoAlchemyBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True for debugging, False for GUI-only
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add .ico path if you have an icon
)
