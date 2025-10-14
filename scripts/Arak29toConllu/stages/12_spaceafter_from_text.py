#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 12 — Derive SpaceAfter=No from # text

For each sentence:
- Aligns numeric-ID tokens to the '# text = …' string.
- If the next token starts immediately after the current token (no space),
  sets SpaceAfter=No on the current token; otherwise removes it.
- Skips MWT lines (IDs like '2-3'); preserves order and all other columns.

I/O (fixed filenames in working directory)
- input  : CoNLL-U (or CoNLL-U-like) file
- output : CoNLL-U with corrected SpaceAfter=No flags
"""

from __future__ import annotations
from pathlib import Path
import re
from typing import List, Tuple

INPUT_PATH = Path("input")
OUTPUT_PATH = Path("output")

TOKEN_SPLIT_RE = re.compile(r"\n\n+", flags=re.M)


def _split_sentences(doc: str) -> List[str]:
    doc = doc.strip()
    return TOKEN_SPLIT_RE.split(doc) if doc else []


def _is_comment(line: str) -> bool:
    return line.startswith("#")


def _is_token(line: str) -> bool:
    return not _is_comment(line) and bool(line.strip())


def _is_numeric_id(tid: str) -> bool:
    return tid.isdigit()


def _add_spaceafter_no(misc: str) -> str:
    misc = misc.strip()
    if misc == "_" or not misc:
        return "SpaceAfter=No"
    parts = [p for p in misc.split("|") if p and p != "SpaceAfter=No"]
    return "SpaceAfter=No|" + "|".join(parts) if parts else "SpaceAfter=No"


def _remove_spaceafter_no(misc: str) -> str:
    misc = misc.strip()
    if misc == "_" or not misc:
        return "_"
    parts = [p for p in misc.split("|") if p and p != "SpaceAfter=No"]
    return "|".join(parts) if parts else "_"


def _find_text_line(lines: List[str]) -> Tuple[int, str]:
    """
    Returns (index, text) for the '# text = …' line.
    Raises ValueError if not found.
    """
    for i, line in enumerate(lines):
        if line.startswith("# text ="):
            return i, line[len("# text ="):].strip("\n ").rstrip()
    raise ValueError("Sentence block missing '# text =' line.")


def _align_forms_in_text(text: str, forms: List[str]) -> List[Tuple[int, int]]:
    """
    Greedy left-to-right alignment of token forms to #text.
    Returns a list of (start, end) character indices for each form.
    If a form is not found in sequence, falls back to a best-effort linear scan.
    """
    spans: List[Tuple[int, int]] = []
    cursor = 0
    for form in forms:
        # Find next occurrence of form at or after cursor
        pos = text.find(form, cursor)
        if pos == -1:
            # As a fallback: try to skip spaces then search
            skip = cursor
            while skip < len(text) and text[skip].isspace():
                skip += 1
            pos = text.find(form, skip)
            if pos == -1:
                # Last resort: do not crash—record a synthetic span where possible
                pos = max(cursor, 0)
        start = pos
        end = start + len(form)
        spans.append((start, end))
        cursor = end
    return spans


def _process_sentence(sent_block: str) -> str:
    """
    Adjusts SpaceAfter=No on numeric-ID tokens using '# text' spacing.
    Preserves MWT lines and comments as-is (except for SpaceAfter changes on numeric tokens).
    """
    lines = [ln for ln in sent_block.splitlines() if ln is not None]

    # Extract #text
    _, text = _find_text_line(lines)

    # Collect all token lines (keep indices to write back)
    token_idx: List[int] = [i for i, ln in enumerate(lines) if _is_token(ln)]
    if not token_idx:
        return sent_block  # no tokens; return unchanged

    # Separate numeric tokens (real tokens) from MWT lines
    numeric_token_info: List[Tuple[int, List[str]]] = []
    for idx in token_idx:
        cols = lines[idx].split("\t")
        if len(cols) != 10:
            continue  # skip malformed
        tid = cols[0]
        if _is_numeric_id(tid):
            numeric_token_info.append((idx, cols))

    if not numeric_token_info:
        return sent_block

    # Prepare forms in order and align against #text
    forms = [cols[1] for _, cols in numeric_token_info]
    spans = _align_forms_in_text(text, forms)

    # Decide SpaceAfter=No by checking adjacency to next token span
    for k, ((idx, cols), (start, end)) in enumerate(zip(numeric_token_info, spans)):
        misc = cols[9]
        if k < len(spans) - 1:
            next_start, _ = spans[k + 1]
            adjacent = (next_start == end)
            if adjacent:
                cols[9] = _add_spaceafter_no(misc)
            else:
                cols[9] = _remove_spaceafter_no(misc)
        else:
            # Last token in sentence — derive from trailing text char if you want,
            # but standard practice: remove SpaceAfter=No unless explicitly needed.
            cols[9] = _remove_spaceafter_no(misc)

        # Write modified columns back
        lines[idx] = "\t".join(cols)

    return "\n".join(lines)


def process(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> None:
    doc = input_path.read_text(encoding="utf-8")
    sentences = _split_sentences(doc)
    processed = [_process_sentence(s) for s in sentences]
    output_path.write_text("\n\n".join(processed) + "\n", encoding="utf-8")
    print(f"[ok] Wrote: {output_path}")


if __name__ == "__main__":
    process()
