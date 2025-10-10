#!/usr/bin/env python3
"""
Stage 01 — Split the multiword token 'kʻan z' into two tokens.

PURPOSE
    Find tokens with lemma="kʻan z", transfer their dependency relation
    to their dependent, then split into two tokens:
      - 'kʻan' (part-of-speech="G-", relation="case")
      - 'z'    (part-of-speech="R-", relation="aux")
    The duplicated 'z' token reuses the original token's attributes, but:
      - gets a new id (original id + "0"),
      - form/lemma/part-of-speech/relation are updated as above.
    The original 'kʻan z' token's head-id is rewired to point to its dependent.

INPUT
    Plain text with sentences delimited by '</sentence>'.
    Each token is one line with XML-like attributes, e.g.:
      id="42" head-id="41" relation="obj" lemma="kʻan z" form="kʻan z" part-of-speech="X-"

OUTPUT
    Same format, with 'kʻan z' replaced by two lines ('kʻan' then 'z') and
    updated dependency attributes as described above.

CLI
    python scripts/prioel2conllu/stages/01_split_kan_z.py \
        --in output.txt --out output1.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

SENTENCE_DELIM = "</sentence>"

# --- Attribute helpers --------------------------------------------------------

def get_attr(line: str, name: str) -> Optional[str]:
    """Return the value of attribute `name` from a token line, or None if absent."""
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def set_attr(line: str, name: str, value: str) -> str:
    """
    Set (or replace) attribute `name` to `value` within a token line.
    If missing, insert before '>' if present, else append to the line.
    """
    if re.search(fr'\b{name}="', line):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def replace_id_suffix(line: str, old_id: str, new_suffix: str) -> str:
    """Replace id="old_id" with id="old_id{new_suffix}" only (not head-id)."""
    return re.sub(fr'\bid="{re.escape(old_id)}"\b', f'id="{old_id}{new_suffix}"', line, count=1)

# --- Core transformation ------------------------------------------------------

def transform_sentence(sentence_block: str) -> str:
    """
    Transform one sentence block (without the closing delimiter) by splitting 'kʻan z'.
    Returns the transformed block.
    """
    tokens = sentence_block.splitlines()

    kan_z_id: Optional[str] = None
    kan_z_relation: Optional[str] = None
    kan_z_idx: Optional[int] = None
    dependent_id: Optional[str] = None

    # 1) Find the 'kʻan z' token
    for idx, tok in enumerate(tokens):
        if 'lemma="kʻan z"' in tok:
            kan_z_id = get_attr(tok, "id")
            kan_z_relation = get_attr(tok, "relation")
            kan_z_idx = idx
            break

    if kan_z_id and kan_z_relation is not None and kan_z_idx is not None:
        # 2) Find a token whose head-id points to kan_z_id and transfer relation
        for idx, tok in enumerate(tokens):
            if f'head-id="{kan_z_id}"' in tok:
                tokens[idx] = set_attr(tok, "relation", kan_z_relation)
                dependent_id = get_attr(tokens[idx], "id")
                break

        # 3) Rewire the original 'kʻan z' token's head to point to dependent
        if dependent_id is not None:
            tokens[kan_z_idx] = set_attr(tokens[kan_z_idx], "head-id", dependent_id)

        # 4) Duplicate the 'kʻan z' token with id suffix "0" (this will become 'z')
        duplicated = replace_id_suffix(tokens[kan_z_idx], kan_z_id, "0")
        tokens.insert(kan_z_idx + 1, duplicated)

        # 5) Retarget attributes:
        #    - first line (original index): becomes 'kʻan', G-, relation=case
        tok_kan = tokens[kan_z_idx]
        tok_kan = set_attr(tok_kan, "form", "kʻan")
        tok_kan = set_attr(tok_kan, "lemma", "kʻan")
        tok_kan = set_attr(tok_kan, "part-of-speech", "G-")
        tok_kan = set_attr(tok_kan, "relation", "case")
        tokens[kan_z_idx] = tok_kan

        #    - second line (duplicated): becomes 'z', R-, relation=aux
        tok_z = tokens[kan_z_idx + 1]
        tok_z = set_attr(tok_z, "form", "z")
        tok_z = set_attr(tok_z, "lemma", "z")
        tok_z = set_attr(tok_z, "part-of-speech", "R-")
        tok_z = set_attr(tok_z, "relation", "aux")
        tokens[kan_z_idx + 1] = tok_z

    return "\n".join(tokens)

# --- File I/O wrapper ---------------------------------------------------------

def update_and_split_kan_token(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")
    sentences = text.split(SENTENCE_DELIM)

    for i in range(len(sentences) - 1):
        sentences[i] = transform_sentence(sentences[i])

    output_path.write_text(SENTENCE_DELIM.join(sentences), encoding="utf-8")

# --- CLI ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 01: split 'kʻan z' multiword token.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    update_and_split_kan_token(args.inp, args.out)

if __name__ == "__main__":
    main()
