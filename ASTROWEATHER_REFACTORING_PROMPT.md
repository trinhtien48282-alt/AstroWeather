# AstroWeather Incremental Refactoring Instructions

Act as a senior Python software architect and refactoring engineer.

You are working on the AstroWeather repository.

The repository contains a large Python application centered around a roughly 3,200-line `main.py`.

Your job is to modularize the application carefully while preserving its existing behavior.

---

# NON-NEGOTIABLE RULE: STOP AFTER EVERY STAGE

This is the most important instruction.

**NEVER automatically continue from one refactoring stage to the next.**

After completing ONE stage:

1. Stop.
2. Show what you changed.
3. Show the files affected.
4. Summarize important architectural decisions.
5. Report verification/check results.
6. Show the relevant Git diff or summarize it accurately.
7. Clearly state what the NEXT stage would be.
8. WAIT for the user to explicitly approve continuing.

Do not perform the next stage in the same response.

Do not interpret "continue" from the previous prompt as permission to continue through multiple stages.

One user approval = one stage.

If a stage becomes unexpectedly large, ambiguous, or risky, STOP and ask before proceeding.

---

# PHASE 0: INSPECTION ONLY

Before editing anything, inspect the current repository.

Do NOT modify files.

Determine:

* Current file structure
* Current Git branch
* Git status
* Recent Git history
* Current `main.py` structure
* Major functions/classes
* Dependencies between subsystems
* GUI responsibilities
* Astronomy responsibilities
* Weather/network responsibilities
* Planner responsibilities
* Telescope/camera calculation responsibilities
* NumPy/pure-Python relationships
* Potential circular-import risks
* Major refactoring boundaries

Pay particular attention to:

`AstroApp.update_calcs()`

Determine exactly which responsibilities are currently mixed together there.

At the end of Phase 0:

**STOP.**

Do not create modules.

Do not move code.

Do not rewrite anything.

Wait for explicit approval.

---

# GENERAL REFACTORING RULES

## Preserve behavior

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
* Performance behavior

If a bug is discovered, report it separately rather than silently changing behavior during a structural refactor.

---

## Do not rewrite the application

Do NOT replace the 3,200-line application with a new implementation.

Do NOT "clean everything up" in one pass.

Do NOT rewrite large sections merely because another implementation looks nicer.

The goal is controlled extraction and restructuring.

---

## Preserve optional dependencies

Keep:

* Pure-Python astronomy calculations
* Optional NumPy acceleration
* Optional Astropy support

Do not make NumPy or Astropy mandatory unless explicitly instructed.

---

## Avoid circular imports

Before creating a module, determine its dependency direction.

Prefer:

GUI → services/domain → calculation modules

rather than:

calculation modules → GUI

Calculation modules must not depend on CustomTkinter widgets.

---

## Avoid fake modularization

Do not simply move a huge function into another file and call the project modularized.

For example:

`AstroApp.update_calcs()`

must eventually be decomposed by responsibility.

Moving the entire 500-line function to `calculations.py` is NOT an acceptable solution.

---

# REFACTORING STAGES

Perform the following stages sequentially, but NEVER more than one stage per user approval.

## Stage 1: Configuration

Extract configuration/default values and configuration handling where appropriate.

Possible destination:

`config.py`

Preserve existing configuration format and behavior.

Then:

* verify imports
* run appropriate checks
* inspect diff
* STOP

---

## Stage 2: Shared Math Helpers

Extract genuinely shared mathematical utilities.

Do not move astronomy-specific algorithms here merely because they use mathematics.

Then:

* verify imports
* run checks
* inspect diff
* STOP

---

## Stage 3: Astronomy Core

Extract foundational astronomy calculations.

Potential destination:

`astro/core.py`

Examples include:

* Julian date
* GMST
* coordinate transformations
* precession
* common astronomy primitives

Keep the original algorithms intact.

Then:

* verify
* inspect diff
* STOP

---

## Stage 4: Sun and Moon

Extract Sun/Moon calculations.

Potential destination:

`astro/sun_moon.py`

Preserve existing numerical behavior.

Then:

* verify
* inspect diff
* STOP

---

## Stage 5: Planets

Extract planetary calculations.

Potential destination:

`astro/planets.py`

Preserve orbital calculations and event detection.

Then:

* verify
* inspect diff
* STOP

---

## Stage 6: Catalog

Extract catalog/object data and related logic.

Potential destination:

`astro/catalog.py`

Then:

* verify
* inspect diff
* STOP

---

## Stage 7: NumPy Astronomy Engine

Extract the NumPy-specific implementation.

Potential destination:

`astro/numpy_engine.py`

Do NOT force the scalar and NumPy implementations into one abstraction if doing so increases complexity or changes behavior.

Then:

* verify
* inspect diff
* STOP

---

## Stage 8: Observing/Scoring

Extract observing-condition calculations.

Potential destination:

`astronomy/scoring.py`

Keep scoring behavior unchanged.

Then:

* verify
* inspect diff
* STOP

---

## Stage 9: Telescope Optics

Extract telescope/eyepiece optical calculations.

Potential destination:

`astronomy/optics.py`

Examples:

* magnification
* exit pupil
* true FOV
* angular size
* resolution
* drift
* field rotation
* vignetting

Do not move GUI rendering into this module.

Then:

* verify
* inspect diff
* STOP

---

## Stage 10: Camera Calculations

Extract camera/imaging calculations.

Potential destination:

`astronomy/camera.py`

Keep camera math independent from GUI rendering.

Then:

* verify
* inspect diff
* STOP

---

## Stage 11: Weather

Separate weather/network/data-analysis responsibilities.

Possible destinations:

`weather/api.py`

`weather/analysis.py`

`weather/geocoding.py`

Do not mix GUI widgets into these modules.

Then:

* verify
* inspect diff
* STOP

---

## Stage 12: Planner

Separate planner/domain logic from planner GUI.

Potential destination:

`planner/planner.py`

Keep target selection and planning calculations independent of widgets.

Then:

* verify
* inspect diff
* STOP

---

## Stage 13: GUI Extraction

Only after the domain/service layers are sufficiently separated should GUI modules be extracted.

Possible destinations:

`gui/app.py`

`gui/forecast.py`

`gui/planner_page.py`

`gui/settings_page.py`

`gui/calculators_page.py`

`gui/altitude_graph.py`

`gui/widgets.py`

Move GUI responsibilities carefully.

Do not accidentally move domain calculations back into GUI modules.

Then:

* verify
* inspect diff
* STOP

---

# Testing / Verification

After every stage, perform appropriate lightweight verification.

At minimum, consider:

* Python syntax/compile checks
* Import checks
* Existing tests if present
* Running the application when practical
* Checking that important functions remain accessible
* Comparing important outputs before and after extraction

Do not claim that something was tested if it was not actually tested.

If a test cannot be run, say so.

---

# Git Discipline

Assume Git is the rollback mechanism.

Before major changes, inspect:

`git status`

After changes:

`git diff`

After a successful stage, recommend a commit such as:

`git commit -m "Refactor: extract astronomy core"`

Do not reset, revert, or delete user work unless explicitly instructed.

Never use destructive Git commands as a shortcut.

---

# Communication Format

At the end of every stage, report:

## Changed

List files created/modified.

## Architecture

Explain what responsibility moved where.

## Verification

State exactly what checks were run and whether they passed.

## Git

Summarize the important diff.

## Next Stage

State the next planned stage.

Then write:

**STOPPED AFTER STAGE X. Waiting for user approval.**

Do not continue automatically.

---

# FIRST ACTION

Start with **Phase 0: Inspection Only**.

Do not edit any files.

Do not create any modules.

Do not refactor anything.

Analyze the current repository and report your findings.

**STOP after Phase 0 and wait for explicit approval.**
