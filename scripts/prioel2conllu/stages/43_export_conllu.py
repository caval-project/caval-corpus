#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 43 — Export PRIOEL tokens to CoNLL-U with transliteration.

Behavior
  • Per sentence:
      - Build sent_id from the first and last token's `citation-part`.
      - Skip tokens that have `empty-token-sort` (empty nodes).
      - For each token, write CoNLL-U 10 columns (tab-separated):
            ID, FORM, LEMMA, UPOS, XPOS, FEATS, HEAD, DEPREL, DEPS, MISC
      - FEATS are alphabetically sorted (case-insensitive).
      - FORM/LEMMA are transliterated (longest-match-first) + punctuation mapping:
            replace '.' ↔ ':' using a TEMP swap, exactly like your original logic.
      - MISC contains:
            Translit=<original form>
            LTranslit=<original lemma (w/o #n)>
            LId=<lemma>-<n> (when lemma like foo#2)
            |#<n>  (literal tag as in original code)

CLI
  python scripts/prioel2conllu/stages/43_export_conllu.py \
      --in input.txt --out output.conllu [--verbose]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------- Transliteration ----------------

TRANSLIT_RULES: Dict[str, str] = {
    'A':'Ա','B':'Բ','G':'Գ','D':'Դ','E':'Ե','Z':'Զ','Ē':'Է','Ə':'Ը','Tʻ':'Թ','Ž':'Ժ','I':'Ի','L':'Լ','X':'Խ',
    'Cʻ':'Ց','C':'Ծ','Kʻ':'Ք','K':'Կ','H':'Հ','J':'Ձ','Ł':'Ղ','Čʻ':'Չ','Č':'Ճ','M':'Մ','Y':'Յ','N':'Ն','Š':'Շ',
    'O':'Ո','Pʻ':'Փ','P':'Պ','J̌':'Ջ','Ṙ':'Ռ','S':'Ս','V':'Վ','T':'Տ','R':'Ր','W':'Ւ','F':'Ֆ',
    'a':'ա','b':'բ','g':'գ','d':'դ','e':'ե','z':'զ','ē':'է','ə':'ը','tʻ':'թ','ž':'ժ','i':'ի','l':'լ','x':'խ',
    'cʻ':'ց','c':'ծ','kʻ':'ք','k':'կ','h':'հ','j':'ձ','ł':'ղ','čʻ':'չ','č':'ճ','m':'մ','y':'յ','n':'ն','š':'շ',
    'o':'ո','pʻ':'փ','p':'պ','ǰ':'ջ','ṙ':'ռ','s':'ս','v':'վ','t':'տ','r':'ր','w':'ւ','f':'ֆ',';':'՝','?':'՞',
}

# Longest-key-first for safe replacement
_TRANSLIT_KEYS = sorted(TRANSLIT_RULES.keys(), key=len, reverse=True)

def transliterate_word(word: str) -> str:
    out = word
    for k in _TRANSLIT_KEYS:
        out = out.replace(k, TRANSLIT_RULES[k])
    return out

def swap_punct(s: str) -> str:
    """Swap '.' ↔ ':' via a TEMP placeholder (preserving multiple occurrences)."""
    return s.replace(".", "TEMP").replace(":", ".").replace("TEMP", ":")

# ---------------- Helpers ----------------

ATTR_RE       = re.compile(r'([-\w]+)="(.*?)"')
TOKEN_OPEN_RE = re.compile(r'<token\b')
SENT_OPEN_RE  = re.compile(r'<sentence\b')
SENT_CLOSE_RE = re.compile(r'</sentence\b')

def sort_feats(feat: str) -> str:
    if not feat or feat == "_":
        return "_"
    feats = [f for f in feat.split("|") if f]
    if not feats:
        return "_"
    feats.sort(key=lambda x: x.lower())
    return "|".join(feats)

def parse_token_attrs(line: str) -> Dict[str, str]:
    return dict(ATTR_RE.findall(line))

def safe_get(d: Dict[str, str], key: str, default: str = "_") -> str:
    return d.get(key, default) or default

def build_sent_id(first: str, last: str) -> Optional[str]:
    """
    first, last are citation-part strings like "Book 1.2"
    Rules (compatible with your original):
      - if same book and chapter:
            one verse    -> Book_Chapter.Verse
            range verses -> Book_Chapter.V1-V2
      - else: "first - last"
    Returns a string without spaces around underscores/dots.
    """
    try:
        fb, fcv = first.rsplit(" ", 1)
        lb, lcv = last.rsplit(" ", 1)
        fc, fv = fcv.split(".")
        lc, lv = lcv.split(".")
    except Exception:
        # Fallback: return the first citation-part as-is (sanitized)
        return first.replace(" ", "_") if first else None

    if fb == lb:
        if fc == lc:
            if fv == lv:
                return f"{fb}_{fc}.{fv}"
            return f"{fb}_{fc}.{fv}-{lv}"
        # different chapters same book -> span as text
        return f"{first} - {last}"
    # different books -> span as text
    return f"{first} - {last}"

def emit_conllu_token(attrs: Dict[str, str]) -> str:
    """
    Map PRIOEL token attrs to CoNLL-U columns.
    """
    tid    = safe_get(attrs, "id")
    form   = safe_get(attrs, "form")
    lemma  = safe_get(attrs, "lemma")
    upos   = safe_get(attrs, "part-of-speech")
    xpos   = "_"   # not provided
    feats  = sort_feats(safe_get(attrs, "FEAT"))
    head   = safe_get(attrs, "head-id")
    deprel = safe_get(attrs, "relation")
    deps   = safe_get(attrs, "rel")  # your code places "rel" in column 9

    # Transliteration + punctuation mapping (preserving your exact behavior)
    form_tr  = swap_punct(transliterate_word(form))  if form  != "_" else "_"
    lemma_raw, lemma_id = (lemma.split("#", 1) + [None])[:2] if "#" in lemma else (lemma, None)
    lemma_tr = swap_punct(transliterate_word(lemma_raw)) if lemma_raw != "_" else "_"

    # MISC
    misc_items: List[str] = []
    if form != "_":
        misc_items.append(f"Translit={form}")
    if lemma_raw != "_":
        misc_items.append(f"LTranslit={lemma_raw}")
    if lemma_id is not None:
        misc_items.append(f"LId={lemma_raw}-{lemma_id}")
        misc_items.append(f"#{lemma_id}")  # keep your literal marker

    misc = "|".join(misc_items) if misc_items else "_"

    # CoNLL-U requires str, tab-separated
    cols = [tid, form_tr, lemma_tr, upos, xpos, feats, head, deprel, deps, misc]
    return "\t".join(cols)

# ---------------- Core processing ----------------

def process_file(inp: Path, outp: Path, verbose: bool = False) -> None:
    text = inp.read_text(encoding="utf-8")
    # Split sentences while keeping the closing tag sentinel
    parts = re.split(r'(?<=)</sentence>\s*', text)  # keep delimiters
    out_lines: List[str] = []

    for block in parts:
        if not block.strip():
            continue

        lines = block.splitlines()
        sentence_tokens: List[Dict[str, str]] = []
        first_cit: Optional[str] = None
        last_cit:  Optional[str] = None

        for ln in lines:
            if TOKEN_OPEN_RE.search(ln):
                attrs = parse_token_attrs(ln)
                # skip empties
                if "empty-token-sort" in attrs:
                    continue
                sentence_tokens.append(attrs)
                cit = attrs.get("citation-part")
                if cit:
                    if first_cit is None:
                        first_cit = cit
                    last_cit = cit

            elif SENT_OPEN_RE.search(ln):
                # Print sentence open as a comment? In CoNLL-U we just use sent_id line later.
                # No direct emission here.
                pass

            elif SENT_CLOSE_RE.search(ln):
                # Emit sentence now
                if sentence_tokens:
                    sent_id = build_sent_id(first_cit or "", last_cit or "")
                    if sent_id:
                        out_lines.append(f"# sent_id = {sent_id}")
                    # Optionally include raw citation span for clarity:
                    if first_cit and last_cit and (first_cit != last_cit):
                        out_lines.append(f"# cite = {first_cit} – {last_cit}")
                    elif first_cit:
                        out_lines.append(f"# cite = {first_cit}")

                    for tok in sentence_tokens:
                        out_lines.append(emit_conllu_token(tok))

                    out_lines.append("")  # blank line separating sentences

                sentence_tokens = []
                first_cit = last_cit = None

            else:
                # Non-token line: ignore for CoNLL-U
                pass

    outp.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")
    if verbose:
        print(f"[export] wrote {outp}")

# ---------------- CLI ----------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 43: export PRIOEL tokens to CoNLL-U with transliteration.")
    ap.add_argument("--in", dest="inp", required=True, type=Path, help="Input PRIOEL-like XML-ish tokens file")
    ap.add_argument("--out", dest="out", required=True, type=Path, help="Output CoNLL-U file")
    ap.add_argument("--verbose", action="store_true", help="Print basic progress")
    args = ap.parse_args()
    process_file(args.inp, args.out, verbose=args.verbose)

if __name__ == "__main__":
    main()
