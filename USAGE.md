# Using Stiltstep

Three checks, one report format, one exit-code contract. Every dimension is in
centimetres.

```
python3 stiltstep.py CHECK [options]
```

Run it as `python3 stiltstep.py ...` from the project directory, or as
`stiltstep ...` after `bash install.sh`.

## grade - one staddle stone

```
$ python3 stiltstep.py grade --height 60 --cap-diameter 45 --base-diameter 30

STILTSTEP GRADE
rule set grade-v1 | units: centimetres (cm)
==============================================================================
Inputs
  height                             60 cm
  cap diameter                       45 cm
  base diameter                      30 cm
  height/cap ratio                    1.33
  base/cap ratio                      0.67

Rules
Rule                      Measured   Required  Result
-------------------------------------------------------------------
Height/cap ratio (min)        1.33    >= 0.90  PASS
Height/cap ratio (max)        1.33    <= 2.20  PASS
Base/cap ratio (min)          0.67    >= 0.55  PASS

Grade band: A   score: 100.0 of 100
Band A means well proportioned, no reservations.
Summary: PASS - 3 of 3 rules satisfied
```

- `--base-diameter` is optional. Without it the base rule is skipped and the
  skipped rule is named under the table.
- The band is `A`, `B`, `C` or `reject`. Any failed rule means `reject` and
  exit code 1, however good the score is.
- The score is the weighted quality of the measurements out of 100: full marks
  once a measurement is clear of its threshold by the comfort factor, 70 at the
  threshold itself.

A stone that fails:

```
$ python3 stiltstep.py grade --height 30 --cap-diameter 45

Rules
Rule                      Measured   Required  Result
-------------------------------------------------------------------
Height/cap ratio (min)        0.67    >= 0.90  FAIL
Height/cap ratio (max)        0.67    <= 2.20  PASS

  Height/cap ratio (min): A squat stone lets a rodent brace between the cap
    underside and the floor. Needed at least 0.9, measured 0.67.

Grade band: reject   score: 70.4 of 100
Band reject means at least one rule failed; re-cut or re-source the stone.
Summary: FAIL - 1 of 2 rules failed
```

Exit code 1.

## layout - the granary floor grid

```
$ python3 stiltstep.py layout --length 400 --width 300 --stone-spacing 100

STILTSTEP LAYOUT
rule set layout-v1 | units: centimetres (cm)
==============================================================================
Inputs
  floor length                      400 cm
  floor width                       300 cm
  stone spacing                     100 cm
  cap diameter                       60 cm
  edge margin                40 cm (fixed)

Grid
  columns (along length)         4
  rows (across width)            3
  staddle stones                12
  floor coverage           28.27 %

Row positions
  Row  From edge  Stones   Spacing
  --------------------------------
    1      40 cm       4    100 cm
    2     140 cm       4    100 cm
    3     240 cm       4    100 cm

Rules
Rule                      Measured   Required  Result
-------------------------------------------------------------------
Stone count (min)            12.00    >= 4.00  PASS
Stone spacing (max)         100.00  <= 150.00  PASS
Floor coverage (min)         28.27    >= 8.00  PASS

Plan: 12 stones on a 4 x 3 grid, covering 28.27% of the floor footprint.
Summary: PASS - 3 of 3 rules satisfied
```

- The edge margin is a fixed 40 cm from every wall to the first row of stone
  centres; the grid is closed-form, `floor((span - 2 x margin) / spacing) + 1`
  stones per axis, so identical flags always print the identical plan.
- `--cap-diameter` (default 60 cm) sets the cap footprint used for the coverage
  percentage: the share of the floor area sitting directly over a cap.
- A spacing that leaves a single line of stones is a complete report whose fit
  lines read FAIL, with an explanation and exit code 1 - not a usage error.

## guard - rodent-guard geometry

```
$ python3 stiltstep.py guard --guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50

STILTSTEP GUARD
rule set guard-v1 | units: centimetres (cm)
==============================================================================
Inputs
  guard disc diameter                45 cm
  cap diameter                       60 cm
  cap overhang per side             7.5 cm
  cap-to-guard gap                    3 cm
  ground clearance                   50 cm

Rules
Rule                      Measured   Required  Result
-------------------------------------------------------------------
Cap overhang (min)            7.50    >= 5.00  PASS
Cap-to-guard gap (max)        3.00    <= 4.00  PASS
Ground clearance (min)       50.00   >= 40.00  PASS

Guard geometry: overhang 7.5 cm per side, cap-to-guard gap 3 cm, ground
clearance 50 cm.
Summary: PASS - 3 of 3 rules satisfied
```

Overhang is measured per side, `(cap diameter - guard diameter) / 2`. A cap
narrower than the guard disc is a validation error (exit code 2), not a rule
failure: the geometry cannot exist.

## Threshold overrides

Every threshold has a built-in default and a single-run override flag. The
overridden rule is marked on its line and the replaced default is printed under
the table:

```
$ python3 stiltstep.py grade --height 60 --cap-diameter 45 --min-height-ratio 1.40
...
Height/cap ratio (min)        1.33    >= 1.40  FAIL (overridden)
...
  Override: --min-height-ratio 1.4 replaces the built-in 0.90.

Grade band: reject   score: 79.5 of 100
Summary: FAIL - 1 of 2 rules failed
```

Exit code 1. Overrides are never persisted: no config file, no profile, no
history.

## Errors

Bad input never produces half a report. stdout stays empty, the message goes to
stderr and the exit code is 2:

```
$ python3 stiltstep.py grade --height abc --cap-diameter 45
stiltstep: --height must be a number in centimetres, got 'abc'
stiltstep: run 'python3 stiltstep.py grade --help' for usage

$ python3 stiltstep.py grade --height 60
stiltstep: missing required flag --cap-diameter
stiltstep: run 'python3 stiltstep.py grade --help' for usage

$ python3 stiltstep.py layout --length 0 --width 300 --stone-spacing 100
stiltstep: --length must be greater than zero, got '0'

$ python3 stiltstep.py guard --guard-diameter 45 --cap-diameter 40 --gap 3 --clearance 50
stiltstep: --cap-diameter must be at least as wide as --guard-diameter (45 cm), got 40 cm

$ python3 stiltstep.py grade --height 60 --cap-diameter 45 --min-height-ratio tall
stiltstep: --min-height-ratio must be a number, got 'tall'

$ python3 stiltstep.py frobnicate
stiltstep: unknown command 'frobnicate'
```

Running a check with no flags at all prints its usage block and one example:

```
$ python3 stiltstep.py layout
stiltstep layout - plan the staddle-stone grid for a rectangular granary floor

usage: python3 stiltstep.py layout --length CM --width CM --stone-spacing CM

example:
  python3 stiltstep.py layout --length 400 --width 300 --stone-spacing 100

All dimensions are centimetres (cm).
Run 'python3 stiltstep.py layout --help' for every flag and default.
```

## Scripting

```
python3 stiltstep.py guard --guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50 \
  > guard.txt || echo "guard check failed" >> problems.log
```

Reports go to stdout, diagnostics to stderr, and the exit code distinguishes a
failing stone (1) from a mis-typed command (2). Output is ASCII only and
wrapped at 78 columns, so it renders the same in any terminal, file or log.
