#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 40 — Collapse multiple roots per sentence.

Behavior:
  - In each sentence, keep the first token with relation="root" as the true root.
  - Every subsequent root is attached to the *preceding* root:
        head-id := preceding_root.id
        relation := "ccomp"

Notes:
  - Attribute-safe edits (no brittle string replaces).
  - Idempotent (re-running preserves the same structure).
  - Supports either "</sentence>" or "\n</sentence>" as a separator.

CLI:
  python scripts/prioel2conllu/stages/40_collapse_multiple_roots.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------- Attribute helpers ----------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b' + re.escape(name) + r'="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value" on a token line."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', rf'\1{value}\2', line, count=1)
    # Insert before '/>' or '>'
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

# ---------------- Core per-sentence transform ----------------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process one sentence block (no trailing </sentence> in `block`).
    Keeps the first root; demotes later roots to ccomp under the previous root.
    """
    tokens: List[str] = block.splitlines()

    # Collect (index, id) for all root tokens in order of appearance
    root_info: List[Tuple[int, str]] = []
    for idx, tok in enumerate(tokens):
        if get_attr(tok, "relation") == "root":
            tid = get_attr(tok, "id")
            if tid:
                root_info.append((idx, tid))

    if len(root_info) <= 1:
        return "\n".join(tokens)  # nothing to change

    # Keep the first root; reattach subsequent roots to the previous root
    for i in range(1, len(root_info)):
        curr_idx, _curr_id = root_info[i]
        prev_idx, prev_id = root_info[i - 1]

        # Defensive: skip if previous root has no id
        if not prev_id:
            continue

        tok = tokens[curr_idx]
        tok = set_attr(tok, "head-id", prev_id)
        tok = set_attr(tok, "relation", "ccomp")
        tokens[curr_idx] = tok

        if verbose:
            curr_id_shown = get_attr(tok, "id") or "?"
            print(f'[multi-root] demote id={curr_id_shown} -> head={prev_id}, relation=ccomp (prev root at idx {prev_idx})')

    return "\n".join(tokens)

# ---------------- File I/O & CLI ----------------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Support both separators
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
    ap = argparse.ArgumentParser(description="Stage 40: collapse multiple roots into a single root + ccomp chain.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input file (e.g., output39.txt)")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output file (e.g., output40.txt)")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()

    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
