#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
19_validate_and_correct_clitic_rules.py

Apply targeted corrections to Armenian clitic/article tokens in CoNLL-U:
- 'ն'  -> Definite=Def|Deixis=Remt|PronType=Art, deprel=det, head=previous word token
- 'ս'  -> Definite=Def|Deixis=Prox|PronType=Art, deprel=det, head=previous word token
- 'դ'  -> Definite=Def|Deixis=Med|PronType=Art,  deprel=det, head=previous word token
- 'զ'  -> add Definite=Def, deprel=case, head=next word token
- 'ի','յ','ց' -> head=next word token (leave other fields)

I/O (fixed by project convention):
- Read:  ./input
- Write: ./output
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple

INPUT_PATH  = "input"
OUTPUT_PATH = "output"

# ---------- CoNLL-U helpers ----------

REQUIRED_COLS = 10
TAB = "\t"
BLKSEP = "\n\n"

_id_word_re   = re.compile(r"^\d+$")      # word IDs: 1,2,3...
_id_range_re  = re.compile(r"^\d+-\d+$")  # multiword tokens: 1-2
_id_empty_re  = re.compile(r"^\d+\.\d+$") # empty nodes: 3.1

def _ensure_underscore(s: str) -> str:
    return s if (s and s.strip() != "") else "_"

def parse_feats(feats: str) -> Dict[str, List[str]]:
    """Parse FEATS like 'Case=Acc|Number=Plur' into dict."""
    feats = (feats or "").strip()
    if feats in ("", "_"):
        return {}
    out: Dict[str, List[str]] = {}
    for item in feats.split("|"):
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        out.setdefault(k, []).append(v)
    return out

def fmt_feats(fd: Dict[str, List[str]]) -> str:
    if not fd:
        return "_"
    items: List[str] = []
    for k in sorted(fd.keys()):
        # keep stable deterministic order of values
        for v in sorted(set(fd[k])):
            items.append(f"{k}={v}")
    return "|".join(items) if items else "_"

def merge_feats(base: str, updates: Dict[str, List[str]], replace_keys: Tuple[str, ...] = ()) -> str:
    """
    Merge FEATS while optionally replacing specific keys entirely.
    - base: existing feats string
    - updates: dict of key -> list of values to add/replace
    - replace_keys: keys to fully replace (remove old, insert new)
    """
    cur = parse_feats(base)
    for k in replace_keys:
        if k in cur:
            del cur[k]
    for k, vals in updates.items():
        if k in replace_keys:
            cur[k] = list(vals)
        else:
            cur.setdefault(k, [])
            cur[k].extend(vals)
    return fmt_feats(cur)

def is_word_id(tok_id: str) -> bool:
    return bool(_id_word_re.match(tok_id))

def is_multiword(tok_id: str) -> bool:
    return bool(_id_range_re.match(tok_id))

def is_empty(tok_id: str) -> bool:
    return bool(_id_empty_re.match(tok_id))

# ---------- Core correction logic ----------

ART_RULES = {
    "ն": {"Deixis": ["Remt"], "Definite": ["Def"], "PronType": ["Art"]},
    "ս": {"Deixis": ["Prox"], "Definite": ["Def"], "PronType": ["Art"]},
    "դ": {"Deixis": ["Med"],  "Definite": ["Def"], "PronType": ["Art"]},
}

NEXT_HEAD_FORMS = {"զ", "ի", "յ", "ց"}

def validate_and_correct_tokens(token_lines: List[str]) -> Tuple[List[str], int]:
    """
    token_lines: CoNLL-U token lines (no comments)
    Returns: (corrected_lines, num_tokens_changed)
    """
    # Parse rows
    rows: List[List[str]] = []
    for ln in token_lines:
        cols = ln.split(TAB)
        if len(cols) != REQUIRED_COLS:
            # keep malformed as-is
            rows.append(cols + [""] * (REQUIRED_COLS - len(cols)))
        else:
            rows.append(cols)

    # Build an ordered list of indices for real word tokens (by position in rows)
    word_row_indices: List[int] = [
        i for i, cols in enumerate(rows)
        if len(cols) >= 1 and is_word_id((cols[0] or "").strip())
    ]

    changed = 0

    for i, cols in enumerate(rows):
        if len(cols) < REQUIRED_COLS:
            continue

        tok_id = cols[0].strip()
        form   = (cols[1] or "").strip()

        if not is_word_id(tok_id):  # skip multiword/empty IDs for rewriting
            continue

        # Find this row's position among word tokens
        try:
            pos = word_row_indices.index(i)
        except ValueError:
            continue

        original = cols[:]  # copy for change detection

        # Helper: previous/next word token head id
        prev_head = None
        if pos - 1 >= 0:
            prev_row = rows[word_row_indices[pos - 1]]
            prev_head = prev_row[0].strip()

        next_head = None
        if pos + 1 < len(word_row_indices):
            next_row = rows[word_row_indices[pos + 1]]
            next_head = next_row[0].strip()

        # Current fields
        feats = cols[5].strip() if len(cols) > 5 else "_"
        head  = cols[6].strip() if len(cols) > 6 else "_"
        deprel= cols[7].strip() if len(cols) > 7 else "_"

        # --- Rules ---
        if form in ART_RULES:
            # Merge feats but REPLACE these keys entirely to avoid contradictory values
            cols[5] = merge_feats(
                feats,
                updates=ART_RULES[form],
                replace_keys=("Definite", "Deixis", "PronType")
            )
            # set head to previous word token if available
            if prev_head is not None:
                cols[6] = prev_head
            # set deprel to 'det'
            cols[7] = "det"

        elif form == "զ":
            # Add/keep Definite=Def without wiping other keys
            cols[5] = merge_feats(feats, updates={"Definite": ["Def"]})
            # head to next word token if available
            if next_head is not None:
                cols[6] = next_head
            cols[7] = "case"

        elif form in NEXT_HEAD_FORMS:
            # only update head to next word token
            if next_head is not None:
                cols[6] = next_head
            # keep feats/deprel as-is

        # Normalize empties
        for k in range(REQUIRED_COLS):
            cols[k] = _ensure_underscore(cols[k])

        if cols != original:
            changed += 1

        rows[i] = cols

    # Re-stringify
    out_lines = [TAB.join(cols[:REQUIRED_COLS]) for cols in rows]
    return out_lines, changed

def process_file(in_path: str, out_path: str) -> int:
    with open(in_path, "r", encoding="utf-8") as f:
        text = f.read().rstrip()

    if not text:
        with open(out_path, "w", encoding="utf-8") as w:
            w.write("")
        return 0

    sentences = text.split(BLKSEP)
    corrected_blocks: List[str] = []
    total_changed = 0

    for block in sentences:
        if not block.strip():
            continue
        lines = block.split("\n")
        meta   = [ln for ln in lines if ln.startswith("#")]
        tokens = [ln for ln in lines if not ln.startswith("#") and ln.strip()]

        corrected_tok_lines, changed = validate_and_correct_tokens(tokens)
        total_changed += changed
        corrected_blocks.append("\n".join(meta + corrected_tok_lines))

    with open(out_path, "w", encoding="utf-8") as w:
        w.write(BLKSEP.join(corrected_blocks) + "\n")

    return total_changed

if __name__ == "__main__":
    changed = process_file(INPUT_PATH, OUTPUT_PATH)
    print(f"Validation & correction complete. Tokens updated: {changed}. Saved to: {OUTPUT_PATH}")
