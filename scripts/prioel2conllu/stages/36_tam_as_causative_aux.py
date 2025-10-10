#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 36 — Treat lemma="tam" as causative AUX when governing xcomp (and no obj).

RULE
  For each sentence, find the first token with lemma="tam".
  If it has a dependent with relation="xcomp" and has NO dependent with relation="obj":
    - Set tam POS to AUX
    - Set tam head-id to the xcomp child id
    - Set the xcomp child's relation to the original tam relation
    - Reattach all other dependents of tam (including punct) to the xcomp child
    - Relabel tam's subject children: nsubj -> nsubj:caus, csubj -> csubj:caus
    - Finally set tam's own relation to aux:caus

NOTES
  - Sentence-bounded (IDs typically restart per sentence).
  - Attribute-safe edits via helpers.
  - Idempotent if run again (no duplicated attributes).

CLI
  python scripts/prioel2conllu/stages/36_tam_as_causative_aux.py \
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
    """Set or replace XML-like attribute name="value"."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', rf'\1{value}\2', line, count=1)
    # Insert attribute before closing
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

# -------- Core per-sentence transform --------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process a sentence block (without the trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()
    if not tokens:
        return block

    # Index by id for convenience + children map
    id2idx: Dict[str, int] = {}
    children: Dict[str, List[int]] = {}
    for i, line in enumerate(tokens):
        tid = get_attr(line, "id")
        if tid:
            id2idx[tid] = i
        hid = get_attr(line, "head-id")
        if hid:
            children.setdefault(hid, []).append(i)

    # Find first lemma="tam"
    tam_idx = None
    tam_id: Optional[str] = None
    tam_rel: Optional[str] = None
    for i, line in enumerate(tokens):
        if get_attr(line, "lemma") == "tam":
            tam_idx = i
            tam_id = get_attr(line, "id")
            tam_rel = get_attr(line, "relation")
            break

    if tam_idx is None or not tam_id:
        return "\n".join(tokens)

    # Inspect dependents of tam
    xcomp_child_id: Optional[str] = None
    has_obj_child = False
    for j in children.get(tam_id, []):
        rel = get_attr(tokens[j], "relation")
        cid = get_attr(tokens[j], "id")
        if rel == "xcomp" and cid and xcomp_child_id is None:
            xcomp_child_id = cid
        elif rel == "obj":
            has_obj_child = True

    # Only transform if (has_xcomp and not has_obj)
    if not xcomp_child_id or has_obj_child:
        return "\n".join(tokens)

    # 1) Promote tam to AUX
    tam_line = tokens[tam_idx]
    tokens[tam_idx] = set_attr(tam_line, "part-of-speech", "AUX")
    if verbose:
        print(f'[tam] id={tam_id} -> POS=AUX')

    # 2) Reattach tam under its xcomp child
    tokens[tam_idx] = set_attr(tokens[tam_idx], "head-id", xcomp_child_id)

    # 3) Transfer tam’s original relation to the xcomp child
    xcomp_idx = id2idx.get(xcomp_child_id)
    if xcomp_idx is not None and tam_rel:
        tokens[xcomp_idx] = set_attr(tokens[xcomp_idx], "relation", tam_rel)
        if verbose:
            print(f'[tam] xcomp id={xcomp_child_id} relation={tam_rel}')

    # 4) Reattach all other dependents of tam (except the xcomp itself) to the xcomp child
    for j in children.get(tam_id, []):
        if get_attr(tokens[j], "id") == xcomp_child_id:
            continue
        tokens[j] = set_attr(tokens[j], "head-id", xcomp_child_id)
        # 4a) Relabel subjects to causative subjects
        rel_j = get_attr(tokens[j], "relation")
        if rel_j == "nsubj":
            tokens[j] = set_attr(tokens[j], "relation", "nsubj:caus")
        elif rel_j == "csubj":
            tokens[j] = set_attr(tokens[j], "relation", "csubj:caus")

    # 5) Finally, set tam’s own relation to aux:caus
    tokens[tam_idx] = set_attr(tokens[tam_idx], "relation", "aux:caus")

    return "\n".join(tokens)

# -------- File I/O & CLI --------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Accept either "\n</sentence>" or bare "</sentence>" as the delimiter
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
    ap = argparse.ArgumentParser(description='Stage 36: treat lemma="tam" as causative AUX with xcomp (no obj).')
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input file")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output file")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
