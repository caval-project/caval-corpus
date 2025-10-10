#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 29 — Refine relation="obl" into iobj / advmod / advcl (or keep obl).

RULES (applied only when relation="obl"):
  1) If FEAT Case=Dat AND the token has NO dependent with part-of-speech="ADP"
       -> relation="iobj"
  2) Else if part-of-speech="ADV"
       -> relation="advmod"
  3) Else if part-of-speech in {NOUN, PROPN, PRON, DET, ADJ, NUM}
         OR FEAT VerbForm=Vnoun
         OR token has empty-token-sort="P"
       -> keep relation="obl"
  4) Else
       -> relation="advcl"

Notes
  - Sentence-bounded: dependents are searched within the same sentence.
  - Attribute-safe edits (only `relation="..."` is changed).
  - FEAT parsing treats "_" as empty.

CLI
  python scripts/prioel2conllu/stages/29_refine_obl_relations.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional

# ---------- Attribute helpers ----------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b{name}="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value" on a token line."""
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

# ---------- Core per-sentence transform ----------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process one sentence (block without trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    # Build indices for quick lookup
    id2idx: Dict[str, int] = {}
    children: Dict[str, List[int]] = {}
    for i, line in enumerate(tokens):
        tid = get_attr(line, "id")
        if tid:
            id2idx[tid] = i
        hid = get_attr(line, "head-id")
        if hid:
            children.setdefault(hid, []).append(i)

    for i, line in enumerate(tokens):
        if get_attr(line, "relation") != "obl":
            continue

        tid   = get_attr(line, "id") or ""
        upos  = get_attr(line, "part-of-speech") or ""
        feats = parse_feats(get_attr(line, "FEAT"))
        case  = feats.get("Case")
        empty_p = 'empty-token-sort="P"' in line

        # Does this token have any ADP dependents (within this sentence)?
        has_adp_child = False
        for j in children.get(tid, []):
            if get_attr(tokens[j], "part-of-speech") == "ADP":
                has_adp_child = True
                break

        # Apply the decision tree
        new_rel: Optional[str] = None
        if case == "Dat" and not has_adp_child:
            new_rel = "iobj"
        elif upos == "ADV":
            new_rel = "advmod"
        elif upos in {"NOUN", "PROPN", "PRON", "DET", "ADJ", "NUM"} or feats.get("VerbForm") == "Vnoun" or empty_p:
            new_rel = "obl"      # keep as-is
        else:
            new_rel = "advcl"

        if verbose:
            print(f'[obl->{new_rel}] id={tid or "?"} pos={upos} case={case or "-"} adpdep={has_adp_child} vnoun={feats.get("VerbForm")=="Vnoun"} emptyP={empty_p}')

        tokens[i] = set_attr(line, "relation", new_rel)

    return "\n".join(tokens)

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

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
    ap = argparse.ArgumentParser(description="Stage 29: refine relation='obl' into iobj/advmod/advcl (or keep obl).")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
