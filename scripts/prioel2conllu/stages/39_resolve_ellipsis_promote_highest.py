#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 39 — Resolve ellipsis by promoting the highest-ranking dependent of empty V nodes.

Per sentence:
  • For each token with empty-token-sort="V":
      1) Pick the highest-ranking dependent by the given hierarchy.
      2) Reattach the chosen token's dependents to the empty V as orphans.
      3) Promote the chosen token:
           - relation := emptyV.relation
           - head-id  := emptyV.head-id (or remove if none)
           - id       := emptyV.id
      4) For other dependents of the empty V:
           - head-id := chosen.id
           - if relation != punct -> relation := orphan
      5) Remove the empty V line.

CLI
  python scripts/prioel2conllu/stages/39_resolve_ellipsis_promote_highest.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------- Attribute helpers ----------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_attr(line: str, name: str) -> bool:
    return bool(re.search(fr'\b' + re.escape(name) + r'="', line))

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace XML-like attribute name="value" on a token line."""
    if has_attr(line, name):
        return re.sub(fr'({name}=")[^"]*(")', rf'\1{value}\2', line, count=1)
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def remove_attr(line: str, name: str) -> str:
    line = re.sub(fr'\s*{name}="[^"]*"', '', line, count=1)
    line = re.sub(r'\s+(\/?>)', r' \1', line)  # tidy spaces
    return line

# ---------------- Core logic ----------------

HIERARCHY = ["nsubj", "obj", "iobj", "obl", "advmod", "csubj", "ccomp", "advcl", "dislocated", "vocative"]
RANK = {rel: i for i, rel in enumerate(HIERARCHY)}

def choose_highest(deps: List[Tuple[str, str, int, bool]]) -> Optional[Tuple[str, str, int, bool]]:
    """
    deps: list of (id, relation, index_in_tokens, is_empty_v)
    Return the top-ranked dependent or None.
    """
    valid = [d for d in deps if d[1] in RANK]
    if not valid:
        return None
    valid.sort(key=lambda d: RANK[d[1]])
    return valid[0]

def process_sentence(block: str, verbose: bool = False) -> str:
    tokens: List[str] = [ln for ln in block.splitlines() if ln.strip()]
    if not tokens:
        return ""

    # Build initial indices (we'll avoid reindexing by marking deletions as "")
    id2idx: Dict[str, int] = {}
    children: Dict[str, List[int]] = {}
    for i, t in enumerate(tokens):
        tid = get_attr(t, "id")
        if tid:
            id2idx[tid] = i
        hid = get_attr(t, "head-id")
        if hid:
            children.setdefault(hid, []).append(i)

    # Snapshot empty-V list first to avoid index churn
    empty_v_entries: List[Tuple[str, int]] = []
    for i, t in enumerate(tokens):
        if 'empty-token-sort="V"' in t:
            tid = get_attr(t, "id")
            if tid:
                empty_v_entries.append((tid, i))

    for v_id, v_idx in empty_v_entries:
        if v_idx >= len(tokens) or tokens[v_idx] == "":
            continue  # already removed
        v_line = tokens[v_idx]

        # Collect dependents of this empty V
        deps: List[Tuple[str, str, int, bool]] = []
        for j in children.get(v_id, []):
            dep_line = tokens[j]
            dep_id = get_attr(dep_line, "id") or ""
            dep_rel = get_attr(dep_line, "relation") or ""
            deps.append((dep_id, dep_rel, j, 'empty-token-sort="V"' in dep_line))

        chosen = choose_highest(deps)
        if not chosen:
            # No valid dependent to promote; skip
            continue

        chosen_id, chosen_rel, chosen_idx, _ = chosen

        # 1) Reattach chosen token's dependents to empty V (as orphan)
        for j in list(children.get(chosen_id, [])):
            if tokens[j] == "":
                continue
            tokens[j] = set_attr(tokens[j], "head-id", v_id)
            if get_attr(tokens[j], "relation") != "punct":
                tokens[j] = set_attr(tokens[j], "relation", "orphan")

        # 2) Promote chosen token: transfer relation, head-id, id
        v_rel = get_attr(v_line, "relation")
        v_head = get_attr(v_line, "head-id")
        chosen_line = tokens[chosen_idx]

        if v_rel:
            chosen_line = set_attr(chosen_line, "relation", v_rel)
        if v_head:
            chosen_line = set_attr(chosen_line, "head-id", v_head)
        else:
            if has_attr(chosen_line, "head-id"):
                chosen_line = remove_attr(chosen_line, "head-id")

        # Change chosen's id to empty V's id
        chosen_line = set_attr(chosen_line, "id", v_id)
        tokens[chosen_idx] = chosen_line

        # Update indices: all references to chosen_id as head must now point to v_id (we already moved its kids above)
        # 3) For other dependents of empty V: head -> chosen (post-promotion this equals v_id)
        #    Note: after step 2, chosen.id == v_id, so we can attach others directly to v_id.
        for dep_id, dep_rel, dep_idx, _ in deps:
            if dep_id == chosen_id:
                continue
            tokens[dep_idx] = set_attr(tokens[dep_idx], "head-id", v_id)
            if get_attr(tokens[dep_idx], "relation") != "punct":
                tokens[dep_idx] = set_attr(tokens[dep_idx], "relation", "orphan")

        if verbose:
            print(f'[ellipsis] emptyV id={v_id} -> promoted id={chosen_id} (now id={v_id}), rel={v_rel or "-"}, head={v_head or "-"}')

        # 4) Remove the empty V token line
        tokens[v_idx] = ""

    # Drop deleted lines
    kept = [t for t in tokens if t]
    return "\n".join(kept)

# ---------------- File I/O & CLI ----------------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Accept either "\n</sentence>" or bare "</sentence>"
    if "\n</sentence>" in text:
        parts = text.split("\n</sentence>")
        sep = "\n</sentence>"
    else:
        parts = text.split("</sentence>")
        sep = "</sentence>"

    out_parts: List[str] = []
    for part in parts:
        blk = part.strip()
        if not blk:
            out_parts.append("")
            continue
        out_parts.append(process_sentence(blk, verbose=verbose))

    output_path.write_text(sep.join(out_parts), encoding="utf-8")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 39: resolve ellipsis by promoting highest dependent of empty V.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path (e.g., output37.txt)")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path (e.g., output38.txt)")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
