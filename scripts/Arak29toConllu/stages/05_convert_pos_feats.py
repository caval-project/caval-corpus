#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 05 — Convert scraped POS/FEATS to UD (UPOS + FEATS).

What it does
------------
- Maps coarse POS tags (and some compound tags) to UD UPOS.
- Applies lemma-dependent overrides that add/modify UPOS and FEATS.
- Converts short feature codes (e.g., "nom", "sg", "pres", "aor", "imp+neg") into UD FEATS.
- Merges all feature sources, de-duplicates, sorts, and keeps "_" when empty.
- Preserves *all* comments/metadata lines and column counts (10 columns).

Usage
-----
python Arak29toConllu/stages/05_convert_pos_feats.py \
  --in  data/arak29/input.conllu \
  --out data/arak29/output.conllu
"""

from __future__ import annotations

import argparse
import re
from typing import Dict, List, Tuple


# ----------------------------- MAPPINGS ---------------------------------------

# Simple POS → UPOS (last one wins in Python dicts; set 'verb' to VERB by default)
SIMPLE_POS: Dict[str, str] = {
    "adj": "ADJ",
    "adv": "ADV",
    "conj": "SCONJ",
    "intj": "INTJ",
    "noun": "NOUN",
    "part": "PART",
    "post": "ADP",
    "prep": "ADP",
    "prop.gntl": "NOUN",
    "prop.adv": "ADV",
    "prop.adj": "ADJ",
    "prop": "PROPN",
    "verb.pot": "ADJ",
    "verb.prpt": "NOUN",
    "verb": "VERB",
    "pron": "PRON",
}

# Lemma → UPOS overrides (simple)
LEMMA_POS_SIMPLE: Dict[str, str] = {
    "բազում": "DET", "միայն": "DET", "սակաւ": "DET",
    "այսինքն": "ADV", "գէթ": "ADV", "գոնէ": "ADV", "եւեթ": "ADV",
    "բայց": "CCONJ", "եւ": "CCONJ", "կամ": "CCONJ", "սակայն": "CCONJ",
    "քան": "CCONJ", "նաեւ": "CCONJ", "ու": "CCONJ", "չեւ": "CCONJ",
    "իսկ": "PART", "երանի": "ADV",
    "իւրաքանչիւր": "DET",
    "արդարեւ": "ADV", "զիարդ": "ADV", "ընդէր": "ADV", "քաւ": "ADV", "թերեւս": "ADV",
    "ահա": "INTJ", "այո": "INTJ", "միթէ": "SCONJ",
    "գաղտ": "ADV", "յետոյ": "ADV", "վերոյ": "ADV", "մեկուսի": "ADV",
    "իբր": "CCONJ",
    "եմ": "AUX", "լինիմ": "AUX",
    "այլ": "SCONJ",
}

# POS (possibly compound) → (UPOS, extra features)
POS_COMPLEX: Dict[str, Tuple[str, Dict[str, str]]] = {
    "for": ("X", {"Foreign": "Yes"}),
    "num.ord": ("ADJ", {"NumType": "Ord"}),
    "num": ("NUM", {"NumType": "Card"}),
    "verb.des": ("VERB", {"VerbForm": "Conv"}),
    "verb.gen": ("VERB", {"VerbForm": "Vnoun"}),
    "verb.nom": ("VERB", {"VerbForm": "Part"}),
    "verb.inf.gen": ("VERB", {"VerbForm": "Vnoun"}),
    "verb.inf.abl": ("VERB", {"VerbForm": "Vnoun"}),
    "verb.inf.ins": ("VERB", {"VerbForm": "Vnoun"}),
    "verb.inf.loc": ("VERB", {"VerbForm": "Vnoun"}),
    "verb.inf.nom": ("VERB", {"VerbForm": "Inf"}),
    "verb.inf.acc": ("VERB", {"VerbForm": "Inf"}),
    "verb.pfv": ("VERB", {"VerbForm": "Part"}),
    "verb.pvf": ("VERB", {"VerbForm": "Part"}),
}

# (lemma, original_pos) → (UPOS, extra features)
LEMMA_POS_COMPLEX: Dict[Tuple[str, str], Tuple[str, Dict[str, str]]] = {
    ("կրկին", "adv"): ("ADV", {"NumType": "Mult"}),
    ("երկիցս", "adv"): ("ADV", {"NumType": "Mult"}),
    ("այսուհետեւ", "adv"): ("ADV", {"Deixis": "Prox", "PronType": "Dem"}),
    ("աստի", "adv"): ("ADV", {"Deixis": "Prox", "PronType": "Dem"}),
    ("աստ", "adv"): ("ADV", {"Deixis": "Prox", "PronType": "Dem"}),
    ("այսպէս", "adv"): ("ADV", {"Deixis": "Prox", "PronType": "Dem"}),
    ("այսր", "adv"): ("ADV", {"Deixis": "Prox", "PronType": "Dem"}),
    ("անդստին", "adv"): ("ADV", {"Deixis": "Med", "PronType": "Dem"}),
    ("այդպէս", "adv"): ("ADV", {"Deixis": "Med", "PronType": "Dem"}),
    ("այդր", "adv"): ("ADV", {"Deixis": "Med", "PronType": "Dem"}),
    ("այտի", "adv"): ("ADV", {"Deixis": "Med", "PronType": "Dem"}),
    ("անդր", "adv"): ("ADV", {"Deixis": "Remt", "PronType": "Dem"}),
    ("անդ", "adv"): ("ADV", {"Deixis": "Remt", "PronType": "Dem"}),
    ("անդրէն", "adv"): ("ADV", {"Deixis": "Remt", "PronType": "Dem"}),
    ("անտի", "adv"): ("ADV", {"Deixis": "Remt", "PronType": "Dem"}),
    ("այնպէս", "adv"): ("ADV", {"Deixis": "Remt", "PronType": "Dem"}),
    ("նոյնպէս", "adv"): ("ADV", {"Deixis": "Remt", "PronType": "Dem"}),
    ("այնուհետեւ", "adv"): ("ADV", {"Deixis": "Remt", "PronType": "Dem"}),

    ("իննսներորդ", "num․"): ("ADJ", {"NumType": "Ord"}),  # note Armenian dot
    ("մի", "num․"): ("DET", {"Definite": "Spec"}),

    ("ահաւասիկ", "part"): ("INTJ", {"Deixis": "Prox", "PronType": "Dem"}),
    ("աւասիկ", "part"): ("INTJ", {"Deixis": "Prox", "PronType": "Dem"}),
    ("ահաւադիկ", "part"): ("INTJ", {"Deixis": "Med", "PronType": "Dem"}),
    ("աւադիկ", "part"): ("INTJ", {"Deixis": "Med", "PronType": "Dem"}),
    ("ահաւանիկ", "part"): ("INTJ", {"Deixis": "Remt", "PronType": "Dem"}),
    ("աւանիկ", "part"): ("INTJ", {"Deixis": "Remt", "PronType": "Dem"}),
    ("ոչ", "part"): ("PART", {"Polarity": "Neg"}),

    ("իմ", "pron.adj"): ("DET", {"Person": "1", "Poss": "Yes", "PronType": "Prs"}),
    ("մեր", "pron.adj"): ("DET", {"Person": "1", "Poss": "Yes", "PronType": "Prs"}),
    ("քո", "pron.adj"): ("DET", {"Person": "2", "Poss": "Yes", "PronType": "Prs"}),
    ("ձեր", "pron.adj"): ("DET", {"Person": "2", "Poss": "Yes", "PronType": "Prs"}),
    ("իւր", "pron.adj"): ("DET", {"Person": "3", "Poss": "Yes", "PronType": "Prs", "Reflex": "Yes"}),
    ("իւրային", "pron.adj"): ("DET", {"Person": "3", "Poss": "Yes", "PronType": "Prs", "Reflex": "Yes"}),

    ("իմ", "pron"): ("DET", {"Person": "1", "Poss": "Yes", "PronType": "Prs"}),
    ("մեր", "pron"): ("DET", {"Person": "1", "Poss": "Yes", "PronType": "Prs"}),
    ("քո", "pron"): ("DET", {"Person": "2", "Poss": "Yes", "PronType": "Prs"}),
    ("ձեր", "pron"): ("DET", {"Person": "2", "Poss": "Yes", "PronType": "Prs"}),
    ("իւր", "pron"): ("PRON", {"Person": "3", "PronType": "Prs", "Reflex": "Yes"}),
    ("ինքն", "pron"): ("PRON", {"PronType": "Prs", "Reflex": "Yes"}),

    ("սա", "pron"): ("DET", {"Deixis": "Prox", "PronType": "Dem"}),
    ("այս", "pron"): ("DET", {"Deixis": "Prox", "PronType": "Dem"}),
    ("սոյն", "pron"): ("DET", {"Deixis": "Prox", "PronType": "Dem"}),
    ("դոյն", "pron"): ("DET", {"Deixis": "Med", "PronType": "Dem"}),
    ("այդ", "pron"): ("DET", {"Deixis": "Med", "PronType": "Dem"}),
    ("դա", "pron"): ("DET", {"Deixis": "Med", "PronType": "Dem"}),
    ("նոյն", "pron"): ("DET", {"Deixis": "Remt", "PronType": "Dem"}),
    ("այն", "pron"): ("DET", {"Deixis": "Remt", "PronType": "Dem"}),
    ("նա", "pron"): ("DET", {"Deixis": "Remt", "PronType": "Dem"}),

    ("ինչ", "pron"): ("DET", {"PronType": "Ind", "Animacy": "Inan", "Definite": "Ind"}),
    ("իմն", "pron"): ("DET", {"PronType": "Ind", "Animacy": "Inan", "Definite": "Ind"}),
    ("ոմն", "pron"): ("DET", {"PronType": "Ind", "Animacy": "Anim", "Definite": "Spec"}),
    ("ոք", "pron"): ("DET", {"PronType": "Ind", "Animacy": "Anim", "Definite": "Ind"}),
    ("զինչ", "pron"): ("DET", {"PronType": "Int", "Animacy": "Inan"}),

    ("ես", "pron"): ("PRON", {"Person": "1", "PronType": "Prs"}),
    ("մեք", "pron"): ("PRON", {"Person": "1", "PronType": "Prs"}),
    ("դու", "pron"): ("PRON", {"Person": "2", "PronType": "Prs"}),
    ("դուք", "pron"): ("PRON", {"Person": "2", "PronType": "Prs"}),
    ("միմեանք", "pron"): ("PRON", {"PronType": "Rcp"}),
    ("իրեար", "pron"): ("PRON", {"PronType": "Rcp"}),
    ("ով", "pron"): ("PRON", {"PronType": "Int", "Animacy": "Anim"}),
    ("ոչինչ", "pron"): ("PRON", {"PronType": "Ind", "Animacy": "Inan", "Polarity": "Neg"}),
}

# Short features → UD FEATS
FEATS_CONV: Dict[str, str] = {
    "nom": "Case=Nom", "acc": "Case=Acc", "dat": "Case=Dat", "gen": "Case=Gen",
    "abl": "Case=Abl", "loc": "Case=Loc", "ins": "Case=Ins",
    "sg": "Number=Sing", "pl": "Number=Plur",
    "1per": "Person=1", "2per": "Person=2", "3per": "Person=3",
    "pass": "Voice=Pass",
    # finite verbs
    "pres": "VerbForm=Fin|Mood=Ind|Tense=Pres|Aspect=Imp",
    "aor":  "VerbForm=Fin|Mood=Ind|Tense=Past|Aspect=Perf",
    "past": "VerbForm=Fin|Mood=Ind|Tense=Past|Aspect=Imp",
    "sbjv": "VerbForm=Fin|Mood=Sub|Aspect=Perf",
    "imp":  "VerbForm=Fin|Mood=Imp|Aspect=Perf",   # positive imperative
    # participles / non-finite
    "pfv":  "VerbForm=Part|Tense=Past",
    "inf":  "VerbForm=Vnoun",  # note: your source uses 'inf' → verbal noun
    # special combined pattern handled via tokens set: imp + neg -> prohibitive
    # "imp+neg": "VerbForm=Fin|Mood=Imp|Aspect=Imp",  # computed dynamically
}


# ----------------------------- HELPERS ----------------------------------------

def clean_lemma(lemma: str) -> str:
    """Remove any parenthetical gloss in lemma."""
    return re.sub(r"\s*\(.*?\)", "", lemma or "").strip()


def split_pos(pos_field: str) -> List[str]:
    """
    POS field may contain '/', '.' or mixed segments:
    - normalize Armenian dot '․' → '.'
    - split by '/' keeping each chunk trimmed (do not explode internal dots)
    """
    if not pos_field:
        return []
    norm = pos_field.replace("․", ".")
    parts = [p.strip() for p in norm.split("/") if p.strip()]
    return parts


def split_feats_codes(feats_field: str) -> List[str]:
    """
    Scraped FEATS often like: 'nom.sg.3per', 'imp. + neg.', 'gen/sg', etc.
    Strategy:
      - normalize Armenian dot '․' → '.'
      - lower-case
      - replace sequences like '. + .' with '.+.' to ease detection
      - split on [./\\s+], keep tokens, drop empties
    Then we can detect 'imp' and 'neg' co-occurrence for prohibitive.
    """
    if not feats_field or feats_field == "_":
        return []
    s = feats_field.replace("․", ".").lower()
    s = re.sub(r"\.\s*\+\s*\.", ".+.", s)
    # split on dot, slash, plus, whitespace
    tokens = [t for t in re.split(r"[./+\s]+", s) if t]
    return tokens


def merge_feats(parts: List[str]) -> str:
    """
    Merge a list of FEATS strings like ["Case=Nom|Number=Sing","Person=3"].
    De-duplicate keys, keep first value (left-biased), then sort by key.
    """
    if not parts:
        return "_"
    kv: Dict[str, str] = {}
    for chunk in parts:
        if not chunk or chunk == "_":
            continue
        for item in chunk.split("|"):
            if not item or "=" not in item:
                continue
            k, v = item.split("=", 1)
            kv.setdefault(k, v)
    if not kv:
        return "_"
    return "|".join(f"{k}={kv[k]}" for k in sorted(kv.keys(), key=str.lower))


def convert_pos(pos: str, lemma: str) -> Tuple[str, Dict[str, str]]:
    """
    Return (UPOS, extra_feats_dict) for a single pos segment.
    Resolution order:
      1) lemma+pos complex overrides
      2) lemma-only simple overrides (if pos agrees with expectation)
      3) complex pos rules
      4) simple pos
    """
    lemma = clean_lemma(lemma)
    if (lemma, pos) in LEMMA_POS_COMPLEX:
        return LEMMA_POS_COMPLEX[(lemma, pos)]
    if lemma in LEMMA_POS_SIMPLE:
        # accept this override if caller provided the same source POS tag (loosely)
        # or simply apply as a hard override (common in scraped data)
        return LEMMA_POS_SIMPLE[lemma], {}
    if pos in POS_COMPLEX:
        return POS_COMPLEX[pos]
    return SIMPLE_POS.get(pos, pos), {}


def convert_feats_codes(tokens: List[str]) -> str:
    """
    Convert a list of short codes into UD FEATS.
    Special: if both 'imp' and 'neg' present → prohibitive mapping:
             VerbForm=Fin|Mood=Imp|Aspect=Imp
    """
    tset = set(tokens)
    chunks: List[str] = []

    # special combined pattern
    if "imp" in tset and "neg" in tset:
        chunks.append("VerbForm=Fin|Mood=Imp|Aspect=Imp")
        tset.discard("imp")
        tset.discard("neg")

    # remaining singletons
    for code in tokens:
        if code in tset and code in FEATS_CONV:
            chunks.append(FEATS_CONV[code])
            tset.discard(code)

    return merge_feats(chunks)


# ----------------------------- CORE -------------------------------------------

def process_line_cols(cols: List[str]) -> List[str]:
    """
    Process one token line (10 columns). Returns rewritten columns.
    """
    if len(cols) < 10:
        cols = cols + ["_"] * (10 - len(cols))

    lemma = clean_lemma(cols[2])
    pos_field = cols[3]
    feats_field = cols[5]

    # POS conversion (support multi/compound segments separated by '/')
    pos_parts = split_pos(pos_field)
    upos_parts: List[str] = []
    added_feats: List[str] = []

    if pos_parts:
        for p in pos_parts:
            upos, extras = convert_pos(p, lemma)
            upos_parts.append(upos)
            if extras:
                added_feats.append("|".join(f"{k}={v}" for k, v in extras.items()))
        cols[3] = "/".join(upos_parts)
    else:
        # keep as-is if empty
        pass

    # FEATS conversion
    feat_codes = split_feats_codes(feats_field)
    converted = convert_feats_codes(feat_codes)
    merged = merge_feats(([converted] if converted != "_" else []) + added_feats)
    cols[5] = merged

    # restore cleaned lemma
    cols[2] = lemma if lemma else "_"

    return cols


def convert_file(in_path: str, out_path: str) -> None:
    with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip() or line.startswith("#"):
                fout.write(line)
                continue
            cols = line.rstrip("\n").split("\t")
            cols = (cols + ["_"] * (10 - len(cols)))[:10]
            new_cols = process_line_cols(cols)
            fout.write("\t".join(new_cols) + "\n")


# ----------------------------- CLI --------------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Convert scraped POS/FEATS to UD (UPOS+FEATS).")
    ap.add_argument("--in", dest="in_path", required=True, help="Input CoNLL-U file (from previous stage).")
    ap.add_argument("--out", dest="out_path", required=True, help="Output CoNLL-U file with converted POS/FEATS.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    convert_file(args.in_path, args.out_path)
    print(f"[ok] wrote: {args.out_path}")


if __name__ == "__main__":
    main()
