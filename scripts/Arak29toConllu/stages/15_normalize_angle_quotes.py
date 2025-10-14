#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 15 — Normalize Armenian angle quotes in CoNLL-U.

Rules
-----
- Opening « :
  - UPOS=PUNCT, HEAD -> next real token (integer ID), DEPREL=punct
  - MISC: ensure SpaceAfter=No, add Translit=" and LTranslit="
- Closing » :
  - UPOS=PUNCT, HEAD -> previous real token (integer ID), DEPREL=punct
  - MISC: ensure SpaceAfter=No, add Translit=" and LTranslit="
  - Also ensure the previous token has SpaceAfter=No (no space before »)

Notes
-----
- Multi-word tokens (MWTs, e.g., "3-4") are preserved and skipped as anchors.
- Other MISC entries are preserved. No duplicate `SpaceAfter=No`.
- Input file is read from ./input ; output is written to ./output
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Tuple

INPUT_PATH  = Path("input")
OUTPUT_PATH = Path("output")

OPEN_QUOTE  = "«"
CLOSE_QUOTE = "»"
QUOTE_TRANSLIT = '"'  # per project convention


def _is_token_line(cols: List[str]) -> bool:
    return len(cols) == 10


def _is_int_id(token_id: str) -> bool:
    # integer token IDs only (no ranges like "2-3")
    return token_id.isdigit()


def _ensure_misc_flag(misc: str, flag: str) -> str:
    """Add a flag to MISC without duplication; keep '_' semantics."""
    if not misc or misc == "_":
        return flag
    parts = misc.split("|")
    if flag not in parts:
        parts.insert(0, flag) if flag == "SpaceAfter=No" else parts.append(flag)
    return "|".join(p for p in parts if p) or "_"


def _ensure_kv(misc: str, key: str, value: str) -> str:
    """Ensure key=value is present once in MISC."""
    kv = f"{key}={value}"
    if not misc or misc == "_":
        return kv
    parts = misc.split("|")
    # remove any previous key=...
    parts = [p for p in parts if not p.startswith(f"{key}=")]
    parts.append(kv)
    return "|".join(p for p in parts if p) or "_"


def _nearest_prev_int_id(tokens: List[List[str]], idx: int) -> str | None:
    for j in range(idx - 1, -1, -1):
        tid = tokens[j][0]
        if _is_int_id(tid):
            return tid
    return None


def _nearest_next_int_id(tokens: List[List[str]], idx: int) -> str | None:
    for j in range(idx + 1, len(tokens)):
        tid = tokens[j][0]
        if _is_int_id(tid):
            return tid
    return None


def _process_sentence(lines: List[str]) -> List[str]:
    """
    Process a single sentence block (metadata + tokens).
    Returns updated lines for the sentence.
    """
    meta: List[str] = [ln for ln in lines if ln.startswith("#")]
    toks_raw: List[str] = [ln for ln in lines if ln and not ln.startswith("#")]

    # early exit
    if not toks_raw:
        return lines

    # Split token lines to columns; keep non-10-col lines untouched
    tokens: List[List[str]] = []
    others: List[Tuple[int, str]] = []  # (index, raw_line) for non-10-col lines
    for i, ln in enumerate(toks_raw):
        cols = ln.split("\t")
        if _is_token_line(cols):
            tokens.append(cols)
        else:
            tokens.append(cols)  # keep placeholder length
            others.append((i, ln))

    # Pass 1 — modify « and »
    for i, cols in enumerate(tokens):
        if len(cols) != 10:
            continue  # skip irregular lines (e.g., comments accidentally here)

        tid, form = cols[0], cols[1]

        if form == OPEN_QUOTE and _is_int_id(tid):
            next_id = _nearest_next_int_id(tokens, i)
            if next_id:
                cols[3] = "PUNCT"        # UPOS
                cols[4] = "_"            # XPOS
                cols[5] = "_"            # FEATS
                cols[6] = next_id        # HEAD -> next token
                cols[7] = "punct"        # DEPREL
                cols[8] = "_"            # DEPS
                # MISC updates
                misc = cols[9] if cols[9] else "_"
                misc = _ensure_misc_flag(misc, "SpaceAfter=No")
                misc = _ensure_kv(misc, "Translit", QUOTE_TRANSLIT)
                misc = _ensure_kv(misc, "LTranslit", QUOTE_TRANSLIT)
                cols[9] = misc

        elif form == CLOSE_QUOTE and _is_int_id(tid):
            prev_id = _nearest_prev_int_id(tokens, i)
            if prev_id:
                cols[3] = "PUNCT"
                cols[4] = "_"
                cols[5] = "_"
                cols[6] = prev_id        # HEAD -> previous token
                cols[7] = "punct"
                cols[8] = "_"
                misc = cols[9] if cols[9] else "_"
                misc = _ensure_misc_flag(misc, "SpaceAfter=No")
                misc = _ensure_kv(misc, "Translit", QUOTE_TRANSLIT)
                misc = _ensure_kv(misc, "LTranslit", QUOTE_TRANSLIT)
                cols[9] = misc

                # Ensure previous token has SpaceAfter=No (no space before »)
                # Find the actual previous int-id row index
                for j in range(i - 1, -1, -1):
                    if len(tokens[j]) == 10 and _is_int_id(tokens[j][0]):
                        pmisc = tokens[j][9] if tokens[j][9] else "_"
                        tokens[j][9] = _ensure_misc_flag(pmisc, "SpaceAfter=No")
                        break

    # Rebuild sentence:
    out: List[str] = []
    out.extend(meta)
    for i, cols in enumerate(tokens):
        if len(cols) == 10:
            out.append("\t".join(cols))
        else:
            # write original irregular line
            orig = next((raw for idx, raw in others if idx == i), None)
            out.append(orig if orig is not None else "\t".join(cols))
    return out


def process_conllu(input_path: Path, output_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path.resolve()}")

    with input_path.open("r", encoding="utf-8") as f:
        content = f.read()

    # Split into sentence blocks by blank line
    blocks = [blk.strip("\n") for blk in content.split("\n\n")]
    processed: List[str] = []

    for blk in blocks:
        if not blk.strip():
            continue
        lines = blk.split("\n")
        processed.extend(_process_sentence(lines))
        processed.append("")  # blank line separator

    # Write out
    with output_path.open("w", encoding="utf-8") as out:
        out.write("\n".join(processed).rstrip() + "\n")


def main() -> None:
    process_conllu(INPUT_PATH, OUTPUT_PATH)
    print(f"[ok] Wrote: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
