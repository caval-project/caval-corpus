#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 31 — Refine relation="sub" into nsubj / iobj / obl / csubj.

RULES (applied in order to tokens with relation="sub"):
  1) If token FEAT has Case=Gen AND head FEAT has VerbForm=Part AND (Case=Nom OR Case=Acc) -> nsubj
  2) Else if token FEAT has Case=Dat -> iobj
  3) Else if token FEAT has Case in {Gen, Ins} -> obl
  4) Else if token FEAT has VerbForm in {Fin, Inf} OR token line contains empty-token-sort="V"
     OR token has a dependent with relation="cop" -> csubj
  5) Else -> nsubj

NOTES
  - Sentence-bounded: head/dependents resolved within the same sentence.
  - Attribute-safe edits via helpers (no brittle whole-line replace).
  - FEAT parsing treats "_" as empty.

CLI
  python scripts/prioel2conllu/stages/31_refine_sub_relations.py \
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
    Process one sentence block (without the trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    # Build indices and children map
    id2idx: Dict[str, int] = {}
    children: Dict[str, List[int]] = {}
    for i, line in enumerate(tokens):
        tid = get_attr(line, "id")
        if tid:
            id2idx[tid] = i
        hid = get_attr(line, "head-id")
        if hid:
            children.setdefault(hid, []).append(i)

    def has_child_with_relation(tid: Optional[str], rel: str) -> bool:
        if not tid:
            return False
        for j in children.get(tid, []):
            if get_attr(tokens[j], "relation") == rel:
                return True
        return False

    for i, line in enumerate(tokens):
        if get_attr(line, "relation") != "sub":
            continue

        tid   = get_attr(line, "id")
        feats = parse_feats(get_attr(line, "FEAT"))
        hid   = get_attr(line, "head-id")
        head  = tokens[id2idx[hid]] if (hid and hid in id2idx) else None
        hfeats = parse_feats(get_attr(head or "", "FEAT"))

        case      = feats.get("Case")
        vform     = feats.get("VerbForm")
        head_vf   = hfeats.get("VerbForm")
        head_case = hfeats.get("Case")
        empty_v   = 'empty-token-sort="V"' in line
        has_cop_child = has_child_with_relation(tid, "cop")

        new_rel: Optional[str] = None

        # 1) Case=Gen AND head has VerbForm=Part AND head Case in {Nom, Acc} -> nsubj
        if case == "Gen" and head_vf == "Part" and head_case in {"Nom", "Acc"}:
            new_rel = "nsubj"

        # 2) Case=Dat -> iobj
        elif case == "Dat":
            new_rel = "iobj"

        # 3) Case in {Gen, Ins} -> obl
        elif case in {"Gen", "Ins"}:
            new_rel = "obl"

        # 4) VerbForm in {Fin, Inf} OR empty-token-sort="V" OR has `cop` child -> csubj
        elif vform in {"Fin", "Inf"} or empty_v or has_cop_child:
            new_rel = "csubj"

        # 5) default -> nsubj
        else:
            new_rel = "nsubj"

        if verbose:
            print(
                f'[sub->{new_rel}] id={tid or "?"} case={case or "-"} vform={vform or "-"} '
                f'head_vform={head_vf or "-"} head_case={head_case or "-"} '
                f'emptyV={empty_v} cop_child={has_cop_child}'
            )

        tokens[i] = set_attr(line, "relation", new_rel)

    return "\n".join(tokens)

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Support both "\n</sentence>" and bare "</sentence>"
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
    ap = argparse.ArgumentParser(description="Stage 31: refine relation='sub' into nsubj/iobj/obl/csubj.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
