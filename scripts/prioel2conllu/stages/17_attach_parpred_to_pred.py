#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 17 — Attach `parpred` dependents to the sentence predicate.

PURPOSE
    In each sentence:
      - Identify the first token with relation="pred" and capture its id (pred_id).
      - For every token with relation="parpred":
          * Ensure head-id is set to pred_id (insert if missing, otherwise replace).

BEHAVIOR
    - If a sentence has no relation="pred", no changes are made in that sentence.
    - Only the *first* pred in the sentence is used (matches the legacy script).

CLI
    python scripts/prioel2conllu/stages/17_attach_parpred_to_pred.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, List

SENT_END = "</sentence>"

# ---------------- Attribute helpers ----------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b{name}="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace an XML-like attribute name="value" on a token line."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # Insert before '/>' or '>' if present; fall back to append.
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

# ---------------- Per-sentence processing ----------------

def process_sentence(block: str) -> str:
    """
    Process one sentence block (without the trailing </sentence>).
    """
    tokens: List[str] = [t for t in block.splitlines()]

    # Find the first predicate token id
    pred_id: Optional[str] = None
    for tok in tokens:
        if 'relation="pred"' in tok:
            tid = get_attr(tok, "id")
            if tid:
                pred_id = tid
                break

    # If no predicate, return unchanged
    if not pred_id:
        return "\n".join(tokens)

    # Attach all parpred tokens to pred_id
    for i, tok in enumerate(tokens):
        if 'relation="parpred"' not in tok:
            continue

        if has_attr(tok, "head-id"):
            tokens[i] = set_attr(tok, "head-id", pred_id)
        else:
            # Insert head-id; we don't change relation placement semantically,
            # but set_attr will place it neatly before the closing.
            tokens[i] = set_attr(tok, "head-id", pred_id)

    return "\n".join(tokens)

# ---------------- File I/O & CLI ----------------

def process_file(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Be tolerant to either "\n</sentence>" or bare "</sentence>"
    if "\n</sentence>" in text:
        parts = text.split("\n</sentence>")
        sep = "\n</sentence>"
    else:
        parts = text.split("</sentence>")
        sep = "</sentence>"

    for i in range(len(parts)):
        blk = parts[i].strip()
        if not blk:
            continue
        parts[i] = process_sentence(blk)

    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 17: attach parpred tokens to the sentence pred.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
