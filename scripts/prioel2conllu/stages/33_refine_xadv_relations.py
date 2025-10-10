#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 33 — Refine relation="xadv" into xcomp / advcl / advmod.

RULES (applied only when relation="xadv"):
  1) If FEAT VerbForm=Inf      -> relation="xcomp"
  2) Else if VerbForm=Vnoun    -> relation="advmod"
  3) Else if POS in {VERB,AUX} or line has empty-token-sort="V"
         or the token has a dependent with relation in {cop, mark}
         or a dependent whose FEAT has PronType=Rel
                                -> relation="advcl"
  4) Else                      -> relation="advmod"

NOTES
  - Sentence-bounded (IDs typically reset per sentence).
  - Attribute-safe edits (no brittle whole-line replaces).
  - FEAT parsing treats "_" as empty.

CLI
  python scripts/prioel2conllu/stages/33_refine_xadv_relations.py \
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

# ---------- Per-sentence processing ----------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process a sentence block (without the trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    # Build id -> children index
    id2children: Dict[str, List[int]] = {}
    for idx, t in enumerate(tokens):
        hid = get_attr(t, "head-id")
        if hid:
            id2children.setdefault(hid, []).append(idx)

    for i, line in enumerate(tokens):
        if get_attr(line, "relation") != "xadv":
            continue

        tid   = get_attr(line, "id") or ""
        upos  = get_attr(line, "part-of-speech") or ""
        feats = parse_feats(get_attr(line, "FEAT"))
        vform = feats.get("VerbForm")
        empty_v = 'empty-token-sort="V"' in line

        # Detect clausal dependents of this token
        has_clause_dep = False
        for j in id2children.get(tid, []):
            rel_j = get_attr(tokens[j], "relation")
            if rel_j in {"cop", "mark"}:
                has_clause_dep = True
                break
            dep_feats = parse_feats(get_attr(tokens[j], "FEAT"))
            if dep_feats.get("PronType") == "Rel":
                has_clause_dep = True
                break

        # Decision tree
        if vform == "Inf":
            new_rel = "xcomp"
        elif vform == "Vnoun":
            new_rel = "advmod"
        elif upos in {"VERB", "AUX"} or empty_v or has_clause_dep:
            new_rel = "advcl"
        else:
            new_rel = "advmod"

        if verbose:
            print(f'[xadv->{new_rel}] id={tid or "?"} pos={upos} vform={vform or "-"} emptyV={empty_v} clause_dep={has_clause_dep}')

        tokens[i] = set_attr(line, "relation", new_rel)

    return "\n".join(tokens)

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Accept either "\n</sentence>" or bare "</sentence>" as separator
    if "\n</sentence>" in text:
        parts = text.split("\n</sentence>")
        sep = "\n</sentence>"
    else:
        parts = text.split("</sentence>")
        sep = "</sentence>"

    for idx, part in enumerate(parts):
        blk = part.strip()
        if not blk:
            continue
        parts[idx] = process_sentence(blk, verbose=verbose)

    output_path.write_text(sep.join(parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 33: refine relation='xadv' into xcomp/advmod/advcl.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
