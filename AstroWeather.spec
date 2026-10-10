# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for AstroWeather: Windows, "onedir" build (a folder you can zip and run without Python).
#
#   pyinstaller AstroWeather.spec --noconfirm --clean
#   -> dist\AstroWeather\AstroWeather.exe
#
# Optional switches (environment variables, see BUILDING.md):
#   ASTROWEATHER_CONSOLE=1       keep a console window (diagnostic build: shows tracebacks)
#   ASTROWEATHER_WITH_ASTROPY=1  also bundle Astropy (large). Without it the app behaves exactly like a machine
#                                where Astropy is not installed: the "High-precision positions" switch is disabled.
import os

from PyInstaller.utils.hooks import collect_data_files

WITH_ASTROPY = os.environ.get("ASTROWEATHER_WITH_ASTROPY") == "1"
CONSOLE = os.environ.get("ASTROWEATHER_CONSOLE") == "1"

datas = collect_data_files("customtkinter")  # customtkinter loads its theme .json files, fonts and assets from its package folder
binaries = []
hiddenimports = []
excludes = []
if WITH_ASTROPY:
    from PyInstaller.utils.hooks import collect_all
    a_datas, a_binaries, a_hidden = collect_all("astropy")
    datas += a_datas
    binaries += a_binaries
    hiddenimports += a_hidden
else:
    # planner/planner.py imports Astropy lazily inside a function; keep the build from pulling it in implicitly
    excludes.append("astropy")

a = Analysis(
    [os.path.join(SPECPATH, "main.py")],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AstroWeather",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AstroWeather",
)
