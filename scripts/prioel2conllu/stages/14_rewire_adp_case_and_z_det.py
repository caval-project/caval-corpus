#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 14 — Rewire ADP-headed structures to UD `case`, and handle `lemma="z"` → `DET`.

PURPOSE
    - If an ADP token has lemma="z" and relation="aux":
        * part-of-speech="DET"
        * relation="det"
        * FEAT set to Definite=Def (overwrite if FEAT exists; create otherwise)
    - Otherwise, for each ADP that is NOT in the global fixed set:
        * For every dependent (head-id == ADP.id) that is NOT in the fixed set:
            - relation := ADP.relation
            - head-id  := ADP.head-id
            - remember the last such dependent's id
        * If a dependent was found, set ADP.head-id to that dependent's id
        * Set ADP.relation := "case"

NOTES
    - Tokens whose relation="fixed" (any part-of-speech) are excluded from rewiring.
    - Behavior (including FEAT overwrite for `z`) matches the legacy script.

CLI
    python scripts/prioel2conllu/stages/14_rewire_adp_case_and_z_det.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, List, Set

SENT_END = "</sentence>"

# ---------------- Attribute helpers ----------------

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
    """Remove first occurrence of an attribute entirely."""
    return re.sub(fr'\s*\b{name}="[^"]*"', "", line, count=1)

# ---------------- Core processing ----------------

def collect_fixed_ids(sentences: List[str]) -> Set[str]:
    """Gather ids of all tokens whose relation='fixed'."""
    fixed: Set[str] = set()
    for block in sentences:
        for tok in block.splitlines():
            if 'relation="fixed"' in tok:
                tid = get_attr(tok, "id")
                if tid:
                    fixed.add(tid)
    return fixed

def process_sentence(block: str, fixed_ids: Set[str]) -> str:
    """
    Process one sentence's lines (no trailing </sentence>).
    """
    tokens = block.splitlines()
    modified: Set[str] = set()

    for k, tok in enumerate(tokens):
        if 'part-of-speech="ADP"' not in tok:
            continue

        adp_id = get_attr(tok, "id")
        if not adp_id:
            continue

        # Skip if we've already rewritten this ADP
        if adp_id in modified:
            continue

        adp_rel = get_attr(tok, "relation") or ""
        adp_head = get_attr(tok, "head-id")

        # --- Special case: lemma="z" and relation="aux" -> DET/det + Definite=Def
        if 'lemma="z"' in tok and adp_rel == "aux":
            # POS -> DET, relation -> det
            line = set_attr(tok, "part-of-speech", "DET")
            line = set_attr(line, "relation", "det")
            # Overwrite FEAT if present, else add FEAT="Definite=Def"
            if has_attr(line, "FEAT"):
                line = set_attr(line, "FEAT", "Definite=Def")
            else:
                line = set_attr(line, "FEAT", "Definite=Def")
            tokens[k] = line
            modified.add(adp_id)
            continue

        # --- General case: rewire ADP to case (unless ADP itself is fixed)
        if adp_id in fixed_ids:
            # Do not rewire fixed tokens
            continue

        last_dep_id: Optional[str] = None

        for l, oth in enumerate(tokens):
            if l == k:
                continue
            other_id = get_attr(oth, "id")
            if not other_id:
                continue
            if other_id in fixed_ids:
                continue

            if get_attr(oth, "head-id") == adp_id and other_id not in modified:
                # Adopt ADP's relation and ADP's head
                new_line = set_attr(oth, "relation", adp_rel)
                if adp_head:
                    new_line = set_attr(new_line, "head-id", adp_head)
                else:
                    new_line = remove_attr(new_line, "head-id")
                tokens[l] = new_line
                modified.add(other_id)
                last_dep_id = other_id  # track last seen dependent

        # If we found at least one dependent, point ADP to it
        if last_dep_id:
            tok = tokens[k]  # refresh (may have changed)
            tok = set_attr(tok, "head-id", last_dep_id)
            tokens[k] = tok
            modified.add(adp_id)

        # Regardless, ADP relation becomes 'case'
        tokens[k] = set_attr(tokens[k], "relation", "case")

    return "\n".join(tokens)

def process_file(input_path: Path, output_path: Path) -> None:
    raw = input_path.read_text(encoding="utf-8")
    # Be tolerant about the delimiter shape
    parts = raw.split("\n</sentence>") if "\n</sentence>" in raw else raw.split("</sentence>")

    fixed_ids = collect_fixed_ids(parts)

    for i, part in enumerate(parts):
        blk = part.strip()
        if not blk:
            continue
        parts[i] = process_sentence(blk, fixed_ids)

    sep = "\n</sentence>" if "\n</sentence>" in raw else "</sentence>"
    output_path.write_text(sep.join(parts), encoding="utf-8")

# ---------------- CLI ----------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 14: rewire ADP structures to UD `case` and handle `z` → `DET`.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
