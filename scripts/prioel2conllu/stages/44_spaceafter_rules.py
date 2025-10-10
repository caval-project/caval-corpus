#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 44 — Add SpaceAfter=No based on Translit/LTranslit heuristics.

Rules (evaluated per sentence in a streaming fashion):
  A) If CURRENT token's MISC has Translit in {y, z, cʻ, čʻ}, add SpaceAfter=No to CURRENT.
  B) If CURRENT token's MISC has LTranslit in {s, d, n, :, ., ,, ;}, add SpaceAfter=No to PREVIOUS token.

Notes
  • Input is CoNLL-U (10 tab-separated columns) with comment lines starting '#'
    and sentences separated by blank lines.
  • Idempotent: won't add SpaceAfter=No twice.
  • Unknown/other MISC items are preserved as-is.

CLI
  python scripts/prioel2conllu/stages/44_spaceafter_rules.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional

# ---------------- helpers ----------------

def is_token_line(s: str) -> bool:
    return not s.startswith("#") and bool(s.strip())

def split_conllu_cols(line: str) -> Optional[List[str]]:
    """Return list of 10 columns or None if malformed."""
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 10:
        return None
    return parts

def join_conllu_cols(cols: List[str]) -> str:
    return "\t".join(cols) + "\n"

def get_misc_value(misc: str, key: str) -> Optional[str]:
    if not misc or misc == "_":
        return None
    # Match key=value up to the next '|' or end of string.
    m = re.search(rf'(?:(?<=\|)|^){re.escape(key)}=([^|]+)(?:\||$)', misc)
    return m.group(1) if m else None

def has_spaceafter_no(misc: str) -> bool:
    if not misc:
        return False
    return bool(re.search(r'(?:(?<=\|)|^)SpaceAfter=No(?:\||$)', misc))

def add_spaceafter_no(misc: str) -> str:
    """Append SpaceAfter=No if not already present; preserve '_' properly."""
    if has_spaceafter_no(misc):
        return misc
    if not misc or misc == "_":
        return "SpaceAfter=No"
    return misc + "|SpaceAfter=No"

# Sets per your original logic
TRANSLIT_NO_SPACE = {"y", "z", "cʻ", "čʻ"}
LTRANSLIT_PREV_NO_SPACE = {"s", "d", "n", ":", ".", ",", ";"}

# ---------------- core ----------------

def process_file(inp: Path, outp: Path, verbose: bool = False) -> None:
    with inp.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    prev_cols: Optional[List[str]] = None     # buffered previous token columns
    out_lines: List[str] = []

    def flush_prev():
        nonlocal prev_cols
        if prev_cols is not None:
            out_lines.append(join_conllu_cols(prev_cols))
            prev_cols = None

    for raw in lines:
        # Sentence boundary or comment: flush any buffered token first
        if raw.strip() == "" or raw.startswith("#"):
            flush_prev()
            out_lines.append(raw)
            continue

        cols = split_conllu_cols(raw)
        if cols is None:
            # Malformed line: flush prev and pass it through as-is
            flush_prev()
            out_lines.append(raw)
            continue

        # --- Rule B: current token may influence previous token ---
        misc_cur = cols[9]
        ltranslit_val = get_misc_value(misc_cur, "LTranslit")

        if prev_cols is not None and ltranslit_val in LTRANSLIT_PREV_NO_SPACE:
            if verbose:
                print(f"[prev SpaceAfter=No] id={prev_cols[0]} because next LTranslit={ltranslit_val!r}")
            prev_cols[9] = add_spaceafter_no(prev_cols[9])

        # --- Rule A: current token may need SpaceAfter=No itself ---
        translit_val = get_misc_value(misc_cur, "Translit")
        if translit_val in TRANSLIT_NO_SPACE:
            if verbose:
                print(f"[curr SpaceAfter=No] id={cols[0]} because Translit={translit_val!r}")
            cols[9] = add_spaceafter_no(cols[9])

        # Now that prev is fully decided, write it out; keep current as new prev
        flush_prev()
        prev_cols = cols

    # End of file: flush last buffered token
    flush_prev()

    outp.write_text("".join(out_lines), encoding="utf-8")
    if verbose:
        print(f"[spaceafter] wrote {outp}")

# ---------------- CLI ----------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 44: add SpaceAfter=No based on Translit/LTranslit rules.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input CoNLL-U file")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output CoNLL-U file")
    ap.add_argument("--verbose", action="store_true", help="Print decisions")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
