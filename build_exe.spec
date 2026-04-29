# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['smart_join_gui_v2.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'telethon',
        'tkinter',
        'asyncio',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TG智能加群工具_v2.1_群发修复版',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TG智能加群工具_v2.1_群发修复版',
)
