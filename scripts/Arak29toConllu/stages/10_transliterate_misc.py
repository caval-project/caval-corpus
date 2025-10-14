#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 10 — Add transliteration to MISC (Translit=…, LTranslit=…)

Behavior
--------
- For every token line (non-#), replace Armenian 'օ'→'աւ' and 'Օ'→'Աւ' in FORM and LEMMA.
- Transliterate FORM and LEMMA using a character map and store in MISC as:
      Translit=<form_translit>|LTranslit=<lemma_translit>
- If MISC already has Translit/LTranslit, they are replaced; other MISC keys are preserved.
- Comment and empty lines are copied as-is.

I/O (fixed names)
-----------------
- input   : source CoNLL-U (or CoNLL-U-like) file
- output  : destination file with updated MISC
"""

from __future__ import annotations
from pathlib import Path

INPUT_PATH = Path("input")
OUTPUT_PATH = Path("output")

# --- Transliteration rules (replace with your authoritative set if needed) ---
TRANSLIT_RULES = {
    'Ա': 'A', 'Բ': 'B', 'Գ': 'G', 'Դ': 'D', 'Ե': 'E', 'Զ': 'Z', 'Է': 'Ē', 'Ը': 'Ə', 'Թ': 'Tʻ', 'Ժ': 'Ž', 'Ի': 'I',
    'Լ': 'L', 'Խ': 'X', 'Ց': 'Cʻ', 'Ծ': 'C', 'Ք': 'Kʻ', 'Կ': 'K', 'Հ': 'H', 'Ձ': 'J', 'Ղ': 'Ł', 'Չ': 'Čʻ', 'Ճ': 'Č',
    'Մ': 'M', 'Յ': 'Y', 'Ն': 'N', 'Շ': 'Š', 'Ո': 'O', 'Փ': 'Pʻ', 'Պ': 'P', 'Ջ': 'J̌', 'Ռ': 'Ṙ', 'Ս': 'S', 'Վ': 'V',
    'Տ': 'T', 'Ր': 'R', 'Ւ': 'W', 'Ֆ': 'F',
    'ա': 'a', 'բ': 'b', 'գ': 'g', 'դ': 'd', 'ե': 'e', 'զ': 'z', 'է': 'ē', 'ը': 'ə', 'թ': 'tʻ', 'ժ': 'ž', 'ի': 'i',
    'լ': 'l', 'խ': 'x', 'ց': 'cʻ', 'ծ': 'c', 'ք': 'kʻ', 'կ': 'k', 'հ': 'h', 'ձ': 'j', 'ղ': 'ł', 'չ': 'čʻ', 'ճ': 'č',
    'մ': 'm', 'յ': 'y', 'ն': 'n', 'շ': 'š', 'ո': 'o', 'փ': 'pʻ', 'պ': 'p', 'ջ': 'ǰ', 'ռ': 'ṙ', 'ս': 's', 'վ': 'v',
    'տ': 't', 'ր': 'r', 'ւ': 'w', 'ֆ': 'f',
    '՝': ';', '՞': '?', '`': ';', '«': '"', '»': '"',
}

def _replace_o_with_av(text: str) -> str:
    """Apply historic spelling normalization: օ/Օ → ավ/Աւ."""
    return text.replace('օ', 'աւ').replace('Օ', 'Աւ')

def _transliterate(text: str, rules: dict[str, str]) -> str:
    """Character-by-character transliteration (no reordering)."""
    # Iteration order is fine because all keys are single characters here.
    return ''.join(rules.get(ch, ch) for ch in text)

def _parse_misc(misc: str) -> dict[str, str]:
    """Parse MISC into a dict; '_' => {}."""
    if not misc or misc == '_':
        return {}
    parts = [p for p in misc.split('|') if p]
    out: dict[str, str] = {}
    for p in parts:
        if '=' in p:
            k, v = p.split('=', 1)
            out[k] = v
        else:
            # Bare flags (e.g., "SpaceAfter=No" is still k=v; handle true bare flag fallback)
            out[p] = ""
    return out

def _format_misc(m: dict[str, str]) -> str:
    """Serialize misc dict back to string or '_' if empty. Keep stable key order (sorted)."""
    if not m:
        return '_'
    items = []
    for k in sorted(m.keys()):
        v = m[k]
        items.append(f"{k}={v}" if v != "" else k)
    return '|'.join(items)

def process_transliteration(
    input_path: Path = INPUT_PATH,
    output_path: Path = OUTPUT_PATH,
    rules: dict[str, str] = TRANSLIT_RULES,
) -> None:
    """
    Process file line-by-line:
      - Only modify non-comment, non-empty token lines with ≥10 tab-separated columns.
      - Update column[1] (FORM) and column[2] (LEMMA) for o→av rule (internal only).
      - Inject/replace Translit and LTranslit in column[9] (MISC).
    """
    total_tokens = 0
    updated_tokens = 0

    with input_path.open('r', encoding='utf-8') as infile, output_path.open('w', encoding='utf-8') as outfile:
        for raw in infile:
            if raw.startswith('#') or not raw.strip():
                # Comments / sentence breaks unchanged
                outfile.write(raw)
                continue

            cols = raw.rstrip('\n').split('\t')
            if len(cols) < 10:
                # Not a well-formed CoNLL-U token line; write back as-is
                outfile.write(raw)
                continue

            total_tokens += 1

            form = cols[1]
            lemma = cols[2]

            # Apply օ→աւ normalization BEFORE transliteration
            norm_form = _replace_o_with_av(form)
            norm_lemma = _replace_o_with_av(lemma)

            # Transliterate
            trans = _transliterate(norm_form, rules)
            ltrans = _transliterate(norm_lemma, rules)

            # Update MISC (column 9)
            misc_dict = _parse_misc(cols[9])
            # Replace/insert keys
            if misc_dict.get('Translit') != trans or misc_dict.get('LTranslit') != ltrans:
                updated_tokens += 1
            misc_dict['Translit'] = trans
            misc_dict['LTranslit'] = ltrans
            cols[9] = _format_misc(misc_dict)

            # Keep all other columns; write line
            outfile.write('\t'.join(cols) + '\n')

    print(f"[ok] Wrote: {output_path}")
    print(f"[info] tokens: {total_tokens}, updated: {updated_tokens}")

if __name__ == "__main__":
    process_transliteration()
