#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 12 — Remove empty C-tokens and reattach their dependents.

PURPOSE
    For every token with empty-token-sort="C":
      - Identify its dependents (head-id == C.id).
      - The first dependent gets:
          * relation = C.relation
          * head-id = C.head-id (or removed if C lacks head-id)
      - All other dependents:
          * relation = "parataxis" (only if not punctuation)
          * head-id = <first-dependent id>   (applies to punct as well)
      - Remove the C-token from the sentence.

INPUT
    Text containing <sentence> ... </sentence> blocks and <token ... /> lines.

OUTPUT
    Same format with C-tokens removed and dependents rewired as specified.

CLI
    python scripts/prioel2conllu/stages/12_remove_empty_c_tokens.py \
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
    """Set or replace XML-like attribute `name="value"` on a token line."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # Insert before '/>' or '>'
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def remove_attr(line: str, name: str) -> str:
    """Remove first occurrence of an attribute entirely."""
    return re.sub(fr'\s*\b{name}="[^"]*"', "", line, count=1)

def is_punct(line: str) -> bool:
    # Keep the exact spirit of your rule: check relation only
    return 'relation="punct"' in line

# ---------------- Core per-sentence transform ----------------

def process_sentence(block: str) -> str:
    """
    Process a single sentence (no trailing </sentence> included).
    """
    tokens: List[str] = [t for t in block.splitlines() if t.strip()]

    # Collect indices of C tokens
    c_indices: List[int] = []
    for idx, tok in enumerate(tokens):
        if 'empty-token-sort="C"' in tok:
            c_indices.append(idx)

    if not c_indices:
        return "\n".join(tokens)

    # Process each C token independently
    to_delete: List[int] = []
    for c_idx in c_indices:
        c_line = tokens[c_idx]
        c_id = get_attr(c_line, "id")
        if not c_id:
            # No id? We can't reattach; just mark for deletion to match intent.
            to_delete.append(c_idx)
            continue

        c_rel = get_attr(c_line, "relation")
        # If there is no relation, the original code "continue"d (skip handling).
        if c_rel is None:
            continue

        c_head = get_attr(c_line, "head-id")

        # Find dependents of this C token (by sentence order)
        dep_indices: List[int] = []
        for j, tok in enumerate(tokens):
            if j == c_idx:
                continue
            if get_attr(tok, "head-id") == c_id:
                dep_indices.append(j)

        if not dep_indices:
            # Just delete the C token if it has no dependents
            to_delete.append(c_idx)
            continue

        # First dependent is the first by sentence order (punct or not)
        first_dep_idx = dep_indices[0]
        first_dep_line = tokens[first_dep_idx]
        first_dep_id = get_attr(first_dep_line, "id") or ""

        # 1) Update first dependent's relation and head-id
        first_dep_line = set_attr(first_dep_line, "relation", c_rel)
        if c_head:
            first_dep_line = set_attr(first_dep_line, "head-id", c_head)
        else:
            # Remove head-id entirely if C had none
            first_dep_line = remove_attr(first_dep_line, "head-id")
        tokens[first_dep_idx] = first_dep_line

        # 2) Update all other dependents:
        for j in dep_indices[1:]:
            line = tokens[j]
            if not is_punct(line):
                line = set_attr(line, "relation", "parataxis")
            line = set_attr(line, "head-id", first_dep_id)
            tokens[j] = line

        # 3) Delete the C token
        to_delete.append(c_idx)

    # Remove C tokens from the sentence (delete from highest index)
    for idx in sorted(to_delete, reverse=True):
        if 0 <= idx < len(tokens):
            del tokens[idx]

    return "\n".join(tokens)

# ---------------- File I/O & CLI ----------------

def process_file(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")
    sentences = text.split(f"\n{SENT_END}")
    for i in range(len(sentences)):
        blk = sentences[i].strip()
        if not blk:
            continue
        sentences[i] = process_sentence(blk)
    output_path.write_text("\n".join(sentences), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 12: remove empty C-tokens and reattach dependents.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
