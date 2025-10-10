#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 48 — Insert `# translated_text = …` for sentences from a per-verse translations file.

Input translations file format (one per line):
    <id><space(s) or tab><translation text>
Example:
    3.16 For God so loved the world...
    3.16a For God so loved...
    3.16b that He gave...

Behavior:
  • Only sentences whose `# sent_id =` begins with `<BOOK>_` (default "JOHN_") are considered.
  • For IDs ending with `a` or `b`, we split the base verse translation at the first matching punctuation,
    preference order: ".", ":", ";", "," and attach the proper half.
  • For sent_id verse ranges like "3.4-6", we join translations of 3.4 3.5 3.6 (honoring ".1" stepping).
  • For plain verse like "3.16", we use translations[id] directly.
  • We insert the translation immediately after `# transliterated_text = ...` within the sentence block.
  • Existing `# translated_text = ...` lines are removed and replaced (idempotent).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PUNCT_SPLIT_ORDER = [".", ":", ";", ","]  # first match wins

# ---------------- translations file ----------------

def load_translations(path: Path) -> Dict[str, str]:
    """
    Load translations keyed by id (e.g., '3.16', '3.16a', '3.16b').
    Ignores blank and comment lines.
    Allows arbitrary whitespace between id and text.
    """
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        # split at first whitespace
        m = re.match(r'^(\S+)\s+(.*)$', s)
        if not m:
            continue
        idx, sent = m.group(1).strip(), m.group(2).strip()
        if idx and sent:
            out[idx] = sent
    return out

# ---------------- helpers ----------------

def split_by_punctuation(text: str) -> List[str]:
    """
    Split once by the first occurring punctuation from PUNCT_SPLIT_ORDER.
    Returns [left+punct, right] or [text] if none found.
    """
    for p in PUNCT_SPLIT_ORDER:
        if p in text:
            left, right = text.split(p, 1)
            return [left + p, right.strip()]
    return [text]

def expand_range(start_s: str, end_s: str) -> List[str]:
    """
    Expand verse range strings like '4'..'6' and support '.1' stepping as in original code.
    Returns list of string verse numbers: ['4', '5', '6'] (and possibly '4.1' etc).
    The original logic advanced: if current contains '.1' -> next = int(current)+1, else +1
    """
    def parse_num(s: str) -> Tuple[int, bool]:
        return (int(float(s)), ".1" in s)

    out: List[str] = []
    cur_base, cur_dot1 = parse_num(start_s)
    end_base, end_dot1 = parse_num(end_s)

    # We’ll iterate similarly to the original approach:
    #  if current has .1 -> next is int(current)+1; else +1
    while True:
        label = f"{cur_base}.1" if cur_dot1 else f"{cur_base}"
        out.append(label)
        if cur_base == end_base and cur_dot1 == end_dot1:
            break
        if cur_dot1:
            cur_base = int(cur_base) + 1
            cur_dot1 = False
        else:
            # try next integer; if end wants .1 for same base, we’ll allow loop to hit (.1) via a manual step if needed
            nxt = cur_base + 1
            # if we haven’t reached end_base yet, move there
            if nxt <= end_base:
                cur_base = nxt
                # if the *next* desired is exactly '<cur_base>.1' and end has .1 and we’re at end_base,
                # let the loop add a '.1' step on the final iteration by toggling cur_dot1:
                if (end_dot1 and cur_base == end_base):
                    cur_dot1 = True
            else:
                # If somehow overshoot (shouldn’t), stop
                break
    return out

def remove_existing_translated(lines: List[str]) -> List[str]:
    """Remove any pre-existing '# translated_text = ...' lines from a sentence block."""
    return [ln for ln in lines if not ln.startswith("# translated_text =")]

def extract_sent_id(line: str, expected_book: str) -> Optional[str]:
    """
    Given a '# sent_id = ...' line and expected BOOK_ prefix, return the ID part after 'BOOK_'.
    """
    m = re.match(r'#\s*sent_id\s*=\s*(\S+)', line)
    if not m:
        return None
    full = m.group(1)
    prefix = f"{expected_book}_"
    if full.startswith(prefix):
        return full[len(prefix):]
    return None

# ---------------- translation lookup ----------------

def find_translation_for_id(sent_id: str, translations: Dict[str, str]) -> Optional[str]:
    """
    Resolve a translation for a sent_id suffix like:
      '3.16', '3.16a', '3.16b', '3.4-6'
    Strategy mirrors the original code.
    """
    # a/b split?
    if sent_id.endswith("a") or sent_id.endswith("b"):
        base = sent_id[:-1]
        text = translations.get(base)
        if not text:
            return None
        parts = split_by_punctuation(text)
        if sent_id.endswith("a") and len(parts) >= 1:
            return parts[0]
        if sent_id.endswith("b") and len(parts) >= 2:
            return parts[1]
        return None

    # range like '3.4-6'  OR potentially '3.4-6.1'
    if "-" in sent_id:
        # Expect '<chapter>.<start>-<end>'
        try:
            chap, rng = sent_id.split(".", 1)
            start_s, end_s = rng.split("-", 1)
        except ValueError:
            return None

        pieces: List[str] = []
        for v in expand_range(start_s, end_s):
            key = f"{chap}.{v}"
            tr = translations.get(key)
            if tr:
                pieces.append(tr)
        return " ".join(pieces) if pieces else None

    # exact verse
    return translations.get(sent_id)

# ---------------- processing ----------------

def process_file(
    conllu_in: Path,
    translations_path: Path,
    conllu_out: Path,
    book_prefix: str = "JOHN",
    verbose: bool = False,
) -> None:
    translations = load_translations(translations_path)

    out_lines: List[str] = []
    buf: List[str] = []

    total_sentences = 0
    untranslated_ids: List[str] = []

    def flush_sentence(block: List[str]) -> None:
        nonlocal total_sentences, untranslated_ids, out_lines

        if not block:
            out_lines.append("\n")
            return

        # identify sent_id
        sent_id_suffix: Optional[str] = None
        for ln in block:
            if ln.startswith("# sent_id"):
                sid = extract_sent_id(ln, book_prefix)
                if sid:
                    sent_id_suffix = sid
                break

        # remove old translated_text if any
        block_no_trans = remove_existing_translated(block)

        # compute translation if this is our BOOK
        translation: Optional[str] = None
        if sent_id_suffix is not None:
            total_sentences += 1
            translation = find_translation_for_id(sent_id_suffix, translations)
            if not translation:
                untranslated_ids.append(sent_id_suffix)

        # write sentence, inserting translated_text after transliterated_text
        inserted = False
        for ln in block_no_trans:
            out_lines.append(ln if ln.endswith("\n") else ln + "\n")
            if translation and ln.startswith("# transliterated_text =") and not inserted:
                out_lines.append(f"# translated_text = {translation}\n")
                inserted = True

        # If there was a translation but we never saw transliterated_text, append at end of comment block
        if translation and not inserted:
            # Find the index after the last comment line
            i = 0
            while i < len(block_no_trans) and block_no_trans[i].startswith("#"):
                i += 1
            # Rebuild: comments up to i, insert line, then the rest — but we already wrote the whole block above,
            # so just append the translation before the upcoming blank line.
            out_lines.append(f"# translated_text = {translation}\n")

        out_lines.append("\n")

    with conllu_in.open("r", encoding="utf-8") as f:
        for raw in f:
            if raw.strip() == "":
                flush_sentence(buf)
                buf = []
            else:
                buf.append(raw.rstrip("\n"))

    # Final sentence if file lacked trailing blank
    if buf:
        flush_sentence(buf)

    conllu_out.write_text("".join(out_lines), encoding="utf-8")

    # Console report
    print(f"[translations] wrote {conllu_out}")
    print(f"Total {book_prefix} sentences: {total_sentences}")
    print(f"Without translations: {len(untranslated_ids)}")
    if untranslated_ids and verbose:
        print("Missing IDs:")
        for uid in untranslated_ids:
            print("  ", uid)

# ---------------- CLI ----------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 48: insert # translated_text from a verse translations file.")
    ap.add_argument("--in",  dest="inp",  required=True, type=Path, help="Input CoNLL-U file (e.g., output48.txt)")
    ap.add_argument("--out", dest="out",  required=True, type=Path, help="Output CoNLL-U file (e.g., output49.txt)")
    ap.add_argument("--translations", dest="translations", required=True, type=Path, help="Translations text file")
    ap.add_argument("--book", dest="book", default="JOHN", help='Book prefix expected in sent_id (default: "JOHN")')
    ap.add_argument("--verbose", action="store_true", help="Print missing IDs list")
    args = ap.parse_args()
    process_file(args.inp, args.translations, args.out, book_prefix=args.book, verbose=args.verbose)

if __name__ == "__main__":
    main()
