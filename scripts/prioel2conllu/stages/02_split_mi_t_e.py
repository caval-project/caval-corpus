#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 02 — Split the multiword token 'mi tʼe' into two tokens.

PURPOSE
    For any token line with form="mi tʼe", emit two tokens:
      - id="<id>",   form="mi",   lemma="mi",   part-of-speech="Df", relation="adv"
      - id="<id>0",  form="tʼe",  lemma="tʼe",  part-of-speech="G-", relation="discourse"
    All other attributes (e.g., head-id, feats) are preserved from the original line,
    except 'lemma', 'part-of-speech', and 'relation' which are overwritten as above.

INPUT
    A text file of XML-like <token ... /> lines (possibly with indentation).
    We trigger strictly on form="mi tʼe".

OUTPUT
    Same format; each matching line is replaced by two lines.

"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

def get_attr(line: str, name: str) -> str | None:
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
    return re.sub(fr'\bid="{re.escape(old_id)}"\b', f'id="{old_id}{suffix}"', line, count=1)

# --- Core transformation ------------------------------------------------------

# Match a single self-closing token line that has form="mi tʼe"
TOKEN_RE = re.compile(
    r'^(\s*)<token\b([^>]*\s)form="mi tʼe"([^>]*)/>\s*$'
)

def transform_line(line: str) -> str | None:
    """
    If the line is a <token .../> with form="mi tʼe", return two lines (mi, tʼe).
    Otherwise, return None (meaning: keep the original line).
    """
    m = TOKEN_RE.match(line)
    if not m:
        return None

    indent = m.group(1)  # preserve indentation
    before = m.group(2)  # attributes before form
    after  = m.group(3)  # attributes after form

    # Rebuild a normalized base token line so helper functions can operate safely.
    base = f'{indent}<token{before}form="mi tʼe"{after} />'

    tok_id = get_attr(base, "id")
    if not tok_id:
        # If id is missing, we leave the line unchanged (very defensive).
        return None

    # Build original line (mi)
    mi_line = base
    mi_line = set_attr(mi_line, "id", tok_id)
    mi_line = set_attr(mi_line, "form", "mi")
    mi_line = set_attr(mi_line, "lemma", "mi")
    mi_line = set_attr(mi_line, "part-of-speech", "Df")
    mi_line = set_attr(mi_line, "relation", "adv")

    # Build duplicated line (tʼe) with id suffix 0
    te_line = replace_id_suffix(base, tok_id, "0")
    te_line = set_attr(te_line, "form", "tʼe")
    te_line = set_attr(te_line, "lemma", "tʼe")
    te_line = set_attr(te_line, "part-of-speech", "G-")
    te_line = set_attr(te_line, "relation", "discourse")

    # Preserve one trailing newline between emitted lines
    return f"{mi_line}\n{te_line}\n"

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
    ap = argparse.ArgumentParser(description="Stage 02: split 'mi tʼe' multiword token.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
