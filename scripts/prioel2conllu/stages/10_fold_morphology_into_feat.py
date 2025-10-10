#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 10 — Fold any remaining `morphology="..."` into `FEAT="..."`, then remove `morphology`.

PURPOSE
    If a line still has morphology="...", combine it with FEAT:
      - Both present: FEAT="<FEAT>|<morphology>"
      - Only morphology present: FEAT="<morphology>"
    Clean up:
      - Avoid duplicate separators
      - Treat FEAT="_" as empty
      - Trim whitespace
    Finally remove the morphology attribute.

CLI
    python scripts/prioel2conllu/stages/10_fold_morphology_into_feat.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

# --- Attribute helpers --------------------------------------------------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value"."""
    if re.search(fr'\b{name}="', line):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def remove_attr(line: str, name: str) -> str:
    """Remove the first occurrence of an attribute entirely."""
    return re.sub(fr'\s*\b{name}="[^"]*"', "", line, count=1)

# --- Core logic ---------------------------------------------------------------

def normalize_feat_value(val: Optional[str]) -> str:
    """Normalize FEAT content: None/'' -> '', '_' -> ''."""
    if not val or val == "_":
        return ""
    return val.strip("| ")

def combine_feat_and_morph(feat: str, morph: str) -> str:
    """Join two feature strings with '|' (skip empties, de-duplicate pipes)."""
    feat = normalize_feat_value(feat)
    morph = normalize_feat_value(morph)
    if feat and morph:
        return f"{feat}|{morph}"
    return feat or morph or "_"

def transform_line(line: str) -> str:
    morph = get_attr(line, "morphology")
    if morph is None:
        return line

    current_feat = get_attr(line, "FEAT")
    new_feat = combine_feat_and_morph(current_feat or "", morph)

    line = set_attr(line, "FEAT", new_feat)
    line = remove_attr(line, "morphology")
    return line

# --- File I/O & CLI -----------------------------------------------------------

def process_file(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for raw in infile:
            out = transform_line(raw.rstrip("\n"))
            outfile.write(out if out.endswith("\n") else out + "\n")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 10: fold morphology into FEAT and remove morphology.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
