#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 15 — Convert `mi#2` to DET when it follows its head.

RULE
    For each token line inside a sentence:
      If lemma="mi#2" AND its head-id refers to a token that has already
      appeared earlier in the same sentence (i.e., the current token follows
      its head in surface order), then:
        - set part-of-speech="DET"
        - remove feature NumType=Card from FEAT (if present)
        - add feature  Definite=Spec to FEAT

NOTES
    - Tracking resets at sentence boundaries (`</sentence>`).
    - FEAT merging preserves existing features; "_" is treated as empty.

CLI
    python scripts/prioel2conllu/stages/15_mi2_after_head_to_det.py \
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
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def parse_feats(s: Optional[str]) -> Dict[str, str]:
    if not s or s == "_":
        return {}
    out: Dict[str, str] = {}
    for kv in s.split("|"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
    return out

def feats_to_str(d: Dict[str, str]) -> str:
    return "_" if not d else "|".join(f"{k}={d[k]}" for k in sorted(d))

# -------- Core transform --------

def transform_lines(lines: list[str], verbose: bool = False) -> list[str]:
    """
    Process the file line-by-line, resetting state at sentence boundaries.
    """
    processed_ids_in_sentence: set[str] = set()
    out_lines: list[str] = []

    for raw in lines:
        line = raw.rstrip("\n")

        # Reset tracking at sentence end
        if "</sentence>" in line:
            processed_ids_in_sentence.clear()
            out_lines.append(raw)
            continue

        tid = get_attr(line, "id")
        lemma = get_attr(line, "lemma")
        head  = get_attr(line, "head-id")

        # Apply rule: lemma=mi#2 AND head already seen in this sentence
        if lemma == "mi#2" and head and head in processed_ids_in_sentence:
            # POS -> DET
            line = set_attr(line, "part-of-speech", "DET")

            # FEAT: remove NumType=Card (if any), then add Definite=Spec
            feats = parse_feats(get_attr(line, "FEAT"))
            if feats.get("NumType") == "Card":
                del feats["NumType"]
            feats["Definite"] = "Spec"
            line = set_attr(line, "FEAT", feats_to_str(feats))

            if verbose and tid:
                print(f"[mi#2->DET] token id={tid}: removed NumType=Card; added Definite=Spec")

        # After processing, record this token id as seen in the sentence
        if tid:
            processed_ids_in_sentence.add(tid)

        out_lines.append(line + ("\n" if not raw.endswith("\n") else ""))

    return out_lines

# -------- File I/O & CLI --------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    with input_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = transform_lines(lines, verbose=verbose)
    with output_path.open("w", encoding="utf-8") as f:
        f.writelines(new_lines)

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 15: convert mi#2 to DET if it follows its head.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print debug messages")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
