# AstroWeather 🌌

**AstroWeather** is a desktop astronomy planning and observing assistant built with Python and CustomTkinter.

It combines astronomy calculations, observing-condition analysis, telescope/camera calculations, weather information, and observation planning into one application.

> **AI-assisted development:** AstroWeather is a personal, AI-assisted (“vibe-coded”) project. AI tools are used during development, including for code generation, refactoring, debugging, and documentation. The resulting code is reviewed, tested, and integrated by the project author. This project is experimental and may contain bugs or inaccuracies.


> 🚧 **Development status:** AstroWeather is currently undergoing a staged refactor from a large monolithic Python application into a modular architecture.

---

## ✨ Features

### 🔭 Astronomy

* Sun and Moon position calculations
* Moon phase and illumination information
* Planetary positions and orbital calculations
* Altitude / azimuth calculations
* Coordinate precession
* Sidereal time calculations
* Stellar and deep-sky catalog support
* Angular separation calculations

### 🌤️ Observing Conditions

* Seeing estimation
* Transparency assessment
* Dew and wind considerations
* Limiting-magnitude estimation
* Moonlight interference
* Overall observing-condition scoring

### 🔬 Telescope & Camera Calculations

* Telescope magnification
* Exit pupil
* Field of view
* Angular resolution
* Image scale
* Camera sampling
* Planetary image-size estimation
* Astrophotography calculations

### 🗓️ Observation Planning

* Target visibility
* Altitude tracking
* Observation scheduling
* Target suitability analysis

### 🌦️ Weather

* Weather information
* Forecast analysis
* Location/geocoding support

### ⚙️ Performance

AstroWeather supports both:

* Pure-Python astronomy calculations
* Optional NumPy-accelerated calculations

The application is designed to retain a scalar fallback when NumPy is unavailable.

---

## 🧭 Project Structure

AstroWeather is being refactored in stages to separate astronomy calculations, data, observing analysis, GUI code, and application infrastructure.

The intended architecture is roughly:

```text
AstroWeather/
├── main.py
├── config.py
├── mathutil.py
│
├── astro/
│   ├── core.py
│   ├── sun_moon.py
│   ├── planets.py
│   ├── catalog.py
│   └── numpy_engine.py
│
├── astronomy/
│   ├── scoring.py
│   ├── optics.py
│   └── camera.py
│
├── weather/
│   ├── api.py
│   ├── analysis.py
│   └── geocoding.py
│
├── planner/
│   └── planner.py
│
└── gui/
    ├── app.py
    ├── forecast.py
    ├── planner_page.py
    ├── settings_page.py
    ├── calculators_page.py
    ├── altitude_graph.py
    └── widgets.py
```

The exact final structure may change as the refactoring progresses.

---

## 🔧 Refactoring Roadmap

The application is being modularized through several controlled stages:

| Stage | Area                                           |
| ----- | ---------------------------------------------- |
| 0     | Inspection and dependency mapping              |
| 1     | Configuration and shared utilities             |
| 2     | Astronomy core + Sun/Moon                      |
| 3     | Planets + catalog                              |
| 4     | NumPy astronomy engine                         |
| 5     | Observing conditions + scoring                 |
| 6     | Telescope + camera calculations                |
| 7     | Weather + observation planner                  |
| 8     | GUI extraction and final application structure |

Each stage is intended to preserve existing behavior and numerical results while reducing the responsibilities of `main.py`.

---

## 🖥️ Technology

* **Python**
* **CustomTkinter**
* **Tkinter**
* **NumPy** (optional acceleration)
* Standard Python libraries for configuration, networking, threading, and application infrastructure

---

## 🔭 Default Equipment Profile

AstroWeather currently includes a default observing setup based around:

* **Telescope:** 76 mm aperture / 700 mm focal length
* **Mount:** Alt-azimuth
* **Eyepieces:** 20 mm, 12.5 mm, 4 mm
* **Eyepiece AFOV:** 35°
* **Barlows:** 1.5× and 2×
* **Camera:** Custom configuration

The equipment settings can be changed inside the application.

---

## 📍 Default Location

The default observing location is configured for:

**Cà Mau, Vietnam**

The application is designed to support changing the observing location and coordinates.

---

## 🚀 Running AstroWeather

Clone the repository and enter the project directory:

```powershell
git clone <repository-url>
cd AstroWeather
```

Run the application with:

```powershell
python main.py
```

### Optional NumPy support

If NumPy is installed, AstroWeather can use its accelerated calculation paths where supported.

```powershell
pip install numpy
```

---

## 🧪 Development Philosophy

AstroWeather prioritizes:

* **Numerical correctness**
* **Preservation of existing behavior**
* **Small, isolated refactoring stages**
* **Clear separation of responsibilities**
* **Optional performance optimizations**
* **Minimal unnecessary dependencies**

Refactoring should not change astronomy formulas simply for the sake of restructuring the code.

Each major refactoring stage should be verified before moving to the next one.

---

## 📌 Project Status

AstroWeather is actively under development.

The current priority is **modularization and architectural cleanup** rather than adding large numbers of new features.

The long-term goal is to make the application easier to:

* understand
* debug
* test
* extend
* optimize
* maintain

without sacrificing the functionality of the original application.

---

## 📜 License

License information will be added when the project's licensing decision is finalized.
