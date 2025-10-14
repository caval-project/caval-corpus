#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 06 — Apply lemma conversions from a TSV table.

- Input  CoNLL-U:  ./input
- Output CoNLL-U:  ./output
- Mapping TSV:     ./lemma_conversion.tsv

Mapping format (tab-separated, 3 columns):
    form<TAB>lemma_scraped<TAB>lemma_caval[ {LId=123}{LId=456}...]

Examples:
    զքրմինք\tքրմ\tքուրմ {LId=12}
    յերկիր\tերկիր\tերկիր
    զինչ\tինչ\tինչ {LId=9}{LId=10}

If multiple {LId=...} markers appear, they are all merged into MISC as
separate `LId=...` entries (deduplicated), preserving any existing MISC entries.

Notes
-----
- Only non-comment token lines are considered.
- Columns are preserved at 10 per CoNLL-U token line.
- Matching is case-insensitive for FORM (lowercased), but exact for lemma_scraped.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


INPUT_PATH = "input"
OUTPUT_PATH = "output"
CONVERSION_TABLE_PATH = "lemma_conversion.tsv"

LID_PATTERN = re.compile(r"\{LId=([^}]+)\}")


def read_conversion_table(filepath: str) -> Dict[Tuple[str, str], Tuple[str, List[str]]]:
    """
    Read lemma conversions into a dict:
        (form_lower, lemma_scraped) -> (lemma_caval, [LId=...,...])
    Only the first two tabs are structural; anything after lives in column 3.
    """
    table: Dict[Tuple[str, str], Tuple[str, List[str]]] = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            # Split into max 3 parts (form, lemma_scraped, lemma_caval+optional {LId=...})
            parts = line.split("\t", 2)
            if len(parts) < 3:
                # Skip malformed lines quietly
                continue
            form, lemma_scraped, lemma_caval_raw = parts[0].strip(), parts[1].strip(), parts[2].strip()

            lids = [f"LId={m}" for m in LID_PATTERN.findall(lemma_caval_raw)]
            lemma_caval = LID_PATTERN.sub("", lemma_caval_raw).strip()
            key = (form.lower(), lemma_scraped)
            table[key] = (lemma_caval, lids)
    return table


def ensure_10_cols(cols: List[str]) -> List[str]:
    """Pad or trim to 10 columns."""
    if len(cols) < 10:
        cols = cols + ["_"] * (10 - len(cols))
    elif len(cols) > 10:
        cols = cols[:10]
    return cols


def merge_misc(existing_misc: str, extra_fields: List[str]) -> str:
    """Merge extra MISC items (e.g., LId=...) into existing MISC, deduplicated."""
    if not extra_fields:
        return existing_misc or "_"

    if not existing_misc or existing_misc == "_":
        base = []
    else:
        base = [x for x in existing_misc.split("|") if x]

    # Deduplicate by set while keeping order (left-biased)
    seen = set(base)
    for item in extra_fields:
        if item and item not in seen:
            base.append(item)
            seen.add(item)

    return "|".join(base) if base else "_"


def process_lemma_conversion(input_path: str, output_path: str, table: Dict[Tuple[str, str], Tuple[str, List[str]]]) -> None:
    """
    For each token line, if (form_lower, lemma) matches the table,
    replace lemma with lemma_caval and append LId entries to MISC.
    """
    changed = 0
    total_tokens = 0

    with open(input_path, "r", encoding="utf-8") as infile, open(output_path, "w", encoding="utf-8") as outfile:
        for raw in infile:
            line = raw.rstrip("\n")

            # Preserve comments/blank lines untouched
            if not line or line.startswith("#"):
                outfile.write(raw)
                continue

            cols = ensure_10_cols(line.split("\t"))
            total_tokens += 1

            form = cols[1].strip()
            lemma = cols[2].strip()
            misc = cols[9].strip()

            key = (form.lower(), lemma)
            if key in table:
                lemma_caval, lids = table[key]
                if lemma_caval:
                    cols[2] = lemma_caval
                if lids:
                    cols[9] = merge_misc(misc, lids)
                changed += 1

            outfile.write("\t".join(cols) + ("\n" if not raw.endswith("\n") else ""))

    print(f"[ok] wrote: {output_path}")
    print(f"    tokens processed: {total_tokens}")
    print(f"    tokens changed:   {changed}")


def main() -> None:
    table = read_conversion_table(CONVERSION_TABLE_PATH)
    if not table:
        print(f"[warn] no usable entries in {CONVERSION_TABLE_PATH}")
    process_lemma_conversion(INPUT_PATH, OUTPUT_PATH, table)


if __name__ == "__main__":
    main()
