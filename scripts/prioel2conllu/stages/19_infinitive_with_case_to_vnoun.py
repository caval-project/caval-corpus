#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 19 — Promote infinitives to verbal nouns when governed by a case marker.

RULE
    For each token in a sentence:
      If FEAT contains VerbForm=Inf and **any** dependent has relation="case":
        - Set FEAT: VerbForm=Vnoun
        - For all dependents with relation="obl" (and head-id pointing to this token):
            relation := "nmod"

NOTES
    - Sentence-bounded (state resets at </sentence>).
    - Feature editing is structural: FEAT is parsed/serialized, "_" treated as empty.

CLI
    python scripts/prioel2conllu/stages/19_infinitive_with_case_to_vnoun.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Optional, List

# ---------- Attribute helpers ----------

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

def feats_to_str(d: Dict[str, str]) -> str:
    return "_" if not d else "|".join(f"{k}={d[k]}" for k in sorted(d))

# ---------- Core per-sentence transform ----------

def process_sentence(block: str) -> str:
    """
    Process one sentence (block without the trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    # Index by id for convenience
    id_to_idx: Dict[str, int] = {}
    for i, line in enumerate(tokens):
        tid = get_attr(line, "id")
        if tid:
            id_to_idx[tid] = i

    # For each token with VerbForm=Inf, check if any dependent is a 'case'
    for i, line in enumerate(tokens):
        feats = parse_feats(get_attr(line, "FEAT"))
        if feats.get("VerbForm") != "Inf":
            continue

        tid = get_attr(line, "id")
        if not tid:
            continue

        # Does it have at least one dependent with relation="case"?
        has_case_dependent = False
        for dep in tokens:
            if get_attr(dep, "head-id") == tid and get_attr(dep, "relation") == "case":
                has_case_dependent = True
                break

        if not has_case_dependent:
            continue

        # 1) Promote to Vnoun
        feats["VerbForm"] = "Vnoun"
        tokens[i] = set_attr(tokens[i], "FEAT", feats_to_str(feats))

        # 2) Re-label dependents' 'obl' -> 'nmod'
        for j, dep in enumerate(tokens):
            if get_attr(dep, "head-id") == tid and get_attr(dep, "relation") == "obl":
                tokens[j] = set_attr(dep, "relation", "nmod")

    return "\n".join(tokens)

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Be tolerant to either "\n</sentence>" or bare "</sentence>"
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
        parts[i] = process_sentence(blk)

    output_path.write_text(sep.join(parts), encoding="utf-8")

# ---------- CLI ----------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 19: promote infinitives with case into verbal nouns.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
