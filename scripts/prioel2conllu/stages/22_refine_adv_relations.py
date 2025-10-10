#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 22 — Refine generic relation="adv" into UD-specific relations.

RULES (applied only when relation="adv"):
  1) part-of-speech="ADV" AND FEAT PronType in {Int, Rel}  -> relation="mark"
  2) part-of-speech="NUM"                                   -> relation="nummod"
  3) part-of-speech in {"ADV","PART"}                       -> relation="advmod"
  4) part-of-speech in {"NOUN","PROPN","PRON"} OR VerbForm=Vnoun -> relation="obl"
  5) otherwise                                              -> relation="advcl"

CLI
  python scripts/prioel2conllu/stages/22_refine_adv_relations.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, Dict

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

# -------- FEAT parsing --------

def parse_feats(s: Optional[str]) -> Dict[str, str]:
    if not s or s == "_":
        return {}
    out: Dict[str, str] = {}
    for kv in s.split("|"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
    return out

# -------- Core mapping --------

def map_adv_relation(line: str, verbose: bool = False) -> str:
    rel = get_attr(line, "relation")
    if rel != "adv":
        return line

    upos = get_attr(line, "part-of-speech") or ""
    feats = parse_feats(get_attr(line, "FEAT"))

    new_rel: Optional[str] = None

    # 1) ADV + PronType in {Int, Rel} => mark
    if upos == "ADV" and feats.get("PronType") in {"Int", "Rel"}:
        new_rel = "mark"
    # 2) NUM => nummod
    elif upos == "NUM":
        new_rel = "nummod"
    # 3) ADV or PART => advmod
    elif upos in {"ADV", "PART"}:
        new_rel = "advmod"
    # 4) NOUN/PROPN/PRON or VerbForm=Vnoun => obl
    elif upos in {"NOUN", "PROPN", "PRON"} or feats.get("VerbForm") == "Vnoun":
        new_rel = "obl"
    # 5) default => advcl
    else:
        new_rel = "advcl"

    if verbose:
        tid = get_attr(line, "id") or "?"
        print(f'[adv->{new_rel}] token id={tid} pos={upos} feats={feats}')

    return set_attr(line, "relation", new_rel)

# -------- File I/O & CLI --------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for raw in infile:
            line = raw.rstrip("\n")
            line = map_adv_relation(line, verbose=verbose)
            outfile.write(line if raw.endswith("\n") else line + "\n")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 22: refine relation='adv' based on POS and FEATS.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print debug logs to stdout")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
