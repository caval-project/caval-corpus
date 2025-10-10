#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 30 — Refine relation="part" into obl/nmod.

RULE
    For each token with relation="part" in a sentence:
      - If it has any dependent with part-of-speech="ADP" -> relation="obl"
      - Else -> relation="nmod"

NOTES
    - Sentence-bounded (IDs typically reset per sentence).
    - Attribute-safe updates using small helpers.
    - UTF-8 I/O and CLI consistent with earlier stages.

CLI
    python scripts/prioel2conllu/stages/30_refine_part_relations.py \
        --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional

# -------- Attribute helpers --------

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

# -------- Per-sentence processing --------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process one sentence block (without the trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    # Build id -> children index
    children: Dict[str, List[int]] = {}
    for idx, line in enumerate(tokens):
        hid = get_attr(line, "head-id")
        if hid:
            children.setdefault(hid, []).append(idx)

    for i, line in enumerate(tokens):
        if get_attr(line, "relation") != "part":
            continue

        tid = get_attr(line, "id") or ""
        # Does this token have an ADP child?
        has_adp_child = any(
            get_attr(tokens[j], "part-of-speech") == "ADP"
            for j in children.get(tid, [])
        )

        new_rel = "obl" if has_adp_child else "nmod"

        if verbose:
            print(f'[part->{new_rel}] id={tid or "?"} adp_child={has_adp_child}')

        tokens[i] = set_attr(line, "relation", new_rel)

    return "\n".join(tokens)

# -------- File I/O & CLI --------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Accept either "\n</sentence>" or bare "</sentence>" as separator
    if "\n</sentence>" in text:
        parts = text.split("\n</sentence>")
        sep = "\n</sentence>"
    else:
        parts = text.split("</sentence>")
        sep = "</sentence>"

    for idx, part in enumerate(parts):
        blk = part.strip()
        if not blk:
            continue
        parts[idx] = process_sentence(blk, verbose=verbose)

    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 30: refine relation='part' into obl/nmod.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
