#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 11 — Rewire coordination for CCONJ.

PURPOSE
    For each CCONJ within a sentence:
      - If it has no dependents, force relation="cc".
      - Otherwise:
          * Find the first non-punct dependent AFTER the CCONJ (if any) for head rewiring.
          * Among all its dependents within the sentence, choose the first non-punct
            dependent overall (may be before or after); attach it to the CCONJ's head
            (or drop head-id if CCONJ had none) and assign it the CCONJ's relation.
          * Reattach all other dependents to this first dependent; non-punct get relation="conj".
          * Any earlier punctuation dependents get head-id set to the first dependent.
          * Finally, set CCONJ relation="cc" and head-id to the first dependent AFTER it
            (non-punct), if such exists.

INPUT
    Text split by sentences with lines like:
      <token id=".." head-id=".." relation=".." part-of-speech="CCONJ" ... />

OUTPUT
    Same format with updated head-id/relation as above.

CLI
    python scripts/prioel2conllu/stages/11_rewire_coordination_cconj.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, List, Tuple

SENT_CLOSE = "</sentence>"

# ---------------- Attribute helpers ----------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b{name}="', line))

def set_attr(line: str, name: str, value: str) -> str:
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # insert before '/>' or '>'
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def remove_attr(line: str, name: str) -> str:
    return re.sub(fr'\s*\b{name}="[^"]*"', "", line, count=1)

def leading_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]

# ---------------- Small predicates ----------------

def is_cconj(line: str) -> bool:
    return 'part-of-speech="CCONJ"' in line

def is_punct(line: str) -> bool:
    return 'relation="punct"' in line or 'part-of-speech="PUNCT"' in line

def token_id(line: str) -> Optional[str]:
    return get_attr(line, "id")

def head_id(line: str) -> Optional[str]:
    return get_attr(line, "head-id")

def relation(line: str) -> Optional[str]:
    return get_attr(line, "relation")

# ---------------- Core sentence transform ----------------

def process_sentence(block: str) -> str:
    """
    Transform a single sentence block (without trailing </sentence>).
    """
    tokens: List[str] = [t for t in block.splitlines() if t.strip()]

    # Collect CCONJs with their indices
    cconj_positions: List[Tuple[int, str]] = []
    for j, tok in enumerate(tokens):
        if is_cconj(tok):
            tid = token_id(tok)
            if tid:
                cconj_positions.append((j, tid))

    if not cconj_positions:
        return "\n".join(tokens)

    # Precompute: which CCONJs have no dependents
    dependents_by_head = {}
    for j, tok in enumerate(tokens):
        hid = head_id(tok)
        if hid:
            dependents_by_head.setdefault(hid, []).append(j)

    # First non-punct dependent AFTER cconj (used to set cconj head later)
    def first_after_non_punct_dep_idx(c_idx: int, c_id: str) -> Optional[int]:
        for j in range(c_idx + 1, len(tokens)):
            if head_id(tokens[j]) == c_id and not is_punct(tokens[j]):
                return j
        return None

    for c_idx, c_id in cconj_positions:
        c_line = tokens[c_idx]
        c_has_deps = c_id in dependents_by_head
        # If no dependents at all -> relation="cc" and continue
        if not c_has_deps:
            tokens[c_idx] = set_attr(c_line, "relation", "cc")
            continue

        c_head = head_id(c_line)  # may be None
        c_rel  = relation(c_line)
        if c_rel is None:
            # Nothing to propagate—still set cc at the end.
            c_rel = "cc"  # fallback so dependents won't get garbage

        # Find all dependents of this CCONJ (indices)
        dep_idxs = [j for j in dependents_by_head.get(c_id, [])]

        # Determine the first non-punct dependent overall (may appear before or after CCONJ)
        first_non_punct_idx: Optional[int] = None
        skipped_punct_idxs: List[int] = []
        for j in dep_idxs:
            if is_punct(tokens[j]):
                # collect punct BEFORE we locate the first non-punct
                if first_non_punct_idx is None:
                    skipped_punct_idxs.append(j)
                continue
            first_non_punct_idx = j
            break

        if first_non_punct_idx is None:
            # All dependents are punctuation → mark CCONJ as cc and leave others as punct under it
            tokens[c_idx] = set_attr(c_line, "relation", "cc")
            # Still try to set cconj head-id to the first non-punct after it (will be None)
            continue

        # The anchor dependent we will reattach others to:
        anchor_idx = first_non_punct_idx
        anchor_id  = token_id(tokens[anchor_idx]) or ""

        # Reattach anchor to CCONJ's head (or drop head-id if CCONJ had none),
        # and give it the CCONJ's relation.
        if c_head:
            tokens[anchor_idx] = set_attr(tokens[anchor_idx], "head-id", c_head)
        else:
            # remove head-id attribute if present
            tokens[anchor_idx] = remove_attr(tokens[anchor_idx], "head-id")
        tokens[anchor_idx] = set_attr(tokens[anchor_idx], "relation", c_rel)

        # Repoint any previously seen punctuation dependents to the anchor
        for pj in skipped_punct_idxs:
            tokens[pj] = set_attr(tokens[pj], "head-id", anchor_id)

        # Reattach remaining dependents to anchor; non-punct get relation="conj"
        for j in dep_idxs:
            if j == anchor_idx:
                continue
            if not is_punct(tokens[j]):
                tokens[j] = set_attr(tokens[j], "relation", "conj")
            tokens[j] = set_attr(tokens[j], "head-id", anchor_id)

        # Now set the CCONJ’s own head to the first non-punct dependent AFTER it (if any),
        # and force relation="cc".
        after_idx = first_after_non_punct_dep_idx(c_idx, c_id)
        if after_idx is not None:
            after_id = token_id(tokens[after_idx]) or ""
            tokens[c_idx] = set_attr(tokens[c_idx], "head-id", after_id)
        tokens[c_idx] = set_attr(tokens[c_idx], "relation", "cc")

    return "\n".join(tokens)

# ---------------- File I/O & CLI ----------------

def process_file(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")
    sentences = text.split(f"\n{SENT_CLOSE}")
    for i in range(len(sentences)):
        blk = sentences[i].strip()
        if not blk:
            continue
        sentences[i] = process_sentence(blk)
    output_path.write_text("\n".join(sentences), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 11: rewire coordination headed by CCONJ.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
