#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 14 — Inject Gloss and LId from a lookup table into a CoNLL-U file.

Inputs (fixed filenames in working directory):
- glosses : plain text lookup lines such as
    LEMMA=foo POS=NOUN LId=12 GLOSS=“bar baz”
  (Fields can appear in any order; GLOSS may contain spaces up to a trailing '#'-comment)
- input   : CoNLL-U document

Output:
- output  : CoNLL-U with updated MISC:
    - Remove existing Gloss=... and LId=...
    - Append LId=<n> (only if n>0) and Gloss=<gloss> when found for (lemma, upos)
    - Preserve other MISC entries; normalize separators
"""

from __future__ import annotations
from pathlib import Path
import re
from typing import Dict, Tuple, Optional

# Fixed I/O paths as requested
GLOSSES_PATH = Path("glosses")
INPUT_PATH   = Path("input")
OUTPUT_PATH  = Path("output")

# Robust field extractors
# - GLOSS: capture to before '#' or end of line; trim whitespace/quotes
RE_LEMMA = re.compile(r"\bLEMMA=(\S+)")
RE_POS   = re.compile(r"\bPOS=(\S+)")
RE_LID   = re.compile(r"\bLId=(\d+)")
RE_GLOSS = re.compile(r"\bGLOSS=([^\n#]+)")

# MISC sanitizers
RE_MISC_GLOSS = re.compile(r"(?:^|\|)Gloss=[^|]*")
RE_MISC_LID   = re.compile(r"(?:^|\|)LId=[^|]*")


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {'"', '“', '”', '‘', '’', "'"}:
        return s[1:-1].strip()
    return s


def parse_glosses_file(path: Path) -> Dict[Tuple[str, str], Tuple[int, str]]:
    """
    Build a map: (lemma, upos) -> (lid, gloss)
    Keeps the first occurrence for each pair.
    """
    mapping: Dict[Tuple[str, str], Tuple[int, str]] = {}
    if not path.exists():
        raise FileNotFoundError(f"Glosses file not found: {path.resolve()}")

    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            m_lemma = RE_LEMMA.search(line)
            m_pos   = RE_POS.search(line)
            m_lid   = RE_LID.search(line)
            m_gloss = RE_GLOSS.search(line)

            if not (m_lemma and m_pos and m_gloss and m_lid):
                # Skip incomplete records silently; you can log if desired
                continue

            lemma = m_lemma.group(1)
            pos   = m_pos.group(1)
            try:
                lid = int(m_lid.group(1))
            except ValueError:
                continue

            gloss = _strip_quotes(m_gloss.group(1))

            key = (lemma, pos)
            if key not in mapping:
                mapping[key] = (lid, gloss)

    return mapping


def _clean_misc_remove_old(misc: str) -> str:
    """Remove existing Gloss=... and LId=...; collapse delimiters; return '_' if empty."""
    if not misc or misc == "_":
        return "_"
    # remove matching spans
    misc = RE_MISC_GLOSS.sub("", misc)
    misc = RE_MISC_LID.sub("", misc)
    # fix leftover pipes and whitespace
    misc = misc.strip().strip("|")
    # also collapse any duplicated pipes
    misc = re.sub(r"\|{2,}", "|", misc)
    return misc if misc else "_"


def _append_misc(misc: str, field: str) -> str:
    if not field:
        return misc if misc else "_"
    if not misc or misc == "_":
        return field
    return f"{misc}|{field}"


def update_conllu_file(conllu_in: Path, mapping: Dict[Tuple[str, str], Tuple[int, str]], conllu_out: Path) -> None:
    if not conllu_in.exists():
        raise FileNotFoundError(f"Input CoNLL-U not found: {conllu_in.resolve()}")

    with conllu_in.open("r", encoding="utf-8") as fin, conllu_out.open("w", encoding="utf-8") as fout:
        for raw in fin:
            line = raw.rstrip("\n")

            # Pass through comments/blank lines
            if not line or line.startswith("#"):
                fout.write(raw)
                continue

            cols = line.split("\t")
            if len(cols) != 10:
                # Non-standard line; pass through
                fout.write(raw)
                continue

            # CoNLL-U columns
            # 0=ID 1=FORM 2=LEMMA 3=UPOS 4=XPOS 5=FEATS 6=HEAD 7=DEPREL 8=DEPS 9=MISC
            lemma = cols[2]
            upos  = cols[3]
            misc  = cols[9]

            # Remove any previous Gloss/LId from MISC
            misc = _clean_misc_remove_old(misc)

            # Look up (lemma, upos)
            key = (lemma, upos)
            if key in mapping:
                lid, gloss = mapping[key]
                # Only add LId if > 0
                if lid > 0:
                    misc = _append_misc(misc, f"LId={lid}")
                misc = _append_misc(misc, f"Gloss={gloss}")

            cols[9] = misc
            fout.write("\t".join(cols) + "\n")


def main() -> None:
    mapping = parse_glosses_file(GLOSSES_PATH)
    update_conllu_file(INPUT_PATH, mapping, OUTPUT_PATH)
    print(f"[ok] Wrote: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
