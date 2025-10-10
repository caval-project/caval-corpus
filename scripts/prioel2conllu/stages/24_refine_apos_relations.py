#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 24 — Refine relation="apos" into flat:name / acl / parataxis / advcl / appos.

RULES (evaluated in order, first match wins), for tokens with relation="apos":
  1) POS=PROPN and HEAD.POS=PROPN -> flat:name
  2) POS=PROPN and token has a dependent with lemma="anown" -> acl
  3) (token is VERB/AUX/empty-V and HEAD.POS in {NOUN,PROPN,PRON,ADJ,NUM}) or token VerbForm=Vnoun -> acl
  4) token has dependent (relation in {cop,mark} or PronType=Rel) AND
     (HEAD.POS in {NOUN,PROPN,PRON,ADJ,NUM} or token VerbForm=Vnoun) -> acl
  5) token is VERB/AUX/empty-V AND (HEAD is VERB/AUX/empty-V OR HEAD has such a clausal dependent) -> parataxis
  6) token has such a clausal dependent AND (HEAD is VERB/AUX/empty-V OR HEAD has such a clausal dependent) -> parataxis
  7) token is VERB/AUX/empty-V OR token has such a clausal dependent -> advcl
  8) else -> appos

NOTES
  - Sentence-bounded (IDs usually restart per sentence).
  - “empty-V” means a token line containing empty-token-sort="V".
  - “such a clausal dependent” := a dependent whose relation in {cop, mark} OR FEAT has PronType=Rel.

CLI
  python scripts/prioel2conllu/stages/24_refine_apos_relations.py \
      --in input.txt --out output.txt [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional

# -------- Attribute helpers --------

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

# -------- Tiny predicates --------

def is_verbalish(line: str) -> bool:
    return (
        get_attr(line, "part-of-speech") in {"VERB", "AUX"}
        or ('empty-token-sort="V"' in line)
    )

def head_pos_is(line: Optional[str], pos_set: set[str]) -> bool:
    return bool(line and get_attr(line, "part-of-speech") in pos_set)

def has_clausal_dependent(token_id: str, tokens: List[str]) -> bool:
    """
    A dependent is 'clausal' if relation in {cop, mark} OR FEAT PronType=Rel.
    """
    for t in tokens:
        if get_attr(t, "head-id") == token_id:
            rel = get_attr(t, "relation")
            if rel in {"cop", "mark"}:
                return True
            feats = parse_feats(get_attr(t, "FEAT"))
            if feats.get("PronType") == "Rel":
                return True
    return False

def has_dependent_lemma(token_id: str, tokens: List[str], lemma: str) -> bool:
    for t in tokens:
        if get_attr(t, "head-id") == token_id and get_attr(t, "lemma") == lemma:
            return True
    return False

# -------- Per-sentence processing --------

def process_sentence(block: str, verbose: bool = False) -> str:
    tokens: List[str] = block.splitlines()

    # Indexes
    id2idx: Dict[str, int] = {}
    for i, line in enumerate(tokens):
        tid = get_attr(line, "id")
        if tid:
            id2idx[tid] = i

    for i, line in enumerate(tokens):
        if get_attr(line, "relation") != "apos":
            continue

        tid   = get_attr(line, "id")
        upos  = get_attr(line, "part-of-speech") or ""
        feats = parse_feats(get_attr(line, "FEAT"))
        hid   = get_attr(line, "head-id")
        head  = tokens[id2idx[hid]] if (hid and hid in id2idx) else None

        # Helpers for rules
        token_is_verbalish = is_verbalish(line)
        head_is_verbalish  = is_verbalish(head or "")
        head_is_nominalish = head_pos_is(head, {"NOUN", "PROPN", "PRON", "ADJ", "NUM"})
        token_vnoun        = (feats.get("VerbForm") == "Vnoun")
        token_has_clause_dep = bool(tid and has_clausal_dependent(tid, tokens))
        head_has_clause_dep  = bool(hid and has_clausal_dependent(hid, tokens))

        new_rel: Optional[str] = None

        # 1) PROPN + head PROPN -> flat:name
        if upos == "PROPN" and head_pos_is(head, {"PROPN"}):
            new_rel = "flat:name"

        # 2) PROPN + has dependent lemma="anown" -> acl
        elif upos == "PROPN" and tid and has_dependent_lemma(tid, tokens, "anown"):
            new_rel = "acl"

        # 3) acl condition 1
        elif (token_is_verbalish and head_is_nominalish) or token_vnoun:
            new_rel = "acl"

        # 4) acl condition 2
        elif (tid and token_has_clause_dep) and (head_is_nominalish or token_vnoun):
            new_rel = "acl"

        # 5) parataxis (clausal) 1
        elif token_is_verbalish and (head_is_verbalish or head_has_clause_dep):
            new_rel = "parataxis"

        # 6) parataxis (clausal) 2
        elif (tid and token_has_clause_dep) and (head_is_verbalish or head_has_clause_dep):
            new_rel = "parataxis"

        # 7) advcl
        elif token_is_verbalish or (tid and token_has_clause_dep):
            new_rel = "advcl"

        # 8) default appos
        else:
            new_rel = "appos"

        if verbose:
            print(
                f'[apos->{new_rel}] id={tid or "?"} pos={upos} head={hid or "?"} '
                f'headpos={get_attr(head or "", "part-of-speech") or "-"} '
                f'verbalish={token_is_verbalish} head_verbalish={head_is_verbalish} '
                f'vnoun={token_vnoun} token_clause_dep={token_has_clause_dep} head_clause_dep={head_has_clause_dep}'
            )

        tokens[i] = set_attr(line, "relation", new_rel)

    return "\n".join(tokens)

# -------- File I/O & CLI --------

def process_file(input_path: Path, output_path: Path, verbose: bool = False) -> None:
    text = input_path.read_text(encoding="utf-8")

    # Accept either "\n</sentence>" or bare "</sentence>" as separators
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
    ap = argparse.ArgumentParser(description="Stage 24: refine relation='apos' into UD labels.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    ap.add_argument("--verbose", action="store_true", help="Print decision logs")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
