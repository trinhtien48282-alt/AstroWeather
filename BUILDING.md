# Building the Windows application

AstroWeather is packaged with **PyInstaller** as an *onedir* build: a folder containing `AstroWeather.exe` plus the Python
runtime, CustomTkinter (with its theme files), NumPy and everything else the app imports. The folder runs on a Windows PC
that has no Python installed. Nothing is downloaded when the app starts.

> Status: this configuration was written without access to a Windows build machine. It has **not** been built or run yet.
> Work through "First build checklist" below and report any problem.

## Build environment

* Windows 10/11, 64-bit, and the same Python you develop with (3.12 or newer: the GUI code uses an f-string form that older
  versions reject).
* A dedicated virtual environment, so the build only contains what the app needs:

```powershell
cd "C:\Users\Dell\Documents\VS Code Projects\Akaruis Toolbox\AstroWeather"
python -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-build.txt
```

(`requirements-build.txt` = `customtkinter`, `numpy`, `pyinstaller>=6`. Once a build works, run
`pip freeze > requirements-lock.txt` and keep that file to reproduce the exact versions.)

## Build

```powershell
pyinstaller AstroWeather.spec --noconfirm --clean
```

Result: `dist\AstroWeather\AstroWeather.exe` (and its support files next to it). `build\` and `dist\` are already in
`.gitignore`.

Variants (PowerShell; unset with `Remove-Item Env:ASTROWEATHER_CONSOLE`):

```powershell
$env:ASTROWEATHER_CONSOLE = "1"          # diagnostic build with a console window
$env:ASTROWEATHER_WITH_ASTROPY = "1"     # also bundle Astropy (needs: pip install astropy; makes the folder much larger)
pyinstaller AstroWeather.spec --noconfirm --clean
```

## Distributing

Zip the whole `dist\AstroWeather` folder and share the zip. The person unzips it anywhere and runs `AstroWeather.exe`.
Keep the folder together: the exe needs the files beside it. Windows SmartScreen / antivirus may warn about an unsigned,
newly built exe; that is normal for unsigned PyInstaller builds.

## Where the app keeps its data

Unchanged from the Python version, and always in a user-writable place (never next to the exe):
`%APPDATA%\AstroWeather\config.json`, `cache.json` and `error.log`.

## Optional dependencies in the packaged app

* **NumPy** is bundled, so the vector engine and the Planner work.
* **Astropy** is *not* bundled by default. The packaged app then behaves like a PC without Astropy: the
  "High-precision positions" switch is disabled and the planner uses the built-in engine. (Its tooltip text says
  `pip install astropy`, which cannot be done inside a packaged app; build with `ASTROWEATHER_WITH_ASTROPY=1` if you want it.)

## First build checklist (please run, especially on a PC without Python)

1. The build finishes and `dist\AstroWeather\AstroWeather.exe` exists.
2. Start it. The window appears with the dark theme and the sidebar (this proves CustomTkinter's files were bundled).
3. Click through Tonight, Forecast, Planner, Sky chart, Telescope (all three tabs), Settings.
4. With internet: Refresh updates the Tonight page. Run the Planner ("Plan"). Search a city in Settings.
5. Settings > "Run engine check" reports NumPy timings (proves NumPy is bundled).
6. Close the app; check that `%APPDATA%\AstroWeather\` holds `config.json` and `cache.json`.
7. Offline: disconnect, start again. It should show the cached forecast (or "offline: ..." in the status line).
8. If it does not start: rebuild with `ASTROWEATHER_CONSOLE=1` and read the console, then `%APPDATA%\AstroWeather\error.log`.
