#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 41 — If the sentence root is lemma="linim", promote its first obl child to root.

Behavior per sentence:
  - Find the token with lemma="linim" and relation="root". If none, leave sentence unchanged.
  - Find the FIRST dependent of that token with relation="obl" (call it OBL*).
  - Set OBL* -> relation="root", head-id="0".
  - Reattach every other dependent of linim to OBL* (head-id := OBL*.id).
  - Turn linim into a copula under OBL*: relation="cop", head-id := OBL*.id.

Idempotent & attribute-safe (only edits relation/head-id).
CLI:
  python scripts/prioel2conllu/stages/41_promote_obl_root_for_linim.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional

# ---------- Attribute helpers ----------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b' + re.escape(name) + r'="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace name="value" on a token line (XML-like)."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', rf'\1{value}\2', line, count=1)
    # insert before '/>' or '>'
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

# ---------- Core per-sentence transform ----------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process a single sentence block (without trailing </sentence>).
    """
    tokens: List[str] = [t for t in block.splitlines() if t.strip()]
    if not tokens:
        return ""

    # Index children by head-id
    children: Dict[str, List[int]] = {}
    for i, tok in enumerate(tokens):
        hid = get_attr(tok, "head-id")
        if hid:
            children.setdefault(hid, []).append(i)

    # Find linim root
    linim_idx: Optional[int] = None
    linim_id: Optional[str] = None
    for i, tok in enumerate(tokens):
        if get_attr(tok, "lemma") == "linim" and get_attr(tok, "relation") == "root":
            linim_idx = i
            linim_id = get_attr(tok, "id")
            break

    if linim_idx is None or not linim_id:
        return "\n".join(tokens)

    # Find first obl child of linim
    obl_idx: Optional[int] = None
    obl_id: Optional[str] = None
    for j in children.get(linim_id, []):
        if get_attr(tokens[j], "relation") == "obl":
            obl_idx = j
            obl_id = get_attr(tokens[j], "id")
            break

    if obl_idx is None or not obl_id:
        # No obl to promote; leave sentence unchanged
        return "\n".join(tokens)

    # --- Promote OBL to root
    obl_tok = tokens[obl_idx]
    obl_tok = set_attr(obl_tok, "relation", "root")
    obl_tok = set_attr(obl_tok, "head-id", "0")
    tokens[obl_idx] = obl_tok

    # --- Reattach other children of linim to OBL
    for j in children.get(linim_id, []):
        if j == obl_idx:
            continue
        tokens[j] = set_attr(tokens[j], "head-id", obl_id)

    # --- Make linim a cop under OBL
    linim_tok = tokens[linim_idx]
    linim_tok = set_attr(linim_tok, "head-id", obl_id)
    linim_tok = set_attr(linim_tok, "relation", "cop")
    tokens[linim_idx] = linim_tok

    if verbose:
        print(f'[linim-root] promoted obl id={obl_id} -> ROOT; linim id={linim_id} -> cop under {obl_id}')

    return "\n".join(tokens)

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Accept either "\n</sentence>" or bare "</sentence>" as separator
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
    ap = argparse.ArgumentParser(description='Stage 41: promote obl as root when lemma="linim" is root.')
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input file (e.g., output41.txt)")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output file (e.g., output42.txt)")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
