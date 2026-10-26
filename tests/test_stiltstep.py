"""End-to-end tests for the Stiltstep command-line tool.

Every test drives the real CLI in a subprocess, so the exit-code contract,
the stream routing and the report layout are all exercised as a user would
see them. Runs with pytest or with `python3 -m unittest discover -s tests`.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "stiltstep.py"
WIDTH = 78

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stiltstep  # noqa: E402  (imported after the path fix so both runners work)

REPORT_INVOCATIONS = [
    ("grade", "--height", "60", "--cap-diameter", "45"),
    ("grade", "--height", "60", "--cap-diameter", "45", "--base-diameter", "30"),
    ("grade", "--height", "180", "--cap-diameter", "45"),
    ("grade", "--height", "60", "--cap-diameter", "45", "--min-height-ratio", "1.4"),
    ("layout", "--length", "400", "--width", "300", "--stone-spacing", "100"),
    ("layout", "--length", "400", "--width", "300", "--stone-spacing", "500"),
    ("layout", "--length", "600", "--width", "400", "--stone-spacing", "120"),
    ("guard", "--guard-diameter", "45", "--cap-diameter", "60", "--gap", "3",
     "--clearance", "50"),
    ("guard", "--guard-diameter", "45", "--cap-diameter", "50", "--gap", "6",
     "--clearance", "30"),
    ("guard", "--guard-diameter", "45", "--cap-diameter", "60", "--gap", "3",
     "--clearance", "50", "--min-overhang", "8"),
]


def run(*args: str) -> subprocess.CompletedProcess:
    """Run the CLI with `args` and capture both streams as text."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def squash(text: str) -> str:
    """Collapse all whitespace so assertions survive the 78-column wrapping."""
    return " ".join(text.split())


def last_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def extract_examples(text: str) -> list[str]:
    """Pull the documented example commands out of the usage listing."""
    lines = text.splitlines()
    examples: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("example:"):
            parts = [stripped[len("example:"):].strip()]
            while parts[-1].endswith("\\"):
                parts[-1] = parts[-1][:-1].strip()
                index += 1
                parts.append(lines[index].strip())
            examples.append(" ".join(part for part in parts if part))
        index += 1
    return examples


class RuleEngineTests(unittest.TestCase):
    """The rule engine is the tool's public library surface, so test it directly."""

    def test_finding_carries_label_measured_required_and_status(self) -> None:
        rule = stiltstep.GRADE_RULESET.rules[0]
        finding = stiltstep.evaluate(rule, 1.33)
        self.assertEqual(finding.rule_id, "height_ratio_min")
        self.assertEqual(finding.label, "Height/cap ratio (min)")
        self.assertAlmostEqual(finding.measured, 1.33)
        self.assertAlmostEqual(finding.required, 0.90)
        self.assertEqual(finding.comparison, "min")
        self.assertEqual(finding.status, "pass")
        self.assertFalse(finding.overridden)

    def test_evaluation_is_deterministic(self) -> None:
        rule = stiltstep.GUARD_RULESET.rules[2]
        self.assertEqual(stiltstep.evaluate(rule, 30), stiltstep.evaluate(rule, 30))

    def test_thresholds_are_the_documented_defaults(self) -> None:
        defaults = {
            "grade": [0.90, 2.20, 0.55],
            "layout": [4.0, 150.0, 8.0],
            "guard": [5.0, 4.0, 40.0],
        }
        for name, expected in defaults.items():
            with self.subTest(check=name):
                rules = stiltstep.RULESETS[name].rules
                self.assertEqual([rule.default_threshold for rule in rules], expected)
                self.assertTrue(all(rule.threshold == rule.default_threshold
                                    for rule in rules))

    def test_override_replaces_threshold_and_marks_the_rule(self) -> None:
        rule = stiltstep.GUARD_RULESET.rules[0]
        overridden = stiltstep.with_override(rule, 8.0)
        self.assertEqual(overridden.threshold, 8.0)
        self.assertEqual(overridden.default_threshold, 5.0)
        self.assertTrue(overridden.overridden)
        self.assertFalse(rule.overridden)

    def test_grid_math_is_closed_form(self) -> None:
        plan = stiltstep.plan_grid(400.0, 300.0, 100.0,
                                   stiltstep.DEFAULT_CAP_DIAMETER_CM)
        self.assertEqual((plan.columns, plan.rows), (4, 3))
        self.assertEqual(plan.stone_count, 12)
        self.assertEqual(plan.row_positions, (40.0, 140.0, 240.0))
        self.assertAlmostEqual(plan.coverage_pct, 28.27, places=2)

    def test_bands_never_beat_a_failed_rule(self) -> None:
        self.assertEqual(stiltstep.grade_band(99.0, passed=False), "reject")
        self.assertEqual(stiltstep.grade_band(95.0, passed=True), "A")
        self.assertEqual(stiltstep.grade_band(80.0, passed=True), "B")
        self.assertEqual(stiltstep.grade_band(65.0, passed=True), "C")


class UsageTests(unittest.TestCase):
    def test_no_subcommand_prints_usage_listing(self) -> None:
        result = run()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        for command in ("grade", "layout", "guard"):
            self.assertIn(command, result.stdout)
        self.assertIn("centimetres", result.stdout)
        self.assertIn("example:", result.stdout)

    def test_help_is_the_same_listing(self) -> None:
        self.assertEqual(run("--help").stdout, run().stdout)
        self.assertEqual(run("-h").returncode, 0)

    def test_unknown_subcommand_exits_two_with_message(self) -> None:
        result = run("frobnicate")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("unknown command 'frobnicate'", result.stderr)
        self.assertIn("grade", result.stderr)

    def test_each_subcommand_help_lists_flags_and_defaults(self) -> None:
        expected_defaults = {
            "grade": ["0.90", "2.20", "0.55"],
            "layout": ["4", "150", "8"],
            "guard": ["5", "4", "40"],
        }
        for command, defaults in expected_defaults.items():
            with self.subTest(command=command):
                result = run(command, "--help")
                self.assertEqual(result.returncode, 0)
                self.assertIn("centimetres", result.stdout)
                self.assertIn("examples:", result.stdout)
                flat = squash(result.stdout)
                for default in defaults:
                    self.assertIn(f"default {default}", flat)

    def test_bare_subcommand_invites_with_example(self) -> None:
        for command in ("grade", "layout", "guard"):
            with self.subTest(command=command):
                result = run(command)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn(f"usage: ", result.stderr)
                self.assertIn("example:", result.stderr)
                self.assertIn(command, result.stderr)


class GradeTests(unittest.TestCase):
    def test_pass_echoes_inputs_band_and_score(self) -> None:
        result = run("grade", "--height", "60", "--cap-diameter", "45")
        self.assertEqual(result.returncode, 0)
        output = result.stdout
        self.assertEqual(output.splitlines()[0], "STILTSTEP GRADE")
        self.assertIn("centimetres (cm)", output)
        self.assertIn("60 cm", output)
        self.assertIn("45 cm", output)
        self.assertIn("Height/cap ratio (min)", output)
        self.assertIn("PASS", output)
        self.assertRegex(output, r"Grade band: [ABC]")
        self.assertRegex(output, r"score: \d+\.\d of 100")
        self.assertTrue(last_line(output).startswith("Summary: PASS"))

    def test_optional_base_diameter_is_echoed_and_graded(self) -> None:
        result = run(
            "grade", "--height", "60", "--cap-diameter", "45",
            "--base-diameter", "30",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("base diameter", result.stdout)
        self.assertIn("30 cm", result.stdout)
        self.assertIn("Base/cap ratio (min)", result.stdout)
        self.assertTrue(last_line(result.stdout).startswith("Summary: PASS - 3 of 3"))

    def test_failing_rule_shows_measured_and_threshold(self) -> None:
        result = run("grade", "--height", "30", "--cap-diameter", "45")
        self.assertEqual(result.returncode, 1)
        failing = [line for line in result.stdout.splitlines() if "FAIL" in line]
        self.assertTrue(failing, "expected a FAIL rule line")
        self.assertIn("0.67", failing[0])
        self.assertIn("0.90", failing[0])
        self.assertIn("reject", result.stdout)
        self.assertTrue(last_line(result.stdout).startswith("Summary: FAIL"))

    def test_override_is_applied_and_marked(self) -> None:
        baseline = run("grade", "--height", "60", "--cap-diameter", "45")
        self.assertEqual(baseline.returncode, 0)

        tightened = run(
            "grade", "--height", "60", "--cap-diameter", "45",
            "--min-height-ratio", "1.40",
        )
        self.assertEqual(tightened.returncode, 1)
        self.assertIn("(overridden)", tightened.stdout)
        self.assertIn(">= 1.40", tightened.stdout)
        self.assertNotIn("(overridden)", baseline.stdout)

    def test_non_numeric_value_names_flag_and_value(self) -> None:
        result = run("grade", "--height", "abc", "--cap-diameter", "45")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--height", result.stderr)
        self.assertIn("abc", result.stderr)

    def test_missing_flag_is_named_with_help_hint(self) -> None:
        result = run("grade", "--height", "60")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--cap-diameter", result.stderr)
        self.assertIn("--help", result.stderr)

    def test_zero_and_negative_heights_are_rejected(self) -> None:
        for value in ("0", "-12"):
            with self.subTest(value=value):
                result = run("grade", "--height", value, "--cap-diameter", "45")
                self.assertEqual(result.returncode, 2)
                self.assertIn("greater than zero", result.stderr)

    def test_base_wider_than_cap_is_a_usage_error(self) -> None:
        result = run(
            "grade", "--height", "60", "--cap-diameter", "45",
            "--base-diameter", "80",
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--base-diameter", result.stderr)


class LayoutTests(unittest.TestCase):
    def test_grid_counts_coverage_and_row_listing(self) -> None:
        result = run("layout", "--length", "400", "--width", "300",
                     "--stone-spacing", "100")
        self.assertEqual(result.returncode, 0)
        output = result.stdout
        self.assertEqual(output.splitlines()[0], "STILTSTEP LAYOUT")
        self.assertIn("Row positions", output)
        self.assertRegex(output, r"columns \(along length\)\s+4")
        self.assertRegex(output, r"rows \(across width\)\s+3")
        self.assertRegex(output, r"staddle stones\s+12")
        self.assertRegex(output, r"floor coverage\s+\d+\.\d\d %")

        row_lines = re.findall(r"^\s+\d+\s+[\d.]+ cm\s+\d+\s+[\d.]+ cm$",
                               output, flags=re.MULTILINE)
        self.assertEqual(len(row_lines), 3)
        self.assertTrue(last_line(output).startswith("Summary: PASS"))

    def test_spacing_larger_than_floor_fails_with_explanation(self) -> None:
        result = run("layout", "--length", "400", "--width", "300",
                     "--stone-spacing", "500")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL", result.stdout)
        self.assertIn("cannot carry a granary floor", squash(result.stdout))
        self.assertTrue(last_line(result.stdout).startswith("Summary: FAIL"))

    def test_zero_length_is_rejected(self) -> None:
        result = run("layout", "--length", "0", "--width", "300",
                     "--stone-spacing", "100")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("greater than zero", result.stderr)

    def test_override_is_applied_and_marked(self) -> None:
        result = run("layout", "--length", "400", "--width", "300",
                     "--stone-spacing", "100", "--max-stone-spacing", "80")
        self.assertEqual(result.returncode, 1)
        self.assertIn("(overridden)", result.stdout)
        self.assertIn("<= 80.00", result.stdout)


class GuardTests(unittest.TestCase):
    def test_all_three_checks_pass(self) -> None:
        result = run("guard", "--guard-diameter", "45", "--cap-diameter", "60",
                     "--gap", "3", "--clearance", "50")
        self.assertEqual(result.returncode, 0)
        output = result.stdout
        self.assertEqual(output.splitlines()[0], "STILTSTEP GUARD")
        self.assertIn("Cap overhang (min)", output)
        self.assertIn("Cap-to-guard gap (max)", output)
        self.assertIn("Ground clearance (min)", output)
        self.assertIn("7.5 cm", output)
        self.assertTrue(last_line(output).startswith("Summary: PASS - 3 of 3"))

    def test_short_overhang_fails(self) -> None:
        result = run("guard", "--guard-diameter", "45", "--cap-diameter", "50",
                     "--gap", "3", "--clearance", "50")
        self.assertEqual(result.returncode, 1)
        overhang_line = next(
            line for line in result.stdout.splitlines()
            if "Cap overhang" in line and "PASS" in line or
            ("Cap overhang" in line and "FAIL" in line)
        )
        self.assertIn("FAIL", overhang_line)
        self.assertIn("2.50", overhang_line)
        self.assertIn("5.00", overhang_line)

    def test_cap_narrower_than_guard_is_a_usage_error(self) -> None:
        result = run("guard", "--guard-diameter", "45", "--cap-diameter", "40",
                     "--gap", "3", "--clearance", "50")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("at least as wide as", result.stderr)

    def test_bad_override_value_is_named(self) -> None:
        result = run("guard", "--guard-diameter", "45", "--cap-diameter", "60",
                     "--gap", "3", "--clearance", "50",
                     "--min-overhang", "wide")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--min-overhang", result.stderr)
        self.assertIn("wide", result.stderr)

    def test_override_can_tighten_and_mark(self) -> None:
        result = run("guard", "--guard-diameter", "45", "--cap-diameter", "60",
                     "--gap", "3", "--clearance", "50", "--min-overhang", "8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("(overridden)", result.stdout)


class ContractTests(unittest.TestCase):
    def test_every_report_is_ascii_and_within_78_columns(self) -> None:
        invocations = list(REPORT_INVOCATIONS)
        invocations.append(())
        invocations.append(("grade", "--height", "abc", "--cap-diameter", "45"))
        invocations.append(("guard", "--guard-diameter", "45", "--cap-diameter",
                            "40", "--gap", "3", "--clearance", "50"))
        invocations.append(("layout",))
        for args in invocations:
            with self.subTest(args=args):
                result = run(*args)
                combined = result.stdout + result.stderr
                self.assertTrue(combined, "expected some output")
                for line in combined.splitlines():
                    self.assertLessEqual(len(line), WIDTH, f"too wide: {line!r}")
                    line.encode("ascii")  # raises UnicodeEncodeError if not ASCII

    def test_output_is_deterministic(self) -> None:
        for args in REPORT_INVOCATIONS:
            with self.subTest(args=args):
                first = run(*args)
                second = run(*args)
                self.assertEqual(first.stdout, second.stdout)
                self.assertEqual(first.returncode, second.returncode)

    def test_module_compiles(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_documented_examples_run_verbatim_at_zero(self) -> None:
        listing = run("--help").stdout
        examples = extract_examples(listing)
        self.assertEqual(len(examples), 3, examples)
        for example in examples:
            with self.subTest(example=example):
                parts = shlex.split(example)
                if parts[0] in ("python3", "python"):
                    parts = parts[2:]
                elif parts[0] == "stiltstep":
                    parts = parts[1:]
                result = run(*parts)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(last_line(result.stdout).startswith("Summary: PASS"))

    def test_exit_codes_are_the_documented_ones(self) -> None:
        self.assertEqual(run("grade", "--height", "60", "--cap-diameter", "45").returncode, 0)
        self.assertEqual(run("grade", "--height", "30", "--cap-diameter", "45").returncode, 1)
        self.assertEqual(run("grade", "--height", "x", "--cap-diameter", "45").returncode, 2)

    def test_scripts_are_non_interactive(self) -> None:
        python_sources = [SCRIPT]
        for path in python_sources:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("input(", text)
            self.assertNotIn("sys.stdin", text)

    @unittest.skipUnless(shutil.which("bash"), "bash is not available")
    def test_demo_script_runs_end_to_end(self) -> None:
        result = subprocess.run(
            ["bash", "demo.sh"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("STILTSTEP GRADE", result.stdout)
        self.assertIn("STILTSTEP LAYOUT", result.stdout)
        self.assertIn("STILTSTEP GUARD", result.stdout)
        self.assertNotIn("Traceback", result.stdout)
        self.assertIn("Demo complete", result.stdout)


if __name__ == "__main__":
    unittest.main()
