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

# STAGE 8: GUI EXTRACTION + PYINSTALLER PACKAGING

## Context

This is the final planned refactoring stage for AstroWeather.

The project has already extracted its domain and calculation layers into modules such as:

* `astro/`
* `astronomy/`
* `mathutil/`
* `weather/`
* `planner/`

The Python application uses CustomTkinter. NumPy is used for calculation and planner functionality. Astropy is optional.

The goal is to finish separating the GUI from the calculation/domain layers, reduce `main.py` to a small application entry point/controller, and prepare a distributable Windows application using **PyInstaller**.

## Critical rules

* Python behavior is the behavioral reference.
* Do not rewrite formulas, change calculations, or improve existing behavior during extraction.
* Do not delete `main.py`. Keep it as the application entry point.
* Do not blindly create every suggested GUI module.
* Inspect the actual repository and current Git state before making changes.
* Preserve existing application behavior, configuration, cache, logging, threading, event queues, and error handling.
* Do not modify unrelated files.
* Do not commit or push changes unless explicitly requested.
* Do not proceed if a prerequisite stage is missing or the repository is in an unexpected state.
* Make small, verifiable changes and report the exact files changed.
* Do not claim tests passed unless they were actually executed.

## Part A: Inspect the repository

Before editing:

1. Inspect `git status`, the current branch, and recent commits.
2. Inspect the actual `main.py`, existing package structure, and imports.
3. Confirm the status of Stages 1–7 and identify any incomplete or untracked artifacts.
4. Inspect GUI responsibilities and their dependencies.
5. Identify which methods, widgets, and callbacks can be moved without changing behavior.

Do not overwrite, delete, or blindly regenerate existing files.

If the repository is inconsistent or a prerequisite is incomplete, STOP and report the problem before editing.

## Part B: GUI extraction

Create only GUI modules justified by the actual code. Potential destinations include:

* `gui/app.py`
* `gui/forecast.py`
* `gui/planner_page.py`
* `gui/settings_page.py`
* `gui/calculators_page.py`
* `gui/altitude_graph.py`
* `gui/widgets.py`

These are suggestions, not mandatory files.

### Architecture rules

* GUI modules may import and call domain/calculation modules.
* Domain/calculation modules must not depend on GUI widgets.
* Preserve existing method signatures and callback behavior wherever practical.
* Preserve CustomTkinter widget configuration, layouts, theme behavior, and user-visible text.
* Preserve threading, worker lifecycle, event queues, and UI-thread boundaries.
* Preserve settings, configuration persistence, caches, and error logging.
* Avoid circular imports.
* Avoid introducing unnecessary abstractions or rewriting working code.
* Keep `main.py` as a small entry point/controller that initializes and connects the application.

Do not move code merely to reduce line count if doing so creates fragile dependencies.

## Part C: PyInstaller packaging

Use **PyInstaller** as the required packaging solution.

The finished project must support building a Windows distribution that runs on a machine where Python is not installed.

### Packaging requirements

1. Inspect the actual imports and runtime resources before configuring PyInstaller.
2. Add a reproducible PyInstaller configuration, preferably a `.spec` file, rather than relying on undocumented manual build steps.
3. Include the Python runtime and all required third-party dependencies.
4. Include all required project packages and runtime assets.
5. Handle CustomTkinter's package resources and theme files correctly.
6. Include NumPy and its required binary/runtime dependencies.
7. Treat Astropy according to its existing optional-dependency behavior. Do not silently make an optional dependency mandatory or remove an existing fallback.
8. Preserve access to configuration, cache, and log files using the application's existing paths. User data must not be written into a potentially read-only installation directory.
9. Ensure resource paths work in both normal Python execution and the packaged application.
10. Do not download Python, NumPy, or other dependencies dynamically on the end user's first launch. Bundle dependencies during the build.
11. Do not bundle API keys, credentials, local secrets, developer-specific paths, or unrelated files.
12. Prefer a windowed application build if the current GUI is intended to run without a console. Provide a documented diagnostic build or troubleshooting instructions if needed.

### Distribution format

Start with a PyInstaller `onedir` build unless repository-specific constraints justify another approach.

The initial deliverable should be a self-contained application directory that can be tested reliably. A single-file executable or installer can be considered later and must not compromise correctness.

Document:

* Required build environment.
* How to install build dependencies.
* The exact build command.
* Where the resulting application is produced.
* How to distribute it.
* Known limitations and optional dependencies.

Use a dedicated build environment where practical. Do not pollute or replace the developer's existing Python environment unnecessarily.

## Part D: Validation

Perform the checks that are practical in the current environment.

### Source checks

* Compile `main.py` and the new GUI modules.
* Import the new modules in a fresh interpreter.
* Check for circular imports and accidental GUI dependencies in domain modules.
* Inspect the diff for unintended changes.
* Run the project's existing tests, if any.
* Run `git diff --check`.

### Application checks

Launch the application when practical and verify:

* Application startup.
* Forecast page.
* Planner page.
* Settings page.
* Calculator pages, if present.
* Altitude graph, if present.
* Existing configuration and cache behavior.
* Existing error handling and weather-fetch behavior.

Do not claim a feature was tested if it was not actually exercised.

### Packaging checks

1. Build the application using the committed PyInstaller configuration.
2. Confirm the build completes and the expected executable and support files exist.
3. Launch the packaged application.
4. Test it on a clean Windows environment or virtual machine without a system Python installation, if such an environment is available.
5. Confirm required bundled dependencies, including NumPy, import successfully in the packaged application.
6. Check that CustomTkinter assets load and the GUI renders correctly.
7. Verify that configuration, cache, and logs are written to the intended user-writable locations.
8. Test offline startup where practical.

A successful PyInstaller build alone is not proof that the packaged application works.

If testing on a machine without Python is not possible, state that explicitly. Do not claim this requirement has been verified.

## Part E: Final review

Before stopping:

1. Inspect `git diff --stat` and the full relevant diff.
2. Run `git diff --check`.
3. Review `git status`.
4. Confirm no unrelated files or temporary build artifacts were accidentally included.
5. Summarize the final module structure.
6. Explain how to build and run the packaged application.
7. List tests actually performed and their results.
8. Clearly list untested behavior, unresolved issues, and packaging limitations.

## Completion criteria

Stage 8 is complete only when:

* GUI responsibilities have been extracted where justified by the actual code.
* `main.py` remains the entry point/controller.
* Existing behavior has been preserved as far as verified.
* The PyInstaller configuration and build instructions are present.
* The packaged application builds and launches in the available environment.
* Any unavailable clean-machine tests are clearly documented.
* The final diff and repository state have been reviewed.

## STOP CONDITION

After completing Stage 8, report the results and STOP.

Do not start another refactoring stage, redesign the architecture, rewrite calculations, commit, or push without explicit approval.

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

The local AstroWeather repository is located at:

`C:\Users\Dell\Documents\VS Code Projects\Akaruis Toolbox\AstroWeather`

Whenever giving Git instructions to the user, always begin with:

```powershell
cd "C:\Users\Dell\Documents\VS Code Projects\Akaruis Toolbox\AstroWeather"
```

After each completed and verified refactoring stage, provide the exact Git commands the user should run, including the `cd` command above.

Before changes:

```powershell
cd "C:\Users\Dell\Documents\VS Code Projects\Akaruis Toolbox\AstroWeather"
git status
```

After changes:

```powershell
cd "C:\Users\Dell\Documents\VS Code Projects\Akaruis Toolbox\AstroWeather"
git diff
```

After a successful stage, recommend an appropriate commit such as:

```powershell
cd "C:\Users\Dell\Documents\VS Code Projects\Akaruis Toolbox\AstroWeather"
git add .
git commit -m "Refactor: extract configuration and shared utilities"
```

If the user asks how to push the completed stage, provide the exact push command appropriate to the user's current branch.

If branch state is relevant, first inspect it with:

```powershell
cd "C:\Users\Dell\Documents\VS Code Projects\Akaruis Toolbox\AstroWeather"
git branch --show-current
git status
```

Do not assume the branch name. Use the branch name actually reported by Git.

Do not automatically push commits unless explicitly instructed.

Do not reset, revert, delete, force-push, or overwrite user work unless explicitly instructed.

Never use destructive Git commands as a shortcut.

When a stage is complete, clearly separate:

1. What Claude changed.
2. What the user must do locally.
3. The exact Git commands to run.
4. Whether pushing is optional or explicitly requested.

Do not claim a commit or push happened unless it was actually performed and verified.


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
