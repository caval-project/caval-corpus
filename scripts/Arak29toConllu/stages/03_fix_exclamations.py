#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 03 — Normalize Armenian exclamation forms (՜) into MWTs and renumber IDs.

What this does (same logic as your script, made robust)
------------------------------------------------------
1) For any single token whose FORM contains '՜':
   - Create an MWT line whose FORM equals the original full token (e.g., «Աւա՜ղ).
   - Split into:
       * base token (original minus '՜', and minus leading « if present)
       * optionally a separate « punct token if the original started with «
       * an exclamation punct token '՜' attaching to the base
   - The resulting MWT spans 2 tokens (base + ՜) or 3 tokens (if « is split out).
2) For adjacent tokens of the shape:
      current:   <word w/o ՜>
      next:      starts with '՜'  (e.g., "՜ղ")
   - Build an MWT whose surface FORM is current+next (e.g., "Աւա՜ղ").
   - Split into base token (the current) and a punct token '՜' headed to the base.
   - (As in your original logic, any remainder after the leading '՜' in the
     second token is **not** emitted as a separate token; it remains only in the
     MWT surface form.)
3) Renumber the resulting sentence tokens to valid CoNLL-U IDs:
   - Preserve synthetic MWT spans with correct numeric ranges i..j.
   - Remap numeric HEAD IDs accordingly; root '0' and '_' remain unchanged.
   - Existing MWTs in the input are preserved and renumbered safely.

Input/Output
------------
- Input:  CoNLL-U-ish file (comments + token lines, tab-separated 10 columns).
- Output: Same format, with normalized exclamation handling and stable IDs.

Usage
-----
python Arak29toConllu/stages/03_fix_exclamations.py \
  --in  data/output/arak29/02Agat3.merged.conllu \
  --out data/output/arak29/02Agat3.exclam.conllu
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import List, Dict, Iterable, Tuple
import re


# ---------------------- CoNLL-U helpers ----------------------

@dataclass
class Token:
    id: str
    form: str
    lemma: str
    upos: str
    xpos: str
    feats: str
    head: str
    deprel: str
    deps: str
    misc: str
    # Internal, not written out:
    _mwt_span: int | None = None  # if this token is an MWT placeholder, how many subtokens follow?

    def to_line(self) -> str:
        return "\t".join([
            self.id, self.form, self.lemma, self.upos, self.xpos,
            self.feats, self.head, self.deprel, self.deps, self.misc
        ])

    @staticmethod
    def from_line(line: str) -> Token | None:
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 10:
            return None
        return Token(
            id=cols[0], form=cols[1], lemma=cols[2], upos=cols[3], xpos=cols[4],
            feats=cols[5], head=cols[6], deprel=cols[7], deps=cols[8], misc=cols[9]
        )


@dataclass
class Sentence:
    meta: List[str]
    tokens: List[Token]


def read_conllu(path: str) -> List[Sentence]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    blocks = [b for b in raw.split("\n\n") if b.strip()]
    sents: List[Sentence] = []
    for b in blocks:
        lines = [ln for ln in b.splitlines() if ln.strip()]
        meta = [ln for ln in lines if ln.startswith("#")]
        toks = [ln for ln in lines if not ln.startswith("#")]
        parsed: List[Token] = []
        for ln in toks:
            tk = Token.from_line(ln)
            if tk:
                parsed.append(tk)
        sents.append(Sentence(meta=meta, tokens=parsed))
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
            for t in s.tokens:
                f.write(t.to_line() + "\n")


# ---------------------- Core transformations ----------------------

EXCL = "՜"
LEFT_GUIL = "«"

def _make_mwt(form: str, span: int) -> Token:
    """
    Create an MWT placeholder token with a synthetic ID (filled later)
    and a private span marker telling how many atomic tokens follow.
    """
    return Token(
        id="MWT", form=form, lemma="_", upos="_", xpos="_",
        feats="_", head="_", deprel="_", deps="_", misc="_",
        _mwt_span=span
    )


def fix_exclamations(tokens: List[Token]) -> Tuple[List[Token], bool]:
    """
    Apply exclamation normalization on a single sentence.
    Returns (new_tokens, changed_flag).

    This preserves your original behavior, including:
      - Splitting a single token with '՜' into MWT + base + (optional «) + exclam punct.
      - Combining current + next(where next starts with '՜') into an MWT with base + exclam punct.
      - Not emitting any extra token for the remainder after '՜' (when present in the next token).
    """
    out: List[Token] = []
    i = 0
    changed = False

    while i < len(tokens):
        cur = tokens[i]
        form = cur.form

        # Case A: single token contains '՜'
        if EXCL in form:
            changed = True
            # Decide span: 2 (base + ՜) or 3 (if leading « is split out)
            has_left_guil = form.startswith(LEFT_GUIL) and len(form) > 1
            span = 3 if has_left_guil else 2

            # MWT with the *original* surface form
            out.append(_make_mwt(form=form, span=span))

            # Base token: remove leading « if present, then drop all '՜'
            base = Token(**vars(cur))  # copy
            base.id = "BASE"  # placeholder
            base_form = form[1:] if has_left_guil else form
            base_form = re.sub(EXCL + r"+", "", base_form)
            base.form = base_form
            out.append(base)

            # Optional separate « punctuation (headed to base)
            if has_left_guil:
                q = Token(
                    id="Q", form=LEFT_GUIL, lemma=LEFT_GUIL, upos="PUNCT", xpos="_",
                    feats="_", head="BASE", deprel="punct", deps="_", misc="_"
                )
                out.append(q)

            # Exclamation punctuation (head to base)
            y = Token(
                id="EXCL", form=EXCL, lemma=EXCL, upos="PUNCT", xpos="_",
                feats="_", head="BASE", deprel="punct", deps="_", misc="_"
            )
            out.append(y)

            i += 1
            continue

        # Case B: current + next (next starts with '՜...')
        if i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.form.startswith(EXCL):
                changed = True
                combined_form = cur.form + nxt.form  # e.g., "Աւա" + "՜ղ" => "Աւա՜ղ"

                # MWT over 2 subtokens (base + punct)
                out.append(_make_mwt(form=combined_form, span=2))

                base = Token(**vars(cur))
                base.id = "BASE"
                out.append(base)

                ex = Token(
                    id="EXCL", form=EXCL, lemma=EXCL, upos="PUNCT", xpos="_",
                    feats="_", head="BASE", deprel="punct", deps="_", misc="_"
                )
                out.append(ex)

                i += 2
                continue

        # Default: unchanged
        out.append(cur)
        i += 1

    return out, changed


def renumber_preserving_mwts(tokens: List[Token]) -> List[Token]:
    """
    Assign numeric IDs 1..N. For every MWT placeholder (Token._mwt_span),
    emit a numeric range i..j and renumber the following `_mwt_span` atomic
    tokens to those IDs. Also remap numeric HEADs using the old→new mapping.

    Existing MWTs with already numeric ranges (e.g., '2-3') are preserved by
    treating them like standard MWTs with span inferred from the range; the
    next (j-i+1) atomic tokens are renumbered to i..j.
    """
    result: List[Token] = []
    id_map: Dict[int, int] = {}
    next_id = 1
    i = 0

    def _append(tk: Token) -> None:
        result.append(tk)

    while i < len(tokens):
        tk = tokens[i]

        # Synthetic MWT created in this stage
        if tk._mwt_span is not None:
            span = tk._mwt_span
            start, end = next_id, next_id + span - 1
            tk_out = Token(**vars(tk))
            tk_out.id = f"{start}-{end}"
            _append(tk_out)

            # rewrite the next `span` atomic tokens
            for j in range(span):
                i += 1
                if i >= len(tokens):
                    break
                sub = Token(**vars(tokens[i]))
                old_id = sub.id
                new_id = start + j
                sub.id = str(new_id)
                # record mapping if old id was numeric
                if old_id.isdigit():
                    id_map[int(old_id)] = new_id
                # placeholder heads: BASE/Q/EXCL -> remap after we know BASE id
                # here we temporarily keep heads as is; a second pass fixes them
                _append(sub)
            next_id += span
            i += 1
            continue

        # Existing numeric MWT 'a-b'
        if "-" in tk.id and tk.id.replace("-", "").isdigit():
            a, b = map(int, tk.id.split("-"))
            span = b - a + 1
            start, end = next_id, next_id + span - 1
            tk_out = Token(**vars(tk))
            tk_out.id = f"{start}-{end}"
            _append(tk_out)

            # Renumber the following `span` tokens
            for j in range(span):
                i += 1
                if i >= len(tokens):
                    break
                sub = Token(**vars(tokens[i]))
                old_id = sub.id
                new_id = start + j
                sub.id = str(new_id)
                if old_id.isdigit():
                    id_map[int(old_id)] = new_id
                _append(sub)
            next_id += span
            i += 1
            continue

        # Regular atomic token
        tk_out = Token(**vars(tk))
        old_id = tk_out.id
        tk_out.id = str(next_id)
        if old_id.isdigit():
            id_map[int(old_id)] = next_id
        _append(tk_out)
        next_id += 1
        i += 1

    # Second pass: fix heads
    for tk in result:
        # skip MWT lines
        if "-" in tk.id:
            continue
        h = tk.head
        if h.isdigit():
            oh = int(h)
            if oh in id_map:
                tk.head = str(id_map[oh])
        elif h in {"BASE", "EXCL", "Q"}:
            # map placeholder heads to the *nearest* previous non-MWT token,
            # which will be the base we created within the same MWT block.
            # (By construction, BASE is always the first subtoken of that block.)
            # Scan backward to find the most recent token whose deprel/head we need:
            k = result.index(tk)
            # find the last MWT block start before k
            # and set head to that block's first atomic token id
            p = k - 1
            while p >= 0 and "-" in result[p].id:
                # step to the first atomic token after this MWT header
                # but since we just need the first token id of this block, find p+1
                p -= 1
            # find nearest preceding atomic
            q = k - 1
            while q >= 0 and "-" in result[q].id:
                q -= 1
            # fallback: set head to self (shouldn't happen)
            if q >= 0:
                tk.head = result[q].id

    return result


# ---------------------- Pipeline per sentence ----------------------

def process_sentence(sent: Sentence) -> Tuple[Sentence, bool]:
    new_tokens, changed = fix_exclamations(sent.tokens)
    renumbered = renumber_preserving_mwts(new_tokens)
    return Sentence(meta=sent.meta, tokens=renumbered), changed


def process_file(in_path: str, out_path: str) -> None:
    sents = read_conllu(in_path)
    out_sents: List[Sentence] = []
    modified: List[str] = []
    for s in sents:
        # fetch sent_id for reporting
        sid = next((m.split("=", 1)[1].strip() for m in s.meta if m.startswith("# sent_id")), None)
        updated, changed = process_sentence(s)
        if changed and sid:
            modified.append(sid)
        out_sents.append(updated)

    write_conllu(out_sents, out_path)

    if modified:
        print("[info] Modified sentences:")
        for sid in modified:
            print(f"  - {sid}")
    else:
        print("[info] No sentences were modified.")


# ---------------------- CLI ----------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Normalize Armenian exclamation (՜) into MWTs and renumber IDs.")
    ap.add_argument("--in", dest="in_path", required=True, help="Input CoNLL-U file.")
    ap.add_argument("--out", dest="out_path", required=True, help="Output CoNLL-U file.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    process_file(args.in_path, args.out_path)
    print(f"[ok] wrote: {args.out_path}")

if __name__ == "__main__":
    main()
