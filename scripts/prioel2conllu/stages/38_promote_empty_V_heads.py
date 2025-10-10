#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 38 — Promote dependents of empty-token-sort="V" and remove the empty V.

Behavior (per sentence):
  • For each token with empty-token-sort="V":
      - If it has a child with relation in {xadv, xcomp}, choose the *first* such child:
          · child's relation := emptyV.relation (when present)
          · child's head-id  := emptyV.head-id (if absent on emptyV, child's head-id is removed)
          · every other child of emptyV gets head-id := chosen child's id
          · drop the empty V token
      - If no xadv/xcomp child found, leave the empty V as-is.

Idempotent and attribute-safe.

CLI
  python scripts/prioel2conllu/stages/38_promote_empty_V_heads.py \
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
    """Set or replace name="value" on a token line."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', rf'\1{value}\2', line, count=1)
    # insert before '/>' or '>'
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def remove_attr(line: str, name: str) -> str:
    """
    Remove an attribute name="...".
    Handles optional leading space to avoid double spaces.
    """
    # remove with optional leading whitespace
    line = re.sub(fr'\s*{name}="[^"]*"', '', line, count=1)
    # clean up double spaces before "/>" or ">"
    line = re.sub(r'\s+(\/?>)', r' \1', line)
    return line

# ---------- Core per-sentence transform ----------

def process_sentence(block: str, verbose: bool = False) -> str:
    tokens: List[str] = [ln for ln in block.splitlines() if ln.strip()]

    # Build indexes
    id2idx: Dict[str, int] = {}
    children: Dict[str, List[int]] = {}
    for i, tok in enumerate(tokens):
        tid = get_attr(tok, "id")
        if tid:
            id2idx[tid] = i
        hid = get_attr(tok, "head-id")
        if hid:
            children.setdefault(hid, []).append(i)

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if 'empty-token-sort="V"' not in tok:
            i += 1
            continue

        v_id = get_attr(tok, "id")
        if not v_id:
            i += 1
            continue

        # Find first xadv/xcomp child
        promoted_idx: Optional[int] = None
        for j in children.get(v_id, []):
            rel = get_attr(tokens[j], "relation")
            if rel in {"xadv", "xcomp"}:
                promoted_idx = j
                break

        # If no suitable child, leave this empty V untouched
        if promoted_idx is None:
            i += 1
            continue

        # Gather info from empty V
        v_rel = get_attr(tok, "relation")
        v_head = get_attr(tok, "head-id")

        # Promote the chosen child
        child = tokens[promoted_idx]
        child_id = get_attr(child, "id") or ""

        if v_rel:
            child = set_attr(child, "relation", v_rel)
        if v_head:
            child = set_attr(child, "head-id", v_head)
        else:
            # remove head-id if empty V had none
            if has_attr(child, "head-id"):
                child = remove_attr(child, "head-id")

        tokens[promoted_idx] = child

        # Reattach every other child of the empty V to the promoted child
        for j in children.get(v_id, []):
            if j == promoted_idx:
                continue
            tokens[j] = set_attr(tokens[j], "head-id", child_id)

        if verbose:
            print(f'[emptyV] id={v_id} -> promote child id={child_id} rel={v_rel or "-"} head={v_head or "-"}')

        # Remove the empty V token
        del tokens[i]

        # Rebuild indices after deletion
        id2idx.clear()
        children.clear()
        for k, tk in enumerate(tokens):
            tid = get_attr(tk, "id")
            if tid:
                id2idx[tid] = k
            hid = get_attr(tk, "head-id")
            if hid:
                children.setdefault(hid, []).append(k)

        # Do not increment i: after deletion, the next token shifts into position i

    return "\n".join(tokens)

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Accept either "\n</sentence>" or bare "</sentence>" separators
    if "\n</sentence>" in text:
        parts = text.split("\n</sentence>")
        sep = "\n</sentence>"
    else:
        parts = text.split("</sentence>")
        sep = "</sentence>"

    for idx, part in enumerate(parts):
        blk = part.strip()
        if not blk:
            continue
        parts[idx] = process_sentence(blk, verbose=verbose)

    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 38: promote dependents of empty-token-sort="V" and drop it.')
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input file")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output file")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
