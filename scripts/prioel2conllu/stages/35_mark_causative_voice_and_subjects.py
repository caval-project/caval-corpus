#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 35 — Mark causative voice and relabel causative subjects.

RULES
  1) If token lemma is in {"korowsanem", "pʻlowzanem"} OR lemma endswith("owcʻanem")
     but NOT in {"cʻowcʻanem", "lowcʻanem"}:
       - If FEAT Voice=Act  -> set Voice=Cau
       - If FEAT Voice=Pass -> set Voice=CauPass
  2) For any head with Voice in {Cau, CauPass}, change dependents:
       - relation="nsubj"  -> "nsubj:caus"
       - relation="csubj"  -> "csubj:caus"

NOTES
  - Sentence-bounded (IDs usually reset per sentence).
  - Attribute-safe edits; FEAT parsing treats "_" as empty.
  - Idempotent: re-running won’t double-tag.

CLI
  python scripts/prioel2conllu/stages/35_mark_causative_voice_and_subjects.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

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

def feats_to_str(d: Dict[str, str]) -> str:
    return "_" if not d else "|".join(f"{k}={d[k]}" for k in sorted(d))

# ---------- Lemma checks ----------

CAUSATIVE_EXACT = {"korowsanem", "pʻlowzanem"}
CAUSATIVE_EXCLUDE = {"cʻowcʻanem", "lowcʻanem"}

def is_causative_lemma(lemma: Optional[str]) -> bool:
    if not lemma:
        return False
    if lemma in CAUSATIVE_EXACT:
        return True
    if lemma.endswith("owcʻanem") and lemma not in CAUSATIVE_EXCLUDE:
        return True
    return False

# ---------- Per-sentence processing ----------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process one sentence block (without the trailing </sentence>).
    """
    tokens: List[str] = block.splitlines()

    # Pass 1: set causative Voice when matches lemma
    causative_heads: Set[str] = set()
    for i, line in enumerate(tokens):
        lemma = get_attr(line, "lemma")
        if not is_causative_lemma(lemma):
            continue

        feats = parse_feats(get_attr(line, "FEAT"))
        voice = feats.get("Voice")

        # Only map Act/Pass to Cau/CauPass (mirror legacy behavior)
        if voice == "Act":
            feats["Voice"] = "Cau"
        elif voice == "Pass":
            feats["Voice"] = "CauPass"
        else:
            # No change if Voice absent or already Cau/CauPass/other
            continue

        tokens[i] = set_attr(line, "FEAT", feats_to_str(feats))
        tid = get_attr(line, "id")
        if tid:
            causative_heads.add(tid)
        if verbose:
            print(f'[voice] id={tid or "?"} lemma={lemma} Voice={voice}->{feats["Voice"]}')

    # Also consider tokens that already have Cau/CauPass from prior runs
    for i, line in enumerate(tokens):
        feats = parse_feats(get_attr(line, "FEAT"))
        if feats.get("Voice") in {"Cau", "CauPass"}:
            tid = get_attr(line, "id")
            if tid:
                causative_heads.add(tid)

    if not causative_heads:
        return "\n".join(tokens)

    # Pass 2: relabel subjects headed by a causative
    for i, line in enumerate(tokens):
        rel = get_attr(line, "relation")
        if rel not in {"nsubj", "csubj"}:
            continue
        hid = get_attr(line, "head-id")
        if not hid or hid not in causative_heads:
            continue

        new_rel = "nsubj:caus" if rel == "nsubj" else "csubj:caus"
        if verbose:
            tid = get_attr(line, "id") or "?"
            print(f'[subj->{new_rel}] id={tid} head={hid}')
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
    ap = argparse.ArgumentParser(description="Stage 35: mark causative voice and causative subjects.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
