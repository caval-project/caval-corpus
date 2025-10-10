#!/usr/bin/env python3
"""
Stage 01 — Split the multiword token 'ibrew z' into two tokens.

PURPOSE
    Find tokens with lemma="ibrew z", transfer their dependency relation
    to their dependent, then split into two tokens:
      - 'ibrew'  (part-of-speech="G-", relation="case")
      - 'z'      (part-of-speech="R-", relation="aux")
    The duplicated 'z' token gets the same attributes except for a new id
    (original id + "0") and updated fields. The original 'ibrew z' token's
    head-id is rewired to point to its dependent.

INPUT
    Plain text with sentences delimited by '</sentence>'.
    Every token is a single line with XML-like attributes, e.g.:
      id="42" head-id="41" relation="obj" lemma="ibrew z" form="ibrew z" part-of-speech="X-"

OUTPUT
    Same format, with 'ibrew z' replaced by two lines ('ibrew' then 'z') and
    updated dependency attributes as described above.

CLI
    python -m prioel2conllu.stages.01_split_ibrew_z \
        --in armenian-nt_proiel.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

SENTENCE_DELIM = "</sentence>"

# Reusable helpers -------------------------------------------------------------

def get_attr(line: str, name: str) -> Optional[str]:
    """Return the value of attribute `name` from a token line, or None if absent."""
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def set_attr(line: str, name: str, value: str) -> str:
    """
    Set (or replace) attribute `name` to `value` within a token line.
    If the attribute doesn't exist, it is inserted before the closing angle bracket if present,
    otherwise appended to the line.
    """
    if re.search(fr'\b{name}="', line):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # Insert before '>' if present; otherwise, append.
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def replace_id_suffix(line: str, old_id: str, new_suffix: str) -> str:
    """
    Replace id="old_id" with id="old_id{new_suffix}" only (not head-id).
    """
    return re.sub(fr'\bid="{re.escape(old_id)}"\b', f'id="{old_id}{new_suffix}"', line, count=1)

# Core transformation ----------------------------------------------------------

def transform_sentence(sentence_block: str) -> str:
    """
    Transform one sentence block (without the closing delimiter) by splitting 'ibrew z'.
    Returns the transformed block.
    """
    tokens = sentence_block.splitlines()

    ibrew_z_id: Optional[str] = None
    ibrew_z_relation: Optional[str] = None
    ibrew_z_idx: Optional[int] = None
    dependent_id: Optional[str] = None

    # 1) Find the 'ibrew z' token
    for idx, tok in enumerate(tokens):
        if 'lemma="ibrew z"' in tok:
            ibrew_z_id = get_attr(tok, "id")
            ibrew_z_relation = get_attr(tok, "relation")
            ibrew_z_idx = idx
            break

    if ibrew_z_id and ibrew_z_relation is not None and ibrew_z_idx is not None:
        # 2) Find a token whose head-id points to ibrew_z_id and transfer relation
        for idx, tok in enumerate(tokens):
            if f'head-id="{ibrew_z_id}"' in tok:
                # transfer the 'ibrew z' relation to this dependent
                tokens[idx] = set_attr(tok, "relation", ibrew_z_relation)
                dependent_id = get_attr(tokens[idx], "id")
                break

        # 3) Rewire the original 'ibrew z' token's head to point to dependent
        if dependent_id is not None:
            tokens[ibrew_z_idx] = set_attr(tokens[ibrew_z_idx], "head-id", dependent_id)

        # 4) Duplicate the 'ibrew z' token with id suffix "0" (this will become 'z')
        if ibrew_z_id is not None:
            duplicated = replace_id_suffix(tokens[ibrew_z_idx], ibrew_z_id, "0")
            tokens.insert(ibrew_z_idx + 1, duplicated)

            # 5) Retarget attributes:
            #    - first line (original index): becomes 'ibrew', G-, relation=case
            tok_ibrew = tokens[ibrew_z_idx]
            tok_ibrew = set_attr(tok_ibrew, "form", "ibrew")
            tok_ibrew = set_attr(tok_ibrew, "lemma", "ibrew")
            tok_ibrew = set_attr(tok_ibrew, "part-of-speech", "G-")
            tok_ibrew = set_attr(tok_ibrew, "relation", "case")
            tokens[ibrew_z_idx] = tok_ibrew

            #    - second line (duplicated): becomes 'z', R-, relation=aux
            tok_z = tokens[ibrew_z_idx + 1]
            tok_z = set_attr(tok_z, "form", "z")
            tok_z = set_attr(tok_z, "lemma", "z")
            tok_z = set_attr(tok_z, "part-of-speech", "R-")
            tok_z = set_attr(tok_z, "relation", "aux")
            tokens[ibrew_z_idx + 1] = tok_z

    return "\n".join(tokens)

# File I/O wrapper -------------------------------------------------------------

def update_and_split_token(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")
    sentences = text.split(SENTENCE_DELIM)

    # Transform all full sentences; keep trailing segment (after last delimiter) as-is
    for i in range(len(sentences) - 1):
        sentences[i] = transform_sentence(sentences[i])

    output_path.write_text(SENTENCE_DELIM.join(sentences), encoding="utf-8")

# CLI -------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 01: split 'ibrew z' multiword token.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input PRIOEL-like text")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    update_and_split_token(args.inp, args.out)

if __name__ == "__main__":
    main()
