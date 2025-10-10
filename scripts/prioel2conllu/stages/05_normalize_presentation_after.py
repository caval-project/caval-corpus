#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 05 — Normalize punctuation in the `presentation-after` attribute.

PURPOSE
    Clean whitespace and normalize specific punctuation patterns in
    presentation-after="...":
      - Remove any spaces inside the attribute value.
      - Map "."  -> ":"
      - Map ":" or any repetition of ":." (":.", ":.:.", ":.:.:.", ...) -> "."
      - Leave all other values unchanged.

INPUT
    Arbitrary lines that may contain the attribute presentation-after="...".

OUTPUT
    Same lines with normalized presentation-after values.

CLI
    python scripts/prioel2conllu/stages/05_normalize_presentation_after.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Match presentation-after="...". Group(1) is the prefix, group(2) is value, group(3) is the trailing quote.
PA_RE = re.compile(r'(presentation-after=")([^"]*)(")')

# Matches ":" or any repetition of the sequence ":."
# Examples that match: ":", ":.", ":.:.", ":.:.:.", ...
SPECIAL_COLON_DOT_RE = re.compile(r'^(?:$|:|\:(?:\.)+)(?:\.(?::\.)*)?$')  # we'll simplify below with a cleaner rule


def normalize_presentation_after(value: str) -> str:
    """
    Apply the same effective logic as the original two-pass script:
      - strip spaces
      - if value == "." -> ":"
      - if value in {":", ":.", ":.:.", ":.:.:.", ":.:.:.:.", ...} -> "."
      - else unchanged
    """
    v = value.replace(" ", "")

    # Handle dot -> colon
    if v == ".":
        return ":"

    # Handle ":" and any repetitions of ":."
    # Equivalent to your explicit list: ":", ":.", ":.:.", ":.:.:.", ":.:.:.:.", ...
    # Pattern: start with ":"; then zero or more occurrences of ".:"
    # BUT your examples end with ".", not ":". So the general form is ": (.:)* ."
    # We also allow just ":".
    if v == ":" or re.fullmatch(r':(?:\.(?:\:))*(?:\.)?', v) and (v == ":" or v.endswith(".")):
        return "."

    return v


def process_line(line: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        prefix, val, suffix = m.groups()
        return f'{prefix}{normalize_presentation_after(val)}{suffix}'

    # Replace every occurrence on the line
    return PA_RE.sub(_sub, line)


def process_file(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for raw in infile:
            outfile.write(process_line(raw))


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 05: normalize `presentation-after` punctuation.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)


if __name__ == "__main__":
    main()
