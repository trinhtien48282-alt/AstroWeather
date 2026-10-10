<div align="center">

# AstroWeather 🌌

**A desktop astronomy and observing planner.**

Explore sky positions, estimate observing conditions, check your equipment, and plan a night around the forecast.

</div>

AstroWeather is an experimental Python desktop application for amateur astronomers. Its astronomy calculations run locally; weather and place search use Open-Meteo over the internet. Position, seeing, transparency, and visibility results are estimates and should be treated as informational.

## Features

- **Tonight and forecast:** weather-aware observing scores, hourly conditions, Moon interference, and best observing windows.
- **Planner:** rank targets by visibility, altitude, equipment, and forecast conditions.
- **Sky chart:** inspect the Sun, Moon, planets, stars, and deep-sky targets.
- **Telescope tools:** calculate magnification, field of view, resolution, camera sampling, and related values.
- **Local astronomy engine:** built-in Sun, Moon, and planet positions, with optional NumPy acceleration and optional Astropy high-precision positions.
- **Location and equipment settings:** save coordinates, observing conditions, telescope, eyepieces, and Barlow lenses.

## Requirements

- Python 3.12 or newer
- Tkinter support in your Python installation
- Internet access for weather forecasts and location search

The required packages are listed in [`requirements.txt`](requirements.txt). NumPy is installed by that file and enables the vector engine and Planner. Astropy is optional and is not included in the default requirements.

## Install and run from source

```powershell
git clone https://github.com/trinhtien48282-alt/AstroWeather.git
cd AstroWeather
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

The app opens a desktop window and keeps running until you close it. Run commands from the repository directory.

### Optional Astropy support

To enable the high-precision positions option when running from source:

```powershell
python -m pip install astropy
```

Astropy is not bundled in the standard Windows build. See [`BUILDING.md`](BUILDING.md) to include it in a build.

## Configuration and local data

The application stores its configuration, weather cache, and error log in a user-writable `AstroWeather` directory:

- Windows: `%APPDATA%\AstroWeather\`
- Other platforms: `~/.config/AstroWeather/`

The files are `config.json`, `cache.json`, and `error.log`. Weather data is cached so the last successful forecast can remain available when a refresh fails. Location search and forecast refresh require internet access.

## Build the Windows application

The project includes a PyInstaller onedir specification. Follow [`BUILDING.md`](BUILDING.md) for build prerequisites, diagnostic options, and the first-run checklist. The executable and its supporting files are produced in `dist\AstroWeather\`.

**Build status:** the checked-in build guide says this configuration has not yet been built or run. No release or prebuilt download is advertised here.

## Troubleshooting

<details>
<summary>The app does not start</summary>

Run `python main.py` from the repository directory and check the Python traceback. Confirm Python 3.12 or newer, Tkinter, and the packages in `requirements.txt` are installed. The app writes unexpected GUI callback and worker errors to `error.log` in the data directory above.

</details>

<details>
<summary>Weather or city search fails</summary>

Check your internet connection. Weather and geocoding requests use Open-Meteo; service outages, network restrictions, and invalid responses can prevent updates. When available, the app continues to show the last cached forecast.

</details>

<details>
<summary>The Planner is unavailable</summary>

The Planner requires NumPy. Install project dependencies with `python -m pip install -r requirements.txt`, then restart the app.

</details>

## Development

The code is organized by responsibility: `astro/` for sky calculations, `astronomy/` for observing and equipment calculations, `weather/` for forecast data, `planner/` for target planning, and `gui/` for the desktop interface. `main.py` remains the entry point. See [`BUILDING.md`](BUILDING.md) for packaging instructions.

AstroWeather is under active development. Forecast-based seeing and transparency are proxies, and deep-sky visibility ratings are approximate. Astronomy calculations and observing scores should not be treated as authoritative measurements.

## Star History

<a href="https://www.star-history.com/?repos=trinhtien48282-alt%2Fastroweather&type=date&legend=top-left">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=trinhtien48282-alt/astroweather&type=date&theme=dark&legend=top-left" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=trinhtien48282-alt/astroweather&type=date&legend=top-left" />
    <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=trinhtien48282-alt/astroweather&type=date&legend=top-left" />
  </picture>
</a>
