# AstroWeather 🌌

**A desktop astronomy planning and observing assistant built with Python.**

AstroWeather brings astronomical calculations, observing-condition estimates, weather forecasts, telescope and camera tools, and observation planning together in one desktop application.

The goal is simple: help amateur astronomers decide **what to observe, when to observe it, and what conditions to expect**.

> [!WARNING]
> **Experimental software:** AstroWeather is a personal, AI-assisted project currently under active development. AI tools are used for code generation, refactoring, debugging, and documentation. Changes are reviewed, tested, and integrated by the project author, but the application may still contain bugs, numerical inaccuracies, or incomplete features. Astronomy calculations and observing-condition estimates should be treated as informational rather than authoritative.

> [!NOTE]
> **Development status:** AstroWeather is being refactored from a monolithic Python application into a modular architecture. Features and internal interfaces may change during development.

---

## ✨ Features

### 🔭 Astronomy engine

* Sun and Moon position calculations
* Lunar phase and illumination information
* Planetary positions and orbital calculations
* Altitude and azimuth calculations
* Coordinate precession
* Sidereal time calculations
* Stellar and deep-sky catalog support
* Angular separation calculations

### 🌤️ Observing conditions

Evaluate conditions that may affect a night of observing:

* Seeing estimates
* Transparency assessment
* Dew and wind considerations
* Limiting-magnitude estimation
* Moonlight interference
* Overall observing-condition scoring

These are estimates, not substitutes for direct observations or professional meteorological measurements.

### 🔬 Telescope and camera tools

Explore how your equipment affects what you can observe or photograph:

* Telescope magnification
* Exit pupil
* True field of view
* Angular resolution
* Image scale
* Camera sampling
* Planetary image-size estimation
* Astrophotography calculations

### 🗓️ Observation planning

* Target visibility analysis
* Altitude tracking
* Observation scheduling
* Target suitability analysis

### 🌦️ Weather and location

* Weather information and forecast analysis
* Location and geocoding support
* Weather-aware observing preparation

### ⚡ Flexible calculation engine

AstroWeather supports:

* **Pure Python:** scalar calculation paths without NumPy
* **Optional NumPy acceleration:** faster calculation paths where supported

NumPy is optional, and the application is designed to retain a pure-Python fallback.

---

## 🖥️ Technology

| Component                       | Technology                |
| ------------------------------- | ------------------------- |
| Language                        | Python                    |
| Desktop interface               | CustomTkinter, Tkinter    |
| Optional numerical acceleration | NumPy                     |
| Weather data                    | Open-Meteo                |
| Configuration and local data    | Standard Python libraries |

---

## 🚀 Getting started

### Requirements

* Python compatible with the project's current dependencies
* Windows or another environment capable of running Tkinter, subject to compatibility testing
* An internet connection for online weather and geocoding features
* NumPy is optional

### 1. Clone the repository

```powershell
git clone https://github.com/trinhtien48282-alt/AstroWeather.git
cd AstroWeather
```

### 2. Install dependencies

Install the main GUI dependency:

```powershell
python -m pip install customtkinter
```

For optional NumPy acceleration:

```powershell
python -m pip install numpy
```

Install any additional dependencies required by the current version of the project.

### 3. Launch the application

```powershell
python main.py
```

If the application fails to start, check the installed Python version and dependencies, then review any error output or application logs.

> [!TIP]
> Run these commands from the repository directory. A virtual environment is recommended for development to keep project dependencies separate from other Python applications.

---

## 🔭 Default observing profile

AstroWeather includes a default equipment profile that can be adjusted in the application.

| Setting                         | Default              |
| ------------------------------- | -------------------- |
| Telescope aperture              | 76 mm                |
| Telescope focal length          | 700 mm               |
| Mount type                      | Alt-azimuth          |
| Eyepieces                       | 20 mm, 12.5 mm, 4 mm |
| Eyepiece apparent field of view | 35°                  |
| Barlow lenses                   | 1.5× and 2×          |
| Camera                          | Custom configuration |

These values are a starting profile, not a requirement. Actual observing results depend on the equipment, atmospheric conditions, target, and observing technique.

## 📍 Default observing location

**Cà Mau, Vietnam**

The application is designed to support changing the observing location and coordinates.

---

## 🧱 Project architecture

AstroWeather is being organized into modules with distinct responsibilities:

* `astro/` contains core astronomical calculations and related engines.
* `astronomy/` contains observing-condition scoring and telescope/camera calculations.
* `weather/` handles weather data, forecast analysis, and geocoding.
* `planner/` contains observation-planning logic.
* `gui/` is the planned home for the desktop interface as GUI extraction progresses.
* `main.py` remains the application entry point.

The exact module layout may evolve as the refactor progresses. Consult the repository itself for the current implementation rather than treating a proposed structure as a guarantee.

---

## 🛠️ Development and refactoring

AstroWeather is being refactored in small, controlled stages to improve maintainability while preserving the original application's behavior.

| Stage | Scope                                    |
| ----: | ---------------------------------------- |
|     0 | Code inspection and dependency mapping   |
|     1 | Configuration and shared utilities       |
|     2 | Astronomy core and Sun/Moon calculations |
|     3 | Planetary calculations and catalogs      |
|     4 | NumPy astronomy engine                   |
|     5 | Observing-condition scoring              |
|     6 | Telescope and camera calculations        |
|     7 | Weather and observation planning         |
|     8 | GUI extraction and application structure |

The guiding rule is **preserve behavior first, restructure second**. Refactoring should not change established formulas or numerical results simply to make the code look cleaner.

### Development priorities

* Numerical consistency and correctness
* Clear separation of responsibilities
* Small, verifiable changes
* Minimal unnecessary dependencies
* Optional performance optimizations
* Easier debugging, testing, and future maintenance

---

## 📦 Packaging

Standalone application packaging is a planned or in-progress development task. Check the latest repository files and releases for the current packaging status and any available packaged builds.

---

## 🗺️ Project status

AstroWeather is an experimental personal project under active development.

The current focus is improving the codebase's architecture and maintainability while retaining the application's existing functionality. Future work may include further testing, packaging improvements, and additional astronomy-planning tools.

Contributions, bug reports, and suggestions are welcome, but please remember that the project and its interfaces may change during development.

---

## 📜 License

**No license has been specified yet.**

Until a license is added to the repository, do not assume that the code is available for unrestricted reuse, redistribution, or modification.
