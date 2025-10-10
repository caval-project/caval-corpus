#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 45 — Reconstruct # text and # transliterated_text from CoNLL-U.

Behavior per sentence
  • Build surface text from FORM (col 2) with spaces unless MISC has SpaceAfter=No.
  • Build transliterated text from MISC Translit=… (fallbacks described below).
  • Properly handle multiword tokens (IDs like "3-4"):
      - Use the multiword row’s Translit if available; otherwise, concatenate
        children’s words (FORM for # text, Translit for translit text) honoring
        their SpaceAfter=No.
      - Skip component rows covered by the multiword span.
  • Ignore empty nodes (IDs with a dot, e.g., "5.1").
  • Replace any existing "# text =" / "# transliterated_text =" lines.
  • Insert the two comments right after "# sent_id =" if present, else at the
    top of the sentence’s comment block.

CLI
  python scripts/prioel2conllu/stages/45_reconstruct_text_and_translit.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple

# ---------- CoNLL-U helpers ----------

def is_comment(line: str) -> bool:
    return line.startswith("#")

def split_cols(line: str) -> Optional[List[str]]:
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 10:
        return None
    return parts

def join_cols(cols: List[str]) -> str:
    return "\t".join(cols) + "\n"

def get_misc_value(misc: str, key: str) -> Optional[str]:
    if not misc or misc == "_":
        return None
    m = re.search(rf'(?:(?<=\|)|^){re.escape(key)}=([^|]+)(?:\||$)', misc)
    return m.group(1) if m else None

def has_spaceafter_no(misc: str) -> bool:
    return bool(re.search(r'(?:(?<=\|)|^)SpaceAfter=No(?:\||$)', misc or ""))

def is_multiword_id(idcol: str) -> bool:
    return "-" in idcol

def is_empty_node_id(idcol: str) -> bool:
    # CoNLL-U empty nodes use decimal IDs like 3.1
    return "." in idcol

# ---------- Reconstruction core ----------

def reconstruct_sentence(lines: List[str], want_translit: bool) -> str:
    """
    Reconstruct a sentence text from a list of raw CoNLL-U lines (one sentence).
    want_translit=False -> use FORM
    want_translit=True  -> use MISC Translit (fallbacks as needed)
    """
    words: List[str] = []
    # When we consume a multiword token "a-b", skip atomic tokens in [a, b]
    skip_until: Optional[int] = None

    # Build quick access for component tokens to support MWT fallback
    # Map from integer token id to (FORM, Translit, SpaceAfter=No)
    comp: dict[int, Tuple[str, str, bool]] = {}
    for ln in lines:
        if is_comment(ln) or not ln.strip():
            continue
        cols = split_cols(ln)
        if not cols:
            continue
        tid = cols[0]
        if is_multiword_id(tid) or is_empty_node_id(tid):
            continue
        try:
            tid_i = int(tid)
        except ValueError:
            continue
        form = cols[1]
        misc = cols[9]
        translit = get_misc_value(misc, "Translit") or "_"
        comp[tid_i] = (form, translit, has_spaceafter_no(misc))

    for ln in lines:
        if is_comment(ln) or not ln.strip():
            continue
        cols = split_cols(ln)
        if not cols:
            continue

        tid = cols[0]
        misc = cols[9]

        # Skip empty nodes
        if is_empty_node_id(tid):
            continue

        # Skip components covered by a previous multiword token
        try:
            tid_i = int(tid.split("-")[0])
        except ValueError:
            continue

        if skip_until is not None:
            if tid_i <= skip_until and not is_multiword_id(tid):
                continue
            if tid_i > skip_until:
                skip_until = None

        if is_multiword_id(tid):
            start_s, end_s = tid.split("-", 1)
            try:
                start_i, end_i = int(start_s), int(end_s)
            except ValueError:
                # Malformed; degrade gracefully by using FORM / Translit of this row
                word = cols[1] if not want_translit else (get_misc_value(misc, "Translit") or cols[1])
                words.append(word)
                if not has_spaceafter_no(misc):
                    words.append(" ")
                continue

            skip_until = end_i

            if want_translit:
                mwt_tr = get_misc_value(misc, "Translit")
                if mwt_tr:
                    word = mwt_tr
                    space_no = has_spaceafter_no(misc)
                else:
                    # Fallback: concatenate children’s Translits honoring SpaceAfter=No
                    segs: List[str] = []
                    last_space_no = False
                    for i in range(start_i, end_i + 1):
                        if i not in comp:
                            continue
                        _, ttr, sa_no = comp[i]
                        segs.append(ttr)
                        last_space_no = sa_no
                        if not sa_no and i != end_i:
                            segs.append(" ")
                    word = "".join(segs) if segs else cols[1]
                    space_no = last_space_no
            else:
                # Build surface from children (preferred), fallback to MWT FORM
                segs: List[str] = []
                last_space_no = False
                for i in range(start_i, end_i + 1):
                    if i not in comp:
                        continue
                    tform, _ttr, sa_no = comp[i]
                    segs.append(tform)
                    last_space_no = sa_no
                    if not sa_no and i != end_i:
                        segs.append(" ")
                word = "".join(segs) if segs else cols[1]
                space_no = last_space_no

            words.append(word)
            if not space_no:
                words.append(" ")
            continue

        # Regular token
        if want_translit:
            token = get_misc_value(misc, "Translit") or "_"
        else:
            token = cols[1]
        words.append(token)
        if not has_spaceafter_no(misc):
            words.append(" ")

    return "".join(words).strip()

# ---------- Sentence processing & I/O ----------

def process_block(block_lines: List[str], verbose: bool = False) -> List[str]:
    """
    Take a sentence block (comments + tokens + trailing blank),
    return new block with fresh # text and # transliterated_text.
    """
    text = reconstruct_sentence(block_lines, want_translit=False)
    translit = reconstruct_sentence(block_lines, want_translit=True)

    out: List[str] = []
    inserted = False

    for ln in block_lines:
        # Skip any existing text/translit comments (we will replace them)
        if ln.startswith("# text =") or ln.startswith("# transliterated_text ="):
            continue
        # After sent_id, insert our comments once
        if not inserted and ln.startswith("# sent_id"):
            out.append(ln if ln.endswith("\n") else ln + "\n")
            out.append(f"# text = {text}\n")
            out.append(f"# transliterated_text = {translit}\n")
            inserted = True
            continue
        out.append(ln if ln.endswith("\n") else ln + "\n")

    # If no sent_id line existed, place comments at the top (before tokens)
    if not inserted:
        # find first non-comment or end
        i = 0
        while i < len(out) and out[i].startswith("#"):
            i += 1
        out = out[:i] + [f"# text = {text}\n", f"# transliterated_text = {translit}\n"] + out[i:]

    # Ensure sentence ends with exactly one blank line
    while out and out[-1].strip():
        out.append("\n")
    return out

def process_file(inp: Path, outp: Path, verbose: bool = False) -> None:
    with inp.open("r", encoding="utf-8") as f:
        all_lines = f.readlines()

    out_lines: List[str] = []
    buf: List[str] = []

    for ln in all_lines:
        if ln.strip() == "":
            if buf:
                out_lines.extend(process_block(buf, verbose=verbose))
                buf = []
            out_lines.append("\n")  # sentence separator
        else:
            buf.append(ln)

    # Last sentence (if file didn't end with a blank)
    if buf:
        out_lines.extend(process_block(buf, verbose=verbose))
        out_lines.append("\n")

    outp.write_text("".join(out_lines), encoding="utf-8")
    if verbose:
        print(f"[reconstruct] wrote {outp}")

# ---------- CLI ----------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 45: reconstruct # text and # transliterated_text from CoNLL-U.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input CoNLL-U file")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output CoNLL-U file")
    ap.add_argument("--verbose", action="store_true", help="Print basic progress")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
