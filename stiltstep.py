#!/usr/bin/env python3
"""Stiltstep - three practical checks on a granary staddle-stone setup.

One file, standard library only. Three checks:

  grade    score one staddle stone against the built-in proportion rules
  layout   plan the staddle-stone grid for a rectangular granary floor
  guard    verify cap overhang, cap-to-guard gap and ground clearance

Every check prints the same aligned plain-text report on stdout and returns
0 when all rules pass, 1 when a rule fails and 2 on a usage or validation
error. All dimensions are centimetres.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import textwrap
from dataclasses import dataclass, field, replace
from typing import TextIO

PROGRAM = "Stiltstep"
COMMAND_NAME = "stiltstep"
VERSION = "1.0.0"

REPORT_WIDTH = 78
UNIT_SYSTEM = "cm"
UNIT_NAME = "centimetres (cm)"

EDGE_MARGIN_CM = 40.0
DEFAULT_CAP_DIAMETER_CM = 60.0

MIN_RULE_IDEAL_FACTOR = 1.20
MAX_RULE_IDEAL_FACTOR = 0.80
BAND_THRESHOLDS = ((88.0, "A"), (76.0, "B"), (62.0, "C"))
BAND_DESCRIPTIONS = {
    "A": "well proportioned, no reservations",
    "B": "sound, with a little margin to spare",
    "C": "marginal, sitting at the edge of the built-in rules",
    "reject": "at least one rule failed; re-cut or re-source the stone",
}


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------


class UsageError(Exception):
    """A usage or validation problem: reported on stderr, exit code 2."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


# ---------------------------------------------------------------------------
# rule model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """One threshold rule. `threshold` holds the effective value for this run."""

    id: str
    label: str
    comparison: str  # "min" or "max"
    default_threshold: float
    weight: float
    detail: str
    threshold: float = 0.0
    overridden: bool = False


@dataclass(frozen=True)
class RuleSet:
    """A named, versioned group of rules sharing one unit system."""

    name: str
    version: str
    unit_system: str
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class Finding:
    """The outcome of evaluating one rule against one measured value."""

    rule_id: str
    label: str
    measured: float
    required: float
    comparison: str
    status: str  # "pass" | "fail"
    overridden: bool
    detail: str
    quality: float


@dataclass
class Report:
    """Everything one check wants printed, handed to the shared renderer."""

    title: str
    ruleset: RuleSet
    inputs: list[tuple[str, str]]
    findings: list[Finding]
    verdict: list[str]
    blocks: list[tuple[str, list[str]]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(finding.status == "pass" for finding in self.findings)

    @property
    def failed_count(self) -> int:
        return sum(1 for finding in self.findings if finding.status == "fail")


def _rule(
    rule_id: str,
    label: str,
    comparison: str,
    default_threshold: float,
    weight: float,
    detail: str,
) -> Rule:
    return Rule(
        id=rule_id,
        label=label,
        comparison=comparison,
        default_threshold=default_threshold,
        weight=weight,
        detail=detail,
        threshold=default_threshold,
        overridden=False,
    )


def with_override(rule: Rule, value: float | None) -> Rule:
    """Return `rule` with its threshold replaced, or unchanged with no override."""
    if value is None:
        return rule
    return replace(rule, threshold=value, overridden=True)


GRADE_RULESET = RuleSet(
    name="grade",
    version="v1",
    unit_system=UNIT_SYSTEM,
    rules=(
        _rule(
            "height_ratio_min",
            "Height/cap ratio (min)",
            "min",
            0.90,
            40.0,
            "A squat stone lets a rodent brace between the cap underside and the floor.",
        ),
        _rule(
            "height_ratio_max",
            "Height/cap ratio (max)",
            "max",
            2.20,
            25.0,
            "A column this slender can tip once the floor above is loaded.",
        ),
        _rule(
            "base_ratio_min",
            "Base/cap ratio (min)",
            "min",
            0.55,
            35.0,
            "A base this narrow spreads too little load into the ground.",
        ),
    ),
)

LAYOUT_RULESET = RuleSet(
    name="layout",
    version="v1",
    unit_system=UNIT_SYSTEM,
    rules=(
        _rule(
            "stone_count_min",
            "Stone count (min)",
            "min",
            4.0,
            40.0,
            "Four stones is the minimum stable support for a granary floor.",
        ),
        _rule(
            "spacing_max",
            "Stone spacing (max)",
            "max",
            150.0,
            30.0,
            "Wider spacing leaves the floor boards unsupported between stones.",
        ),
        _rule(
            "coverage_min",
            "Floor coverage (min)",
            "min",
            8.0,
            30.0,
            "Too little of the floor footprint sits directly over a cap.",
        ),
    ),
)

GUARD_RULESET = RuleSet(
    name="guard",
    version="v1",
    unit_system=UNIT_SYSTEM,
    rules=(
        _rule(
            "overhang_min",
            "Cap overhang (min)",
            "min",
            5.0,
            40.0,
            "The cap must overhang the guard disc so a rodent cannot reach past it.",
        ),
        _rule(
            "gap_max",
            "Cap-to-guard gap (max)",
            "max",
            4.0,
            30.0,
            "A wider cap-to-guard gap gives a rodent a handhold.",
        ),
        _rule(
            "clearance_min",
            "Ground clearance (min)",
            "min",
            40.0,
            30.0,
            "Low clearance lets a rodent reach the cap straight from the ground.",
        ),
    ),
)

RULESETS = {
    "grade": GRADE_RULESET,
    "layout": LAYOUT_RULESET,
    "guard": GUARD_RULESET,
}


# ---------------------------------------------------------------------------
# rule evaluation
# ---------------------------------------------------------------------------


def rule_quality(comparison: str, measured: float, threshold: float) -> float:
    """Score one measurement from 0.0 (worst) to 1.0 (full marks).

    A rule earns full marks once the measurement is clear of the threshold by
    the comfort factor, 0.70 exactly at the threshold, and falls away from
    there in either direction.
    """
    if threshold <= 0:
        return 0.0
    if comparison == "min":
        ideal = threshold * MIN_RULE_IDEAL_FACTOR
        if measured >= ideal:
            return 1.0
        if measured >= threshold:
            return 0.70 + 0.30 * (measured - threshold) / (ideal - threshold)
        return 0.70 * (measured / threshold)
    ideal = threshold * MAX_RULE_IDEAL_FACTOR
    if measured <= ideal:
        return 1.0
    if measured <= threshold:
        return 0.70 + 0.30 * (threshold - measured) / (threshold - ideal)
    if measured <= 0:
        return 0.0
    return 0.70 * (threshold / measured)


def evaluate(rule: Rule, measured: float) -> Finding:
    """Evaluate one rule and return its finding. Pure and deterministic."""
    if rule.comparison == "min":
        passed = measured >= rule.threshold
    else:
        passed = measured <= rule.threshold
    return Finding(
        rule_id=rule.id,
        label=rule.label,
        measured=measured,
        required=rule.threshold,
        comparison=rule.comparison,
        status="pass" if passed else "fail",
        overridden=rule.overridden,
        detail=rule.detail,
        quality=rule_quality(rule.comparison, measured, rule.threshold),
    )


def weighted_score(findings: list[Finding], rules: tuple[Rule, ...]) -> float:
    """Weighted mean of the finding qualities as a percentage, one decimal."""
    weights = {rule.id: rule.weight for rule in rules}
    total = sum(weights.get(finding.rule_id, 0.0) for finding in findings)
    if total <= 0:
        return 0.0
    earned = sum(
        weights.get(finding.rule_id, 0.0) * finding.quality for finding in findings
    )
    return round(100.0 * earned / total, 1)


def grade_band(score: float, passed: bool) -> str:
    """Map a score onto the A/B/C/reject bands; any failed rule rejects."""
    if not passed:
        return "reject"
    for threshold, band in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "C"


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------


def fmt(value: float) -> str:
    """Trim trailing zeros: 60.0 -> '60', 0.90 -> '0.9', 1.3333 -> '1.33'."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


def cm(value: float) -> str:
    return f"{fmt(value)} cm"


def plural(count: float, singular: str, plural_form: str = "") -> str:
    """'1 stone' vs '12 stones' without a silent lone plural."""
    if count == 1:
        return f"1 {singular}"
    return f"{fmt(count)} {plural_form or singular + 's'}"


def wrap_line(line: str, width: int = REPORT_WIDTH) -> list[str]:
    """Wrap one line to `width` columns, keeping its indentation."""
    if len(line) <= width:
        return [line]
    indent = " " * (len(line) - len(line.lstrip()))
    return textwrap.wrap(
        line.strip(),
        width=width,
        initial_indent=indent,
        subsequent_indent=indent + "  ",
        break_long_words=False,
        break_on_hyphens=False,
    ) or [indent]


def flatten(lines: list[str]) -> list[str]:
    """Wrap every line in the block, returning the final list of lines."""
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(wrap_line(line))
    return wrapped


def shell_lines(
    command_line: str,
    first_prefix: str,
    continuation_prefix: str,
    width: int = REPORT_WIDTH,
) -> list[str]:
    """Lay a long command out with trailing backslashes so it stays runnable.

    A flag is never separated from its value: when a break is needed the flag
    travels to the next line with it.
    """
    words = command_line.split()
    lines: list[str] = []
    prefix = first_prefix
    current: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        candidate = prefix + " ".join(current + [word])
        if current and len(candidate) > width - 2:
            carried: list[str] = []
            if not word.startswith("-") and current[-1].startswith("-"):
                carried = [current.pop()]
            lines.append(prefix + " ".join(current) + " \\")
            prefix = continuation_prefix
            current = carried + [word]
            index += 1
            continue
        current.append(word)
        index += 1
    lines.append(prefix + " ".join(current))
    return lines


def _kv(label: str, value: str, label_width: int = 26, value_width: int = 14) -> str:
    return f"  {label:<{label_width}}{value:>{value_width}}"


def _rule_table(findings: list[Finding]) -> list[str]:
    label_w, measure_w, require_w, result_w = 24, 9, 9, 20
    header = (
        f"{'Rule':<{label_w}} {'Measured':>{measure_w}}  "
        f"{'Required':>{require_w}}  {'Result':<{result_w}}"
    )
    separator = "-" * (label_w + 1 + measure_w + 2 + require_w + 2 + result_w)
    rows = [header, separator]
    for finding in findings:
        operator = ">=" if finding.comparison == "min" else "<="
        required = f"{operator} {finding.required:.2f}"
        result = "PASS" if finding.status == "pass" else "FAIL"
        if finding.overridden:
            result = f"{result} (overridden)"
        rows.append(
            f"{finding.label[:label_w]:<{label_w}} "
            f"{finding.measured:>{measure_w}.2f}  "
            f"{required:>{require_w}}  {result:<{result_w}}"
        )
    return rows


def _failure_details(findings: list[Finding]) -> list[str]:
    lines: list[str] = []
    for finding in findings:
        if finding.status != "fail":
            continue
        needed = "at least" if finding.comparison == "min" else "at most"
        lines.append(
            f"  {finding.label}: {finding.detail} "
            f"Needed {needed} {fmt(finding.required)}, "
            f"measured {fmt(finding.measured)}."
        )
    return lines


def summary_line(report: Report) -> str:
    total = len(report.findings)
    failed = report.failed_count
    if failed == 0:
        return f"Summary: PASS - {total} of {total} rules satisfied"
    return f"Summary: FAIL - {failed} of {total} rules failed"


def render_report(report: Report) -> str:
    """Render one report: title, inputs, blocks, rule table, verdict, summary."""
    lines: list[str] = []
    lines.append(report.title)
    lines.append(
        f"rule set {report.ruleset.name}-{report.ruleset.version} "
        f"| units: {UNIT_NAME}"
    )
    lines.append("=" * REPORT_WIDTH)
    lines.append("Inputs")
    for label, value in report.inputs:
        lines.append(_kv(label, value))
    for heading, block_lines in report.blocks:
        lines.append("")
        lines.append(heading)
        lines.extend(block_lines)
    lines.append("")
    lines.append("Rules")
    lines.extend(_rule_table(report.findings))
    details = _failure_details(report.findings)
    if details:
        lines.append("")
        lines.extend(details)
    if report.notes:
        lines.append("")
        lines.extend(f"  {note}" for note in report.notes)
    lines.append("")
    lines.extend(report.verdict)
    lines.append(summary_line(report))
    rendered = flatten(lines)
    return "\n".join(line.rstrip() for line in rendered) + "\n"


def print_wrapped(text: str, stream: TextIO) -> None:
    """Print a diagnostic wrapped to the report width, never mid-word."""
    for line in textwrap.wrap(
        text,
        width=REPORT_WIDTH,
        subsequent_indent="    ",
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]:
        print(line, file=stream)


def exit_code_for(report: Report) -> int:
    return 0 if report.passed else 1


# ---------------------------------------------------------------------------
# invocation help text
# ---------------------------------------------------------------------------


def invocation() -> str:
    """How the user reached us, so every printed example is copy-pasteable."""
    name = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else COMMAND_NAME
    if not name or name in ("-c", "-m"):
        return COMMAND_NAME
    if name.endswith(".py"):
        return f"python3 {name}"
    return name


def help_hint(command: str) -> str:
    return f"run '{invocation()} {command} --help' for usage"


def command_example(
    command: str, example_flags: str, first_prefix: str = "    example: "
) -> list[str]:
    """One runnable example line for `command`, wrapped with backslashes."""
    return shell_lines(
        f"{invocation()} {command} {example_flags}",
        first_prefix=first_prefix,
        continuation_prefix=" " * len(first_prefix),
    )


def usage_listing() -> str:
    inv = invocation()
    lines = [
        f"{PROGRAM.upper()} {VERSION} - three checks on a granary staddle-stone setup",
        f"All dimensions are {UNIT_NAME}.",
        "Exit codes: 0 all rules pass, 1 a rule failed, 2 usage or validation error.",
        "",
        f"usage: {inv} CHECK [options]",
        "",
        "checks",
    ]
    for command, summary, example_flags in (
        (
            "grade",
            "grade one staddle stone from its dimensions",
            "--height 60 --cap-diameter 45 --base-diameter 30",
        ),
        (
            "layout",
            "plan the staddle-stone grid for a rectangular floor",
            "--length 400 --width 300 --stone-spacing 100",
        ),
        (
            "guard",
            "check cap overhang, cap-to-guard gap and ground clearance",
            "--guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50",
        ),
    ):
        lines.append(f"  {command} - {summary}")
        lines.extend(command_example(command, example_flags))
    lines.append("")
    lines.append(f"Run '{inv} CHECK --help' for every flag, its built-in default")
    lines.append("and further worked examples.")
    return "\n".join(flatten(lines))


INVITATIONS = {
    "grade": (
        "grade --height CM --cap-diameter CM [--base-diameter CM]",
        "--height 60 --cap-diameter 45 --base-diameter 30",
        "grade one staddle stone from its height and cap diameter",
    ),
    "layout": (
        "layout --length CM --width CM --stone-spacing CM",
        "--length 400 --width 300 --stone-spacing 100",
        "plan the staddle-stone grid for a rectangular granary floor",
    ),
    "guard": (
        "guard --guard-diameter CM --cap-diameter CM --gap CM --clearance CM",
        "--guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50",
        "check cap overhang, cap-to-guard gap and ground clearance",
    ),
}


def invitation_text(command: str) -> str:
    """The 'no flags supplied' block: what the check does, usage, one example."""
    synopsis, example_flags, summary = INVITATIONS[command]
    inv = invocation()
    lines = [
        f"{COMMAND_NAME} {command} - {summary}",
        "",
        f"usage: {inv} {synopsis}",
        "",
        "example:",
    ]
    lines.extend(command_example(command, example_flags, first_prefix="  "))
    lines.append("")
    lines.append(f"All dimensions are {UNIT_NAME}.")
    lines.append(f"Run '{inv} {command} --help' for every flag and default.")
    return "\n".join(flatten(lines))


# ---------------------------------------------------------------------------
# input validation
# ---------------------------------------------------------------------------


def read_number(
    raw: str | None,
    flag: str,
    command: str,
    unit_name: str = "centimetres",
) -> float | None:
    """Parse one optional numeric flag. Returns None when the flag was absent."""
    if raw is None:
        return None
    try:
        value = float(raw.strip())
    except (AttributeError, ValueError):
        unit = f" in {unit_name}" if unit_name else ""
        raise UsageError(
            f"{flag} must be a number{unit}, got '{raw}'", help_hint(command)
        ) from None
    if not math.isfinite(value):
        raise UsageError(
            f"{flag} must be a finite number, got '{raw}'", help_hint(command)
        )
    if value <= 0:
        raise UsageError(
            f"{flag} must be greater than zero, got '{raw}'", help_hint(command)
        )
    return value


def require(value: float | None, flag: str, command: str) -> float:
    if value is None:
        raise UsageError(f"missing required flag {flag}", help_hint(command))
    return value


def require_above(
    value: float, minimum: float, flag: str, command: str, why: str
) -> float:
    if value <= minimum:
        raise UsageError(
            f"{flag} must be greater than {fmt(minimum)} cm ({why}), "
            f"got {fmt(value)} cm",
            help_hint(command),
        )
    return value


# ---------------------------------------------------------------------------
# grade
# ---------------------------------------------------------------------------


def build_grade_report(
    height: float,
    cap_diameter: float,
    base_diameter: float | None,
    min_height_ratio: float | None,
    max_height_ratio: float | None,
    min_base_ratio: float | None,
) -> Report:
    height_ratio = height / cap_diameter
    rules = GRADE_RULESET.rules
    min_rule = with_override(rules[0], min_height_ratio)
    max_rule = with_override(rules[1], max_height_ratio)
    base_rule = with_override(rules[2], min_base_ratio)

    findings = [evaluate(min_rule, height_ratio), evaluate(max_rule, height_ratio)]
    used_rules = (min_rule, max_rule)
    if base_diameter is not None:
        findings.append(evaluate(base_rule, base_diameter / cap_diameter))
        used_rules = (min_rule, max_rule, base_rule)

    score = weighted_score(findings, used_rules)
    passed = all(finding.status == "pass" for finding in findings)
    band = grade_band(score, passed)

    inputs = [
        ("height", cm(height)),
        ("cap diameter", cm(cap_diameter)),
        (
            "base diameter",
            cm(base_diameter) if base_diameter is not None else "not supplied",
        ),
        ("height/cap ratio", fmt(height_ratio)),
    ]
    if base_diameter is not None:
        inputs.append(("base/cap ratio", fmt(base_diameter / cap_diameter)))

    verdict = [
        f"Grade band: {band}   score: {score:.1f} of 100",
        f"Band {band} means {BAND_DESCRIPTIONS[band]}.",
    ]

    notes: list[str] = []
    if base_diameter is None:
        notes.append(
            "Base/cap ratio not checked - add --base-diameter CM to grade the base."
        )
    if min_height_ratio is not None:
        notes.append(
            f"Override: --min-height-ratio {fmt(min_height_ratio)} replaces the "
            f"built-in {min_rule.default_threshold:.2f}."
        )
    if max_height_ratio is not None:
        notes.append(
            f"Override: --max-height-ratio {fmt(max_height_ratio)} replaces the "
            f"built-in {max_rule.default_threshold:.2f}."
        )
    if min_base_ratio is not None:
        notes.append(
            f"Override: --min-base-ratio {fmt(min_base_ratio)} replaces the "
            f"built-in {base_rule.default_threshold:.2f}."
        )

    return Report(
        title=f"{PROGRAM.upper()} GRADE",
        ruleset=GRADE_RULESET,
        inputs=inputs,
        findings=findings,
        verdict=verdict,
        notes=notes,
    )


def cmd_grade(args: argparse.Namespace) -> int:
    command = "grade"
    height = read_number(args.height, "--height", command)
    cap_diameter = read_number(args.cap_diameter, "--cap-diameter", command)
    base_diameter = read_number(args.base_diameter, "--base-diameter", command)
    min_height_ratio = read_number(
        args.min_height_ratio, "--min-height-ratio", command, unit_name=""
    )
    max_height_ratio = read_number(
        args.max_height_ratio, "--max-height-ratio", command, unit_name=""
    )
    min_base_ratio = read_number(
        args.min_base_ratio, "--min-base-ratio", command, unit_name=""
    )

    height = require(height, "--height", command)
    cap_diameter = require(cap_diameter, "--cap-diameter", command)
    if base_diameter is not None and base_diameter > cap_diameter:
        raise UsageError(
            "--base-diameter must not exceed --cap-diameter "
            f"({fmt(cap_diameter)} cm), got {fmt(base_diameter)} cm",
            help_hint(command),
        )
    if (
        max_height_ratio is not None
        and min_height_ratio is not None
        and max_height_ratio <= min_height_ratio
    ):
        raise UsageError(
            "--max-height-ratio must be greater than --min-height-ratio "
            f"({fmt(min_height_ratio)}), got {fmt(max_height_ratio)}",
            help_hint(command),
        )

    report = build_grade_report(
        height,
        cap_diameter,
        base_diameter,
        min_height_ratio,
        max_height_ratio,
        min_base_ratio,
    )
    sys.stdout.write(render_report(report))
    return exit_code_for(report)


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GridPlan:
    columns: int
    rows: int
    stone_count: int
    coverage_pct: float
    row_positions: tuple[float, ...]


def plan_grid(
    length: float,
    width: float,
    spacing: float,
    cap_diameter: float,
    margin: float = EDGE_MARGIN_CM,
) -> GridPlan:
    """Closed-form grid: stones every `spacing` cm inside a fixed edge margin."""
    columns = max(1, int((length - 2 * margin) // spacing) + 1)
    rows = max(1, int((width - 2 * margin) // spacing) + 1)
    stone_count = columns * rows
    cap_area = math.pi * (cap_diameter / 2.0) ** 2
    coverage_pct = round(100.0 * stone_count * cap_area / (length * width), 2)
    row_positions = tuple(margin + index * spacing for index in range(rows))
    return GridPlan(columns, rows, stone_count, coverage_pct, row_positions)


def build_layout_report(
    length: float,
    width: float,
    spacing: float,
    cap_diameter: float,
    min_stone_count: float | None,
    max_stone_spacing: float | None,
    min_coverage: float | None,
) -> Report:
    plan = plan_grid(length, width, spacing, cap_diameter)
    rules = LAYOUT_RULESET.rules
    count_rule = with_override(rules[0], min_stone_count)
    spacing_rule = with_override(rules[1], max_stone_spacing)
    coverage_rule = with_override(rules[2], min_coverage)

    findings = [
        evaluate(count_rule, float(plan.stone_count)),
        evaluate(spacing_rule, spacing),
        evaluate(coverage_rule, plan.coverage_pct),
    ]

    grid_lines = [
        _kv("columns (along length)", str(plan.columns), 24, 8),
        _kv("rows (across width)", str(plan.rows), 24, 8),
        _kv("staddle stones", str(plan.stone_count), 24, 8),
        _kv("floor coverage", f"{plan.coverage_pct:.2f} %", 24, 8),
    ]

    row_lines = [
        f"  {'Row':>3}  {'From edge':>9}  {'Stones':>6}  {'Spacing':>8}",
        "  " + "-" * 32,
    ]
    for index, position in enumerate(plan.row_positions, start=1):
        row_lines.append(
            f"  {index:>3}  {cm(position):>9}  {plan.columns:>6}  {cm(spacing):>8}"
        )

    verdict = [
        f"Plan: {plural(plan.stone_count, 'stone')} on a "
        f"{plan.columns} x {plan.rows} grid, covering "
        f"{plan.coverage_pct:.2f}% of the floor footprint.",
    ]

    notes: list[str] = []
    if plan.columns < 2 or plan.rows < 2:
        notes.append(
            f"The requested spacing leaves a {plan.columns} x {plan.rows} grid - "
            "a single line of stones cannot carry a granary floor."
        )
        notes.append("Reduce --stone-spacing or extend the floor, then run again.")
    if max_stone_spacing is not None:
        notes.append(
            f"Override: --max-stone-spacing {fmt(max_stone_spacing)} replaces the "
            f"built-in {spacing_rule.default_threshold:.2f}."
        )
    if min_stone_count is not None:
        notes.append(
            f"Override: --min-stone-count {fmt(min_stone_count)} replaces the "
            f"built-in {count_rule.default_threshold:.2f}."
        )
    if min_coverage is not None:
        notes.append(
            f"Override: --min-coverage {fmt(min_coverage)} replaces the "
            f"built-in {coverage_rule.default_threshold:.2f}."
        )

    inputs = [
        ("floor length", cm(length)),
        ("floor width", cm(width)),
        ("stone spacing", cm(spacing)),
        ("cap diameter", cm(cap_diameter)),
        ("edge margin", f"{cm(EDGE_MARGIN_CM)} (fixed)"),
    ]

    return Report(
        title=f"{PROGRAM.upper()} LAYOUT",
        ruleset=LAYOUT_RULESET,
        inputs=inputs,
        findings=findings,
        verdict=verdict,
        blocks=[("Grid", grid_lines), ("Row positions", row_lines)],
        notes=notes,
    )


def cmd_layout(args: argparse.Namespace) -> int:
    command = "layout"
    length = read_number(args.length, "--length", command)
    width = read_number(args.width, "--width", command)
    spacing = read_number(args.stone_spacing, "--stone-spacing", command)
    cap_diameter = read_number(args.cap_diameter, "--cap-diameter", command)
    min_stone_count = read_number(
        args.min_stone_count, "--min-stone-count", command, unit_name=""
    )
    max_stone_spacing = read_number(
        args.max_stone_spacing, "--max-stone-spacing", command
    )
    min_coverage = read_number(
        args.min_coverage, "--min-coverage", command, unit_name=""
    )

    length = require(length, "--length", command)
    width = require(width, "--width", command)
    spacing = require(spacing, "--stone-spacing", command)
    if cap_diameter is None:
        cap_diameter = DEFAULT_CAP_DIAMETER_CM

    margin_span = 2 * EDGE_MARGIN_CM
    require_above(
        length,
        margin_span,
        "--length",
        command,
        f"the {fmt(EDGE_MARGIN_CM)} cm edge margin at both ends",
    )
    require_above(
        width,
        margin_span,
        "--width",
        command,
        f"the {fmt(EDGE_MARGIN_CM)} cm edge margin at both ends",
    )

    report = build_layout_report(
        length,
        width,
        spacing,
        cap_diameter,
        min_stone_count,
        max_stone_spacing,
        min_coverage,
    )
    sys.stdout.write(render_report(report))
    return exit_code_for(report)


# ---------------------------------------------------------------------------
# guard
# ---------------------------------------------------------------------------


def build_guard_report(
    guard_diameter: float,
    cap_diameter: float,
    gap: float,
    clearance: float,
    min_overhang: float | None,
    max_gap: float | None,
    min_clearance: float | None,
) -> Report:
    overhang = (cap_diameter - guard_diameter) / 2.0
    rules = GUARD_RULESET.rules
    overhang_rule = with_override(rules[0], min_overhang)
    gap_rule = with_override(rules[1], max_gap)
    clearance_rule = with_override(rules[2], min_clearance)

    findings = [
        evaluate(overhang_rule, overhang),
        evaluate(gap_rule, gap),
        evaluate(clearance_rule, clearance),
    ]

    verdict = [
        f"Guard geometry: overhang {cm(overhang)} per side, "
        f"cap-to-guard gap {cm(gap)}, ground clearance {cm(clearance)}.",
    ]

    notes: list[str] = []
    if min_overhang is not None:
        notes.append(
            f"Override: --min-overhang {fmt(min_overhang)} replaces the built-in "
            f"{overhang_rule.default_threshold:.2f}."
        )
    if max_gap is not None:
        notes.append(
            f"Override: --max-gap {fmt(max_gap)} replaces the built-in "
            f"{gap_rule.default_threshold:.2f}."
        )
    if min_clearance is not None:
        notes.append(
            f"Override: --min-clearance {fmt(min_clearance)} replaces the built-in "
            f"{clearance_rule.default_threshold:.2f}."
        )

    inputs = [
        ("guard disc diameter", cm(guard_diameter)),
        ("cap diameter", cm(cap_diameter)),
        ("cap overhang per side", cm(overhang)),
        ("cap-to-guard gap", cm(gap)),
        ("ground clearance", cm(clearance)),
    ]

    return Report(
        title=f"{PROGRAM.upper()} GUARD",
        ruleset=GUARD_RULESET,
        inputs=inputs,
        findings=findings,
        verdict=verdict,
        notes=notes,
    )


def cmd_guard(args: argparse.Namespace) -> int:
    command = "guard"
    guard_diameter = read_number(args.guard_diameter, "--guard-diameter", command)
    cap_diameter = read_number(args.cap_diameter, "--cap-diameter", command)
    gap = read_number(args.gap, "--gap", command)
    clearance = read_number(args.clearance, "--clearance", command)
    min_overhang = read_number(args.min_overhang, "--min-overhang", command)
    max_gap = read_number(args.max_gap, "--max-gap", command)
    min_clearance = read_number(args.min_clearance, "--min-clearance", command)

    guard_diameter = require(guard_diameter, "--guard-diameter", command)
    cap_diameter = require(cap_diameter, "--cap-diameter", command)
    gap = require(gap, "--gap", command)
    clearance = require(clearance, "--clearance", command)

    if cap_diameter < guard_diameter:
        raise UsageError(
            "--cap-diameter must be at least as wide as --guard-diameter "
            f"({fmt(guard_diameter)} cm), got {fmt(cap_diameter)} cm",
            help_hint(command),
        )

    report = build_guard_report(
        guard_diameter,
        cap_diameter,
        gap,
        clearance,
        min_overhang,
        max_gap,
        min_clearance,
    )
    sys.stdout.write(render_report(report))
    return exit_code_for(report)


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


class ReportFormatter(argparse.RawDescriptionHelpFormatter):
    """Keep --help at the report width whatever the terminal reports."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, width=REPORT_WIDTH, max_help_position=26)


def _add_flag(
    parser: argparse.ArgumentParser,
    flag: str,
    metavar: str,
    text: str,
) -> None:
    parser.add_argument(
        flag, metavar=metavar, dest=flag.lstrip("-").replace("-", "_"), help=text
    )


def _examples_epilog(command: str, examples: list[str]) -> str:
    lines = ["examples:", ""]
    for example_flags in examples:
        lines.extend(command_example(command, example_flags, first_prefix="  "))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    inv = invocation()
    parser = argparse.ArgumentParser(
        prog=inv,
        add_help=False,
        description=(
            f"{PROGRAM} {VERSION} - three checks on a granary staddle-stone setup.\n"
            f"All dimensions are {UNIT_NAME}."
        ),
        formatter_class=ReportFormatter,
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {VERSION}")
    subparsers = parser.add_subparsers(dest="command", metavar="CHECK")

    grade = subparsers.add_parser(
        "grade",
        add_help=True,
        description=(
            "Grade one staddle stone from its dimensions and report a band.\n"
            "Every length is in centimetres; ratios are unitless."
        ),
        epilog=_examples_epilog(
            "grade",
            [
                "--height 60 --cap-diameter 45 --base-diameter 30",
                "--height 180 --cap-diameter 45",
                "--height 60 --cap-diameter 45 --min-height-ratio 1.40",
            ],
        ),
        formatter_class=ReportFormatter,
    )
    _add_flag(grade, "--height", "CM", "stone height (cm); required")
    _add_flag(grade, "--cap-diameter", "CM", "cap diameter (cm); required")
    _add_flag(
        grade,
        "--base-diameter",
        "CM",
        "base diameter (cm); optional, enables the base/cap rule",
    )
    _add_flag(
        grade,
        "--min-height-ratio",
        "RATIO",
        "override: minimum height/cap ratio (built-in default 0.90)",
    )
    _add_flag(
        grade,
        "--max-height-ratio",
        "RATIO",
        "override: maximum height/cap ratio (built-in default 2.20)",
    )
    _add_flag(
        grade,
        "--min-base-ratio",
        "RATIO",
        "override: minimum base/cap ratio (built-in default 0.55)",
    )
    grade.set_defaults(handler=cmd_grade)

    layout = subparsers.add_parser(
        "layout",
        add_help=True,
        description=(
            "Plan the staddle-stone grid for a rectangular granary floor.\n"
            "Every length is in centimetres; the edge margin is a fixed "
            f"{fmt(EDGE_MARGIN_CM)} cm."
        ),
        epilog=_examples_epilog(
            "layout",
            [
                "--length 400 --width 300 --stone-spacing 100",
                "--length 600 --width 400 --stone-spacing 120 --cap-diameter 70",
            ],
        ),
        formatter_class=ReportFormatter,
    )
    _add_flag(layout, "--length", "CM", "floor length (cm); required")
    _add_flag(layout, "--width", "CM", "floor width (cm); required")
    _add_flag(
        layout,
        "--stone-spacing",
        "CM",
        "centre-to-centre stone spacing (cm); required",
    )
    _add_flag(
        layout,
        "--cap-diameter",
        "CM",
        "cap diameter used for the coverage figure "
        f"(cm; built-in default {fmt(DEFAULT_CAP_DIAMETER_CM)})",
    )
    _add_flag(
        layout,
        "--min-stone-count",
        "COUNT",
        "override: minimum stone count (built-in default 4)",
    )
    _add_flag(
        layout,
        "--max-stone-spacing",
        "CM",
        "override: maximum stone spacing (built-in default 150)",
    )
    _add_flag(
        layout,
        "--min-coverage",
        "PERCENT",
        "override: minimum coverage in percent (built-in default 8)",
    )
    layout.set_defaults(handler=cmd_layout)

    guard = subparsers.add_parser(
        "guard",
        add_help=True,
        description=(
            "Check a stone's rodent-guard geometry: cap overhang, cap-to-guard\n"
            "gap and ground clearance. Every length is in centimetres."
        ),
        epilog=_examples_epilog(
            "guard",
            [
                "--guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50",
                "--guard-diameter 40 --cap-diameter 60 --gap 6 --clearance 30",
                "--guard-diameter 45 --cap-diameter 60 --gap 3 --clearance 50 "
                "--min-overhang 8",
            ],
        ),
        formatter_class=ReportFormatter,
    )
    _add_flag(guard, "--guard-diameter", "CM", "guard disc diameter (cm); required")
    _add_flag(guard, "--cap-diameter", "CM", "cap diameter (cm); required")
    _add_flag(
        guard, "--gap", "CM", "gap between cap underside and guard disc (cm); required"
    )
    _add_flag(
        guard, "--clearance", "CM", "ground clearance to the guard disc (cm); required"
    )
    _add_flag(
        guard,
        "--min-overhang",
        "CM",
        "override: minimum cap overhang per side (built-in default 5)",
    )
    _add_flag(
        guard,
        "--max-gap",
        "CM",
        "override: maximum cap-to-guard gap (built-in default 4)",
    )
    _add_flag(
        guard,
        "--min-clearance",
        "CM",
        "override: minimum ground clearance (built-in default 40)",
    )
    guard.set_defaults(handler=cmd_guard)

    return parser


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)

    if not args_list or args_list[0] in ("-h", "--help"):
        print(usage_listing())
        return 0
    if args_list[0] in ("--version", "-V"):
        print(f"{PROGRAM} {VERSION}")
        return 0

    command = args_list[0]
    if command not in RULESETS:
        print_wrapped(
            f"{COMMAND_NAME}: unknown command '{command}'", sys.stderr
        )
        print("", file=sys.stderr)
        print(usage_listing(), file=sys.stderr)
        return 2

    if len(args_list) == 1:
        print(invitation_text(command), file=sys.stderr)
        return 2

    parser = build_parser()
    args = parser.parse_args(args_list)
    handler = getattr(args, "handler", None)
    if handler is None:
        print(usage_listing(), file=sys.stderr)
        return 2

    try:
        return handler(args)
    except UsageError as error:
        print_wrapped(f"{COMMAND_NAME}: {error.message}", sys.stderr)
        if error.hint:
            print_wrapped(f"{COMMAND_NAME}: {error.hint}", sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
