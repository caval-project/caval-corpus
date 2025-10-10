#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 18 — Attach vocatives to the predicate (prefer imperative).

BEHAVIOR
    For each sentence:
      - pred_id := id of the first token with relation="pred"
      - imp_pred_id := id of the first token that has Mood=Imp and
                       relation in {"pred", "parpred"} (prefer this)
      - For each token with relation="voc":
          * set head-id to imp_pred_id if available,
            otherwise to pred_id (insert if missing, else replace)

CLI
    python scripts/prioel2conllu/stages/18_attach_vocatives.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, List

SENT_END = "</sentence>"

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
    # Insert before '/>' or '>'
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

# ---------- Per-sentence processing ----------

def process_sentence(block: str) -> str:
    """
    Process one sentence (block without trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    pred_id: Optional[str] = None
    imp_pred_id: Optional[str] = None

    # Pass 1: find pred_id and imp_pred_id (prefer imperative)
    for tok in tokens:
        rel = get_attr(tok, "relation")
        if rel == "pred" and not pred_id:
            pred_id = get_attr(tok, "id")
        if ("Mood=Imp" in tok) and (rel in {"pred", "parpred"}) and not imp_pred_id:
            imp_pred_id = get_attr(tok, "id")
            # We can break if we already have pred_id, but keeping it simple & clear
            # continue to finish scanning quickly.

    # Pass 2: attach vocatives
    target_id = imp_pred_id or pred_id
    if not target_id:
        return "\n".join(tokens)

    for i, tok in enumerate(tokens):
        if get_attr(tok, "relation") == "voc":
            tokens[i] = set_attr(tok, "head-id", target_id)

    return "\n".join(tokens)

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Be tolerant to either "\n</sentence>" or bare "</sentence>"
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
        parts[i] = process_sentence(blk)

    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 18: attach vocatives to the predicate (prefer imperative).")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
