#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 03 — Split reduplicated tokens (form="X X") into two tokens.

PURPOSE
    For any single-line, self-closing <token .../> where the 'form' consists of two
    identical parts separated by a single space (e.g., "šat šat"), emit TWO lines:
      1) A new token that duplicates the original but:
           - id becomes "<id>0"
           - head-id becomes "<id>" (points to the original)
           - relation becomes "compound:redup"
      2) The original token unchanged except that its form is set to the single part (X)
    All other attributes are preserved. The output order is: NEW line first, then ORIGINAL.

INPUT
    Lines such as:
      <token id="12" head-id="5" relation="obj" form="bar bar" part-of-speech="X-" />

OUTPUT
    <token id="120" head-id="12" relation="compound:redup" form="bar" ... />
    <token id="12"  head-id="5"  relation="obj"               form="bar" ... />

"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

# --- Attribute helpers (consider moving to common/attrs.py) -------------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def set_attr(line: str, name: str, value: str) -> str:
    """
    Set (or replace) attribute `name` to `value` within a token line.
    Works whether the attribute exists or not; preserves other content.
    """
    if re.search(fr'\b{name}="', line):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # Insert before '/>' or '>' if present; else append.
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def replace_id_suffix(line: str, old_id: str, suffix: str) -> str:
    """Replace id="old_id" with id="old_id{suffix}" (does not touch head-id)."""
    return re.sub(fr'\bid="{re.escape(old_id)}"\b', f'id="{old_id}{suffix}"', line, count=1)

# --- Core transformation ------------------------------------------------------

# Match a self-closing token with any attributes where form="X Y"
TOKEN_RE = re.compile(r'^(\s*)<token\b([^>]*?)\bform="([^"]+)"([^>]*)/>\s*$')

def transform_line(line: str) -> str | None:
    """
    If line is a <token .../> with reduplicated form ("X X"), return two lines
    (new then original). Otherwise return None to keep the line unchanged.
    """
    m = TOKEN_RE.match(line)
    if not m:
        return None

    indent, pre_attrs, form_val, post_attrs = m.groups()
    parts = form_val.split(" ")
    if len(parts) != 2 or parts[0] != parts[1]:
        return None

    single = parts[0]

    # Normalize a base token string so helpers can mutate reliably
    base = f'{indent}<token{pre_attrs} form="{form_val}"{post_attrs} />'

    tok_id = get_attr(base, "id")
    if not tok_id:
        return None  # very defensive: require id

    # ---------------- New duplicated token (id "<id>0") ----------------
    dup = replace_id_suffix(base, tok_id, "0")
    dup = set_attr(dup, "form", single)
    dup = set_attr(dup, "head-id", tok_id)             # points to original
    dup = set_attr(dup, "relation", "compound:redup")  # mark the relation

    # ---------------- Original token (keep id, head-id etc.) ------------
    orig = base
    orig = set_attr(orig, "form", single)
    # leave lemma/pos/relation/head-id as they were

    return f"{dup}\n{orig}\n"

def process_file(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for raw in infile:
            transformed = transform_line(raw.rstrip("\n"))
            if transformed is None:
                outfile.write(raw)
            else:
                outfile.write(transformed)

# --- CLI ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 03: split reduplicated tokens (form='X X').")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
