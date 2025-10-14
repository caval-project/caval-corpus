#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 09 — Normalize spacing around Armenian guillemets in # text lines.

Rules implemented
-----------------
- Left guillemet « :
    • ensure exactly ONE space before « (unless it starts the text)
    • ensure NO space immediately after «
- Right guillemet » :
    • remove any space immediately BEFORE »
    • remove any space immediately AFTER »

Only lines that start with "# text =" are modified; everything else is copied as-is.

I/O (fixed names)
-----------------
- input   : source CoNLL-U (or CoNLL-U-like) file
- output  : destination file with normalized # text lines
"""

from __future__ import annotations
import re
from pathlib import Path

INPUT_PATH = Path("input")
OUTPUT_PATH = Path("output")

# Precompiled regexes for performance and clarity
_RE_SPACE_AFTER_LEFT  = re.compile(r'«\s+')     # remove spaces after «
_RE_BEFORE_LEFT       = re.compile(r'(?<!^)\s*«')  # normalize spaces before « (not at line start)
_RE_SPACE_BEFORE_RIGHT = re.compile(r'\s+»')     # remove spaces before »
_RE_SPACE_AFTER_RIGHT  = re.compile(r'»\s+')     # remove spaces after »

def _normalize_guillemets(text: str) -> str:
    """
    Apply normalization rules to a raw sentence text (without the '# text = ' prefix).
    """
    # 1) Left guillemet «
    #    - remove any spaces after «
    text = _RE_SPACE_AFTER_LEFT.sub('«', text)
    #    - ensure exactly one space before «, unless it's the very start
    text = _RE_BEFORE_LEFT.sub(' «', text)

    # 2) Right guillemet »
    #    - remove space before »
    text = _RE_SPACE_BEFORE_RIGHT.sub('»', text)
    #    - remove space after »
    text = _RE_SPACE_AFTER_RIGHT.sub('»', text)

    return text

def process_text_lines(input_file: Path = INPUT_PATH, output_file: Path = OUTPUT_PATH) -> None:
    """
    Normalize guillemet spacing for '# text =' lines.
    """
    modified = 0
    total_text = 0

    with input_file.open('r', encoding='utf-8') as infile, output_file.open('w', encoding='utf-8') as outfile:
        for raw_line in infile:
            if raw_line.startswith("# text ="):
                total_text += 1
                original = raw_line[len("# text ="):].rstrip("\n")
                normalized = _normalize_guillemets(original)
                if normalized != original:
                    modified += 1
                outfile.write("# text = " + normalized + "\n")
            else:
                outfile.write(raw_line)

    print(f"[ok] Wrote: {output_file}")
    print(f"[info] # text lines: {total_text}, modified: {modified}")

if __name__ == "__main__":
    process_text_lines()
