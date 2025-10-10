#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 21 — Relabel `parpred` depending on its head's lemma.

RULE
    For each token with relation="parpred":
      - Find its head token (same sentence) via head-id
      - If head has lemma="asem"  -> relation="ccomp"
        else                      -> relation="parataxis"
      - If head cannot be found   -> relation="parataxis" (fallback)

NOTES
    - Sentence-bounded (IDs are often per-sentence).
    - Attribute edits are structural (no brittle string slicing).

CLI
    python scripts/prioel2conllu/stages/21_parpred_to_ccomp_or_parataxis.py \
        --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, List, Dict

# ---------- Attribute helpers ----------

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

# ---------- Core per-sentence transform ----------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process one sentence block (without the trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()
    if not tokens:
        return block

    # Build an id -> index map for fast head lookup
    id2idx: Dict[str, int] = {}
    for idx, line in enumerate(tokens):
        tid = get_attr(line, "id")
        if tid:
            id2idx[tid] = idx

    for i, line in enumerate(tokens):
        if get_attr(line, "relation") != "parpred":
            continue

        head_id = get_attr(line, "head-id")
        new_rel = "parataxis"  # default fallback

        if head_id and head_id in id2idx:
            head_line = tokens[id2idx[head_id]]
            if get_attr(head_line, "lemma") == "asem":
                new_rel = "ccomp"

        # apply relation change
        tokens[i] = set_attr(line, "relation", new_rel)
        if verbose:
            tid = get_attr(line, "id") or "?"
            print(f"[parpred->${new_rel}] token id={tid}, head={head_id}")

    return "\n".join(tokens)

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Tolerate either "\n</sentence>" or bare "</sentence>"
    if "\n</sentence>" in text:
        parts = text.split("\n</sentence>")
        sep = "\n</sentence>"
    else:
        parts = text.split("</sentence>")
        sep = "</sentence>"

    for i, part in enumerate(parts):
        blk = part.strip()
        if not blk:
            continue
        parts[i] = process_sentence(blk, verbose=verbose)

    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 21: relabel parpred to ccomp/parataxis based on head lemma.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print debug messages")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
