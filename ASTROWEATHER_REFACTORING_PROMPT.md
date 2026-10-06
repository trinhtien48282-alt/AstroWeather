# AstroWeather Incremental Refactoring Instructions

Act as a senior Python software architect and refactoring engineer.

You are working on the **AstroWeather** repository, a large Python application currently centered around a roughly 3,200-line `main.py`.

Your goal is to modularize the application carefully while preserving its existing behavior.

---

# NON-NEGOTIABLE RULE: ONE STAGE AT A TIME

This is the most important instruction.

**NEVER automatically continue from one stage to another.**

One explicit user approval = exactly **ONE refactoring stage**.

After completing one stage:

1. Stop.
2. Show what changed.
3. Show files created/modified.
4. Explain important architectural decisions.
5. Report exactly what verification was performed.
6. Summarize the relevant Git diff.
7. State the next stage.
8. STOP and wait for explicit approval.

Do not perform the next stage in the same response.

Do not interpret previous approval, "continue", or the existence of this instruction as permission to perform multiple stages.

If a stage becomes unexpectedly large, ambiguous, risky, or requires architectural decisions beyond its scope, STOP and ask before continuing.

---

# REPOSITORY ACCESS IS REQUIRED

Before performing any refactoring stage, you must work from the **actual AstroWeather repository**, not from pasted or remembered code.

You must first verify that you can actually inspect the repository files relevant to the stage.

If the repository is unavailable:

* Do NOT fabricate repository state.
* Do NOT claim the stage is complete.
* Do NOT generate a "completed" patch based only on pasted code.
* Do NOT tell the user to manually apply a patch unless they explicitly request a manual patch.
* Clearly report that repository access is unavailable.
* STOP.

A stage is considered complete only when the actual repository was inspected and the actual repository changes were verified.

---

# PHASE 0: REPOSITORY INSPECTION ONLY

Before any refactoring, inspect the actual repository.

Do NOT modify files during Phase 0.

Inspect:

* Current file structure
* Git branch
* Git status
* Recent Git history
* `main.py`
* Existing packages/modules
* Major functions and classes
* Imports and dependency relationships
* GUI responsibilities
* Astronomy responsibilities
* Weather/network responsibilities
* Planner responsibilities
* Telescope/camera calculation responsibilities
* Pure-Python versus NumPy relationships
* Optional Astropy usage
* Potential circular-import risks

Pay particular attention to:

`AstroApp.update_calcs()`

Determine exactly which responsibilities are mixed together there.

Also identify where the following currently live:

* Configuration
* Shared math helpers
* Astronomy core
* Sun/Moon calculations
* Planet calculations
* Catalog data
* NumPy astronomy engine
* Observing/scoring calculations
* Telescope optics
* Camera calculations
* Weather/network code
* Planner logic
* GUI code

At the end of Phase 0:

**STOP.**

Do not create modules.

Do not move code.

Do not rewrite anything.

Wait for explicit approval.

---

# GENERAL REFACTORING RULES

## 1. Preserve behavior

The refactor must preserve existing behavior.

Do not casually change:

* Astronomy formulas
* Numerical results
* Defaults
* UI behavior
* Configuration behavior
* Weather behavior
* Planner behavior
* Telescope calculations
* Camera calculations
* Performance characteristics

If an existing bug is discovered, report it separately.

Do not silently "fix" unrelated bugs during structural refactoring.

---

## 2. Do not rewrite the application

Do NOT replace the application with a new implementation.

Do NOT rewrite large sections simply because another design appears cleaner.

Do NOT redesign the UI.

Do NOT redesign the astronomy algorithms.

The goal is controlled extraction and restructuring.

---

## 3. Preserve optional dependencies

Keep:

* Pure-Python astronomy calculations
* Optional NumPy acceleration
* Optional Astropy support

Do not make NumPy or Astropy mandatory unless explicitly instructed.

---

## 4. Avoid circular imports

Prefer dependency direction such as:

GUI
↓
services/domain
↓
calculation modules

Calculation modules must not depend on CustomTkinter widgets.

---

## 5. Avoid fake modularization

Do not simply move a huge function into another file and call the application modularized.

For example:

`AstroApp.update_calcs()`

must eventually be decomposed by responsibility.

Moving the entire function into `calculations.py` is NOT an acceptable solution.

---

## 6. Respect the existing project structure

Do not blindly create directories just because a destination is suggested below.

First inspect the repository.

Choose module locations that fit the existing Python package structure.

If the repository already has a suitable package directory, use it.

If a new package is genuinely necessary, create it only as part of the relevant stage.

Keep the architecture simple.

---

# REFACTORING STAGES

The following are the **only stages**.

Perform them sequentially, but never perform more than one stage per explicit user approval.

---

# STAGE 1: CONFIGURATION + SHARED UTILITIES

Extract configuration handling and genuinely generic mathematical utilities.

### Configuration responsibilities

Move appropriate configuration responsibilities such as:

* `APP_NAME`
* configuration/cache/log paths
* `DEFAULT_CONFIG`
* `log_error`
* `load_config`
* `save_config`

Preserve the existing configuration format and behavior.

### Shared utility responsibilities

Extract only genuinely generic helpers such as:

* `D2R`
* `R2D`
* `AU_KM` only if repository inspection shows it is appropriate here
* `rad`
* `deg`
* `clamp`
* `piecewise`
* `mean`

Do NOT move astronomy-specific algorithms here merely because they involve mathematics.

Keep the module dependency-light.

After completion:

* verify imports
* run syntax/import checks
* run relevant tests
* inspect the diff
* verify no behavior was unintentionally changed
* STOP

---

# STAGE 2: ASTRONOMY CORE + SUN/MOON

Extract foundational astronomy calculations and Sun/Moon calculations.

Potential structure, depending on the existing repository:

`astro/core.py`

`astro/sun_moon.py`

### Astronomy core may include:

* Julian date
* GMST
* altitude/azimuth conversion
* coordinate transformations
* precession
* common astronomy primitives

### Sun/Moon may include:

* Sun position
* Moon position
* Sun altitude
* Moon altitude
* Moon state
* Moon phase
* next phase calculations
* Moon separation/drop calculations where appropriate

Keep numerical algorithms intact.

Do not redesign the astronomy engine.

After completion:

* verify imports
* compare important numerical outputs where practical
* run checks
* inspect diff
* STOP

---

# STAGE 3: PLANETS + CATALOG

Extract planetary calculations and astronomical catalog responsibilities.

Potential structure:

`astro/planets.py`

`astro/catalog.py`

### Planet responsibilities may include:

* orbital elements
* Kepler calculations
* heliocentric state
* planetary state
* event detection

### Catalog responsibilities may include:

* catalog data
* object type definitions
* bright-star data
* catalog coordinate calculations
* catalog-related helpers

Keep data and numerical behavior unchanged.

After completion:

* verify
* compare representative outputs
* inspect diff
* STOP

---

# STAGE 4: NUMPY ASTRONOMY ENGINE

Extract the NumPy-specific astronomy implementation.

Potential destination:

`astro/numpy_engine.py`

This may include the existing NumPy implementations of:

* Julian date arrays
* GMST arrays
* altitude/azimuth arrays
* precession arrays
* Sun/Moon arrays
* Kepler/planet arrays
* crossings
* sky series
* body scanning
* star/catalog vector calculations

Do NOT force the scalar and NumPy implementations into one abstraction if doing so increases complexity or risks behavior changes.

Preserve NumPy as an optional acceleration path.

Do not make NumPy mandatory.

After completion:

* verify NumPy-enabled behavior
* verify fallback behavior where practical
* run checks
* inspect diff
* STOP

---

# STAGE 5: OBSERVING CONDITIONS + SCORING

Extract observing-condition and scoring calculations.

Potential destination:

`astronomy/scoring.py`

This may include:

* seeing calculations
* transparency scoring
* dew calculations
* wind scoring
* sky brightness / NELM calculations
* Moon brightness/penalty calculations
* angular separation
* observing verdict logic
* related scoring constants

Keep scoring behavior unchanged.

Do not mix GUI presentation into this module.

After completion:

* verify representative scoring outputs
* run checks
* inspect diff
* STOP

---

# STAGE 6: TELESCOPE + CAMERA CALCULATIONS

Separate telescope optical calculations from camera/imaging calculations.

Potential destinations:

`astronomy/optics.py`

`astronomy/camera.py`

### Telescope/optics responsibilities may include:

* magnification
* exit pupil
* true field of view
* angular size
* resolution
* drift
* field rotation
* vignetting
* light matching
* eyepiece calculations

### Camera responsibilities may include:

* camera presets
* image scale
* sensor/FOV calculations
* sampling
* Moon/Jupiter pixel dimensions
* ideal focal ratio
* NPF/500 calculations
* afocal/prime-focus calculations

Keep calculation logic independent from GUI widgets and rendering.

This stage is specifically intended to reduce the responsibilities currently concentrated in:

`AstroApp.update_calcs()`

Do NOT simply move the entire `update_calcs()` function elsewhere.

Break it apart by responsibility.

After completion:

* verify important calculator outputs
* run checks
* inspect diff
* STOP

---

# STAGE 7: WEATHER + PLANNER

Separate weather/network services and planner/domain logic from GUI responsibilities.

Potential structure:

`weather/api.py`

`weather/analysis.py`

`weather/geocoding.py`

`planner/planner.py`

Use only the modules actually justified by the existing code.

### Weather

Separate:

* network/API access
* weather data processing
* weather analysis
* geocoding/location lookup

Do not place GUI widgets in weather modules.

### Planner

Separate:

* target selection
* planning calculations
* plan generation
* target filtering
* planner data structures

from planner GUI operations.

Do not move GUI rendering into the planner domain module.

After completion:

* verify network/data behavior where practical
* verify planner calculations
* inspect diff
* STOP

---

# STAGE 8: GUI EXTRACTION

Only after the domain/calculation layers have been sufficiently separated should GUI modules be extracted.

Potential destinations, depending on the actual repository:

`gui/app.py`

`gui/forecast.py`

`gui/planner_page.py`

`gui/settings_page.py`

`gui/calculators_page.py`

`gui/altitude_graph.py`

`gui/widgets.py`

Do not blindly create every file above.

Create only modules justified by the actual code.

Move GUI responsibilities carefully.

The GUI may call domain/calculation modules, but domain/calculation modules must not depend on GUI widgets.

The final goal is for `main.py` to become a small application entry point/controller rather than a 3,200-line everything-file.

After completion:

* run syntax/import checks
* launch the application when practical
* verify major pages/features
* inspect the diff
* STOP

---

# VERIFICATION

After every stage, perform appropriate lightweight verification.

At minimum, consider:

* Python syntax/compile checks
* Import checks
* Existing tests
* Representative calculations
* Running the application when practical
* Checking important functions remain accessible
* Comparing important outputs before and after extraction

Do not claim a test was run if it was not actually run.

If a test cannot be run, explicitly say so.

---

# GIT DISCIPLINE

Git is the rollback mechanism.

Before changes:

`git status`

After changes:

`git diff`

After a successful stage, recommend a commit such as:

`git commit -m "Refactor: extract configuration and shared utilities"`

Do not reset, revert, delete, or overwrite user work unless explicitly instructed.

Never use destructive Git commands as a shortcut.

Do not automatically push commits unless explicitly instructed.

---

# COMMUNICATION FORMAT

At the end of every completed stage, use exactly this structure:

## Changed

List files created and modified.

## Architecture

Explain what responsibilities moved and why.

## Verification

State exactly what checks were run and whether they passed.

## Git

Summarize the important diff and mention whether the working tree has uncommitted changes.

## Next Stage

State the next stage by its exact name and briefly describe its scope.

Then write:

**STOPPED AFTER STAGE X. Waiting for user approval.**

Do not continue automatically.

---

# CURRENT STAGE TRACKING

If `ASTROWEATHER_CONTEXT.md` or another project progress file exists, update its refactoring progress only when the actual repository has been modified and the stage has been successfully verified.

Never claim a stage is complete merely because a patch or proposed file was generated in chat.

If the progress file does not exist, do not create one during Phase 0 unless explicitly instructed.

---

# FIRST ACTION

Start with:

**Phase 0: Inspection Only**

Do not edit any files.

Do not create modules.

Do not generate patches.

Do not refactor anything.

Inspect the actual repository and report your findings.

**STOP after Phase 0 and wait for explicit approval.**
