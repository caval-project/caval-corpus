#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 34 — Mark passive subjects when a predicate has an agent.

RULE
    Per sentence:
      - Find all heads that have at least one dependent with relation="obl:agent".
      - For any token with head-id in that set:
          * relation "nsubj"  -> "nsubj:pass"
          * relation "csubj"  -> "csubj:pass"

NOTES
    - Sentence-bounded (IDs usually reset per sentence).
    - Attribute-safe updates (touch only the relation attribute).
    - UTF-8 I/O; CLI consistent with earlier stages.

CLI
    python scripts/prioel2conllu/stages/34_mark_passive_subjects.py \
        --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Set

# ---------- Attribute helpers ----------

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

# ---------- Per-sentence processing ----------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process one sentence (block without trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    # 1) Collect heads that have an obl:agent dependent
    heads_with_agent: Set[str] = set()
    for tok in tokens:
        if get_attr(tok, "relation") == "obl:agent":
            hid = get_attr(tok, "head-id")
            if hid:
                heads_with_agent.add(hid)

    if not heads_with_agent:
        return "\n".join(tokens)

    # 2) Relabel subjects headed by those heads
    for i, tok in enumerate(tokens):
        rel = get_attr(tok, "relation")
        if rel not in {"nsubj", "csubj"}:
            continue
        hid = get_attr(tok, "head-id")
        if hid and hid in heads_with_agent:
            new_rel = "nsubj:pass" if rel == "nsubj" else "csubj:pass"
            if verbose:
                tid = get_attr(tok, "id") or "?"
                print(f'[subj->{new_rel}] id={tid} head={hid}')
            tokens[i] = set_attr(tok, "relation", new_rel)

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

    for idx, part in enumerate(parts):
        blk = part.strip()
        if not blk:
            continue
        parts[idx] = process_sentence(blk, verbose=verbose)

    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 34: mark passive subjects using obl:agent presence.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
