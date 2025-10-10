#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 13 — Rewire SCONJ into `mark` and relabel clause dependents.

PURPOSE
    For each token with part-of-speech="SCONJ":
      * Map the SCONJ's relation to a dependent-clause relation:
          sub  -> csubj
          comp -> ccomp
          aux  -> ccomp
          adv  -> advcl
          apos -> acl
          atr  -> acl
      * For every token with head-id == SCONJ.id:
          - relation := mapped dependent relation (if mapping exists)
          - head-id  := SCONJ.head-id (or removed if SCONJ has none)
      * If at least one dependent was rewritten:
          - SCONJ.relation := "mark"
          - SCONJ.head-id  := <id of the LAST rewritten dependent> (preserves legacy behavior)

INPUT
    Text with <sentence>...</sentence> blocks containing <token ... /> lines.

OUTPUT
    Same text with updated relations and heads for SCONJ structures.

CLI
    python scripts/prioel2conllu/stages/13_rewire_sconj_mark.py \
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
    """Set or replace XML-like attribute name="value"."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def remove_attr(line: str, name: str) -> str:
    """Remove the first occurrence of an attribute entirely."""
    return re.sub(fr'\s*\b{name}="[^"]*"', "", line, count=1)

# ---------------- Mapping ----------------

DEPENDENT_RELATION_MAP = {
    "sub":  "csubj",
    "comp": "ccomp",
    "aux":  "ccomp",
    "adv":  "advcl",
    "apos": "acl",
    "atr":  "acl",
}

# ---------------- Per-sentence processing ----------------

def process_sentence(block: str) -> str:
    """Process a single sentence block (without trailing </sentence>)."""
    tokens: List[str] = [t for t in block.splitlines() if t.strip()]

    for k, tok in enumerate(tokens):
        if 'part-of-speech="SCONJ"' not in tok:
            continue

        sconj_id = get_attr(tok, "id")
        if not sconj_id:
            continue

        sconj_head = get_attr(tok, "head-id")    # may be None
        sconj_rel  = get_attr(tok, "relation")   # may be None

        # Relation for dependents derived from SCONJ's relation
        dep_rel = DEPENDENT_RELATION_MAP.get(sconj_rel or "", None)

        last_dep_id: Optional[str] = None

        # For every token that depends on the SCONJ
        for j in range(len(tokens)):
            if j == k:
                continue
            if get_attr(tokens[j], "head-id") == sconj_id:
                if dep_rel:
                    tokens[j] = set_attr(tokens[j], "relation", dep_rel)
                # Set head to SCONJ's head, or remove head-id if SCONJ has none
                if sconj_head:
                    tokens[j] = set_attr(tokens[j], "head-id", sconj_head)
                else:
                    tokens[j] = remove_attr(tokens[j], "head-id")
                # Track the (last) dependent's id (matches legacy behavior)
                last_dep_id = get_attr(tokens[j], "id") or last_dep_id

        # If we rewrote at least one dependent, turn SCONJ into `mark`
        if last_dep_id:
            tokens[k] = set_attr(tokens[k], "relation", "mark")
            tokens[k] = set_attr(tokens[k], "head-id", last_dep_id)

    return "\n".join(tokens)

# ---------------- File I/O & CLI ----------------

def process_file(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")
    # Keep the delimiter shape used elsewhere: split by newline + </sentence> if present,
    # but be tolerant of files that use bare </sentence>.
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
    ap = argparse.ArgumentParser(description="Stage 13: rewire SCONJ as `mark` and relabel clause dependents.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
