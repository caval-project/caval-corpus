#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 25 — Refine tokens with relation="aux" using POS.

Rules (applied only when relation="aux"):
  - part-of-speech="DET"   -> relation="det"
  - part-of-speech="INTJ"  -> relation="discourse"
  - part-of-speech="AUX"   -> relation remains "aux"
  - otherwise              -> relation="advmod"

CLI
    python scripts/prioel2conllu/stages/25_refine_aux_relations.py \
        --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

# ---------------- Attribute helpers ----------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b{name}="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value" on a token line."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # Insert before '/>' or '>'
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

# ---------------- Core mapping ----------------

def refine_aux_relation(line: str, verbose: bool = False) -> str:
    rel = get_attr(line, "relation")
    if rel != "aux":
        return line

    upos = get_attr(line, "part-of-speech") or ""
    new_rel = None

    if upos == "DET":
        new_rel = "det"
    elif upos == "INTJ":
        new_rel = "discourse"
    elif upos == "AUX":
        new_rel = "aux"  # explicit, no change
    else:
        new_rel = "advmod"

    if verbose:
        tid = get_attr(line, "id") or "?"
        print(f'[aux->{new_rel}] token id={tid} pos={upos}')

    return set_attr(line, "relation", new_rel)

# ---------------- File I/O & CLI ----------------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for raw in infile:
            line = raw.rstrip("\n")
            line = refine_aux_relation(line, verbose=verbose)
            outfile.write(line if raw.endswith("\n") else line + "\n")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 25: refine relation='aux' using part-of-speech.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
