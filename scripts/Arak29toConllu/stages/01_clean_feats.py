#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 01 — Clean FEATS column in scraped CoNLL-U blocks.

What it does
------------
- Reads CoNLL-U-like lines produced by the scraper.
- For token lines (non-comment, non-empty), cleans column #6 (FEATS):
  * Split on '/'
  * Drop empty segments and segments that are just '.'
  * Keep everything else unchanged (e.g., "a.", "adj.", raw fragments)
  * If nothing remains, set FEATS to '_'
- Passes through comments (# …) and blank lines unchanged.
- Writes a well-formed tab-separated file.

Notes
-----
This stage intentionally does not enforce UD feature format (Key=Val).
It only removes noise introduced by scraping (stray slashes and bare periods).

Usage
-----
python Arak29toConllu/stages/01_clean_feats.py \
  --in  "data/output/arak29/02Agat3 - Agatangeghos 3 - Ագաթանգեղոս 3.txt" \
  --out "data/output/arak29/02Agat3.clean.txt" \
  --preview 40
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterable, List


def _clean_feats(raw: str) -> str:
    """
    Clean a raw FEATS cell by:
      - splitting on '/'
      - trimming whitespace
      - dropping empty segments and lone '.'
      - preserving other fragments (including 'a.', 'adj.', etc.)
    If resulting list is empty, return '_'.
    """
    if not raw or raw == "_":
        return "_"

    parts = [seg.strip() for seg in raw.split("/")]

    cleaned: List[str] = []
    for seg in parts:
        if not seg:
            continue
        if seg == ".":       # drop bare dot fragments
            continue
        cleaned.append(seg)

    return "/".join(cleaned) if cleaned else "_"


def _process_stream(lines: Iterable[str], strict_columns: bool = False) -> Iterable[str]:
    """
    Process an iterable of lines and yield cleaned lines.
    If strict_columns is True, only clean lines with >= 6 columns; otherwise pass through as-is.
    """
    for line in lines:
        if not line.strip() or line.startswith("#"):
            yield line
            continue

        cols = line.rstrip("\n").split("\t")

        # CoNLL-U requires 10 columns; scraper may already satisfy this.
        # We only need FEATS at index 5 if present.
        if len(cols) >= 6:
            cols[5] = _clean_feats(cols[5])
            yield "\t".join(cols) + "\n"
        else:
            if strict_columns:
                # Skip or raise in strict mode
                sys.stderr.write(f"[warn] skipping short line (<6 cols): {line}")
                continue
            # Non-strict: just pass through
            yield line


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Clean FEATS column in scraped CoNLL-U output.")
    p.add_argument("--in", dest="in_path", required=True, help="Input file path (scraped .txt).")
    p.add_argument("--out", dest="out_path", required=True, help="Output file path.")
    p.add_argument("--preview", type=int, default=0,
                   help="Print the first N output lines to stdout (for quick inspection).")
    p.add_argument("--strict-columns", action="store_true",
                   help="Warn/skip lines with < 6 tab-separated columns.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    with open(args.in_path, "r", encoding="utf-8") as fin:
        processed = list(_process_stream(fin, strict_columns=args.strict_columns))

    with open(args.out_path, "w", encoding="utf-8") as fout:
        fout.writelines(processed)

    if args.preview > 0:
        to_show = processed[: args.preview]
        print("".join(to_show), end="")

    sys.stderr.write(f"[ok] wrote cleaned file: {args.out_path}\n")


if __name__ == "__main__":
    main()
