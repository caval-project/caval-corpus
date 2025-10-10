#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 37 — Drop tokens with empty-token-sort="P" and report if any have dependents.

BEHAVIOR
  • Per sentence, find tokens whose line contains empty-token-sort="P".
  • If any have dependents (another token with head-id equal to their id),
    print a report (when --verbose).
  • Remove all such P-tokens from the output.

CLI
  python scripts/prioel2conllu/stages/37_drop_empty_P_and_report_dependents.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

# ---------------- Attribute helpers ----------------

def get_attr(line: str, name: str) -> Optional[str]:
    m = re.search(fr'\b{name}="([^"]*)"', line)
    return m.group(1) if m else None

def has_flag(line: str, frag: str) -> bool:
    return frag in line

# ---------------- Core per-sentence transform ----------------

def process_sentence(block: str, verbose: bool = False) -> str:
    """
    Process a single sentence block (without the trailing </sentence>).
    Removes lines that contain empty-token-sort="P" and logs their dependents.
    """
    lines: List[str] = [ln for ln in block.splitlines() if ln.strip()]

    # Collect ids of P-tokens
    p_ids: Set[str] = set()
    for ln in lines:
        if has_flag(ln, 'empty-token-sort="P"'):
            tid = get_attr(ln, "id")
            if tid:
                p_ids.add(tid)

    if not p_ids:
        # Nothing to drop
        return "\n".join(lines)

    # Build dependents map: head-id -> [child ids]
    dependents: Dict[str, List[str]] = {}
    for ln in lines:
        hid = get_attr(ln, "head-id")
        cid = get_attr(ln, "id")
        if hid and cid:
            dependents.setdefault(hid, []).append(cid)

    # Report P-tokens that still have dependents
    if verbose:
        for pid in sorted(p_ids, key=lambda x: (len(x), x)):
            kids = dependents.get(pid, [])
            if kids:
                print(f'[empty-P] token id {pid} has dependents: {", ".join(kids)}')

    # Filter out P-token lines
    kept = [ln for ln in lines if not has_flag(ln, 'empty-token-sort="P"')]

    return "\n".join(kept)

# ---------------- File I/O & CLI ----------------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Support either "\n</sentence>" or bare "</sentence>"
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
    ap = argparse.ArgumentParser(description='Stage 37: remove empty-token-sort="P" tokens and report their dependents.')
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input file")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output file")
    ap.add_argument("--verbose", action="store_true", help="Print logs for P-tokens that have dependents")
    args = ap.parse_args()

    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
