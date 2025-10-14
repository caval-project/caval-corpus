#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 11 — Finalize transliteration & clean-ups

- Ensures a "# transliterated_text = …" line exists for each sentence (computed from "# text = …").
- Normalizes lemmas: Օ → Աւ, օ → ավ (pre-transliteration historical norm).
- Sorts FEATS alphabetically (case-insensitive).
- Cleans extra whitespace in MISC.
- Corrects Translit/LTranslit in MISC for punctuation tokens using same translit rules.

I/O (fixed names)
-----------------
- input   : source file (CoNLL-U or CoNLL-U-like)
- output  : destination file
"""

from __future__ import annotations
from pathlib import Path
import re

INPUT_PATH = Path("input")
OUTPUT_PATH = Path("output")

# Transliteration rules (character-to-character)
TRANSLIT_RULES = {
    'Ա': 'A', 'Բ': 'B', 'Գ': 'G', 'Դ': 'D', 'Ե': 'E', 'Զ': 'Z', 'Է': 'Ē', 'Ը': 'Ə', 'Թ': 'Tʻ', 'Ժ': 'Ž', 'Ի': 'I',
    'Լ': 'L', 'Խ': 'X', 'Ց': 'Cʻ', 'Ծ': 'C', 'Ք': 'Kʻ', 'Կ': 'K', 'Հ': 'H', 'Ձ': 'J', 'Ղ': 'Ł', 'Չ': 'Čʻ', 'Ճ': 'Č',
    'Մ': 'M', 'Յ': 'Y', 'Ն': 'N', 'Շ': 'Š', 'Ո': 'O', 'Փ': 'Pʻ', 'Պ': 'P', 'Ջ': 'J̌', 'Ռ': 'Ṙ', 'Ս': 'S', 'Վ': 'V',
    'Տ': 'T', 'Ր': 'R', 'Ւ': 'W', 'Ֆ': 'F',
    'ա': 'a', 'բ': 'b', 'գ': 'g', 'դ': 'd', 'ե': 'e', 'զ': 'z', 'է': 'ē', 'ը': 'ə', 'թ': 'tʻ', 'ժ': 'ž', 'ի': 'i',
    'լ': 'l', 'խ': 'x', 'ց': 'cʻ', 'ծ': 'c', 'ք': 'kʻ', 'կ': 'k', 'հ': 'h', 'ձ': 'j', 'ղ': 'ł', 'չ': 'čʻ', 'ճ': 'č',
    'մ': 'm', 'յ': 'y', 'ն': 'n', 'շ': 'š', 'ո': 'o', 'փ': 'pʻ', 'պ': 'p', 'ջ': 'ǰ', 'ռ': 'ṙ', 'ս': 's', 'վ': 'v',
    'տ': 't', 'ր': 'r', 'ւ': 'w', 'ֆ': 'f',
    # Punctuation & symbols
    '՝': ';', '՞': '?', '՛': '!', ',': ',', '.': ':', ':': '.', '`': ';', '«': '"', '»': '"'
}

# Characters considered punctuation for token-level Translit/LTranslit fix
PUNCT_TOKENS = set(['.', ':', ',', '՝', '՞', '՛', '«', '»'])

def _transliterate_text(text: str) -> str:
    """Character-wise transliteration using TRANSLIT_RULES, normalize Armenian comma (՝) to ';' result."""
    translit = ''.join(TRANSLIT_RULES.get(ch, ch) for ch in text)
    # safeguard: make sure U+055D gets represented as ';' if passed through untouched
    return translit.replace('՝', ';')

def _normalize_lemma_o_av(lemma: str) -> str:
    """Historical normalization: Օ/օ → Աւ/աւ."""
    return lemma.replace('օ', 'աւ').replace('Օ', 'Աւ')

def _sort_feats(feats: str) -> str:
    """Sort features in FEATS alphabetically (case-insensitive). '_' stays '_'."""
    feats = feats.strip()
    if feats == '_' or not feats:
        return '_'
    parts = [p for p in feats.split('|') if p]
    parts.sort(key=lambda s: s.lower())
    return '|'.join(parts) if parts else '_'

def _clean_misc_ws(misc: str) -> str:
    """Collapse multiple spaces in MISC (only inside field values). '_' stays '_'."""
    if misc.strip() == '_' or not misc.strip():
        return '_'
    # We do not want to break the '|' structure; only compact spaces within values.
    # Simple approach: global collapse.
    return re.sub(r'\s+', ' ', misc).strip()

def _ensure_transliterated_text(lines: list[str], idx: int) -> list[str]:
    """
    If the current line is a '# text = ...' line, ensure there is a matching
    '# transliterated_text = ...' line before the next non-comment line.
    """
    line = lines[idx]
    if not line.startswith("# text ="):
        return [line]

    out = [line]
    original_text = line[len("# text ="):].strip()

    # Peek ahead for an existing transliterated_text in the immediate metadata block
    j = idx + 1
    has_translit = False
    while j < len(lines):
        nxt = lines[j]
        if nxt.startswith("# transliterated_text ="):
            has_translit = True
            break
        if not (nxt.startswith("#") or nxt.strip() == ""):
            break  # next token line reached; stop searching
        j += 1

    if not has_translit:
        out.append("# transliterated_text = " + _transliterate_text(original_text) + "\n")
    return out

def _fix_punct_translit(columns: list[str]) -> list[str]:
    """
    If token FORM is strictly a punctuation in PUNCT_TOKENS,
    recompute Translit/LTranslit in MISC to match the mapping.
    """
    form = columns[1]
    if form not in PUNCT_TOKENS:
        return columns

    correct = _transliterate_text(form)
    misc = columns[9].strip()
    if not misc or misc == '_':
        columns[9] = f"Translit={correct}|LTranslit={correct}"
        return columns

    parts = [p for p in misc.split('|') if p]
    new_parts = []
    seen_t = False
    seen_lt = False
    for p in parts:
        if p.startswith("Translit="):
            new_parts.append(f"Translit={correct}")
            seen_t = True
        elif p.startswith("LTranslit="):
            new_parts.append(f"LTranslit={correct}")
            seen_lt = True
        else:
            new_parts.append(p)
    if not seen_t:
        new_parts.insert(0, f"Translit={correct}")
    if not seen_lt:
        new_parts.insert(1, f"LTranslit={correct}")
    columns[9] = '|'.join(new_parts)
    return columns

def process(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> None:
    """Main entry — stream through, updating metadata and token lines as specified."""
    with input_path.open('r', encoding='utf-8') as infile:
        lines = infile.readlines()

    with output_path.open('w', encoding='utf-8') as outfile:
        i = 0
        while i < len(lines):
            line = lines[i]

            # Comments / blank lines — possibly add transliterated_text
            if line.startswith('#') or line.strip() == '':
                if line.startswith("# transliterated_text ="):
                    # normalize Armenian comma in existing transliterated_text
                    line = line.replace('՝', ';')
                    outfile.write(line)
                    i += 1
                    continue

                if line.startswith("# text ="):
                    for out_line in _ensure_transliterated_text(lines, i):
                        outfile.write(out_line)
                    i += 1
                    continue

                # other comment/blank
                outfile.write(line)
                i += 1
                continue

            # Token line
            cols = line.rstrip('\n').split('\t')
            if len(cols) != 10:
                # Not a well-formed CoNLL-U line — pass through
                outfile.write(line)
                i += 1
                continue

            # 1) Lemma normalization (Օ/օ → Աւ/աւ)
            cols[2] = _normalize_lemma_o_av(cols[2])

            # 2) FEATS sorting
            cols[5] = _sort_feats(cols[5])

            # 3) MISC whitespace compaction
            cols[9] = _clean_misc_ws(cols[9])

            # 4) Fix Translit/LTranslit for punctuation-only tokens
            cols = _fix_punct_translit(cols)

            outfile.write('\t'.join(cols) + '\n')
            i += 1

    print(f"[ok] Wrote: {output_path}")

if __name__ == "__main__":
    process()
