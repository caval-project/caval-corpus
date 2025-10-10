#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 42 — Renumber token ids per sentence, remap head-id and rel references.

Behavior per sentence:
  1) Build id mapping:
       - Non-hyphen ids get sequential numbers "1..n" in order of appearance.
       - Hyphen ids like "A-B" remap to "<map(A)>-<map(B)>" (if both parts exist).
       - Hyphen ids themselves are not assigned sequence numbers.
  2) Rewrite attributes:
       - id := mapped id (or kept if unmapped hyphen whose parts missing).
       - head-id := mapped when present in mapping; if missing or "_":
           * "_"   for hyphenated tokens
           * "0"   for non-hyphen tokens
       - rel="ID:..." -> map the leading ID if it exists in the mapping.
  3) Preserve attribute order and indentation; pass through non-token lines verbatim.

CLI:
  python scripts/prioel2conllu/stages/42_renumber_ids_per_sentence.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TOKEN_TAG_RE = re.compile(r'<token\b')
ATTR_RE      = re.compile(r'([-\w]+)="(.*?)"')
ATTR_ORDER_RE= re.compile(r'([-\w]+)=')

def parse_token_line(line: str) -> Tuple[str, Dict[str, str], List[str]]:
    """
    Return (indent, attrs, order) for a <token ... /> line.
    """
    indent = line[: line.index("<")] if "<" in line else ""
    attrs = dict(ATTR_RE.findall(line))
    order = ATTR_ORDER_RE.findall(line)
    return indent, attrs, order

def serialize_token(indent: str, attrs: Dict[str, str], order: List[str]) -> str:
    parts: List[str] = []
    seen = set()
    for k in order:
        if k in attrs and k not in seen:
            parts.append(f'{k}="{attrs[k]}"')
            seen.add(k)
    # append any new attrs not originally present (e.g., added head-id)
    for k in attrs:
        if k not in seen:
            parts.append(f'{k}="{attrs[k]}"')
            seen.add(k)
    return f'{indent}<token {" ".join(parts)} />\n'

def is_hyphen_id(id_value: str) -> bool:
    return "-" in id_value

def build_id_mapping(tokens: List[Tuple[str, Dict[str, str], List[str]]]) -> Dict[str, str]:
    """
    Create mapping for ids in a sentence:
      - Non-hyphen ids -> "1..n" in order of appearance
      - Hyphen ids -> mapped by expanding their parts with mapping when available
    """
    mapping: Dict[str, str] = {}
    counter = 1

    # First pass: assign sequential ids to non-hyphen ids
    for _indent, attrs, _order in tokens:
        tid = attrs.get("id")
        if not tid:
            continue
        if not is_hyphen_id(tid) and tid not in mapping:
            mapping[tid] = str(counter)
            counter += 1

    # Second pass: compute hyphen id mappings when both parts are known
    for _indent, attrs, _order in tokens:
        tid = attrs.get("id")
        if not tid or not is_hyphen_id(tid):
            continue
        a, b = tid.split("-", 1)
        if a in mapping and b in mapping:
            mapping[tid] = f"{mapping[a]}-{mapping[b]}"

    return mapping

def map_head_id(head_id: Optional[str], id_map: Dict[str, str], is_hyphen: bool) -> str:
    if not head_id or head_id == "_":
        # default per spec
        return "_" if is_hyphen else "0"
    if head_id in id_map:
        return id_map[head_id]
    # pass through (could be "0" or already hyphen-mapped or external)
    return head_id

def map_rel_attr(rel_val: str, id_map: Dict[str, str]) -> str:
    """
    rel is like "<ID>:<value>". Only map the leading ID when present in id_map.
    """
    if ":" not in rel_val:
        return rel_val
    lead, rest = rel_val.split(":", 1)
    if lead in id_map:
        return f"{id_map[lead]}:{rest}"
    return rel_val

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process one sentence (without trailing </sentence>).
    """
    lines = block.splitlines(keepends=False)
    token_buf: List[Tuple[str, Dict[str, str], List[str]]] = []
    other_lines: List[Tuple[int, str]] = []  # (index, line)

    # Collect tokens and non-token lines with positions
    for idx, line in enumerate(lines):
        if TOKEN_TAG_RE.search(line):
            indent, attrs, order = parse_token_line(line)
            token_buf.append((indent, attrs, order))
        else:
            other_lines.append((idx, line))

    if not token_buf:
        # No tokens - return original block
        return "\n".join(lines)

    # Build id mapping
    id_map = build_id_mapping(token_buf)

    # Rewrite tokens
    rewritten: List[str] = []
    for indent, attrs, order in token_buf:
        tid = attrs.get("id", "")
        new_id = id_map.get(tid, tid)
        attrs["id"] = new_id

        # head-id mapping / defaults
        is_hyph = is_hyphen_id(new_id)
        hid_old = attrs.get("head-id")
        attrs["head-id"] = map_head_id(hid_old, id_map, is_hyph)

        # rel mapping (if present) — "ID:..."
        if "rel" in attrs:
            attrs["rel"] = map_rel_attr(attrs["rel"], id_map)

        if verbose and tid != new_id:
            print(f'[renumber] {tid} -> {new_id} (head-id={hid_old!r} -> {attrs["head-id"]!r})')

        rewritten.append(serialize_token(indent, attrs, order))

    # Reassemble sentence, preserving non-token line order
    out_lines: List[str] = []
    t_iter = iter(rewritten)
    for idx in range(len(lines)):
        if TOKEN_TAG_RE.search(lines[idx]):
            out_lines.append(next(t_iter))
        else:
            out_lines.append(lines[idx] + ("\n" if not lines[idx].endswith("\n") else ""))

    return "".join(out_lines).rstrip("\n")

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Support separators with or without preceding newline
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
    ap = argparse.ArgumentParser(description="Stage 42: renumber token ids per sentence (and remap head-id / rel).")
    ap.add_argument("--in",  dest="inp", required=True, type=Path, help="Input file (e.g., output42.txt)")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output file (e.g., output43.txt)")
    ap.add_argument("--verbose", action="store_true", help="Print renumbering details")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
