# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("sklearn") + collect_submodules("joblib") + collect_submodules("sevenbeing")

a = Analysis(
    ["sevenbeing/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[("sevenbeing/gui/static", "sevenbeing/gui/static")],
    hiddenimports=hidden + ["Crypto.Cipher.AES"],
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
    name="7Being",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="7Being",
)
