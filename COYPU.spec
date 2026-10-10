# -*- mode: python ; coding: utf-8 -*-
import sys

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

sys.path.insert(0, SPECPATH)
from app_version import __version__

# File properties Windows shows for COYPU.exe, derived from the single version source in app_version.py
versionNumbers = tuple(int(part) for part in __version__.split('.')) + (0,)
versionInfo = VSVersionInfo(
    ffi=FixedFileInfo(filevers=versionNumbers, prodvers=versionNumbers, mask=0x3f, flags=0x0, OS=0x40004,
                      fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('FileDescription', 'COYPU - railway track geometry analysis and train simulation'),
            StringStruct('FileVersion', __version__),
            StringStruct('InternalName', 'COYPU'),
            StringStruct('LegalCopyright', 'Copyright (c) 2026 Jakub Surovsky. MIT License.'),
            StringStruct('OriginalFilename', 'COYPU.exe'),
            StringStruct('ProductName', 'COYPU'),
            StringStruct('ProductVersion', __version__)])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.'), ('README.md', '.'), ('translations', 'translations'), ('config', 'config'),
           ('vehicles', 'vehicles')],
    hiddenimports=['PySide6.QtSvg', 'PySide6.QtWebChannel'],
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
    name='COYPU',
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
    icon=['icon.png'],
    version=versionInfo,
)
