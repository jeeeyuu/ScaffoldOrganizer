# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

_root = os.path.abspath(os.path.join(SPECPATH, ".."))
_main = os.path.join(_root, "app", "main.py")
_icon = os.path.join(
    _root, "assets", "icon.ico" if sys.platform == "win32" else "icon.icns"
)

_datas = []
_datas += collect_data_files('nicegui')
_datas += collect_data_files('webview')
_datas += copy_metadata('nicegui')
_datas += copy_metadata('pywebview')

a = Analysis(
    [_main],
    pathex=[_root],
    binaries=[],
    datas=_datas,
    hiddenimports=['nicegui', 'webview'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ScaffoldOrganizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[_icon],
)

# macOS .app bundle — only created when building on macOS
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name='ScaffoldOrganizer.app',
        icon=_icon,
        bundle_identifier=None,
    )
