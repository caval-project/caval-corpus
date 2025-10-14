#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
21_fix_translit_and_ltranslit.py

Populate/repair MISC fields Translit and LTranslit in a CoNLL-U file:
- Normalize Armenian 'օ'→'աւ' and 'Օ'→'Աւ' *before* transliteration.
- Map characters via a deterministic Armenian→Latin table.
- Only overwrite Translit/LTranslit if missing or they still contain Armenian codepoints.

I/O (fixed by project convention):
- Read  : ./input
- Write : ./output
"""

from __future__ import annotations
import re
import sys

try:
    from conllu import parse_incr
except Exception as e:
    raise SystemExit(
        "ERROR: The 'conllu' package is required.\n"
        "Install with: pip install conllu\n"
        f"Details: {e}"
    )

# ---------------------- Transliteration rules ---------------------- #
TRANSLIT_RULES = {
    'Ա': 'A', 'Բ': 'B', 'Գ': 'G', 'Դ': 'D', 'Ե': 'E', 'Զ': 'Z', 'Է': 'Ē', 'Ը': 'Ə',
    'Թ': "Tʻ", 'Ժ': 'Ž', 'Ի': 'I', 'Լ': 'L', 'Խ': 'X', 'Ց': "Cʻ", 'Ծ': 'C', 'Ք': "Kʻ",
    'Կ': 'K', 'Հ': 'H', 'Ձ': 'J', 'Ղ': 'Ł', 'Չ': "Čʻ", 'Ճ': 'Č', 'Մ': 'M', 'Յ': 'Y',
    'Ն': 'N', 'Շ': 'Š', 'Ո': 'O', 'Փ': "Pʻ", 'Պ': 'P', 'Ջ': 'J̌', 'Ռ': 'Ṙ', 'Ս': 'S',
    'Վ': 'V', 'Տ': 'T', 'Ր': 'R', 'Ւ': 'W', 'Ֆ': 'F',
    'ա': 'a', 'բ': 'b', 'գ': 'g', 'դ': 'd', 'ե': 'e', 'զ': 'z', 'է': 'ē', 'ը': 'ə',
    'թ': "tʻ", 'ժ': 'ž', 'ի': 'i', 'լ': 'l', 'խ': 'x', 'ց': "cʻ", 'ծ': 'c', 'ք': "kʻ",
    'կ': 'k', 'հ': 'h', 'ձ': 'j', 'ղ': 'ł', 'չ': "čʻ", 'ճ': 'č', 'մ': 'm', 'յ': 'y',
    'ն': 'n', 'շ': 'š', 'ո': 'o', 'փ': "pʻ", 'պ': 'p', 'ջ': 'ǰ', 'ռ': 'ṙ', 'ս': 's',
    'վ': 'v', 'տ': 't', 'ր': 'r', 'ւ': 'w', 'ֆ': 'f',
    # Armenian punctuation we want mapped
    '՝': ';', '՞': '?', '`': ';', '«': '"', '»': '"'
}

# Precompile a regex that matches any Armenian codepoint
ARMENIAN_RE = re.compile(r'[\u0530-\u058F]')

def replace_o_with_av(text: str) -> str:
    """Normalize Armenian օ/Օ into ավ/Աւ before transliterating."""
    return text.replace('օ', 'աւ').replace('Օ', 'Աւ')

def transliterate(text: str, rules: dict[str, str]) -> str:
    """Character-wise transliteration with pass-through for unknown chars."""
    return "".join(rules.get(ch, ch) for ch in text)

def needs_fix(s: str | None) -> bool:
    """Return True if s is missing or still contains Armenian codepoints."""
    if s is None:
        return True
    return bool(ARMENIAN_RE.search(s))

def is_word_token(token) -> bool:
    """
    conllu semantics:
      - word tokens: token["id"] is int
      - multi-word tokens: token["id"] is (start, end)
      - empty nodes: token["id"] is float (e.g., 3.1 -> 3.1)
    """
    tid = token.get("id")
    return isinstance(tid, int)

def process_conllu(in_path: str, out_path: str) -> None:
    with open(in_path, "r", encoding="utf-8") as infile, \
         open(out_path, "w", encoding="utf-8") as outfile:

        for tokenlist in parse_incr(infile):
            for token in tokenlist:
                if not is_word_token(token):
                    continue  # leave multi-word tokens and empty nodes untouched

                misc = token.get("misc")
                if misc is None:
                    # conllu treats missing MISC as None; set a dict to populate fields
                    misc = {}

                form  = token.get("form", "") or ""
                lemma = token.get("lemma", "") or ""

                # Compute canonical transliterations
                canon_form  = transliterate(replace_o_with_av(form), TRANSLIT_RULES)
                canon_lemma = transliterate(replace_o_with_av(lemma), TRANSLIT_RULES)

                # Read existing values
                old_translit  = misc.get("Translit")
                old_ltranslit = misc.get("LTranslit")

                # Overwrite only if missing or still Armenian
                if needs_fix(old_translit):
                    misc["Translit"] = canon_form
                if needs_fix(old_ltranslit):
                    misc["LTranslit"] = canon_lemma

                token["misc"] = misc  # assign back (Token is a dict-like)

            # Serialize sentence (keeps comments and formatting)
            outfile.write(tokenlist.serialize())

if __name__ == "__main__":
    in_path  = "input"
    out_path = "output"
    try:
        process_conllu(in_path, out_path)
        print(f"Transliteration fields fixed. Saved to '{out_path}'.")
    except FileNotFoundError:
        sys.exit("ERROR: input file not found. Ensure a file named 'input' exists next to this script.")
