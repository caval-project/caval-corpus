#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 32 — Refine relation="voc" into vocative/discourse.

RULES (applied only when relation="voc"):
  - If part-of-speech in {"INTJ", "PART"} -> relation="discourse"
  - Otherwise -> relation="vocative"

CLI
    python scripts/prioel2conllu/stages/32_refine_voc_relation.py \
        --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

# ------------- Attribute helpers -------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b{name}="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value" on a token line."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

# ------------- Core mapping -------------

def refine_voc(line: str, verbose: bool = False) -> str:
    rel = get_attr(line, "relation")
    if rel != "voc":
        return line

    upos = get_attr(line, "part-of-speech") or ""
    new_rel = "discourse" if upos in {"INTJ", "PART"} else "vocative"

    if verbose:
        tid = get_attr(line, "id") or "?"
        print(f'[voc->{new_rel}] id={tid} pos={upos}')

    return set_attr(line, "relation", new_rel)

# ------------- File I/O & CLI -------------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for raw in infile:
            line = raw.rstrip("\n")
            line = refine_voc(line, verbose=verbose)
            outfile.write(line if raw.endswith("\n") else line + "\n")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 32: refine relation='voc' into vocative/discourse.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
