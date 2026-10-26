# Installing Stiltstep

Stiltstep is a single Python file that uses only the standard library. There is
no dependency to resolve, no database, no service to start and nothing to
configure. Installation is therefore two things: a supported interpreter, and
(optionally) the `stiltstep` console command.

## 1. Prerequisites

| Requirement | Minimum | Notes |
| ----------- | ------- | ----- |
| CPython | 3.9 | 3.11 is what this build was developed and tested on |
| `pip` (optional) | 19.0 | only needed for step 3, the console command |
| `pytest` (optional) | any | only needed for step 6; `unittest` ships with Python |

Nothing else is required. No compiler, no system library, no network access at
run time, no root access.

Check the interpreter:

```
python3 -V
```

## 2. Install the tool (step 1 of the only install script)

```
bash install.sh
```

What it does, in order:

1. prints the interpreter version;
2. tries to refresh `pip`, `setuptools` and `wheel` — a warning, not a failure,
   when the machine is offline (the tool needs none of them to run);
3. installs the optional console command with `pip install --no-build-isolation -e .`
   and reports clearly if it had to skip it;
4. hard-checks the tool: `import stiltstep`, `python3 -m py_compile stiltstep.py`,
   `--version`, and one passing invocation of `grade`, `layout` and `guard`.

It exits 0 when the tool is usable and non-zero when a check fails. It never
starts a server and never installs a system package.

## 3. The console command (optional)

`install.sh` does this for you. To do it by hand:

```
python3 -m pip install --no-build-isolation -e .
stiltstep --version
```

`python3 stiltstep.py ...` always works, with or without this step.

## 4. Verify

```
python3 stiltstep.py --version
python3 stiltstep.py --help
python3 stiltstep.py grade --height 60 --cap-diameter 45
```

The third command prints a complete report and exits 0.

## 5. Run the demo tour

```
bash demo.sh
```

Every check, a passing and a failing case per check, two overrides and every
error path, non-interactively. The tour exits 0 when the tool behaved.

## 6. Run the test suite

```
python3 -m pytest tests
# or without pytest:
python3 -m unittest discover -s tests
```

Both commands run the same thirty-five tests.

## 7. Uninstall

Delete the checkout. If you installed the console command:

```
python3 -m pip uninstall stiltstep
```

Stiltstep writes no state, so there is nothing else to clean up.
