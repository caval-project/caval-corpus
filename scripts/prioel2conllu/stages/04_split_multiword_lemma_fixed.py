#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 04 — Split tokens with multi-word lemma into two tokens (fixed relation).

PURPOSE
    For any <token .../> line where lemma="X Y" (space-separated two parts),
    emit two tokens:
      1) Original token:
           - id="<id>"
           - lemma="X"
           - form becomes the FIRST word of the original form (if form had spaces)
             (matches prior script behavior)
      2) Duplicated token:
           - id="<id>0"
           - lemma="Y"
           - form="Y"
           - head-id="<id>"
           - relation="fixed"
    All other attributes are preserved unless explicitly overwritten above.

INPUT
    Single-line XML-like token entries, e.g.:
      <token id="23" head-id="5" relation="dep" form="foo bar" lemma="alpha beta" part-of-speech="X-" />

OUTPUT
    <token id="23"  ... form="foo" lemma="alpha" ... />
    <token id="230" ... head-id="23" relation="fixed" form="beta" lemma="beta" ... />

CLI
    python scripts/prioel2conllu/stages/04_split_multiword_lemma_fixed.py \
        --in input.txt --out output.txt
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

def ensure_self_closing(line: str) -> str:
    """Normalize '<token ...>' to a self-closing '<token ... />' form."""
    line = line.rstrip()
    # already self-closing
    if re.search(r'/>\s*$', line):
        return line
    # close an open tag '>' as '/>'
    return re.sub(r'>\s*$', ' />', line)

def replace_id_suffix(line: str, old_id: str, suffix: str) -> str:
    """Replace id="old_id" with id="old_id{suffix}" (does not touch head-id)."""
    return re.sub(fr'\bid="{re.escape(old_id)}"\b', f'id="{old_id}{suffix}"', line, count=1)

# --- Core transformation ------------------------------------------------------

# Match a single-line <token ...> with both form and lemma attributes (order-agnostic)
TOKEN_RE = re.compile(r'^(\s*)<token\b([^>]*)>(?:\s*)$')

def transform_line(line: str) -> str | None:
    """
    If the line is a <token ...> with lemma containing a space (two parts),
    return two lines (original first, then duplicated). Otherwise return None.
    """
    m = TOKEN_RE.match(line)
    if not m:
        return None

    indent, attrs = m.groups()
    base = ensure_self_closing(f"{indent}<token {attrs}>")

    tok_id = get_attr(base, "id")
    lemma = get_attr(base, "lemma")
    form  = get_attr(base, "form")

    if not tok_id or not lemma or not form:
        return None

    # Only act if lemma has exactly two space-separated parts
    parts = lemma.split(" ", 1)
    if len(parts) != 2:
        return None

    lemma_first, lemma_second = parts

    # Original form becomes FIRST word of original form (matches your script)
    form_first = form.split(" ")[0] if " " in form else form

    # -------- Original token (id="<id>", lemma=X, form=first(form)) ----------
    orig = base
    orig = set_attr(orig, "lemma", lemma_first)
    orig = set_attr(orig, "form", form_first)
    # keep original head-id, relation, pos, etc.

    # -------- Duplicated token (id="<id>0", lemma=Y, form=Y) -----------------
    dup = replace_id_suffix(base, tok_id, "0")
    dup = set_attr(dup, "lemma", lemma_second)
    dup = set_attr(dup, "form", lemma_second)         # your script sets form from lemma2
    dup = set_attr(dup, "head-id", tok_id)
    dup = set_attr(dup, "relation", "fixed")

    # Emit original first, then duplicated (matches your order)
    return f"{orig}\n{dup}\n"

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
    ap = argparse.ArgumentParser(description="Stage 04: split tokens with multi-word lemma into two tokens (fixed).")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
