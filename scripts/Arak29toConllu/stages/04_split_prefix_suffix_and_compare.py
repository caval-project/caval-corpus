#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 04 — Split Armenian clitics/prefixes and demonstrative/possessive finals; renumber & remap heads.

What it does
------------
1) Prefix split (process_y_c_z):
   If FORM begins with one of 'յ', 'ց', 'զ' but LEMMA does not start with that char,
   insert a new token for the prefix (ADP, deprel=case, SpaceAfter=No) before the base
   word; strip the prefix from the base token's FORM.

2) Suffix split (process_poss_def):
   If FEATS contains any of {"poss1","poss2","def"} AND FORM ends with one of 'ս','դ','ն',
   split the last letter into a separate DET token:
      - new DET: FORM=LEMMA=that last letter, UPOS=DET,
        FEATS=Definite=Def|Deixis=Prox|PronType=Dem,
        HEAD = (original token's HEAD), DEPREL=det, MISC=SpaceAfter=No
      - base token: FORM without the final letter
   (This preserves your original semantics.)

3) Renumber tokens from 1..N AND remap numeric HEADs consistently:
   - We build an old_id → new_id mapping from the original atomic tokens.
   - All numeric HEADs are remapped through that mapping.
   - Roots "0" and "_" remain unchanged.

4) Comparison helper:
   - Normalize text (lowercase + strip punctuation) and compare sentence texts between two files.
   - Report sentences from the processed file that fail to find a textual match in the reference file.
   - Warn if token counts differ for matched pairs.

Usage
-----
python Arak29toConllu/stages/04_split_prefix_suffix_and_compare.py \
  --in  data/arak29/slashless_scraped_file.conllu \
  --out data/arak29/processed_file.conllu \
  --compare-with data/arak29/exclamation_fixed.conllu
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import List, Tuple, Iterable, Dict, Optional


# ----------------------------- CoNLL-U helpers --------------------------------

@dataclass
class Token:
    cols: List[str]         # 10 columns
    orig_id: Optional[int]  # original numeric ID (if any), used for head remap

    @property
    def id(self) -> str:
        return self.cols[0]

    @id.setter
    def id(self, v: str) -> None:
        self.cols[0] = v

    @property
    def form(self) -> str:
        return self.cols[1]

    @form.setter
    def form(self, v: str) -> None:
        self.cols[1] = v

    @property
    def lemma(self) -> str:
        return self.cols[2]

    @lemma.setter
    def lemma(self, v: str) -> None:
        self.cols[2] = v

    @property
    def upos(self) -> str:
        return self.cols[3]

    @upos.setter
    def upos(self, v: str) -> None:
        self.cols[3] = v

    @property
    def feats(self) -> str:
        return self.cols[5]

    @feats.setter
    def feats(self, v: str) -> None:
        self.cols[5] = v

    @property
    def head(self) -> str:
        return self.cols[6]

    @head.setter
    def head(self, v: str) -> None:
        self.cols[6] = v

    @property
    def deprel(self) -> str:
        return self.cols[7]

    @deprel.setter
    def deprel(self, v: str) -> None:
        self.cols[7] = v

    @property
    def misc(self) -> str:
        return self.cols[9]

    @misc.setter
    def misc(self, v: str) -> None:
        self.cols[9] = v

    def to_line(self) -> str:
        return "\t".join(self.cols)


@dataclass
class Sentence:
    meta: List[str]   # lines starting with '#'
    toks: List[Token] # token lines (10 columns)


def parse_conllu(path: str) -> List[Sentence]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return []
    blocks = raw.split("\n\n")
    sents: List[Sentence] = []
    for b in blocks:
        lines = [ln for ln in b.splitlines()]
        meta = [ln for ln in lines if ln.startswith("#")]
        tok_lines = [ln for ln in lines if ln and not ln.startswith("#")]
        toks: List[Token] = []
        for ln in tok_lines:
            cols = ln.split("\t")
            if len(cols) != 10:
                # keep malformed lines as-is but with no ID remap
                toks.append(Token(cols=cols + ["_"] * (10 - len(cols)), orig_id=None))
                continue
            tid = cols[0]
            orig_id = int(tid) if tid.isdigit() else None
            toks.append(Token(cols=cols, orig_id=orig_id))
        sents.append(Sentence(meta=meta, toks=toks))
    return sents


def write_conllu(sents: Iterable[Sentence], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        first = True
        for s in sents:
            if not first:
                f.write("\n")
            first = False
            for m in s.meta:
                f.write(m + "\n")
            for t in s.toks:
                f.write(t.to_line() + "\n")


# ----------------------------- Text normalization -----------------------------

PUNCT_STRIP = re.compile(r"[^\w\s]", re.UNICODE)
SPACE_RE = re.compile(r"\s+")

def normalize_text(s: str) -> str:
    return SPACE_RE.sub(" ", PUNCT_STRIP.sub("", s.lower())).strip()


def extract_sentences(path: str) -> List[Tuple[str, str, str, str]]:
    """Return list of (sent_id, #text, normalized_text, whole_sentence_block)."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return []
    blocks = raw.split("\n\n")
    out = []
    for b in blocks:
        sent_id = None
        text = None
        for ln in b.splitlines():
            if ln.startswith("# sent_id"):
                sent_id = ln.split("=", 1)[1].strip()
            elif ln.startswith("# text"):
                text = ln.split("=", 1)[1].strip()
        if sent_id and text is not None:
            out.append((sent_id, text, normalize_text(text), b))
    return out


# ----------------------------- Transformations --------------------------------

PREFIX_CHARS = ("յ", "ց", "զ")
SUFFIX_CHARS = ("ս", "դ", "ն")  # demonstrative/possessive finals

def process_y_c_z(tokens: List[Token]) -> List[Token]:
    """
    If FORM starts with one of PREFIX_CHARS and LEMMA does not, split the prefix:
      - Insert new ADP token: FORM=LEMMA=prefix, UPOS=ADP, DEPREL=case, HEAD='_', MISC=SpaceAfter=No
      - Update base token: strip prefix from FORM
    """
    out: List[Token] = []
    for tk in tokens:
        if len(tk.cols) != 10:
            out.append(tk)
            continue

        form = tk.form
        lemma = tk.lemma
        if form and form[0] in PREFIX_CHARS and (not lemma or lemma[0] != form[0]):
            prefix = form[0]
            base_form = form[1:] if len(form) > 1 else ""
            # 1) prefix token (new)
            pref_cols = [
                "_",            # id to be filled later
                prefix,         # form
                prefix,         # lemma
                "ADP",          # upos
                "_",            # xpos
                "_",            # feats
                "_",            # head (unknown here; will be attached by later stages)
                "case",         # deprel
                "_",            # deps
                "SpaceAfter=No" # misc
            ]
            out.append(Token(cols=pref_cols, orig_id=None))
            # 2) base token (update form)
            base = Token(cols=tk.cols.copy(), orig_id=tk.orig_id)
            base.form = base_form if base_form else "_"
            out.append(base)
        else:
            out.append(tk)
    return out


def process_poss_def(tokens: List[Token]) -> List[Token]:
    """
    If FEATS contains 'poss1' or 'poss2' or 'def' AND FORM ends with one of SUFFIX_CHARS:
      - Base token: strip final letter
      - New DET token after base:
          FORM=LEMMA=that letter
          UPOS=DET
          FEATS=Definite=Def|Deixis=Prox|PronType=Dem
          HEAD = base's original HEAD (remapped after renumbering)
          DEPREL=det
          MISC=SpaceAfter=No
    """
    out: List[Token] = []
    for tk in tokens:
        if len(tk.cols) != 10:
            out.append(tk)
            continue

        feats = tk.feats or "_"
        form = tk.form or "_"
        if any(x in feats for x in ("poss1", "poss2", "def")) and form != "_" and form[-1] in SUFFIX_CHARS:
            base_form = form[:-1] if len(form) > 1 else "_"
            suffix = form[-1]

            # base (update form)
            base = Token(cols=tk.cols.copy(), orig_id=tk.orig_id)
            base.form = base_form
            out.append(base)

            # suffix DET (use the *original* head now; will be remapped later)
            det_cols = [
                "_",                      # id (later)
                suffix,                   # form
                suffix,                   # lemma
                "DET",                    # upos
                "_",                      # xpos
                "Definite=Def|Deixis=Prox|PronType=Dem",  # feats
                tk.head,                  # head (string; remapped later if numeric)
                "det",                    # deprel
                tk.cols[8],               # deps
                "SpaceAfter=No"           # misc
            ]
            out.append(Token(cols=det_cols, orig_id=None))
        else:
            out.append(tk)

    return out


def renumber_and_remap_heads(tokens: List[Token]) -> List[Token]:
    """
    Assign new IDs 1..N to all atomic tokens (no MWT handling here) and
    remap numeric HEADs via an old_id → new_id mapping, built from the
    original tokens (where `orig_id` was captured).
    """
    # 1) determine new IDs and mapping for original tokens
    new_tokens: List[Token] = []
    old_to_new: Dict[int, int] = {}
    new_id = 1

    for tk in tokens:
        tko = Token(cols=tk.cols.copy(), orig_id=tk.orig_id)
        tko.id = str(new_id)
        if tk.orig_id is not None:
            old_to_new[tk.orig_id] = new_id
        new_tokens.append(tko)
        new_id += 1

    # 2) remap heads
    for t in new_tokens:
        h = t.head
        if h.isdigit():
            old = int(h)
            if old in old_to_new:
                t.head = str(old_to_new[old])
        # keep '0' and '_' as is

    return new_tokens


def process_sentence(sent: Sentence) -> Sentence:
    toks = process_y_c_z(sent.toks)
    toks = process_poss_def(toks)
    toks = renumber_and_remap_heads(toks)
    return Sentence(meta=sent.meta, toks=toks)


# ----------------------------- Comparison helper ------------------------------

def compare_files(scraped_file: str, parsed_file: str) -> None:
    scraped = extract_sentences(scraped_file)
    parsed = extract_sentences(parsed_file)

    parsed_by_norm = {p[2]: p for p in parsed}  # normalized_text -> tuple

    unmatched_scraped: List[str] = []
    mismatched_counts: List[Tuple[str, int, int]] = []

    for sent_id, text, norm, block in scraped:
        match = parsed_by_norm.get(norm)
        if not match:
            unmatched_scraped.append(sent_id)
            continue

        # Compare token counts (rough check)
        scraped_tok_lines = [ln for ln in block.splitlines() if ln and not ln.startswith("#")]
        parsed_tok_lines = [ln for ln in match[3].splitlines() if ln and not ln.startswith("#")]
        if len(scraped_tok_lines) != len(parsed_tok_lines):
            mismatched_counts.append((sent_id, len(scraped_tok_lines), len(parsed_tok_lines)))

    if mismatched_counts:
        print("[warn] Token number mismatches:")
        for sid, a, b in mismatched_counts:
            print(f"  - {sid}: scraped={a} vs parsed={b}")

    if unmatched_scraped:
        print("[warn] No textual match for these sent_id values from the processed file:")
        for sid in unmatched_scraped:
            print(f"  - {sid}")
    else:
        print("[ok] All processed sentences found textual matches in the reference file.")


# --------------------------------- CLI ----------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Split Armenian prefixes (յ/ց/զ) and demonstrative/possessive finals (ս/դ/ն); renumber & remap heads. Optionally compare to a reference file.")
    ap.add_argument("--in", dest="in_path", required=True, help="Input CoNLL-U file (scraped/cleaned).")
    ap.add_argument("--out", dest="out_path", required=True, help="Output CoNLL-U file (processed).")
    ap.add_argument("--compare-with", dest="compare_path", default=None, help="Optional reference CoNLL-U to compare texts/token counts against.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    sents = parse_conllu(args.in_path)
    out_sents = [process_sentence(s) for s in sents]
    write_conllu(out_sents, args.out_path)
    print(f"[ok] wrote: {args.out_path} (sentences: {len(out_sents)})")

    if args.compare_path:
        compare_files(args.out_path, args.compare_path)


if __name__ == "__main__":
    main()
