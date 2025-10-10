#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 47 — Add LId/Gloss to CoNLL-U from a CAVAL glossary file.

Priority:
  1) (lemma, POS, #number)  -> (LId, Gloss)
  2) (lemma, POS)           -> (LId, Gloss)

Behavior:
  • Removes any existing LId=..., Gloss=..., and trailing '#n' marker from MISC,
    then re-adds LId/Gloss from CAVAL if matched and finally re-appends '#n'.
  • Preserves all other MISC items and their order.
  • CoNLL-U safe (10 tab-separated columns), comments/blank lines preserved.

CLI:
  python scripts/prioel2conllu/stages/47_add_glosses_from_caval.py \
      --in input.txt --caval caval_glosses.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# -------------- CAVAL parsing --------------

# Example line pattern (flexible spacing/order):
# LEMMA=foo POS=NOUN LId=2 GLOSS=some gloss text #3
CAVAL_RE = re.compile(
    r'\bLEMMA=(?P<lemma>[^\s:]+)'
    r'.*?\bPOS=(?P<pos>\S+)'
    r'.*?\bLId=(?P<lid>\d+)'
    r'.*?\bGLOSS=(?P<gloss>.*?)(?:\s*#(?P<num>\d+))?\s*$'
)

def extract_glosses_from_caval(caval_glosses_file: Path, verbose: bool = False
    ) -> Tuple[Dict[Tuple[str, str, int], Tuple[int, str]],
               Dict[Tuple[str, str], Tuple[int, str]]]:
    """
    Return two dicts:
      by_triple[(lemma, pos, number)] = (lid, gloss)
      by_pair[(lemma, pos)]           = (lid, gloss)
    """
    triple: Dict[Tuple[str, str, int], Tuple[int, str]] = {}
    pair:   Dict[Tuple[str, str], Tuple[int, str]] = {}

    for raw in caval_glosses_file.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = CAVAL_RE.search(s)
        if not m:
            continue
        lemma = m.group("lemma")
        pos   = m.group("pos")
        lid   = int(m.group("lid"))
        gloss = m.group("gloss").strip()
        num_s = m.group("num")

        if num_s is not None:
            key3 = (lemma, pos, int(num_s))
            triple[key3] = (lid, gloss)
            if verbose:
                print(f"[caval] triple {key3} -> (LId={lid}, Gloss={gloss!r})")
        else:
            key2 = (lemma, pos)
            pair[key2] = (lid, gloss)
            if verbose:
                print(f"[caval] pair   {(lemma, pos)} -> (LId={lid}, Gloss={gloss!r})")

    return triple, pair

# -------------- CoNLL-U helpers --------------

def is_comment(line: str) -> bool:
    return line.startswith("#")

def is_blank(line: str) -> bool:
    return not line.strip()

def split_cols(line: str) -> Optional[List[str]]:
    cols = line.rstrip("\n").split("\t")
    if len(cols) != 10:
        return None
    return cols

def join_cols(cols: List[str]) -> str:
    return "\t".join(cols) + "\n"

def parse_misc(misc: str) -> Tuple[List[Tuple[str, Optional[str]]], Optional[str]]:
    """
    Parse MISC into (items, hash_tag).
    items keeps order: list of (key, value|None).
    '#n' is removed from items and returned as hash_tag.
    '_' -> ([], None)
    """
    if not misc or misc == "_":
        return [], None
    items: List[Tuple[str, Optional[str]]] = []
    hash_tag: Optional[str] = None
    for tok in misc.split("|"):
        if not tok:
            continue
        if tok.startswith("#"):
            hash_tag = tok  # keep the last one if multiple
            continue
        if "=" in tok:
            k, v = tok.split("=", 1)
            items.append((k, v))
        else:
            items.append((tok, None))
    return items, hash_tag

def render_misc(items: List[Tuple[str, Optional[str]]], hash_tag: Optional[str]) -> str:
    if not items and not hash_tag:
        return "_"
    parts = [f"{k}={v}" if v is not None else k for (k, v) in items]
    if hash_tag:
        parts.append(hash_tag)
    return "|".join(parts)

def remove_keys(items: List[Tuple[str, Optional[str]]], keys: List[str]) -> List[Tuple[str, Optional[str]]]:
    keyset = set(keys)
    return [(k, v) for (k, v) in items if k not in keyset]

def upsert(items: List[Tuple[str, Optional[str]]], key: str, value: str) -> List[Tuple[str, Optional[str]]]:
    for i, (k, _) in enumerate(items):
        if k == key:
            items[i] = (key, value)
            return items
    items.append((key, value))
    return items

def get_misc_value(items: List[Tuple[str, Optional[str]]], key: str) -> Optional[str]:
    for k, v in items:
        if k == key:
            return v
    return None

# -------------- Core --------------

def add_gloss_to_conllu_from_caval(conllu_file: Path, caval_glosses_file: Path, output_file: Path, verbose: bool = False) -> None:
    triple, pair = extract_glosses_from_caval(caval_glosses_file, verbose=verbose)
    in_lines = conllu_file.read_text(encoding="utf-8").splitlines(keepends=True)

    out_lines: List[str] = []
    for raw in in_lines:
        if is_comment(raw) or is_blank(raw):
            out_lines.append(raw)
            continue

        cols = split_cols(raw)
        if cols is None:
            # pass through malformed line unchanged
            out_lines.append(raw)
            continue

        lemma = cols[2]
        pos   = cols[3]
        items, hash_tag = parse_misc(cols[9])

        # Capture number markers from MISC (e.g., '#3'). We already pulled one to hash_tag.
        number: Optional[int] = None
        if hash_tag and len(hash_tag) > 1 and hash_tag[1:].isdigit():
            number = int(hash_tag[1:])

        # Remove existing LId/Gloss (we'll re-add)
        items = remove_keys(items, ["LId", "Gloss"])

        # Lookup priority: (lemma,pos,#n) then (lemma,pos)
        info: Optional[Tuple[int, str]] = None
        if number is not None:
            info = triple.get((lemma, pos, number))
        if info is None:
            info = pair.get((lemma, pos))

        if info:
            lid, gloss = info
            # Only emit LId if > 0
            if lid > 0:
                items = upsert(items, "LId", f"{lemma}-{lid}")
            items = upsert(items, "Gloss", gloss)
            if verbose:
                print(f"[gloss] id={cols[0]} lemma={lemma!r} pos={pos!r} -> LId={lemma}-{lid if lid>0 else 0}, Gloss={gloss!r}")

        cols[9] = render_misc(items, hash_tag)
        out_lines.append(join_cols(cols))

    output_file.write_text("".join(out_lines), encoding="utf-8")
    if verbose:
        print(f"[caval->conllu] wrote {output_file}")

# -------------- CLI --------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 47: add LId/Gloss to CoNLL-U from CAVAL glosses.")
    ap.add_argument("--in",    dest="inp",   required=True, type=Path, help="Input CoNLL-U (e.g., output47.txt)")
    ap.add_argument("--caval", dest="caval", required=True, type=Path, help="CAVAL glosses file")
    ap.add_argument("--out",   dest="out",   required=True, type=Path, help="Output CoNLL-U (e.g., output48.txt)")
    ap.add_argument("--verbose", action="store_true", help="Print mapping decisions")
    args = ap.parse_args()
    add_gloss_to_conllu_from_caval(args.inp, args.caval, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
