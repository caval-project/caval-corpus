#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 09 — Expand PROIEL-style morphology codes into UD FEATS.

PURPOSE
    Read morphology="..." compact codes, convert to UD features, merge them into
    FEAT="...". Finally remove the morphology attribute to normalize output.
    If no features are produced and FEAT didn't exist, set FEAT="_".

MAPPING (same as legacy script)
    idx 0: Person      {'1': Person=1, '2': Person=2, '3': Person=3}
    idx 1: Number      {'s': Number=Sing, 'p': Number=Plur}
    idx 2..3: VerbForm {'pi': Fin/Ind/Pres/Imp, 'ii': Fin/Ind/Past/Imp, ...}
    idx 4: Voice       {'a': Voice=Act, 'p': Voice=Pass}
    idx 6: Case        {'n': Nom, 'a': Acc, 'd': Dat, 'i': Ins, 'g': Gen, 'b': Abl, 'l': Loc}

CLI
    python scripts/prioel2conllu/stages/09_morphology_codes_to_feats.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Optional

# ---------- Attribute helpers ----------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value" on a token line."""
    if re.search(fr'\b{name}="', line):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # Insert before '/>' or '>' if present
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def remove_attr(line: str, name: str) -> str:
    """Remove an attribute entirely (first occurrence)."""
    return re.sub(fr'\s*\b{name}="[^"]*"', "", line, count=1)

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

# ---------- Mapping tables (as given) ----------

MORPH_MAP_0 = {'1': 'Person=1', '2': 'Person=2', '3': 'Person=3'}
MORPH_MAP_1 = {'s': 'Number=Sing', 'p': 'Number=Plur'}
MORPH_MAP_2 = {
    'pi': 'VerbForm=Fin|Mood=Ind|Tense=Pres|Aspect=Imp',
    'ii': 'VerbForm=Fin|Mood=Ind|Tense=Past|Aspect=Imp',
    'ai': 'VerbForm=Fin|Mood=Ind|Tense=Past|Aspect=Perf',
    'as': 'VerbForm=Fin|Mood=Sub|Aspect=Perf',
    'ps': 'VerbForm=Fin|Mood=Sub|Aspect=Imp',
    'am': 'VerbForm=Fin|Mood=Imp|Aspect=Perf',
    'pm': 'VerbForm=Fin|Mood=Imp|Aspect=Imp',
    '-n': 'VerbForm=Inf',
    '-d': 'VerbForm=Vnoun',
    '-g': 'VerbForm=Conv',
    '-p': 'VerbForm=Part|Tense=Past',
}
MORPH_MAP_4 = {'a': 'Voice=Act', 'p': 'Voice=Pass'}
MORPH_MAP_6 = {
    'n': 'Case=Nom', 'a': 'Case=Acc', 'd': 'Case=Dat', 'i': 'Case=Ins',
    'g': 'Case=Gen', 'b': 'Case=Abl', 'l': 'Case=Loc'
}

def expand_morph_codes(code: str) -> Dict[str, str]:
    """
    Expand the compact morphology string into a FEAT dict.
    Returns a dict of {FeatName: Value}.
    """
    feats: Dict[str, str] = {}

    # idx 0,1 (single chars)
    if len(code) > 0 and code[0] in MORPH_MAP_0:
        k, v = MORPH_MAP_0[code[0]].split("="); feats[k] = v
    if len(code) > 1 and code[1] in MORPH_MAP_1:
        k, v = MORPH_MAP_1[code[1]].split("="); feats[k] = v

    # idx 2..3 (two chars)
    if len(code) > 3:
        vf = code[2:4]
        if vf in MORPH_MAP_2:
            for kv in MORPH_MAP_2[vf].split("|"):
                k, v = kv.split("=", 1); feats[k] = v

    # idx 4 (voice)
    if len(code) > 4 and code[4] in MORPH_MAP_4:
        k, v = MORPH_MAP_4[code[4]].split("="); feats[k] = v

    # idx 6 (case)
    if len(code) > 6 and code[6] in MORPH_MAP_6:
        k, v = MORPH_MAP_6[code[6]].split("="); feats[k] = v

    return feats

# ---------- Core transform ----------

def transform_line(line: str) -> str:
    morph = get_attr(line, "morphology")
    if morph is None:
        return line

    produced = expand_morph_codes(morph)

    # Merge into FEAT
    cur = parse_feats(get_attr(line, "FEAT"))
    cur.update(produced)
    new_feat_str = feats_to_str(cur)

    line = set_attr(line, "FEAT", new_feat_str)

    # Remove morphology attribute regardless (normalize)
    line = remove_attr(line, "morphology")

    return line

# ---------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for raw in infile:
            out = transform_line(raw.rstrip("\n"))
            outfile.write(out if out.endswith("\n") else out + "\n")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 09: expand morphology codes to UD FEATS.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
