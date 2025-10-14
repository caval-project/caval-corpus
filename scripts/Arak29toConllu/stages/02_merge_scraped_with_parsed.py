#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 02 — Merge scraped CoNLL-U blocks with parser output, preserving MWTs.

What it does
------------
- Reads two CoNLL-U-ish files:
  1) "scraped" file produced by stage 00 (has '# text' + token lines)
  2) "parsed" file produced by an external parser (may split some long sentences)
- Normalizes '# text' strings for robust matching (lowercasing + punctuation cleanup).
- For each parsed sentence, tries to find a scraped sentence whose normalized text
  starts with the parsed one; if needed, merges consecutive parsed sentences until
  the combined normalized text equals the scraped sentence's normalized text.
- Renumbers tokens while preserving multi-word token (MWT) ranges and updates heads.
- Emits the merged (or untouched) sentences with updated '# text' and token IDs.

Notes
-----
- This stage does **not** change dependency relations, lemmas, or features.
- It preserves all comment lines for the first sentence in a merge group and
  updates only '# text = ...' to the concatenated surface string.
- MWT lines (e.g., "2-3") are kept and rewritten with new numeric ranges.
- Heads '0' (root) and '_' are left untouched. Numeric heads are remapped.

Gotchas you can tune with flags
-------------------------------
- Backticks / guillemets / punctuation spacing sometimes differ between sources.
  Use `--canon-guillemet-spacing` and `--backtick` to harmonize before matching.

Usage
-----
python Arak29toConllu/stages/02_merge_scraped_with_parsed.py \
  --scraped data/output/arak29/02Agat3.clean.txt \
  --parsed  data/parsed/Ag_sentences3.conllu \
  --out     data/output/arak29/02Agat3.merged.conllu \
  --canon-guillemet-spacing \
  --backtick \`

"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple


# -------- Normalization helpers ------------------------------------------------

_WORDISH = re.compile(r"\w+", re.UNICODE)
SPACE_RE = re.compile(r"\s+")
PUNCT_STRIP_RE = re.compile(r"[^\w\s]", re.UNICODE)

def normalize_text(s: str, *, backtick: str | None = None,
                   canon_guillemet_spacing: bool = False) -> str:
    """
    Lowercase, canonicalize a few punctuation conventions, then strip punctuation.
    This aims to make sentence text comparable between sources.
    """
    s = s.strip()

    # Optional: standardize « » spacing (space outside, no space inside)
    if canon_guillemet_spacing:
        # remove spaces just inside « and »
        s = re.sub(r"«\s*", "«", s)
        s = re.sub(r"\s*»", "»", s)
        # ensure a space before « and after »
        s = re.sub(r"(?<!\s)«", " «", s)
        s = re.sub(r"»(?!\s)", "» ", s)

    # Optional: enforce a given backtick char
    if backtick is not None:
        s = s.replace("`", backtick)

    # Lowercase + strip punctuation (keeps letters/digits/underscore and spaces)
    s = s.lower()
    s = PUNCT_STRIP_RE.sub("", s)
    s = SPACE_RE.sub(" ", s).strip()
    return s


# -------- CoNLL-U containers ---------------------------------------------------

@dataclass
class ConlluSentence:
    meta: List[str]      # comment lines beginning with '#'
    tokens: List[str]    # token & multiword token lines (tab-separated)

def read_conllu_sentences(path: str) -> List[ConlluSentence]:
    """Split file by blank lines into sentences; keep comments and token lines."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    blocks = raw.split("\n\n") if raw else []
    sents: List[ConlluSentence] = []
    for blk in blocks:
        lines = [ln for ln in blk.splitlines() if ln.strip() != ""]
        meta = [ln for ln in lines if ln.startswith("#")]
        toks = [ln for ln in lines if not ln.startswith("#")]
        sents.append(ConlluSentence(meta=meta, tokens=toks))
    return sents

def extract_meta(meta: List[str], key: str) -> str | None:
    """Return the value of a '# key = value' line if present."""
    prefix = f"# {key} ="
    for ln in meta:
        if ln.startswith(prefix):
            return ln.split("=", 1)[1].strip()
    return None


# -------- Renumbering (preserve MWTs) ------------------------------------------

def renumber_tokens_preserving_mwt(tokens: List[str]) -> List[str]:
    """
    Reassign token IDs from 1..N while preserving multi-word token (MWT) ranges
    and remapping numeric heads via an old→new ID map.

    - For an MWT line 'a-b', emits a new line 'i-j' and rewrites the next
      (b-a+1) atomic token lines to IDs i..j in order.
    - Do not alter head '0' or '_' values. Only digits are remapped.
    - Do not rewrite heads on MWT lines.
    """
    new_tokens: List[str] = []
    id_map: dict[int, int] = {}
    nxt = 1
    i = 0

    # First pass: rewrite IDs and build the map
    while i < len(tokens):
        cols = tokens[i].rstrip("\n").split("\t")
        tid = cols[0]

        if "-" in tid:
            # Multi-word token line
            a, b = map(int, tid.split("-"))
            span = b - a + 1
            new_mwt = f"{nxt}-{nxt + span - 1}"
            cols[0] = new_mwt
            new_tokens.append("\t".join(cols))

            # Rewrite following atomic tokens in this span
            j = 0
            i += 1
            while j < span and i < len(tokens):
                scols = tokens[i].rstrip("\n").split("\t")
                old_id = int(scols[0])
                new_id = nxt + j
                scols[0] = str(new_id)
                id_map[old_id] = new_id
                new_tokens.append("\t".join(scols))
                i += 1
                j += 1

            nxt += span
            continue

        # Atomic token line
        old_id = int(tid)
        id_map[old_id] = nxt
        cols[0] = str(nxt)
        new_tokens.append("\t".join(cols))
        nxt += 1
        i += 1

    # Second pass: remap heads (skip MWT lines)
    final_tokens: List[str] = []
    for ln in new_tokens:
        cols = ln.rstrip("\n").split("\t")
        tid = cols[0]
        if "-" in tid:
            final_tokens.append("\t".join(cols))
            continue
        if len(cols) < 7:
            # malformed; keep as is
            final_tokens.append("\t".join(cols))
            continue

        head = cols[6]
        if head.isdigit():
            old_head = int(head)
            if old_head in id_map:
                cols[6] = str(id_map[old_head])
        final_tokens.append("\t".join(cols))

    return [t + ("\n" if not t.endswith("\n") else "") for t in final_tokens]


# -------- Merge logic ----------------------------------------------------------

def merge_span(parsed: List[ConlluSentence], i: int, j: int) -> ConlluSentence:
    """
    Merge parsed[i..j] into one sentence:
      - metadata: take parsed[i].meta, but replace '# text =' with concatenated text
      - tokens: concatenation of tokens, then renumber with MWT preservation
    """
    base_meta = list(parsed[i].meta)
    text_parts: List[str] = []

    for k in range(i, j + 1):
        text_k = extract_meta(parsed[k].meta, "text") or ""
        if text_k:
            text_parts.append(text_k)

    # Update '# text ='
    full_text = " ".join(tp for tp in text_parts if tp).strip()
    new_meta = []
    replaced = False
    for ln in base_meta:
        if ln.startswith("# text ="):
            new_meta.append(f"# text = {full_text}")
            replaced = True
        else:
            new_meta.append(ln)
    if not replaced:
        new_meta.append(f"# text = {full_text}")

    merged_tokens = []
    for k in range(i, j + 1):
        merged_tokens.extend(parsed[k].tokens)

    merged_tokens = renumber_tokens_preserving_mwt(merged_tokens)
    return ConlluSentence(meta=new_meta, tokens=merged_tokens)

def find_and_merge(scraped: List[ConlluSentence],
                   parsed: List[ConlluSentence],
                   *,
                   backtick: str | None,
                   canon_guillemet_spacing: bool) -> List[ConlluSentence]:
    """
    For each parsed sentence, find a scraped sentence whose normalized text matches.
    If a scraped sentence begins with the parsed text, keep adding consecutive parsed
    sentences until the normalized concatenation equals the scraped one.
    """
    # Build a lookup from normalized scraped text to (index, original)
    scraped_norm = []
    for s in scraped:
        txt = extract_meta(s.meta, "text") or ""
        scraped_norm.append((normalize_text(txt, backtick=backtick,
                                            canon_guillemet_spacing=canon_guillemet_spacing), s))

    out: List[ConlluSentence] = []
    p = 0
    while p < len(parsed):
        p_txt = extract_meta(parsed[p].meta, "text") or ""
        p_norm = normalize_text(p_txt, backtick=backtick,
                                canon_guillemet_spacing=canon_guillemet_spacing)

        # Find a scraped sentence that starts with this parsed prefix
        target_idx = None
        target_norm = None
        for idx, (snorm, _) in enumerate(scraped_norm):
            if snorm.startswith(p_norm):
                target_idx = idx
                target_norm = snorm
                break

        if target_idx is None:
            # no match: output as-is, but renumber to be safe
            out.append(ConlluSentence(
                meta=parsed[p].meta,
                tokens=renumber_tokens_preserving_mwt(parsed[p].tokens)
            ))
            p += 1
            continue

        # Accumulate parsed sentences until they equal the scraped normalized text
        acc_norm = p_norm
        end = p
        while acc_norm != target_norm and end + 1 < len(parsed):
            end += 1
            nxt_txt = extract_meta(parsed[end].meta, "text") or ""
            acc_norm = normalize_text(
                (extract_meta(parsed[p].meta, "text") or "") + " " + " ".join(
                    (extract_meta(parsed[k].meta, "text") or "") for k in range(p + 1, end + 1)
                ),
                backtick=backtick,
                canon_guillemet_spacing=canon_guillemet_spacing
            )

        if acc_norm == target_norm and end > p:
            merged = merge_span(parsed, p, end)
            out.append(merged)
            p = end + 1
        else:
            # Could not extend to match; emit current one as-is
            out.append(ConlluSentence(
                meta=parsed[p].meta,
                tokens=renumber_tokens_preserving_mwt(parsed[p].tokens)
            ))
            p += 1

    return out


# -------- I/O ------------------------------------------------------------------

def write_conllu(sents: Iterable[ConlluSentence], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        first = True
        for s in sents:
            if not first:
                f.write("\n")
            first = False
            for ln in s.meta:
                f.write(ln.rstrip("\n") + "\n")
            for ln in s.tokens:
                f.write(ln if ln.endswith("\n") else ln + "\n")


# -------- CLI ------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Merge scraped CoNLL-U with parsed output; preserve MWTs and heads.")
    ap.add_argument("--scraped", required=True, help="Path to scraped file (from stage 00/01).")
    ap.add_argument("--parsed", required=True, help="Path to parsed file (parser output).")
    ap.add_argument("--out", required=True, help="Path to write merged file.")
    ap.add_argument("--backtick", default=None,
                    help="Canonical backtick character to enforce in normalization (e.g., '`').")
    ap.add_argument("--canon-guillemet-spacing", action="store_true",
                    help="Normalize spacing around « » before matching.")
    return ap.parse_args()

def main() -> None:
    args = parse_args()
    scraped = read_conllu_sentences(args.scraped)
    parsed = read_conllu_sentences(args.parsed)

    merged = find_and_merge(
        scraped, parsed,
        backtick=args.backtick,
        canon_guillemet_spacing=args.canon_guillemet_spacing
    )
    write_conllu(merged, args.out)
    print(f"[ok] wrote merged file: {args.out}  (scraped={len(scraped)} parsed={len(parsed)} merged={len(merged)})")

if __name__ == "__main__":
    main()
