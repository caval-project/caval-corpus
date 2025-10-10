#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 49 — Extract unique Leipzig-style gloss lines from CoNLL-U.

Output lines look like:
  Gloss.IMPF.SG.3
  Gloss.AOR.SUBJ
  Gloss

Rules (derived from your original mapping):
  Person=1/2/3   -> 1 / 2 / 3
  Number=Sing/Plur -> SG / PL
  Voice=Act/Pass      -> ACT / MP
  Voice=Cau           -> CAUS.ACT
  Voice=CauPass       -> CAUS.MP
  Tense=Pres          -> PRS
  Aspect=Imp + Tense=Past   -> IMPF
  Aspect=Perf + Tense=Past  -> AOR
  Aspect=Imp + Mood=Sub     -> PRS.SUBJ
  Aspect=Perf + Mood=Sub    -> AOR.SUBJ
  Aspect=Perf + Mood=Imp    -> IPV
  Aspect=Imp  + Mood=Imp    -> PROH
  VerbForm=Inf/Conv/Part    -> INF / CVB / PTCP  (added at the end if present)

Notes
  • Input must be CoNLL-U (10 tab-separated columns).
  • We read `MISC` column for `Gloss=...`. If absent, the token is ignored.
  • FEATS parsing is robust; unknown features are ignored.
  • Output is unique, sorted lexicographically.
CLI
  python scripts/prioel2conllu/stages/49_generate_leipzig_glosses.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# --------------- FEATS -> compact tag mapping ---------------

def _parse_feats(feats: str) -> Dict[str, str]:
    """Parse FEATS string like 'Person=3|Number=Sing|Tense=Pres' into a dict."""
    out: Dict[str, str] = {}
    if not feats or feats == "_":
        return out
    for kv in feats.split("|"):
        if not kv or "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        out[k] = v
    return out

def convert_feats(feats: str) -> str:
    """
    Convert UD FEATS to your compact tags.
    Ordering: Person, Number, Voice/CAUS, TAM cluster, VerbForm.
    """
    f = _parse_feats(feats)
    tokens: List[str] = []

    # Person
    p = f.get("Person")
    if p in {"1", "2", "3"}:
        tokens.append(p)

    # Number
    num = f.get("Number")
    if num == "Sing":
        tokens.append("SG")
    elif num == "Plur":
        tokens.append("PL")

    # Voice (including causative flavors)
    voice = f.get("Voice")
    if voice == "Cau":
        tokens.append("CAUS.ACT")
    elif voice == "CauPass":
        tokens.append("CAUS.MP")
    elif voice == "Act":
        tokens.append("ACT")
    elif voice == "Pass":
        tokens.append("MP")

    # TAM cluster
    aspect = f.get("Aspect")
    tense  = f.get("Tense")
    mood   = f.get("Mood")

    tam: Optional[str] = None
    if mood == "Sub":
        if aspect == "Perf":
            tam = "AOR.SUBJ"
        elif aspect == "Imp":
            tam = "PRS.SUBJ"
    elif mood == "Imp":
        if aspect == "Perf":
            tam = "IPV"
        elif aspect == "Imp":
            tam = "PROH"
    else:
        if aspect == "Imp" and tense == "Past":
            tam = "IMPF"
        elif aspect == "Perf" and tense == "Past":
            tam = "AOR"
        elif tense == "Pres":
            tam = "PRS"

    if tam:
        tokens.append(tam)

    # VerbForm (placed last)
    vf = f.get("VerbForm")
    if vf == "Inf":
        tokens.append("INF")
    elif vf == "Conv":
        tokens.append("CVB")
    elif vf == "Part":
        tokens.append("PTCP")

    # Join without trailing dot; dedupe in case rules added duplicates
    cleaned: List[str] = []
    seen: Set[str] = set()
    for t in tokens:
        if t and t not in seen:
            cleaned.append(t)
            seen.add(t)
    return ".".join(cleaned)

# --------------- MISC helpers ---------------

def _get_misc_value(misc: str, key: str) -> Optional[str]:
    if not misc or misc == "_":
        return None
    parts = misc.split("|")
    for p in parts:
        if p.startswith(f"{key}="):
            return p.split("=", 1)[1]
    return None

# --------------- Core ---------------

def process_conllu(file_path: Path, output_path: Path, verbose: bool = False) -> None:
    unique: Set[str] = set()
    total, used = 0, 0

    with file_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            if not raw.strip() or raw.startswith("#"):
                continue
            cols = raw.rstrip("\n").split("\t")
            if len(cols) != 10:
                continue
            total += 1
            feats = cols[5]
            misc  = cols[9]
            gloss = _get_misc_value(misc, "Gloss")
            if not gloss:
                continue
            tag = convert_feats(feats)
            line = f"{gloss}.{tag}" if tag else gloss
            unique.add(line)
            used += 1

    sorted_entries = sorted(unique)

    with output_path.open("w", encoding="utf-8") as out:
        for entry in sorted_entries:
            out.write(entry + "\n")

    if verbose:
        print(f"[leipzig] tokens scanned: {total}, with Gloss: {used}, unique lines: {len(sorted_entries)}")
        print(f"[leipzig] wrote {output_path}")

# --------------- CLI ---------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 49: generate Leipzig-style gloss lines from CoNLL-U.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input CoNLL-U (e.g., armenian-nt_connlu.txt)")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text file (e.g., Leipzig_Glosses.txt)")
    ap.add_argument("--verbose", action="store_true", help="Print basic stats")
    args = ap.parse_args()
    process_conllu(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
