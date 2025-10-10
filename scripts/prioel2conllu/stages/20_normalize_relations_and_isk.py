#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 20 — Normalize relations and handle `lemma="isk"`.

RULES (applied per token line):
  1) If the line DOES NOT contain '<slash', then:
       pred -> root
       xobj -> xcomp
       ag   -> obl:agent
       rel  -> acl
  2) AFTER #1, if lemma="isk" is present, force relation="discourse".

NOTES
  - We only touch the `relation` attribute (not substrings elsewhere).
  - Works line-by-line; sentence boundaries are irrelevant here.
  - UTF-8 I/O; CLI consistent with earlier stages.

CLI
  python scripts/prioel2conllu/stages/20_normalize_relations_and_isk.py \
      --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

# -------- Attribute helpers --------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b{name}="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value"."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # Insert before '/>' or '>'
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

# -------- Mapping --------

REL_MAP = {
    "pred": "root",
    "xobj": "xcomp",
    "ag": "obl:agent",
    "rel": "acl",
}

# -------- Core transform --------

def transform_line(line: str) -> str:
    # Skip mapping on lines that contain '<slash' (preserves your negative lookahead semantics)
    if "<slash" not in line:
        cur_rel = get_attr(line, "relation")
        if cur_rel in REL_MAP:
            line = set_attr(line, "relation", REL_MAP[cur_rel])

    # After base replacements, enforce lemma="isk" -> relation="discourse"
    if 'lemma="isk"' in line and has_attr(line, "relation"):
        line = set_attr(line, "relation", "discourse")

    return line

def process_file(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8") as f_in, output_path.open("w", encoding="utf-8") as f_out:
        for raw in f_in:
            out = transform_line(raw.rstrip("\n"))
            f_out.write(out if raw.endswith("\n") else out + "\n")

# -------- CLI --------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 20: normalize relations and set lemma='isk' to discourse.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
