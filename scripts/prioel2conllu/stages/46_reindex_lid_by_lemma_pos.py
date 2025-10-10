#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 46 — Reindex LId=… per lemma & (POS, prior lid-number|None) combination.

Behavior
  • Scan the CoNLL-U once to find all lemmas that ever have an LId=… in MISC.
  • For each such lemma, walk tokens in file order and build a *first-seen* map:
        key := (POS, prior_lid_num_or_None)
        value := f"{lemma}-{k}"   # k = 1..N per lemma
    This means tokens *without* an LId join the (POS, None) bucket for that lemma.
  • Second pass: rewrite MISC:
        - Replace/add LId=… using the lemma’s mapping.
        - Preserve all other MISC items.
        - Keep any literal “#<n>” token at the very end of MISC.
  • Comments (# …) and blank lines are passed through unchanged.
  • Multiword (“1-2”) and empty nodes (“3.1”) are also processed if present.

CLI
  python scripts/prioel2conllu/stages/46_reindex_lid_by_lemma_pos.py \
      --in input --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# -------------- CoNLL-U helpers --------------

def is_comment(line: str) -> bool:
    return line.startswith("#")

def is_blank(line: str) -> bool:
    return not line.strip()

def split_cols(line: str) -> Optional[List[str]]:
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 10:
        return None
    return parts

def join_cols(cols: List[str]) -> str:
    return "\t".join(cols) + "\n"

def parse_misc(misc: str) -> Tuple[List[Tuple[str, Optional[str]]], Optional[str]]:
    """
    Parse MISC into a list of (key, value) pairs, preserving order.
    Returns (items, hash_tag).
      items: [("Key","Val"), ...]  or [("Key",None)] for val-less markers.
      hash_tag: like "#2" if present (kept separately to re-append last).
    '_' -> ([], None)
    """
    if not misc or misc == "_":
        return [], None
    items: List[Tuple[str, Optional[str]]] = []
    hash_tag: Optional[str] = None
    for raw in misc.split("|"):
        if not raw:
            continue
        if raw.startswith("#"):
            # Keep only the last #n if multiple (mirror your original behavior)
            hash_tag = raw
            continue
        if "=" in raw:
            k, v = raw.split("=", 1)
            items.append((k, v))
        else:
            items.append((raw, None))
    return items, hash_tag

def render_misc(items: List[Tuple[str, Optional[str]]], hash_tag: Optional[str]) -> str:
    if not items and not hash_tag:
        return "_"
    parts = [f"{k}={v}" if v is not None else k for (k, v) in items]
    if hash_tag:
        parts.append(hash_tag)
    return "|".join(parts)

def get_misc_value(items: List[Tuple[str, Optional[str]]], key: str) -> Optional[str]:
    for k, v in items:
        if k == key:
            return v
    return None

def upsert_misc(items: List[Tuple[str, Optional[str]]], key: str, value: str) -> List[Tuple[str, Optional[str]]]:
    for i, (k, _) in enumerate(items):
        if k == key:
            items[i] = (key, value)
            return items
    items.append((key, value))
    return items

# -------------- Core logic --------------

LID_RE = re.compile(r'^([^-\s]+)-(\d+)$')  # matches lemma-N, returns (lemma, num)

def collect_lemmas_with_lid(lines: List[str]) -> set:
    lemmas: set = set()
    for ln in lines:
        if is_comment(ln) or is_blank(ln):
            continue
        cols = split_cols(ln)
        if not cols:
            continue
        misc_items, _hash = parse_misc(cols[9])
        lid = get_misc_value(misc_items, "LId")
        if lid:
            m = LID_RE.match(lid)
            if m:
                lemmas.add(cols[2])  # lemma column value (already transliterated Armenian)
    return lemmas

def build_mapping(lines: List[str], target_lemmas: set, verbose: bool = False) -> Dict[str, Dict[Tuple[str, Optional[str]], str]]:
    """
    For each lemma in target_lemmas, map (POS, prior_lid_num_or_None) -> new LId 'lemma-k'
    in **first observed** order.
    """
    mapping: Dict[str, Dict[Tuple[str, Optional[str]], str]] = {}
    counters: Dict[str, int] = {}

    for ln in lines:
        if is_comment(ln) or is_blank(ln):
            continue
        cols = split_cols(ln)
        if not cols:
            continue

        lemma = cols[2]
        if lemma not in target_lemmas:
            continue

        pos = cols[3]
        misc_items, _hash = parse_misc(cols[9])
        lid_val = get_misc_value(misc_items, "LId")
        lid_num: Optional[str] = None
        if lid_val:
            m = LID_RE.match(lid_val)
            if m:
                lid_num = m.group(2)

        key = (pos, lid_num)  # NOTE: None bucket for tokens without LId
        mp = mapping.setdefault(lemma, {})
        if key not in mp:
            counters[lemma] = counters.get(lemma, 0) + 1
            mp[key] = f"{lemma}-{counters[lemma]}"
            if verbose:
                print(f"[map] lemma={lemma!r} key={key} -> {mp[key]}")
    return mapping

def rewrite_lines(lines: List[str], mapping: Dict[str, Dict[Tuple[str, Optional[str]], str]], verbose: bool = False) -> List[str]:
    out: List[str] = []
    for ln in lines:
        if is_comment(ln) or is_blank(ln):
            out.append(ln if ln.endswith("\n") else ln + "\n")
            continue

        cols = split_cols(ln)
        if not cols:
            out.append(ln if ln.endswith("\n") else ln + "\n")
            continue

        lemma = cols[2]
        pos = cols[3]
        misc_items, hash_tag = parse_misc(cols[9])

        # Only adjust lemmas that appear in mapping
        mp = mapping.get(lemma)
        if not mp:
            out.append(ln if ln.endswith("\n") else ln + "\n")
            continue

        # Determine prior lid-number (if any) for the key
        lid_val = get_misc_value(misc_items, "LId")
        lid_num: Optional[str] = None
        if lid_val:
            m = LID_RE.match(lid_val)
            if m:
                lid_num = m.group(2)

        key = (pos, lid_num)
        new_lid = mp.get(key)
        if new_lid:
            # Replace or add LId=
            misc_items = upsert_misc(misc_items, "LId", new_lid)
            if verbose and lid_val != new_lid:
                print(f"[rewrite] id={cols[0]} lemma={lemma!r} pos={pos!r} LId: {lid_val!r} -> {new_lid!r}")

        cols[9] = render_misc(misc_items, hash_tag)
        out.append(join_cols(cols))
    return out

# -------------- File I/O & CLI --------------

def process_file(inp: Path, outp: Path, verbose: bool = False) -> None:
    lines = inp.read_text(encoding="utf-8").splitlines(keepends=True)

    # 1) Which lemmas are in scope? (those that have at least one LId somewhere)
    target_lemmas = collect_lemmas_with_lid(lines)

    # 2) Build first-seen mapping for each lemma
    mapping = build_mapping(lines, target_lemmas, verbose=verbose)

    # 3) Rewrite file using mapping
    rewritten = rewrite_lines(lines, mapping, verbose=verbose)

    outp.write_text("".join(rewritten), encoding="utf-8")
    if verbose:
        print(f"[lid] wrote {outp}")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 46: reindex LId per lemma and (POS, prior lid number|None).")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input CoNLL-U file (e.g., output46.txt)")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output CoNLL-U file (e.g., output47.txt)")
    ap.add_argument("--verbose", action="store_true", help="Print mapping decisions")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
