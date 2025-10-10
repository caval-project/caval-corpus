#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 07 — Handle question marks from `presentation-after`.

PURPOSE
    For any <token ... /> line whose presentation-after value begins with '?':
      1) Emit an "interrogative-marked copy" BEFORE the original line:
           - id = "<id>-<id>0"
           - form = original form with '?' inserted after the RIGHT-MOST vowel
           - lemma = "_", part-of-speech = "_", morphology = "_"
           - head-id = "_", relation = "_"
      2) Write the ORIGINAL line unchanged.
      3) Emit a punctuation token AFTER the original line:
           - id = "<id>0"
           - form = "?"
           - lemma = "?"
           - part-of-speech = "PUNCT", morphology = "_"
           - head-id = nearest token in the same sentence that lacks `head-id`
             (prefer previous on tie), relation = "punct"

INPUT
    A file with <sentence ...>, </sentence>, and <token ... /> lines.

OUTPUT
    Same lines, with the two additional tokens for each qualifying case.

CLI
    python scripts/prioel2conllu/stages/07_handle_question_presentation_after.py \
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
FORM_RE             = re.compile(r'\bform="([^"]*)"')
SENTENCE_OPEN_RE    = re.compile(r'<\s*sentence\b')
SENTENCE_CLOSE_RE   = re.compile(r'</\s*sentence\s*>')
TOKEN_LINE_RE       = re.compile(r'<\s*token\b[^>]*?/?>')  # tolerant

# Define vowels for "right-most vowel" insertion rule (adjust as needed)
# Current set mirrors your intent: a, o, e, ē, i, ǝ
VOWELS = "aoeēiǝ"

# --- Helpers ------------------------------------------------------------------

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

def insert_q_after_last_vowel(text: str) -> str:
    """
    Insert '?' immediately after the right-most vowel in `text`.
    If no vowel exists, append '?' at the end.
    """
    last_vowel_pos = -1
    for i in range(len(text) - 1, -1, -1):
        if text[i] in VOWELS:
            last_vowel_pos = i
            break
    if last_vowel_pos == -1:
        return text + "?"
    return text[: last_vowel_pos + 1] + "?" + text[last_vowel_pos + 1 :]

def find_nearest_orphan_token(lines: list[str], idx: int) -> Optional[int]:
    """
    Find nearest token line to `idx` in the same sentence that has NO head-id.
    Prefer previous if distance ties. Do not cross sentence boundaries.
    """
    prev_idx: Optional[int] = None
    for j in range(idx - 1, -1, -1):
        if is_sentence_open(lines[j]):
            break
        if is_token_line(lines[j]) and not has_attr(lines[j], HEAD_ID_RE):
            prev_idx = j
            break

    next_idx: Optional[int] = None
    for j in range(idx + 1, len(lines)):
        if is_sentence_close(lines[j]):
            break
        if is_token_line(lines[j]) and not has_attr(lines[j], HEAD_ID_RE):
            next_idx = j
            break

    if prev_idx is not None and next_idx is not None:
        if (idx - prev_idx) <= (next_idx - idx):
            return prev_idx
        return next_idx
    return prev_idx if prev_idx is not None else next_idx

def maybe_emit_before_and_after(lines: list[str], i: int, current_line: str) -> tuple[Optional[str], Optional[str]]:
    """
    If current line triggers on presentation-after starting with '?',
    return (before_line, after_line) strings to emit; each may be None.
    """
    tok_id = get_attr(current_line, TOKEN_ID_RE)
    pa_val = get_attr(current_line, PRESENT_AFTER_RE)
    form   = get_attr(current_line, FORM_RE)

    if not tok_id or pa_val is None:
        return None, None

    if len(pa_val) == 0 or pa_val[0] != "?":
        return None, None

    indent = leading_indent(current_line)

    # -------- BEFORE: interrogative-marked copy (id "<id>-<id>0") ----------
    before_line: Optional[str] = None
    if form is not None:
        interrogative_form = insert_q_after_last_vowel(form)
        before_line = (
            f'{indent}<token id="{tok_id}-{tok_id}0" form="{interrogative_form}" '
            f'lemma="_" part-of-speech="_" morphology="_" head-id="_" relation="_" />\n'
        )

    # -------- AFTER: punctuation token '?' attached to nearest orphan -------
    after_line: Optional[str] = None
    nearest_idx = find_nearest_orphan_token(lines, i)
    if nearest_idx is not None:
        head_id = get_attr(lines[nearest_idx], TOKEN_ID_RE)
        if head_id:
            after_line = (
                f'{indent}<token id="{tok_id}0" form="?" lemma="?" '
                f'part-of-speech="PUNCT" morphology="_" head-id="{head_id}" relation="punct" />\n'
            )

    return before_line, after_line

# --- Main processing ----------------------------------------------------------

def process_file(input_path: Path, output_path: Path) -> None:
    lines = input_path.read_text(encoding="utf-8").splitlines(keepends=True)
    with output_path.open("w", encoding="utf-8") as out:
        for i, line in enumerate(lines):
            before, after = maybe_emit_before_and_after(lines, i, line)

            # emit BEFORE line (if any)
            if before:
                out.write(before)

            # original line
            out.write(line)

            # emit AFTER line (if any)
            if after:
                out.write(after)

# --- CLI ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 07: handle question marks from `presentation-after`.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
