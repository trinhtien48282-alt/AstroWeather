 <div align="center">

<img src="assets/astroweather.svg" alt="AstroWeather golden crescent logo" width="112" />

# AstroWeather 🌌

**A desktop astronomy and observing planner.**

*Explore the night sky. Plan your next observation.*

Explore celestial objects, evaluate observing conditions, calculate telescope performance, and find the best opportunities to observe the universe.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Python-0078D4)](https://github.com/trinhtien48282-alt/AstroWeather)
[![Weather](https://img.shields.io/badge/Weather-Open--Meteo-41BDF5)](https://open-meteo.com/)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Optional Astropy Support](#optional-astropy-support)
- [Configuration and Local Data](#configuration-and-local-data)
- [Building for Windows](#building-for-windows)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Limitations](#limitations)
- [Star History](#star-history)

## Overview

AstroWeather is an experimental Python desktop application designed to help amateur astronomers explore the sky and plan observing sessions.

It combines astronomical calculations, weather forecasts, equipment calculations, and target planning in a single desktop interface. Astronomy calculations run locally, while weather forecasts and location searches use online services.

Whether you're checking planetary positions, evaluating the night's observing conditions, or calculating the magnification of an eyepiece, AstroWeather brings the essential tools together in one place.

## Features

- **🌙 Tonight and Forecast:** Evaluate observing conditions, inspect hourly forecasts, account for Moon interference, and identify promising observing windows.
- **🔭 Observing Planner:** Rank celestial targets using visibility, altitude, equipment compatibility, and forecast conditions.
- **🪐 Sky Chart:** Explore the Sun, Moon, planets, stars, and deep-sky objects.
- **📐 Telescope Calculator:** Calculate magnification, field of view, resolution, camera sampling, and other optical values.
- **🌌 Local Astronomy Engine:** Calculate celestial positions using built-in algorithms, with optional NumPy acceleration and optional Astropy high-precision calculations.
- **📍 Location Settings:** Configure observing coordinates and local observing conditions.
- **🛠️ Equipment Configuration:** Set up your telescope, eyepieces, and Barlow lenses.
- **🌦️ Weather Integration:** Retrieve forecast data through Open-Meteo and cache weather data for later reference.
- **🖥️ Windows Application:** Package the desktop application into a standalone Windows distribution using PyInstaller.

## How It Works

AstroWeather combines several components to help plan an observing session:

1. **Location:** Your observing coordinates and local conditions establish the context for astronomical calculations and forecasts.
2. **Astronomy:** The local astronomy engine calculates celestial positions and supplies information used by the sky chart and planner.
3. **Weather:** Open-Meteo provides forecast data used to estimate observing conditions.
4. **Equipment:** Telescope and eyepiece specifications determine magnification, field of view, and related optical calculations.
5. **Planning:** The observing planner combines target information, equipment constraints, and forecast conditions to help prioritize potential targets.

Astronomical positions, forecast-derived observing conditions, and visibility scores have different levels of precision. See [Limitations](#limitations) for important qualifications.

## Requirements

- Python 3.12 or newer
- PySide6, installed from `requirements.txt`
- Internet access for weather forecasts and location searches

Project dependencies are listed in [`requirements.txt`](requirements.txt).

NumPy is included in the default dependencies and supports the vector calculation engine and observing planner. Astropy is optional and is not included in the standard dependency list.

## Installation

### Run from source

Clone the repository and install its dependencies:

```powershell
git clone https://github.com/trinhtien48282-alt/AstroWeather.git
cd AstroWeather

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
python main.py
```

The application opens in a desktop window. Keep the terminal open while running it, and execute the commands from the repository directory.

If PowerShell blocks virtual-environment activation, you can invoke the environment's Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

### Windows executable

Prebuilt Windows releases, when available, will be listed on the project's [GitHub Releases page](https://github.com/trinhtien48282-alt/AstroWeather/releases).

To build the application yourself, follow the instructions in [BUILDING.md](BUILDING.md).

## Optional Astropy Support

Astropy can be installed to enable the optional high-precision astronomical position calculations supported by the application.

```powershell
python -m pip install astropy
```

Astropy is not included in the default requirements or the standard Windows build. Consult [BUILDING.md](BUILDING.md) for instructions on including optional Astropy support in a packaged build.

## Configuration and Local Data

AstroWeather stores its configuration, weather cache, and error log in a user-writable application data directory.

| Platform | Data directory |
|---|---|
| Windows | `%APPDATA%\AstroWeather\` |
| Other platforms | `~/.config/AstroWeather/` |

The application data files include:

- `config.json`: saved application settings.
- `cache.json`: cached weather data.
- `error.log`: diagnostic information for unexpected GUI callback and worker errors.

Weather caching can preserve the last successful forecast when a subsequent refresh fails. However, fresh forecasts and location searches require an internet connection.

## Building for Windows

AstroWeather includes a PyInstaller onedir specification for packaging the application.

For build prerequisites, environment variables, optional dependencies, diagnostic builds, and first-run checks, see [BUILDING.md](BUILDING.md).

Build using:

```powershell
uv run pyinstaller --noconfirm AstroWeather.spec
```

The packaged application is produced in:

```text
dist\AstroWeather\
```

Run `AstroWeather.exe` from that directory. **Keep the supporting files and directories alongside the executable.** The onedir distribution is not intended to be reduced to the EXE alone.

## Troubleshooting

<details>
<summary><strong>The application does not start</strong></summary>

Run the application from the repository directory:

```powershell
python main.py
```

Check the traceback for missing dependencies or configuration errors. Confirm that your Python version meets the requirements and that the project dependencies are installed.

Unexpected GUI callback and worker errors may be recorded in `error.log` inside the application data directory.

</details>

<details>
<summary><strong>Weather forecasts or location searches fail</strong></summary>

Check your internet connection. Weather and geocoding requests depend on Open-Meteo services, so network restrictions, service outages, or invalid responses may prevent updates.

When cached data is available, the application may continue displaying the last successful forecast.

</details>

<details>
<summary><strong>The observing planner is unavailable</strong></summary>

The planner requires NumPy. Reinstall the project dependencies and restart AstroWeather:

```powershell
python -m pip install -r requirements.txt
```

</details>

<details>
<summary><strong>The packaged Windows application fails to launch</strong></summary>

Build from the repository's root directory and inspect the terminal output. For a diagnostic build that keeps a console window, consult the build options documented in `BUILDING.md`.

Ensure that you launch the executable from the complete `dist\AstroWeather\` distribution directory rather than copying the executable by itself.

</details>

## Development

AstroWeather is organized by responsibility:

| Directory or file | Purpose |
|---|---|
| `astro/` | Core celestial calculations |
| `astronomy/` | Observing and equipment calculations |
| `weather/` | Weather forecast data |
| `planner/` | Target planning |
| `gui/` | Desktop interface |
| `main.py` | Application entry point |
| `BUILDING.md` | Windows packaging instructions |

The project is under active development. Features, calculations, and the interface may evolve as the application improves.

Contributions, bug reports, and suggestions are welcome through the repository's GitHub issue tracker.

## Limitations

AstroWeather is an amateur astronomy planning tool, not a professional observatory system or a substitute for authoritative astronomical data.

- Forecast-based seeing and transparency values are estimates or proxies, not direct measurements of atmospheric conditions.
- Deep-sky visibility scores are approximate and depend on assumptions about observing conditions and equipment.
- Weather forecasts cannot guarantee that a target will be observable.
- High-precision calculation options depend on the selected astronomy engine and its configuration.

Use the results as planning aids rather than guaranteed predictions.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=trinhtien48282-alt/AstroWeather&type=date)](https://star-history.com/#trinhtien48282-alt/AstroWeather&Date)

