#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
20_rule_based_feats_upos_refiner.py

Refines UPOS/FEATS in a CoNLL-U file for Classical Armenian using lexical rules,
neighbor context, and safe FEATS merging.

I/O (fixed by project convention):
- Read  : ./input
- Write : ./output
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple, Optional

INPUT_PATH  = "input"
OUTPUT_PATH = "output"

TAB = "\t"
BLKSEP = "\n\n"
REQUIRED_COLS = 10

# ---------- ID helpers ----------
_id_word_re   = re.compile(r"^\d+$")       # word IDs: 1,2,3...
_id_range_re  = re.compile(r"^\d+-\d+$")   # multi-word tokens: 1-2
_id_empty_re  = re.compile(r"^\d+\.\d+$")  # empty nodes: 3.1

def is_word_id(tok_id: str) -> bool:
    return bool(_id_word_re.match(tok_id or ""))

def is_range_id(tok_id: str) -> bool:
    return bool(_id_range_re.match(tok_id or ""))

def is_empty_id(tok_id: str) -> bool:
    return bool(_id_empty_re.match(tok_id or ""))

def _ensure(x: str) -> str:
    return x if (x and x.strip() != "") else "_"

# ---------- FEATS utilities ----------
def feats_to_dict(feats: str) -> Dict[str, List[str]]:
    feats = (feats or "").strip()
    if feats in ("", "_"):
        return {}
    out: Dict[str, List[str]] = {}
    for it in feats.split("|"):
        if "=" not in it:
            continue
        k, v = it.split("=", 1)
        out.setdefault(k, []).append(v)
    return out

def dict_to_feats(fd: Dict[str, List[str]]) -> str:
    if not fd:
        return "_"
    items: List[str] = []
    for k in sorted(fd.keys()):
        vals = sorted(set(fd[k]))
        for v in vals:
            items.append(f"{k}={v}")
    return "|".join(items) if items else "_"

def feats_merge(base: str,
                add: Dict[str, List[str]],
                replace_keys: Tuple[str, ...] = ()) -> str:
    cur = feats_to_dict(base)
    # explicit replace
    for rk in replace_keys:
        if rk in cur:
            del cur[rk]
    # merge/apply
    for k, vals in add.items():
        if k in replace_keys:
            cur[k] = list(vals)
        else:
            cur.setdefault(k, [])
            cur[k].extend(vals)
    return dict_to_feats(cur)

def feats_remove_keys(feats: str, keys: List[str]) -> str:
    cur = feats_to_dict(feats)
    for k in keys:
        if k in cur:
            del cur[k]
    return dict_to_feats(cur)

def feats_remove_regex(feats: str, pattern: str) -> str:
    # remove any key that matches pattern (e.g., r"^PronType$")
    cur = feats_to_dict(feats)
    rx = re.compile(pattern)
    for k in list(cur.keys()):
        if rx.match(k):
            del cur[k]
    return dict_to_feats(cur)

# ---------- File parsing ----------
def parse_conllu(path: str) -> List[List[str]]:
    """Return list of sentence blocks, each a list of lines (comments + tokens)."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().rstrip()
    if not text:
        return []
    return [blk.split("\n") for blk in text.split(BLKSEP) if blk.strip()]

def pad_cols(cols: List[str], n: int = REQUIRED_COLS) -> List[str]:
    return cols + [""] * (n - len(cols)) if len(cols) < n else cols[:n]

def next_prev_token_lemmas(lines: List[str], i: int) -> Tuple[Optional[str], Optional[str]]:
    """Return (next_lemma, prev_lemma) for word tokens (skip comments/multiword/empty)."""
    # previous
    prev_lemma = None
    j = i - 1
    while j >= 0:
        if "\t" in lines[j] and not lines[j].startswith("#"):
            c = pad_cols(lines[j].split(TAB))
            if is_word_id((c[0] or "").strip()):
                prev_lemma = c[2]
                break
        j -= 1
    # next
    next_lemma = None
    k = i + 1
    while k < len(lines):
        if "\t" in lines[k] and not lines[k].startswith("#"):
            c = pad_cols(lines[k].split(TAB))
            if is_word_id((c[0] or "").strip()):
                next_lemma = c[2]
                break
        k += 1
    return next_lemma, prev_lemma

# ---------- Core rule set ----------
# Simple UPOS corrections by lemma
LEMMA_TO_UPOS = {
    "վերայ": "ADP",
    "արդարեւ": "ADV",
    "ուրեմն": "ADV",
    "բայց": "CCONJ",
    "կամ": "CCONJ",
    "եւ": "CCONJ",
    "բազում": "DET",
    "յոլով": "DET",
    "միթէ": "SCONJ",
    "միթե": "SCONJ",
    "իսկ": "PART",
}

SPECIAL_INT_LEMMAS = {"իք","ոք","ինչ","ոմն","որ","ուր","յորժամ","որպէս",
                      "որչափ","ուստի","զիարդ","որքան","ընդէր","զինչ","ով","զի","երբ"}

# Voice helpers
NEG_END = ("իմ","իս","ի","իմք","իք","ին","իր","այց","ար")
POS_END = ("այ","ար","աւ","այք","ան")

def process_features(upos: str, feats: str, lemma: str, form: str,
                     token_id: str, sent_id: Optional[str],
                     next_token_lemma: Optional[str],
                     prev_token_lemma: Optional[str]) -> Tuple[str, str, bool, List[str], bool]:
    """
    Return (new_upos, new_feats, modified, change_logs, any_change_flag)
    """
    initial_feats = feats if feats != "_" else ""
    feats = initial_feats
    logs: List[str] = []

    # --- PronType=Int when next token is "՞" for certain lemmas ---
    if lemma in SPECIAL_INT_LEMMAS and upos in ("ADV","DET","PRON") and (next_token_lemma == "՞"):
        feats = feats_remove_keys(feats, ["PronType"])
        feats = feats_merge(feats, {"PronType": ["Int"]})
        logs.append(f"PronType=Int for lemma='{lemma}' (interrogative context)")
        # Short-circuit further changes as in your original intent:
        cleaned = normalize_feats_output(feats)
        return upos, cleaned, True, logs, True

    # --- Connegative=Yes in imperative with previous token 'մի' ---
    if "Mood=Imp" in feats and (prev_token_lemma == "մի"):
        feats = feats_remove_keys(feats, ["Connegative"])
        feats = feats_merge(feats, {"Connegative": ["Yes"]})
        logs.append("Connegative=Yes set due to prev lemma 'մի' and Mood=Imp")

    # --- UPOS direct corrections by lemma (keeping exceptions you encoded) ---
    if lemma in LEMMA_TO_UPOS:
        tgt = LEMMA_TO_UPOS[lemma]
        if lemma == "բայց" and upos in ("CCONJ","ADP","ADV","NOUN"):
            pass  # respect your exception list
        else:
            if upos != tgt:
                upos = tgt
                logs.append(f"UPOS → {tgt} for lemma='{lemma}'")

    # --- Remove/keep certain FEATS by context (condensed and de-duplicated) ---
    # Animacy
    if not (upos in ("DET","PRON") and lemma in {"ով","իք","ոք","ոմն","զինչ","ինչ","իմն"}):
        feats = feats_remove_keys(feats, ["Animacy"])
    # Add Animacy
    if re.match(r"^(ով|ոք|ոմն)$", lemma) and upos in ("PRON","DET"):
        feats = feats_merge(feats, {"Animacy": ["Anim"]})
        logs.append("Animacy=Anim added")
    if re.match(r"^(զինչ|իք|ինչ|իմն)$", lemma) and upos in ("PRON","DET"):
        feats = feats_merge(feats, {"Animacy": ["Inan"]})
        logs.append("Animacy=Inan added")

    # Aspect: only for AUX/VERB
    if upos not in ("AUX","VERB"):
        feats = feats_remove_keys(feats, ["Aspect"])

    # Definite
    if not (upos in ("ADP","ADV","DET","PRON") and lemma in {"զ","ս","դ","ն","ոք","ոմն","մի","ինչ","իմն","երբեմն","ուրեմն","երբեք","ուրեք","ուստեք"}):
        feats = feats_remove_keys(feats, ["Definite"])
    # Overwrite pre-annotated Definite for the listed lemmas
    if upos in ("ADP","ADV","DET","PRON") and lemma in {"զ","ս","դ","ն","իք","ոք","ոմն","մի","ինչ","իմն","երբեմն","ուրեմն","երբեք","ուրեք","ուստեք"}:
        feats = feats_remove_keys(feats, ["Definite"])
    # Add Definite=Def for articles/adpositions
    if re.match(r"^(զ|ն|դ|ս)$", lemma) and upos in ("ADP","DET"):
        feats = feats_merge(feats, {"Definite": ["Def"]})
        logs.append("Definite=Def added")
    # Add Definite=Ind
    if re.match(r"^(ոք|իք|ինչ|երբեք|ուրեք|ուստեք)$", lemma) and upos in ("ADV","DET","PRON"):
        feats = feats_merge(feats, {"Definite": ["Ind"]})
        logs.append("Definite=Ind added")
    # Add Definite=Spec
    if re.match(r"^(ոմն|իմն|մի|երբեմն|ուրեմն)$", lemma) and upos in ("ADV","PRON","DET"):
        feats = feats_merge(feats, {"Definite": ["Spec"]})
        logs.append("Definite=Spec added")

    # Deixis
    if upos in ("ADP","ADV","DET","INTJ","PRON"):
        feats = feats_remove_keys(feats, ["Deixis"])
    # Keep only for allowed combos then add variants
    if not (upos in ("ADP","ADV","DET","INTJ","PRON") and lemma in {
        "այս","այսպէս","այսր","այսուհետեւ","այնպիսի","այդպիսի","այսպիսի","ահաւասիկ","աստ","աստի","աւասիկ","ս","սա","սոյն",
        "այդ","դ","դա","աւադիկ","այդր","այդպէս","ահաւադիկ","այտի","դոյն","այն","ն","նա","անդ","անդէն","անդր","անդրէն","նոյն","նոյնպէս",
        "անտի","այնպէս","ահաւանիկ","աւանիկ","այնուհետեւ"}):
        feats = feats_remove_keys(feats, ["Deixis"])

    def add_deixis(rx: str, tag: str):
        nonlocal feats
        if re.match(rx, lemma) and upos in ("ADP","ADV","DET","INTJ","PRON"):
            feats = feats_merge(feats, {"Deixis": [tag]})
            logs.append(f"Deixis={tag} added")

    add_deixis(r"^(այս|այսպէս|այսր|այսպիսի|այսուհետեւ|ահաւասիկ|աստ|աստի|աւասիկ|ս|սա|սոյն)$", "Prox")
    add_deixis(r"^(այդ|դ|դա|աւադիկ|այդր|այդպիսի|այդպէս|ահաւադիկ|այտի|դոյն)$", "Med")
    add_deixis(r"^(այն|ն|նա|անդ|անդէն|անդր|անդրէն|նոյն|նոյնպէս|անտի|այնպէս|ահաւանիկ|աւանիկ|այնուհետեւ)$", "Remt")

    # Foreign=Yes for X
    if upos == "X":
        feats = feats_merge(feats, {"Foreign": ["Yes"]})
        logs.append("Foreign=Yes added")

    # Mood: keep only for AUX/VERB
    if upos not in ("AUX","VERB"):
        feats = feats_remove_keys(feats, ["Mood"])

    # PronType cleanup then specific adds
    if upos in ("ADP","ADV","DET","INTJ","PRON"):
        feats = feats_remove_regex(feats, r"^PronType$")

    # PronType=Art
    if not (upos == "DET" or lemma in {"ս","դ","ն"}):
        feats = feats_remove_regex(feats, r"^PronType$")
    if re.match(r"^(ս|դ|ն)$", lemma) and upos == "DET":
        feats = feats_merge(feats, {"PronType": ["Art"]})
        logs.append("PronType=Art added")

    # PronType=Dem
    allowed_dem_lemmas = {
        "այնպիսի","այդպիսի","այսպիսի","այս","այսպէս","այսր","այսուհետեւ","ահաւասիկ","աստ","աստի","աւասիկ","սա","սոյն",
        "այդ","դա","աւադիկ","այդր","այդպէս","ահաւադիկ","այտի","դոյն","այն","նա","անդ","անդէն","անդր","անդրէն","նոյն","նոյնպէս",
        "անտի","այնպէս","ահաւանիկ","աւանիկ","այնուհետեւ","այսքան","այդքան","այնքան"
    }
    if upos in ("ADP","ADV","DET","INTJ","PRON") and lemma in allowed_dem_lemmas:
        feats = feats_merge(feats, {"PronType": ["Dem"]})
        logs.append("PronType=Dem added")

    # PronType=Ind
    if upos in ("ADV","DET","PRON") and lemma in {"իք","ոք","ինչ","ոմն","ուր","ուստի","զիարդ","ընդէր","զինչ","ով","զի","երբ"}:
        feats = feats_merge(feats, {"PronType": ["Ind"]})
        logs.append("PronType=Ind added")

    # PronType=Prs
    if upos in ("DET","PRON") and lemma in {"ես","դու","մեք","դուք","ինքն","իմ","քո","մեր","ձեր","իւր"}:
        feats = feats_merge(feats, {"PronType": ["Prs"]})
        logs.append("PronType=Prs added")

    # PronType=Rcp
    if upos == "PRON" and lemma in {"միմեանք","իրեարք"}:
        feats = feats_merge(feats, {"PronType": ["Rcp"]})
        logs.append("PronType=Rcp added")

    # PronType=Rel
    if upos in ("ADV","DET","PRON") and lemma in {"որ","յորժամ","որպէս","որչափ","որքան"}:
        feats = feats_merge(feats, {"PronType": ["Rel"]})
        logs.append("PronType=Rel added")

    # PronType=Tot
    if upos in ("DET","PRON") and lemma in {"ամենայն","ամենեքեան","ամենեքին","բոլոր"}:
        feats = feats_merge(feats, {"PronType": ["Tot"]})
        logs.append("PronType=Tot added")

    # Global FEATS removal by UPOS compatibility
    if upos not in ("VERB","AUX"):
        feats = feats_remove_keys(feats, ["Tense","VerbForm"])
    if upos not in ("ADJ","ADV","NUM"):
        feats = feats_remove_keys(feats, ["NumType"])
    if upos not in ("INTJ","PART"):
        feats = feats_remove_keys(feats, ["Polarity"])
    if upos not in ("ADJ","AUX","DET","NOUN","NUM","PRON","PROPN","VERB"):
        feats = feats_remove_keys(feats, ["Case","Number"])
    if upos not in ("AUX","DET","PRON","VERB"):
        feats = feats_remove_keys(feats, ["Person"])
    if upos not in ("ADV","DET","INTJ","PRON"):
        feats = feats_remove_keys(feats, ["PronType"])

    # Person (lexical) — after we cleared Person for DET/PRON
    if upos in ("DET","PRON"):
        feats = feats_remove_regex(feats, r"^Person$")
        if re.match(r"^(ես|մեք|իմ|մեր)$", lemma):
            feats = feats_merge(feats, {"Person": ["1"]})
            logs.append("Person=1 added")
        if re.match(r"^(դու|դուք|քո|ձեր)$", lemma):
            feats = feats_merge(feats, {"Person": ["2"]})
            logs.append("Person=2 added")
        if re.match(r"^(ինքն|իւր)$", lemma):
            feats = feats_merge(feats, {"Person": ["3"]})
            logs.append("Person=3 added")

    # Polarity=Neg
    if upos in ("PART","PRON") and lemma in {"ոչ","մի","չիք"}:
        feats = feats_merge(feats, {"Polarity": ["Neg"]})
        logs.append("Polarity=Neg added")

    # Poss=Yes for DET with PronType=Prs
    if upos == "DET" and "PronType=Prs" in feats:
        feats = feats_merge(feats, {"Poss": ["Yes"]})
        logs.append("Poss=Yes added")

    # Reflex=Yes for (ինքն,իւր)
    if upos in ("DET","PRON") and lemma in {"ինքն","իւր"}:
        feats = feats_merge(feats, {"Reflex": ["Yes"]})
        logs.append("Reflex=Yes added")

    # Voice logic (only for AUX/VERB)
    voice_added = False
    if upos in ("VERB","AUX"):
        has_voice = "Voice=" in feats

        # CauPass with lemma ending -ուցանել
        if (not voice_added) and lemma.endswith("ուցանել") and "Mood=Imp" not in feats:
            # Without Past + negative-lookahead endings
            if ("Tense=Past" not in feats) and any(form.endswith(e) for e in NEG_END):
                feats = feats_merge(feats, {"Voice": ["CauPass"]})
                logs.append("Voice=CauPass (no Tense=Past, neg endings)")
                voice_added = True
            # With Past + positive-lookahead endings
            elif ("Tense=Past" in feats) and any(form.endswith(e) for e in POS_END):
                feats = feats_merge(feats, {"Voice": ["CauPass"]})
                logs.append("Voice=CauPass (Past, pos endings)")
                voice_added = True
            # With Mood=Imp + positive endings (rare path)
            elif ("Mood=Imp" in feats) and any(form.endswith(e) for e in POS_END):
                feats = feats_merge(feats, {"Voice": ["CauPass"]})
                logs.append("Voice=CauPass (Imp, pos endings)")
                voice_added = True

        # Voice=Cau fallback for -ուցանել (not certain lemmas)
        if (not voice_added) and lemma.endswith("ուցանել") and lemma not in {"ցուցանել","լուցանել"} and "Voice=Cau" not in feats and "Mood=Imp" not in feats:
            feats = feats_merge(feats, {"Voice": ["Cau"]})
            logs.append("Voice=Cau added")
            voice_added = True

        # Voice=Act
        if not voice_added:
            # no Past, finite, not Cau
            if ("Tense=Past" not in feats) and ("VerbForm=Fin" in feats) and ("Voice=Cau" not in feats) and ("Mood=Imp" not in feats):
                if any(form.endswith(suf) for suf in ("եմ","ես","է","եմք","էք","են","ից","եր")):
                    feats = feats_merge(feats, {"Voice": ["Act"]})
                    logs.append("Voice=Act added (no Past)")
                    voice_added = True
            # with Past, finite, not Cau
            if (not voice_added) and ("Tense=Past" in feats) and ("VerbForm=Fin" in feats) and ("Voice=Cau" not in feats) and ("Mood=Imp" not in feats):
                if any(form.endswith(suf) for suf in ("ի","եր","էք","ին")) and not any(form.endswith(s) for s in ("էի","էին","եի","եին","այի","ային","ուի","ուին")):
                    feats = feats_merge(feats, {"Voice": ["Act"]})
                    logs.append("Voice=Act added (Past)")
                    voice_added = True
            # specific packed conditions
            if (not voice_added) and all(k in feats for k in ("Tense=Past","Aspect=Perf","Person=3","Number=Sing")) and ("Mood=Imp" not in feats) and ("Voice=Cau" not in feats) and (not form.endswith("աւ")):
                feats = feats_merge(feats, {"Voice": ["Act"]})
                logs.append("Voice=Act added (Past+Perf 3SG)")
                voice_added = True

        # Voice=Pass
        if (not voice_added) and ("Voice=Pass" not in feats) and ("Mood=Imp" not in feats):
            # no Past
            if ("Tense=Past" not in feats) and ("VerbForm=Fin" in feats) and ("Voice=Cau" not in feats):
                if form.endswith(("իմ","իս","ի","իմք","իք","ին","իր","այց","արուք","այք")):
                    if not (form.endswith("ջիք") or form.endswith("ջիր")):
                        feats = feats_merge(feats, {"Voice": ["Pass"]})
                        logs.append("Voice=Pass added (no Past)")
                        voice_added = True
            # with Past
            if (not voice_added) and ("Tense=Past" in feats) and ("VerbForm=Fin" in feats) and ("Voice=Cau" not in feats):
                if form.endswith(("այ","ար","աւ","այք","ան")):
                    feats = feats_merge(feats, {"Voice": ["Pass"]})
                    logs.append("Voice=Pass added (Past)")
                    voice_added = True

    # Final tidy
    feats = normalize_feats_output(feats)

    modified = (upos != upos) or (feats != initial_feats)  # upos may have changed earlier; compare feats too
    any_change = bool(logs)
    return upos, feats, feats != initial_feats, logs, any_change

def normalize_feats_output(feats: str) -> str:
    if feats == "_":
        return "_"
    # De-dup + sort again to be safe
    d = feats_to_dict(feats)
    return dict_to_feats(d)

# ---------- Missing feature checks ----------
def warn_missing_case(upos: str, feats: str) -> bool:
    if upos in {"ADJ","DET","NOUN","NUM","PRON","PROPN"} and "Case=" not in feats:
        return True
    # If verb has VNOUN or PART, "or" (not both) should trigger — fix original bug
    if upos in {"VERB","AUX"} and (("VerbForm=Vnoun" in feats) or ("VerbForm=Part" in feats)) and "Case=" not in feats:
        return True
    return False

def warn_missing_verbform(upos: str, feats: str) -> bool:
    return upos in {"AUX","VERB"} and "VerbForm=" not in feats

# ---------- Sentence processing ----------
def process_sentence(lines: List[str]):
    sent_id = None
    out_lines: List[str] = []

    changes = []
    animacy_changes = []
    deixis_changes = []
    number_changes = []
    person_changes = []
    poss_changes = []
    reflex_changes = []
    voice_changes = []
    missing_case = []
    missing_verbform = []

    for i, ln in enumerate(lines):
        if ln.startswith("#"):
            if ln.startswith("# sent_id"):
                sent_id = ln.split("=", 1)[-1].strip()
            out_lines.append(ln)
            continue

        if "\t" not in ln:
            out_lines.append(ln)
            continue

        cols = pad_cols(ln.split(TAB))
        tok_id, form, lemma, upos, feats = cols[0], cols[1], cols[2], cols[3], cols[5]
        if not is_word_id(tok_id):
            # keep multi-word/empty nodes unchanged
            out_lines.append(TAB.join([_ensure(c) for c in cols[:REQUIRED_COLS]]))
            continue

        nxt_lemma, prv_lemma = next_prev_token_lemmas(lines, i)
        new_upos, new_feats, modified, logs, any_change = process_features(
            upos, feats, lemma, form, tok_id, sent_id, nxt_lemma, prv_lemma
        )

        cols[3] = new_upos
        cols[5] = new_feats

        # aggregate logs by categories (presence-based, as in your original)
        if modified:
            changes.append((sent_id, tok_id))
        if any_change and "Animacy=Anim" in new_feats or "Animacy=Inan" in new_feats:
            animacy_changes.append((sent_id, tok_id))
        if any_change and ("Deixis=Prox" in new_feats or "Deixis=Med" in new_feats or "Deixis=Remt" in new_feats):
            deixis_changes.append((sent_id, tok_id))
        if any_change and "Number=Sing" in new_feats:
            number_changes.append((sent_id, tok_id))
        if any_change and any(p in new_feats for p in ("Person=1","Person=2","Person=3")):
            person_changes.append((sent_id, tok_id))
        if any_change and "Poss=Yes" in new_feats:
            poss_changes.append((sent_id, tok_id))
        if any_change and "Reflex=Yes" in new_feats:
            reflex_changes.append((sent_id, tok_id))
        if any_change and "Voice=" in new_feats:
            voice_changes.append((sent_id, tok_id))

        if warn_missing_case(new_upos, new_feats):
            missing_case.append((sent_id, tok_id, new_upos))
        if warn_missing_verbform(new_upos, new_feats):
            missing_verbform.append((sent_id, tok_id, new_upos))

        out_lines.append(TAB.join([_ensure(c) for c in cols[:REQUIRED_COLS]]))

    return (out_lines, changes, animacy_changes, deixis_changes, number_changes,
            person_changes, poss_changes, reflex_changes, voice_changes,
            missing_case, missing_verbform)

# ---------- Driver ----------
def process_conllu_file(in_path: str, out_path: str) -> None:
    sentences = parse_conllu(in_path)

    all_changes = []
    all_animacy = []
    all_deixis = []
    all_number = []
    all_person = []
    all_poss = []
    all_reflex = []
    all_voice = []
    all_miss_case = []
    all_miss_vf = []

    with open(out_path, "w", encoding="utf-8") as w:
        for sent in sentences:
            (proc, changes, animacy, deixis, number, person, poss, reflex, voice,
             miss_case, miss_vf) = process_sentence(sent)

            all_changes.extend(changes)
            all_animacy.extend(animacy)
            all_deixis.extend(deixis)
            all_number.extend(number)
            all_person.extend(person)
            all_poss.extend(poss)
            all_reflex.extend(reflex)
            all_voice.extend(voice)
            all_miss_case.extend(miss_case)
            all_miss_vf.extend(miss_vf)

            w.write("\n".join(proc) + "\n\n")

    # ---- Console report ----
    def _print_block(title: str, seq: List[Tuple]):
        if seq:
            print(f"\n{title}")
            for it in seq:
                print(" - " + ", ".join(str(x) for x in it if x is not None))
        else:
            print(f"\nNo {title.lower()}")

    _print_block("Changes (any rules)", all_changes)
    _print_block("Animacy changes", all_animacy)
    _print_block("Deixis changes", all_deixis)
    _print_block("Number changes", all_number)
    _print_block("Person changes", all_person)
    _print_block("Possession changes", all_poss)
    _print_block("Reflexive changes", all_reflex)
    _print_block("Voice changes", all_voice)
    _print_block("Tokens missing 'Case'", all_miss_case)
    _print_block("Tokens missing 'VerbForm'", all_miss_vf)

if __name__ == "__main__":
    try:
        process_conllu_file(INPUT_PATH, OUTPUT_PATH)
        print(f"\nDone. Saved refined file to '{OUTPUT_PATH}'.")
    except FileNotFoundError as e:
        raise SystemExit(f"ERROR: {e}. Ensure an input file named 'input' exists.")
