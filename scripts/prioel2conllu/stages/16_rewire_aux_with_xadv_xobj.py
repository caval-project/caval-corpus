#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 16 — Rewire AUX-headed structures around xadv/xobj predicate.

PURPOSE
    For each token with part-of-speech="AUX" in a sentence:
      1) Find its dependent whose relation is xadv or xobj (call it PRED).
         - Set PRED.relation := AUX.relation  (whatever it was)
         - Set PRED.head-id  := AUX.head-id  (or remove head-id if AUX has none)
         - Decide new AUX relation:
             * If PRED contains 'VerbForm=Part' AND ('Case=Nom' or 'Case=Acc'):
                 AUX.relation := 'aux'
               else:
                 AUX.relation := 'cop'
      2) For every other dependent of the AUX (including punctuation):
         - Set head-id := PRED.id
      3) Set AUX.head-id := PRED.id

NOTES
    - If no xadv/xobj dependent exists, AUX is left unchanged.
    - If AUX had no 'relation', the dependents' relation is not overwritten by step 1 (stays as-is).
    - Sentence boundaries are respected.

CLI
    python scripts/prioel2conllu/stages/16_rewire_aux_with_xadv_xobj.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, List, Tuple

SENT_END = "</sentence>"

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

def remove_attr(line: str, name: str) -> str:
    return re.sub(fr'\s*\b{name}="[^"]*"', "", line, count=1)

# ------------- Per-sentence processing -------------

def is_aux(line: str) -> bool:
    return 'part-of-speech="AUX"' in line

def is_dep_of(line: str, head_id: str) -> bool:
    return get_attr(line, "head-id") == head_id

def is_xadv_or_xobj(line: str) -> bool:
    rel = get_attr(line, "relation")
    return rel in {"xadv", "xobj"}

def decide_aux_relation(pred_line: str) -> str:
    txt = pred_line
    if "VerbForm=Part" in txt and ("Case=Nom" in txt or "Case=Acc" in txt):
        return "aux"
    return "cop"

def process_sentence(block: str) -> str:
    tokens: List[str] = [t for t in block.splitlines() if t.strip()]
    if not tokens:
        return block

    # Collect AUX indices and ids
    aux_positions: List[Tuple[int, str]] = []
    for idx, tok in enumerate(tokens):
        if is_aux(tok):
            tid = get_attr(tok, "id")
            if tid:
                aux_positions.append((idx, tid))

    for aux_idx, aux_id in aux_positions:
        aux_line = tokens[aux_idx]
        aux_head = get_attr(aux_line, "head-id")      # may be None
        aux_rel  = get_attr(aux_line, "relation")     # may be None

        # Find the xadv/xobj predicate among dependents
        pred_idx: Optional[int] = None
        for j, tok in enumerate(tokens):
            if j == aux_idx:
                continue
            if is_dep_of(tok, aux_id) and is_xadv_or_xobj(tok):
                pred_idx = j
                break

        if pred_idx is None:
            # No predicate child found; leave AUX unchanged
            continue

        # ---- Step 1: rewire predicate ----
        pred_line = tokens[pred_idx]
        # predicate gets AUX's original relation only if AUX had one
        if aux_rel:
            pred_line = set_attr(pred_line, "relation", aux_rel)
        # predicate head-id becomes AUX head-id, or removed if AUX had none
        if aux_head:
            pred_line = set_attr(pred_line, "head-id", aux_head)
        else:
            pred_line = remove_attr(pred_line, "head-id")
        tokens[pred_idx] = pred_line

        # Decide AUX new relation based on predicate's features
        new_aux_rel = decide_aux_relation(pred_line)

        # ---- Step 2: move other dependents under predicate ----
        pred_id = get_attr(pred_line, "id") or ""
        for j, tok in enumerate(tokens):
            if j == aux_idx or j == pred_idx:
                continue
            if is_dep_of(tok, aux_id):
                tokens[j] = set_attr(tok, "head-id", pred_id)

        # ---- Step 3: AUX points to predicate, relation becomes aux/cop ----
        tokens[aux_idx] = set_attr(tokens[aux_idx], "head-id", pred_id)
        tokens[aux_idx] = set_attr(tokens[aux_idx], "relation", new_aux_rel)

    return "\n".join(tokens)

# ------------- File I/O & CLI -------------

def process_file(input_path: Path, output_path: Path) -> None:
    raw = input_path.read_text(encoding="utf-8")
    parts = raw.split("\n</sentence>") if "\n</sentence>" in raw else raw.split("</sentence>")
    for i in range(len(parts)):
        blk = parts[i].strip()
        if not blk:
            continue
        parts[i] = process_sentence(blk)
    sep = "\n</sentence>" if "\n</sentence>" in raw else "</sentence>"
    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 16: rewire AUX using xadv/xobj predicate.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
