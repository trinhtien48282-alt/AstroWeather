# AstroWeather Project Context

## Project

AstroWeather is a Python desktop astronomy planning and observing application built with CustomTkinter.

The project currently has a large monolithic `main.py` of approximately 3,200 lines.

The application combines:

* CustomTkinter GUI
* Astronomy calculations
* Pure-Python astronomy fallbacks
* Optional NumPy acceleration
* Optional Astropy detection
* Sun and Moon calculations
* Planet calculations
* Star/catalog calculations
* Altitude/azimuth calculations
* Weather/network functionality
* Astronomy observing-condition scoring
* Telescope and eyepiece calculations
* Camera calculations
* Observation planning
* Altitude graphs
* Settings/configuration
* Geocoding/location search
* Background worker/thread functionality

The goal is to gradually modularize the project without changing its existing behavior.

---

# Source of Truth

The actual repository files and Git history are the authoritative source of truth.

Do NOT assume that a previous conversation, previous AI response, or this document represents the exact current state of the code.

Before making any change:

1. Inspect the current files.
2. Inspect Git status.
3. Inspect the relevant Git history/diff when applicable.
4. Verify that the current code matches the expected architecture.
5. Only then begin the requested stage.

If previous conversation context is unavailable, recover the project state from the repository and Git history rather than reconstructing it from memory.

---

# Current Architecture

Most functionality currently lives inside `main.py`.

Major areas identified in the existing code include:

## Configuration

* UI/configuration constants
* Default configuration
* `load_config()`
* `save_config()`
* Performance settings
* Telescope/eyepiece/camera settings

Default location is Ca Mau, Vietnam.

Default telescope:

* Aperture: 76 mm
* Focal length: 700 mm
* Mount: AZ
* Central obstruction: 0

Default eyepieces:

* 20 mm
* 12.5 mm
* 4 mm
* 35° AFOV

Default Barlows:

* 1.5x
* 2x

---

# Astronomy Math

The current code contains pure-Python astronomy calculations including:

* Julian date
* GMST
* Alt/Az
* Precession
* Sun position
* Moon position
* Sun altitude
* Moon altitude
* Moon phase
* Next lunar phase
* Planetary orbital calculations
* Event/crossing calculations

Important functions include:

* `jd_from_ts`
* `gmst_deg`
* `altaz`
* `precess`
* `sun_pos`
* `moon_pos`
* `sun_altitude`
* `moon_altitude`
* `moon_info`
* `phase_name`
* `next_phase_time`
* `_kepler`
* `_helio`
* `planet_state`
* `find_events`

These calculations are important and must not be casually rewritten.

Preserve numerical behavior unless a bug is explicitly identified and the change is verified.

---

# NumPy Layer

The project has an optional NumPy acceleration layer.

Important functions include:

* `use_numpy`
* `apply_perf`
* `np_jd`
* `np_gmst`
* `np_altaz`
* `np_precess`
* `np_sep`
* `np_sun`
* `np_moon`
* `np_moon_state`
* `np_moon_drop`
* `_np_kepler`
* `_np_helio`
* `np_planet`
* `np_crossings`
* `sky_series`
* `body_events`
* `scan_body`
* `star_altaz`
* `catalog_altaz_sep`

The pure-Python implementation and NumPy implementation should initially remain separate.

Do not aggressively unify or rewrite them unless there is a demonstrated reason.

---

# Astronomy Catalog

The project contains:

* Catalog helpers
* Object metadata
* Object classifications
* Bright-star data
* Target information

Important names include:

* `_o`
* `KIND_NAMES`
* `CATALOG`
* `BRIGHT_STARS`

---

# Observing / Scoring System

The project calculates observing conditions using functions such as:

* `score_color`
* `text_on`
* `verdict`
* `seeing_fwhm`
* `seeing_label`
* `score_transparency`
* `score_seeing`
* `score_dew`
* `score_wind`
* `sky_nelm`
* `moon_flux_rel`
* `moon_sepf`
* `moon_drop`
* `moon_score_from_drop`
* `ang_sep`

These calculations should remain behaviorally compatible.

---

# Telescope / Camera Calculations

The application performs calculations for:

* Magnification
* Exit pupil
* True field of view
* Angular size
* Resolution
* Drift
* Camera/afocal imaging
* Prime focus
* Image scale
* Camera FOV
* Pixel sampling
* Moon/Jupiter pixel width
* Ideal focal ratio
* NPF/500
* Alt-azimuth field rotation
* Vignetting
* Light matching

A particularly important problem area is:

`AstroApp.update_calcs()`

This function currently handles too many responsibilities at once.

It should eventually be decomposed into smaller calculation/service functions and a much thinner GUI controller.

Do NOT simply move the entire function into another file and call that modularization.

---

# Weather / Network

The application includes weather retrieval, analysis, location/geocoding functionality, and background processing.

Network functionality should eventually be separated from GUI code.

GUI code should not directly own all network/data-processing logic.

---

# Planner

The application contains an observing planner.

Relevant functionality includes:

* Planner presets
* Target filtering
* Minimum altitude
* Target types
* Planner calculations
* Planner worker
* Planner result display
* Planner selection
* Plot presets
* Altitude graph rendering

Important methods include:

* `build_planner`
* `plan_page_refresh`
* `plan_preset`
* `run_plan`
* `planner_worker`
* `show_plan`
* `refresh_plan_list`
* `select_plan`
* `show_plan_detail`
* `plot_preset`
* `draw_alt_graph`
* `on_alt_motion`

Planner/domain logic should eventually be separated from GUI rendering.

`draw_alt_graph()` is GUI-specific and is a candidate for a GUI module.

---

# Settings

The application contains:

* Performance settings
* Engine checks
* Location search
* Geocoding results
* Location selection
* Coordinates
* Bortle selection
* Units
* Telescope/gear configuration

Important methods include:

* `build_settings`
* `on_perf`
* `run_engine_check`
* `do_search`
* `show_geo_results`
* `set_location`
* `use_coords`
* `on_bortle`
* `on_units`
* `save_gear`

Settings UI should eventually be separated from configuration/data logic.

---

# GUI

`AstroApp` currently owns a large amount of:

* Application state
* GUI construction
* Event handling
* Astronomy calculations
* Telescope calculations
* Planner logic
* Weather interaction
* Settings
* Graph drawing

The eventual goal is for `AstroApp` to become primarily an application shell/controller rather than the place where every subsystem lives.

---

# Desired Direction

A possible target architecture is:

AstroWeather/

```
main.py

config.py

astro/
    __init__.py
    core.py
    sun_moon.py
    planets.py
    catalog.py
    numpy_engine.py

astronomy/
    __init__.py
    scoring.py
    optics.py
    camera.py

weather/
    __init__.py
    api.py
    analysis.py
    geocoding.py

planner/
    __init__.py
    planner.py

gui/
    __init__.py
    app.py
    forecast.py
    planner_page.py
    settings_page.py
    calculators_page.py
    altitude_graph.py
    widgets.py
```

This is a target direction, NOT a requirement to create all files immediately.

The architecture should be adapted to the actual dependency structure discovered during analysis.

---

# Refactoring Principles

## 1. Preserve behavior

Do not intentionally change:

* Numerical results
* Astronomy algorithms
* User-visible behavior
* Existing settings
* Default values
* Performance fallback behavior
* Existing functionality

unless explicitly requested.

## 2. Small changes

Make small, independently understandable changes.

Avoid massive rewrites.

## 3. Avoid speculative abstractions

Do not create modules/classes merely because they look architecturally elegant.

Extract code based on actual responsibilities and dependencies.

## 4. Avoid circular imports

Dependency direction must remain understandable.

## 5. Preserve optional dependencies

NumPy remains optional.

Astropy remains optional.

The application must retain its pure-Python fallback.

## 6. GUI should eventually depend on domain/service code

Astronomy calculations should not depend on GUI modules.

Weather/network logic should not be tightly coupled to GUI rendering.

Planner logic should not depend unnecessarily on widgets.

---

# Refactoring Order

The intended broad sequence is:

1. Inspect and document current architecture
2. Configuration
3. Shared math/helpers
4. Astronomy core
5. Sun/Moon
6. Planets
7. Catalog
8. Observing/scoring
9. Telescope optics
10. Camera calculations
11. Weather/network
12. Planner
13. GUI extraction
14. Final `main.py` cleanup
15. Final verification

This order may be adjusted if repository inspection shows a better dependency order.

---

# Critical Rule

The project must be refactored incrementally.

Every stage must be independently understandable and preferably independently testable.

After each major stage:

1. Verify the code.
2. Inspect the Git diff.
3. Run appropriate checks/tests.
4. Confirm imports work.
5. Confirm no obvious functionality was removed.
6. STOP.

Do NOT automatically continue into the next stage.

The next stage begins only after explicit user approval.

---

# Current Refactoring Status

At the beginning of a new refactoring session, assume nothing is completed.

Inspect the repository and Git history to determine:

* What has already been modularized
* What files currently exist
* What commits have been made
* What remains inside `main.py`
* What the current branch/status is

Update this section as the refactor progresses.

Current status:

**Phase 0 / Initial inspection unless repository evidence shows otherwise.**
