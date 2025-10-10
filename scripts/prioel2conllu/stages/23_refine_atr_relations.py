#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 23 — Refine relation="atr" into UD-specific labels.

Rules (applied in order to tokens with relation="atr"):
  1) POS=NUM -> nummod
  2) (POS=ADJ or VerbForm=Part) and token has NO dependents -> amod
  3) POS=DET -> det
  4) POS in {NOUN, PROPN, PRON} or VerbForm=Vnoun -> nmod
  5) Else if (HEAD.POS in {VERB, AUX} or HEAD has empty-token-sort="V" or
              HEAD.relation in {cop, mark} or token FEAT PronType=Rel) -> obl
  6) Else if lemma="anown" and HEAD.relation="acl" -> nsubj
  7) Else -> acl

CLI
    python scripts/prioel2conllu/stages/23_refine_atr_relations.py \
        --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

# -------- Attribute helpers --------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b{name}="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value"."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def parse_feats(s: Optional[str]) -> Dict[str, str]:
    if not s or s == "_":
        return {}
    out: Dict[str, str] = {}
    for kv in s.split("|"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
    return out

# -------- Core per-sentence transform --------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process one sentence (block without the trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    # Build indices
    id2idx: Dict[str, int] = {}
    head_to_children: Dict[str, List[int]] = {}
    for i, line in enumerate(tokens):
        tid = get_attr(line, "id")
        if tid:
            id2idx[tid] = i
        hid = get_attr(line, "head-id")
        if hid:
            head_to_children.setdefault(hid, []).append(i)

    def has_dependents(tid: Optional[str]) -> bool:
        if not tid:
            return False
        return tid in head_to_children and len(head_to_children[tid]) > 0

    for i, line in enumerate(tokens):
        rel = get_attr(line, "relation")
        if rel != "atr":
            continue

        tid   = get_attr(line, "id")
        upos  = get_attr(line, "part-of-speech") or ""
        feats = parse_feats(get_attr(line, "FEAT"))
        lemma = get_attr(line, "lemma") or ""
        hid   = get_attr(line, "head-id")

        # Gather head info (if present)
        head_line = tokens[id2idx[hid]] if (hid and hid in id2idx) else None
        head_pos  = get_attr(head_line, "part-of-speech") if head_line else None
        head_rel  = get_attr(head_line, "relation") if head_line else None
        head_is_empty_v = bool(head_line and 'empty-token-sort="V"' in head_line)

        new_rel: Optional[str] = None

        # 1) POS=NUM -> nummod
        if upos == "NUM":
            new_rel = "nummod"

        # 2) (POS=ADJ or VerbForm=Part) and NO dependents -> amod
        elif (upos == "ADJ" or feats.get("VerbForm") == "Part") and not has_dependents(tid):
            new_rel = "amod"

        # 3) POS=DET -> det
        elif upos == "DET":
            new_rel = "det"

        # 4) POS in {NOUN, PROPN, PRON} or VerbForm=Vnoun -> nmod
        elif upos in {"NOUN", "PROPN", "PRON"} or feats.get("VerbForm") == "Vnoun":
            new_rel = "nmod"

        # 5) Complex → obl
        elif (head_pos in {"VERB", "AUX"} or head_is_empty_v or head_rel in {"cop", "mark"} or feats.get("PronType") == "Rel"):
            new_rel = "obl"

        # 6) Special lemma anown with head acl → nsubj
        elif lemma == "anown" and head_rel == "acl":
            new_rel = "nsubj"

        # 7) Default → acl
        else:
            new_rel = "acl"

        if verbose:
            print(f'[atr->{new_rel}] id={tid or "?"} pos={upos} head={hid or "?"} headpos={head_pos or "-"} headrel={head_rel or "-"} feats={feats}')

        tokens[i] = set_attr(line, "relation", new_rel)

    return "\n".join(tokens)

# -------- File I/O & CLI --------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Support either "\n</sentence>" or bare "</sentence>" separators
    if "\n</sentence>" in text:
        parts = text.split("\n</sentence>")
        sep = "\n</sentence>"
    else:
        parts = text.split("</sentence>")
        sep = "</sentence>"

    for i, part in enumerate(parts):
        blk = part.strip()
        if not blk:
            continue
        parts[i] = process_sentence(blk, verbose=verbose)

    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 23: refine relation='atr' into UD labels.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print debug decisions")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
