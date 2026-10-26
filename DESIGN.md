# Stiltstep design source of truth

Stiltstep is a terminal product: its only surface is stdout. This file commits
the design direction and records how each token is expressed (or deliberately
is not expressed) in that surface.

## Committed direction

| Token | Value | How it appears in Stiltstep |
| ----- | ----- | --------------------------- |
| Archetype | `cli` | plain-text reports, no browser, no server |
| Style family | calm-precise | fixed column widths, no decoration, no filler |
| Accent (ONE) | `oklch(0.58 0.12 268)` / `#5c76c1` | reserved; not emitted (see below) |
| Type personality | mono / mono | monospaced grid: every value right-aligned in its column |
| Density | compact | one line per rule, no blank filler inside a table |
| Signature | aligned columns, one accent for primary status, no colour-only signal | `Rule / Measured / Required / Result` columns; PASS/FAIL as words |
| Shape language | monospace, no chrome, separators | `=` rule under the title, `-` rule under the table header |
| Surface | terminal dark | the terminal's own background; Stiltstep prints no background |
| Type family | system monospace | inherited from the terminal, nothing loaded, nothing bundled |

## Expression rules

1. **Aligned columns.** The rule table is a fixed 24 / 9 / 9 / 20 column grid
   (`_rule_table` in `stiltstep.py`), separated by single spaces, so every
   report for every check lines up identically.
2. **Status is a word, never a colour.** `PASS`, `FAIL`, `Summary: PASS`,
   `Summary: FAIL`, `(overridden)`. The plan excludes colour and TTY detection,
   so no ANSI escape is ever emitted and no signal depends on colour.
3. **Two separators, ASCII only.** A `=` run at 78 columns under the header and
   a `-` run under the table header. The house shape language mentions
   box-drawing characters; the brief's non-functional requirement ("ASCII only
   so it renders in any terminal") wins, so the box-drawing set is expressed as
   ASCII runs instead.
4. **78 columns, hard.** Every rendered line - report, help, usage listing and
   diagnostic - is wrapped by `wrap_line` / `print_wrapped`, with wrapped
   continuations indented to their block. Long example commands break on a
   trailing backslash so they stay copy-pasteable.
5. **One spacing scale.** Two spaces between columns, two spaces of block
   indent, one blank line between sections. Nothing else.
6. **Accent.** `oklch(0.58 0.12 268)` / `#5c76c1` is the single accent for this
   product. It is not emitted today because the brief excludes colour output;
   if a companion surface is ever added (a help browser, a printed specification
   sheet), that accent is the only highlight colour, on terminal-dark neutrals,
   used for the primary status only and never as the sole carrier of meaning.
   Charting or canvas code that cannot parse `oklch()` must use `#5c76c1`.

## Neutral ramp (terminal dark)

Reserved for any future non-terminal surface, so the accent keeps one context:

| Token | Value | Use |
| ----- | ----- | --- |
| `--s-base` | `oklch(0.16 0.01 268)` | page background |
| `--s-panel` | `oklch(0.21 0.012 268)` | report block background |
| `--s-line` | `oklch(0.34 0.014 268)` | separators, table rules |
| `--s-muted` | `oklch(0.62 0.02 268)` | secondary labels |
| `--s-text` | `oklch(0.93 0.008 268)` | body text (>= 7:1 on base) |
| `--s-accent` | `oklch(0.58 0.12 268)` | primary status / single highlight |

## Anti-patterns this build refuses

No colour output, no spinners, no box-drawing art, no emoji, no tables wider
than the terminal, no lone plural ("1 stones"), no half-rendered report on bad
input, no report on stdout when validation fails.
