#!/usr/bin/env bash
# Stiltstep setup: verifies the interpreter, installs the optional console
# command and smoke-checks the tool. Installs nothing system-wide, needs no
# network beyond the language's own package index, and exits when done.
#
# Usage:  bash install.sh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

echo "Stiltstep setup"
echo "  interpreter: $("$PYTHON" -V 2>&1)"
echo "  dependencies: none (Python standard library only)"

# Refresh the packaging tools when the environment allows it. The tool needs
# none of them at run time, so a failure here is a noted warning, not a stop.
if "$PYTHON" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1; then
    echo "  packaging tools: up to date"
else
    echo "  packaging tools: could not be refreshed (offline?) - continuing"
fi

# Optional: put the 'stiltstep' command on PATH. 'python3 stiltstep.py' works
# either way, so this is a convenience step and never blocks the install.
if "$PYTHON" -m pip install --no-build-isolation -e . >/dev/null 2>&1; then
    echo "  console command: installed (stiltstep on PATH)"
else
    echo "  console command: skipped - run the tool as '$PYTHON stiltstep.py'"
fi

# Hard gates: the module imports, compiles and answers on all three checks.
"$PYTHON" -c 'import stiltstep; print("  import: ok, version", stiltstep.VERSION)'
"$PYTHON" -m py_compile stiltstep.py
"$PYTHON" stiltstep.py --version >/dev/null
"$PYTHON" stiltstep.py grade --height 60 --cap-diameter 45 >/dev/null
"$PYTHON" stiltstep.py layout --length 400 --width 300 --stone-spacing 100 >/dev/null
"$PYTHON" stiltstep.py guard --guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50 >/dev/null

echo "Setup complete."
echo "  next: $PYTHON stiltstep.py --help"
echo "  tour: bash demo.sh"
echo "  test: $PYTHON -m pytest tests   (or: $PYTHON -m unittest discover -s tests)"
