#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 13 — Split Armenian punctuation (ʼ / ՞) into its own token(s)

For any token whose FORM contains Armenian punctuation ʼ (U+055B) or ՞ (U+055E),
emit:
- An MWT line covering base + k punct tokens
- Base token (FORM with those marks removed), inheriting lemma/upos/feats/etc.
- One PUNCT token per mark (head = base, deprel = punct)

Other tokens are copied, and the whole sentence is renumbered 1..N.
HEADs are remapped via old->new id map (0 stays 0). Comments preserved.

I/O (fixed filenames in working directory)
- input  : CoNLL-U file
- output : CoNLL-U file
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import re

INPUT_PATH = Path("input")
OUTPUT_PATH = Path("output")

# Armenian punctuation we split out
PUNCT_MARKS = ("՛", "՞")

# Transliteration rules (extend as needed)
TRANSLIT_RULES = {
    'Ա': 'A', 'Բ': 'B', 'Գ': 'G', 'Դ': 'D', 'Ե': 'E', 'Զ': 'Z', 'Է': 'Ē', 'Ը': 'Ə',
    'Թ': 'Tʻ', 'Ժ': 'Ž', 'Ի': 'I', 'Լ': 'L', 'Խ': 'X', 'Ց': 'Cʻ', 'Ծ': 'C', 'Ք': 'Kʻ',
    'Կ': 'K', 'Հ': 'H', 'Ձ': 'J', 'Ղ': 'Ł', 'Չ': 'Čʻ', 'Ճ': 'Č', 'Մ': 'M', 'Յ': 'Y',
    'Ն': 'N', 'Շ': 'Š', 'Ո': 'O', 'Փ': 'Pʻ', 'Պ': 'P', 'Ջ': 'J̌', 'Ռ': 'Ṙ', 'Ս': 'S',
    'Վ': 'V', 'Տ': 'T', 'Ր': 'R', 'Ւ': 'W', 'Ֆ': 'F',
    'ա': 'a', 'բ': 'b', 'գ': 'g', 'դ': 'd', 'ե': 'e', 'զ': 'z', 'է': 'ē', 'ը': 'ə',
    'թ': 'tʻ', 'ժ': 'ž', 'ի': 'i', 'լ': 'l', 'խ': 'x', 'ց': 'cʻ', 'ծ': 'c', 'ք': 'kʻ',
    'կ': 'k', 'հ': 'h', 'ձ': 'j', 'ղ': 'ł', 'չ': 'čʻ', 'ճ': 'č', 'մ': 'm', 'յ': 'y',
    'ն': 'n', 'շ': 'š', 'ո': 'o', 'փ': 'pʻ', 'պ': 'p', 'ջ': 'ǰ', 'ռ': 'ṙ', 'ս': 's',
    'վ': 'v', 'տ': 't', 'ր': 'r', 'ւ': 'w', 'ֆ': 'f',
    '՝': ';', '՞': '?', '՛': '!'
}

MWT_ID_RE = re.compile(r"^\d+-\d+$")


def transliterate(s: str) -> str:
    """Character-wise transliteration using TRANSLIT_RULES."""
    return "".join(TRANSLIT_RULES.get(ch, ch) for ch in s)


def split_doc(doc: str) -> List[str]:
    return re.split(r"\n{2,}", doc.strip()) if doc.strip() else []


def is_comment(line: str) -> bool:
    return line.startswith("#")


def parse_token(line: str) -> List[str] | None:
    cols = line.rstrip("\n").split("\t")
    return cols if len(cols) == 10 else None


def sentence_blocks(lines: List[str]) -> List[List[str]]:
    blocks: List[List[str]] = []
    cur: List[str] = []
    for ln in lines:
        if ln.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append(cur)
    return blocks


def build_old_id_list(tokens: List[List[str]]) -> List[int]:
    """Extract numeric IDs in order (skip MWT lines)."""
    out = []
    for cols in tokens:
        tid = cols[0]
        if tid.isdigit():
            out.append(int(tid))
    return out


def collect_marks(form: str) -> List[Tuple[int, str]]:
    """
    Return list of (index, mark) for each Armenian punctuation in FORM,
    in left-to-right order.
    """
    return [(i, ch) for i, ch in enumerate(form) if ch in PUNCT_MARKS]


def clean_misc(misc: str) -> str:
    return misc if misc and misc != "_" else "_"


def strip_translit_fields(misc: str) -> str:
    if misc == "_" or not misc:
        return "_"
    parts = [p for p in misc.split("|") if p and not p.startswith(("Translit=", "LTranslit="))]
    return "|".join(parts) if parts else "_"


def add_translit_fields(misc: str, form: str, lemma: str) -> str:
    base = [] if misc in ("", "_") else [misc]
    base.insert(0, f"LTranslit={transliterate(lemma)}")
    base.insert(0, f"Translit={transliterate(form)}")
    return "|".join([p for p in base if p]) if base else "_"


def process_sentence(block: List[str]) -> List[str]:
    """
    Process one sentence:
    - split target punctuation into separate tokens (with an MWT)
    - renumber 1..N
    - remap HEADs
    """
    # Keep comments as-is; gather tokens
    comments = [ln for ln in block if is_comment(ln)]
    tokens_raw = [ln for ln in block if not is_comment(ln)]

    # Parse tokens; keep original order including MWT lines
    parsed: List[List[str] | str] = []
    for ln in tokens_raw:
        cols = parse_token(ln)
        parsed.append(cols if cols else ln)  # keep malformed as string

    # First pass: plan new IDs (base ids only) and how many puncts to add
    old_numeric_ids = [int(cols[0]) for cols in parsed if isinstance(cols, list) and cols[0].isdigit()]
    next_id = 1
    old_to_new: Dict[int, int] = {}
    plan: List[Tuple[str, List[str] | str, int, int]] = []
    # tuple: (kind, payload, base_id, num_puncts)
    # kind: "MWT_SPLIT" for tokens to split, "COPY" for normal tokens, "MWT" for original MWT lines, "BAD" for malformed

    for item in parsed:
        if isinstance(item, str):
            plan.append(("BAD", item, -1, 0))
            continue

        tid = item[0]
        if MWT_ID_RE.match(tid):
            plan.append(("MWT", item, -1, 0))
            continue

        if tid.isdigit():
            old_id = int(tid)
            form = item[1]
            marks = collect_marks(form)
            base_id = next_id
            if marks:
                # base + N punct tokens
                next_id += 1 + len(marks)
                old_to_new[old_id] = base_id
                plan.append(("MWT_SPLIT", item, base_id, len(marks)))
            else:
                next_id += 1
                old_to_new[old_id] = base_id
                plan.append(("COPY", item, base_id, 0))
        else:
            plan.append(("BAD", "\t".join(item), -1, 0))

    # Second pass: emit lines with proper IDs and heads
    out_lines: List[str] = []
    # Write comments first (preserve order)
    out_lines.extend(comments)

    for kind, payload, base_id, num_puncts in plan:
        if kind == "BAD":
            # pass through unmodified
            out_lines.append(payload)  # type: ignore[arg-type]
            continue

        cols = payload  # type: ignore[assignment]
        if kind == "MWT":
            # Drop original MWT lines — they no longer reflect the final ranges
            continue

        if kind == "COPY":
            ID, FORM, LEMMA, UPOS, XPOS, FEATS, HEAD, DEPREL, DEPS, MISC = cols  # type: ignore[index]
            # remap head
            if HEAD.isdigit():
                new_head = old_to_new.get(int(HEAD), 0)
                HEAD = str(new_head)
            # add translits (prepend), keep previous MISC (minus old Translit/LTranslit)
            MISC = add_translit_fields(strip_translit_fields(clean_misc(MISC)), FORM, LEMMA)
            out_lines.append("\t".join([str(base_id), FORM, LEMMA, UPOS, XPOS, FEATS, HEAD, DEPREL, DEPS, MISC]))
            continue

        if kind == "MWT_SPLIT":
            ID, FORM, LEMMA, UPOS, XPOS, FEATS, HEAD, DEPREL, DEPS, MISC = cols  # type: ignore[index]

            # MWT range spans base .. base+num_puncts
            mwt_start = base_id
            mwt_end = base_id + num_puncts
            out_lines.append("\t".join([
                f"{mwt_start}-{mwt_end}",
                FORM, "_", "_", "_", "_", "_", "_", "_",
                f"Translit={transliterate(FORM)}"  # keep simple MISC on MWT
            ]))

            # Base token: strip marks from FORM
            base_form = "".join(ch for ch in FORM if ch not in PUNCT_MARKS)
            # remap head
            if HEAD.isdigit():
                new_head = old_to_new.get(int(HEAD), 0)
                HEAD = str(new_head)
            # MISC for base: add translits + keep existing (minus old T/LTranslit)
            base_misc = add_translit_fields(strip_translit_fields(clean_misc(MISC)), base_form, LEMMA)

            out_lines.append("\t".join([
                str(base_id), base_form, LEMMA, UPOS, XPOS, FEATS, HEAD, DEPREL, DEPS, base_misc
            ]))

            # Emit one PUNCT token per mark (in original order)
            # Each punct attaches to base with deprel=punct
            # IDs: base_id + i (1..num_puncts)
            marks_in_order = [ch for ch in FORM if ch in PUNCT_MARKS]
            for i, mark in enumerate(marks_in_order, start=1):
                pid = base_id + i
                pmisc = f"Translit={transliterate(mark)}|LTranslit={transliterate(mark)}"
                out_lines.append("\t".join([
                    str(pid), mark, mark, "PUNCT", "_", "_",
                    str(base_id), "punct", "_", pmisc
                ]))

    return out_lines


def process(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> None:
    doc = input_path.read_text(encoding="utf-8")
    lines = doc.splitlines()
    blocks = sentence_blocks(lines)

    out_blocks: List[str] = []
    for block in blocks:
        out_blocks.append("\n".join(process_sentence(block)))

    output_path.write_text("\n\n".join(out_blocks) + "\n", encoding="utf-8")
    print(f"[ok] Wrote: {output_path}")


if __name__ == "__main__":
    process()
