# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['freefcc_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('adb.exe', '.'),
        ('AdbWinApi.dll', '.'),
        ('AdbWinUsbApi.dll', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'PyQt5', 'PyQt6', 'matplotlib', 'numpy', 'PIL', 'pandas'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FreeFCC-Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon=None,
)