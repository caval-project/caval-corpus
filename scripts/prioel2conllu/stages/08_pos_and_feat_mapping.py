#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 08 — Map part-of-speech and inject FEAT values (rule-based).

This stage rewrites `part-of-speech="..."` into UPOS and augments/edits FEATs
based on the combination of the original POS tag and lemma, plus a set of
special-case rules. Logic mirrors the legacy script but in a safer, clearer form.

CLI
    python scripts/prioel2conllu/stages/08_pos_and_feat_mapping.py \
        --in input.txt --out output.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional, Dict, Tuple

# --------- Regexes ----------
LEMMA_RE         = re.compile(r'\blemma="([^"]*)"')
POS_RE           = re.compile(r'\bpart-of-speech="([^"]*)"')
REL_RE           = re.compile(r'\brelation="([^"]*)"')
FEAT_RE          = re.compile(r'\bFEAT="([^"]*)"')
PRESENT_AFTER_RE = re.compile(r'\bpresentation-after="([^"]*)"')

# --------- Core helpers (attribute editing) ----------

def get_attr(line: str, rx: re.Pattern[str]) -> Optional[str]:
    m = rx.search(line)
    return m.group(1) if m else None

def set_attr(line: str, name: str, value: str) -> str:
    """Set or replace an XML-like attribute `name="..."` with `value`."""
    if re.search(fr'\b{name}="', line):
        return re.sub(fr'({name}=")[^"]*(")', frf'\1{value}\2', line, count=1)
    # Insert before '/>' or '>' if present
    if "/>" in line:
        return re.sub(r'\s*/>', f' {name}="{value}" />', line, count=1)
    if ">" in line:
        return re.sub(r'>', f' {name}="{value}">', line, count=1)
    return f'{line} {name}="{value}"'

def parse_feats(feats: str) -> Dict[str, str]:
    """Parse a FEAT string like 'A=B|C=D' into a dict. '_' or '' → {}."""
    if not feats or feats == "_":
        return {}
    out: Dict[str, str] = {}
    for kv in feats.split("|"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
    return out

def feats_to_str(d: Dict[str, str]) -> str:
    """Serialize FEAT dict back to string; '_' if empty."""
    if not d:
        return "_"
    # stable order for readability
    return "|".join(f"{k}={d[k]}" for k in sorted(d))

def merge_feats(line: str, new_feats: Dict[str, str]) -> str:
    """Merge `new_feats` into FEAT=..., creating FEAT if missing."""
    cur = get_attr(line, FEAT_RE)
    cur_dict = parse_feats(cur or "")
    cur_dict.update(new_feats)
    return set_attr(line, "FEAT", feats_to_str(cur_dict))

# --------- Mapping table ----------
# Instead of embedding FEAT text into the POS value, use (UPOS, extra_feats_dict).
# Keys are (old_pos, lemma_or_None).
POS_MAP: Dict[Tuple[str, Optional[str]], Tuple[str, Optional[Dict[str, str]]]] = {
    ("A-", None): ("ADJ", None),
    ("Mo", None): ("ADJ", {"NumType": "Ord"}),
    ("Ma", None): ("NUM", {"NumType": "Card"}),
    ("F-", None): ("X",   None),
    ("Ne", None): ("PROPN", None),
    ("C-", None): ("CCONJ", None),
    ("C-", "isk"): ("PART", None),

    ("Df", "gowcʻē"): ("PART", None),
    ("Df", "mi"):     ("PART", {"Polarity": "Neg"}),
    ("Df", "očʻ"):    ("PART", {"Polarity": "Neg"}),
    ("Df", "s"):      ("DET",  {"Definite": "Def", "PronType": "Dem"}),
    ("Df", "d"):      ("DET",  {"Definite": "Def", "PronType": "Dem"}),
    ("Df", "n"):      ("DET",  {"Definite": "Def", "PronType": "Dem"}),

    ("Df", "ast"):    ("ADV",  {"PronType": "Dem"}),
    ("Df", "aydr"):   ("ADV",  {"PronType": "Dem"}),
    ("Df", "and"):    ("ADV",  {"PronType": "Dem"}),
    ("Df", "andēn"):  ("ADV",  {"PronType": "Dem"}),
    ("Df", "aysowhetew"): ("ADV", {"PronType": "Dem"}),
    ("Df", "aynowhetew"): ("ADV", {"PronType": "Dem"}),
    ("Df", "ayspēs"): ("ADV", {"PronType": "Dem"}),
    ("Df", "aydpēs"): ("ADV", {"PronType": "Dem"}),
    ("Df", "aynpēs"): ("ADV", {"PronType": "Dem"}),
    ("Df", "soynpēs"): ("ADV", {"PronType": "Dem"}),
    ("Df", "noynpēs"): ("ADV", {"PronType": "Dem"}),
    ("Df", "aysr"):   ("ADV", {"PronType": "Dem"}),
    ("Df", "andr"):   ("ADV", {"PronType": "Dem"}),
    ("Df", "andrēn"): ("ADV", {"PronType": "Dem"}),
    ("Df", "asti"):   ("ADV", {"PronType": "Dem"}),
    ("Df", "ayti"):   ("ADV", {"PronType": "Dem"}),
    ("Df", "anti"):   ("ADV", {"PronType": "Dem"}),
    ("Df", "andstin"):("ADV", {"PronType": "Dem"}),

    ("Df", None): ("ADV", None),
    ("Du", None): ("ADV", {"PronType": "Int"}),
    ("Dq", None): ("ADV", {"PronType": "Rel"}),

    ("I-", "awasik"):   ("INTJ", {"PronType": "Dem"}),
    ("I-", "awadik"):   ("INTJ", {"PronType": "Dem"}),
    ("I-", "awanik"):   ("INTJ", {"PronType": "Dem"}),
    ("I-", "ahawasik"): ("INTJ", {"PronType": "Dem"}),
    ("I-", "ahawadik"): ("INTJ", {"PronType": "Dem"}),
    ("I-", "ahawanik"): ("INTJ", {"PronType": "Dem"}),
    ("I-", None): ("INTJ", None),

    ("V-", "em"):    ("AUX",  None),
    ("V-", "linim"): ("AUX",  None),
    ("V-", None):    ("VERB", None),

    ("R-", None): ("ADP",   None),
    ("G-", None): ("SCONJ", None),
    ("Nb", None): ("NOUN",  None),

    ("Py", "amenayn"):       ("DET", {"PronType": "Tot"}),
    ("Py", "amenekʻin"):     ("DET", {"PronType": "Tot"}),
    ("Py", "bazowm"):        ("DET", {"PronType": "Tot"}),
    ("Py", "biwrawor"):      ("DET", {"PronType": "Tot"}),
    ("Py", "iwrakʻančʻiwr"): ("DET", {"PronType": "Tot"}),
    ("Py", "sakaw"):         ("DET", {"PronType": "Tot"}),
    ("Py", "erkokʻin"):      ("NUM", {"NumType": "Sets"}),
    ("Py", "ewtʻnekʻin"):    ("NUM", {"NumType": "Sets"}),
    ("Py", "ekrotasanekʻin"):("NUM", {"NumType": "Sets"}),
    ("Py", "amenekʻean"):    ("PRON", {"PronType": "Tot"}),
    ("Py", "erekʻean"):      ("PRON", {"PronType": "Tot"}),
    ("Py", "erkokʻean"):     ("PRON", {"PronType": "Tot"}),
    ("Py", "ewtʻnekʻean"):   ("PRON", {"PronType": "Tot"}),

    ("Pp", None): ("PRON", {"PronType": "Prs"}),
    ("Pc", None): ("PRON", {"PronType": "Rcp"}),
    ("Pk", None): ("PRON", {"PronType": "Prs", "Reflex": "Yes"}),
    ("Pi", None): ("PRON", {"PronType": "Int"}),
    ("Px", None): ("PRON", {"PronType": "Ind"}),
    ("Px", "čʻikʻ"): ("PRON", {"PronType": "Ind", "Polarity": "Neg"}),

    ("Pd", "sa"):   ("PRON", {"PronType": "Dem"}),
    ("Pd", "da"):   ("PRON", {"PronType": "Dem"}),
    ("Pd", "na"):   ("PRON", {"PronType": "Dem"}),
    ("Pd", "soyn"): ("PRON", {"PronType": "Dem"}),
    ("Pd", "doyn"): ("PRON", {"PronType": "Dem"}),
    ("Pd", "noyn"): ("PRON", {"PronType": "Dem"}),
    ("Pd", "ayd"):  ("DET",  {"PronType": "Dem"}),
    ("Pd", "ayn"):  ("DET",  {"PronType": "Dem"}),

    ("Ps", "im"):  ("DET", {"PronType": "Prs", "Poss": "Yes"}),
    ("Ps", "kʻo"): ("DET", {"PronType": "Prs", "Poss": "Yes"}),
    ("Ps", "mer"): ("DET", {"PronType": "Prs", "Poss": "Yes"}),
    ("Ps", "jer"): ("DET", {"PronType": "Prs", "Poss": "Yes"}),
    ("Ps", "iwr"):  ("DET", {"PronType": "Prs", "Reflex": "Yes", "Poss": "Yes"}),
    ("Ps", "iwr#1"):("DET", {"PronType": "Prs", "Reflex": "Yes", "Poss": "Yes"}),
    ("Ps", "iwr#2"):("DET", {"PronType": "Prs", "Reflex": "Yes", "Poss": "Yes"}),
}

# --------- Core transformation ----------

def apply_pos_map(line: str) -> str:
    lemma = get_attr(line, LEMMA_RE)
    old_pos = get_attr(line, POS_RE)

    if not old_pos:
        return line

    # Prefer lemma-specific rule; fall back to POS-only rule.
    key = (old_pos, lemma) if (old_pos, lemma) in POS_MAP else (old_pos, None)
    if key in POS_MAP:
        new_upos, extra = POS_MAP[key]
        line = set_attr(line, "part-of-speech", new_upos)
        if extra:
            line = merge_feats(line, extra)
    return line

def handle_pr(line: str) -> str:
    """
    If POS is 'Pr', choose DET/PRON with PronType depending on presence of '?' in presentation-after.
    """
    pos = get_attr(line, POS_RE)
    if pos != "Pr":
        return line

    pa = get_attr(line, PRESENT_AFTER_RE) or ""
    if "?" in pa:
        # DET + PronType=Int
        line = set_attr(line, "part-of-speech", "DET")
        line = merge_feats(line, {"PronType": "Int"})
    else:
        # PRON + PronType=Rel
        line = set_attr(line, "part-of-speech", "PRON")
        line = merge_feats(line, {"PronType": "Rel"})
    return line

def handle_miayn_det(line: str) -> str:
    if 'lemma="miayn"' in line and 'part-of-speech="ADJ"' in line and 'relation="atr"' in line:
        line = set_attr(line, "part-of-speech", "DET")
    return line

def handle_cop_for_cxik(line: str) -> str:
    if 'lemma="čʻikʻ"' in line:
        # Force relation="cop"
        m = REL_RE.search(line)
        if m:
            line = set_attr(line, "relation", "cop")
    return line

def add_animacy_anim(line: str) -> str:
    # lemmas that should be animate
    if any(s in line for s in ['lemma="okʻ"', 'lemma="omn"', 'lemma="ov"', 'lemma="o"']):
        line = merge_feats(line, {"Animacy": "Anim"})
    return line

def add_animacy_inan_for_pron(line: str) -> str:
    if any(s in line for s in ['lemma="inčʻ"', 'lemma="zi"', 'lemma="zinčʻ"']) and 'part-of-speech="PRON"' in line:
        line = merge_feats(line, {"Animacy": "Inan"})
    return line

def handle_ays_hash(line: str) -> str:
    # lemmas like ays#1, ays#2 ...
    if re.search(r'lemma="ays#\d+"', line):
        # Force DET and replace FEAT entirely with PronType=Dem (matches original behavior)
        line = set_attr(line, "part-of-speech", "DET")
        if FEAT_RE.search(line):
            line = re.sub(r'(FEAT=")[^"]*(")', r'\1PronType=Dem\2', line, count=1)
        else:
            line = set_attr(line, "FEAT", "PronType=Dem")
    return line

def add_definite_spec_for_omn(line: str) -> str:
    if 'lemma="omn"' in line:
        line = merge_feats(line, {"Definite": "Spec"})
    return line

def add_definite_ind_for_ok(line: str) -> str:
    if 'lemma="okʻ"' in line:
        line = merge_feats(line, {"Definite": "Ind"})
    return line

def transform_line(line: str) -> str:
    # 1) table-driven POS/FEAT mapping
    line = apply_pos_map(line)

    # 2) special 'Pr' logic (DET/PRON + PronType=Int/Rel)
    line = handle_pr(line)

    # 3) special lexical tweaks
    line = handle_miayn_det(line)
    line = handle_cop_for_cxik(line)
    line = add_animacy_anim(line)
    line = add_animacy_inan_for_pron(line)
    line = handle_ays_hash(line)
    line = add_definite_spec_for_omn(line)
    line = add_definite_ind_for_ok(line)

    return line

# --------- File I/O & CLI ----------

def process_file(input_path: Path, output_path: Path) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for raw in infile:
            line = raw.rstrip("\n")
            out = transform_line(line)
            # ensure a newline (mirrors your original behavior)
            outfile.write(out if out.endswith("\n") else out + "\n")

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 08: rule-based POS mapping and FEAT injection.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input text path")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output text path")
    args = ap.parse_args()
    process_file(args.inp, args.out)

if __name__ == "__main__":
    main()
