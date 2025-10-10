#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 06 — Insert punctuation tokens inferred from `presentation-after`.

PURPOSE
    For each <token ... /> line that has presentation-after="<c>" where <c> is a
    single character (and not '?'), insert a new punctuation token on the next line:
        <token id="<id>0" form="<c>" lemma="<c>" part-of-speech="PUNCT"
               morphology="_" head-id="<nearest_token_id>" relation="punct" />
    The head is chosen as the nearest token within the same sentence that lacks a
    `head-id` attribute. If both previous and next candidates are equidistant, prefer
    the previous one. Do not cross sentence boundaries.

INPUT
    A file with XML-like lines including <sentence ...>, </sentence>, and <token ... />.

OUTPUT
    Same lines; for matching cases, a new punctuation token is appended right after
    the triggering line (with preserved indentation).

CLI
    python scripts/prioel2conllu/stages/06_infer_punct_from_presentation_after.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

# --- Regexes ------------------------------------------------------------------

TOKEN_ID_RE         = re.compile(r'\btoken\s+id="([^"]+)"')
HEAD_ID_RE          = re.compile(r'\bhead-id="([^"]+)"')
PRESENT_AFTER_RE    = re.compile(r'\bpresentation-after="([^"]*)"')
SENTENCE_OPEN_RE    = re.compile(r'<\s*sentence\b')
SENTENCE_CLOSE_RE   = re.compile(r'</\s*sentence\s*>')
TOKEN_LINE_RE       = re.compile(r'<\s*token\b[^>]*?/?>')  # tolerant: <token ... /> or <token ...>

# --- Small helpers ------------------------------------------------------------

def get_attr(line: str, regex: re.Pattern[str]) -> Optional[str]:
    m = regex.search(line)
    return m.group(1) if m else None

def has_attr(line: str, regex: re.Pattern[str]) -> bool:
    return bool(regex.search(line))

def leading_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]

def is_sentence_open(line: str) -> bool:
    return bool(SENTENCE_OPEN_RE.search(line))

def is_sentence_close(line: str) -> bool:
    return bool(SENTENCE_CLOSE_RE.search(line))

def is_token_line(line: str) -> bool:
    return bool(TOKEN_LINE_RE.search(line))

# --- Core logic ---------------------------------------------------------------

def find_nearest_orphan_token(lines: list[str], idx: int) -> Optional[int]:
    """
    Find the nearest token line to `idx` within the same sentence that has NO head-id.
    Search backwards first (until <sentence ...>), then forwards (until </sentence>).
    If both sides are candidates at equal distance, prefer the previous one.
    Return the line index, or None if not found.
    """
    # Search backwards to sentence open
    prev_idx: Optional[int] = None
    for j in range(idx - 1, -1, -1):
        if is_sentence_open(lines[j]):
            break
        if is_token_line(lines[j]) and not has_attr(lines[j], HEAD_ID_RE):
            prev_idx = j
            break

    # Search forwards to sentence close
    next_idx: Optional[int] = None
    for j in range(idx + 1, len(lines)):
        if is_sentence_close(lines[j]):
            break
        if is_token_line(lines[j]) and not has_attr(lines[j], HEAD_ID_RE):
            next_idx = j
            break

    # Decide: prefer previous if equally close (or if only previous exists)
    if prev_idx is not None and next_idx is not None:
        if (idx - prev_idx) <= (next_idx - idx):
            return prev_idx
        return next_idx
    return prev_idx if prev_idx is not None else next_idx

def maybe_emit_punct(lines: list[str], i: int, current_line: str) -> Optional[str]:
    """
    If current_line qualifies, return the new punctuation token string to append;
    otherwise return None.
    """
    tok_id = get_attr(current_line, TOKEN_ID_RE)
    pa_val = get_attr(current_line, PRESENT_AFTER_RE)
    if not tok_id or pa_val is None:
        return None

    # We only act if presentation-after is a single char and not '?'
    if len(pa_val) != 1 or pa_val == "?":
        return None

    nearest_idx = find_nearest_orphan_token(lines, i)
    if nearest_idx is None:
        return None

    head_id = get_attr(lines[nearest_idx], TOKEN_ID_RE)
    if not head_id:
        return None

    indent = leading_indent(current_line)
    punct = pa_val
    # Emit exactly as per your original shape, but self-closing and normalized spacing
    return (
        f'{indent}<token id="{tok_id}0" form="{punct}" lemma="{punct}" '
        f'part-of-speech="PUNCT" morphology="_" head-id="{head_id}" relation="punct" />\n'
    )

def process_file(input_path: Path, output_path: Path) -> None:
    lines = input_path.read_text(encoding="utf-8").splitlines(keepends=True)
    with output_path.open("w", encoding="utf-8") as out:
        for i, line in enumerate(lines):
            out.write(line)
            # Append punctuation line if conditions match
            punct_line = maybe_emit_punct(lines, i, line)
            if punct_line:
                out.write(punct_line)

# --- CLI ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 06: insert punctuation tokens from `presentation-after`.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
