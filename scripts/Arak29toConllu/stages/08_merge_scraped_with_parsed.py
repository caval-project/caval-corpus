#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 08 — Align scraped vs. parsed CoNLL-U (with MWT preservation) and write edits.

Inputs (fixed names, same folder):
  - input.scraped  : scraped CoNLL-U
  - input.parsed   : parsed CoNLL-U
Output:
  - output         : merged/edited CoNLL-U

What it does
------------
1) Reads both files, sentence-by-sentence.
2) Matches sentences by normalized # text (lowercased, punctuation-stripped).
3) For matched pairs:
   - (Hook) place your token-level edit logic inside `process_and_modify_tokens`.
   - Preserves multi-word token (MWT) placeholder lines (e.g., "5-6") and
     re-numbers tokens consistently, remapping heads.
4) For unmatched parsed sentences: writes them unchanged.

Notes
-----
- MWT handling: we parse and retain MWT lines and their following sub-tokens.
- `process_and_modify_tokens` is intentionally conservative (pass-through). Add your
  domain-specific moves there if/when you need them.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple, Optional

INPUT_SCRAPED = "input.scraped"
INPUT_PARSED = "input.parsed"
OUTPUT_PATH = "output"


# ------------------- text normalization (for sentence matching) -------------------

def normalize_text(text: str) -> str:
    """Lowercase and strip all non-word, non-space characters."""
    return re.sub(r"[^\w\s]", "", text.lower())


# ------------------- CoNLL-U parsing/formatting with MWT support -------------------

def parse_conllu_sentence(conllu_sentence: str) -> List[Dict[str, object]]:
    """
    Parse *all* lines including multi-word token placeholders (e.g. "2-3").
    Returns a list of dicts. Each dict has:
      - is_mwt: bool
      - token_id: int (for real tokens) or str like "2-3" for MWT lines
      - form, lemma, upostag, xpostag, feats, head, deprel, deps, misc
        - for real tokens, 'head' is Optional[int]; for MWT lines, keep as raw str (usually "_").
    """
    tokens: List[Dict[str, object]] = []
    for line in conllu_sentence.strip().split("\n"):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 10:
            # Skip malformed lines, or pad to 10 columns if you prefer
            continue

        tid = cols[0]
        if "-" in tid:  # MWT placeholder
            tokens.append({
                "is_mwt": True,
                "token_id": tid,
                "form": cols[1],
                "lemma": cols[2],
                "upostag": cols[3],
                "xpostag": cols[4],
                "feats": cols[5],
                "head": cols[6],    # keep as-is (typically "_")
                "deprel": cols[7],  # keep as-is (typically "_")
                "deps": cols[8],
                "misc": cols[9],
            })
        else:
            head_val = cols[6]
            tokens.append({
                "is_mwt": False,
                "token_id": int(tid),
                "form": cols[1],
                "lemma": cols[2],
                "upostag": cols[3],
                "xpostag": cols[4],
                "feats": cols[5],
                "head": int(head_val) if head_val.isdigit() else None,
                "deprel": cols[7],
                "deps": cols[8],
                "misc": cols[9],
            })
    return tokens


def format_conllu_sentence(tokens: List[Dict[str, object]]) -> str:
    """Format token dicts back to CoNLL-U lines (exactly 10 columns)."""
    lines: List[str] = []
    for t in tokens:
        if t["is_mwt"]:
            tid = t["token_id"]  # str like "5-6"
            head_str = str(t["head"])
        else:
            tid = str(t["token_id"])
            head = t["head"]
            head_str = str(head) if isinstance(head, int) else "_"

        cols = [
            tid,
            str(t["form"]),
            str(t["lemma"]),
            str(t["upostag"]),
            str(t["xpostag"]),
            str(t["feats"]),
            head_str,
            str(t["deprel"]),
            str(t["deps"]),
            str(t["misc"]),
        ]
        if len(cols) < 10:
            cols += ["_"] * (10 - len(cols))
        elif len(cols) > 10:
            cols = cols[:10]
        lines.append("\t".join(cols))
    return "\n".join(lines)


def renumber_tokens(token_dicts: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """
    Reassign IDs 1..N in order while preserving/renumbering MWT ranges and
    remapping heads on real tokens.
    """
    new_list: List[Dict[str, object]] = []
    old2new: Dict[int, str] = {}
    next_id = 1
    i = 0

    while i < len(token_dicts):
        tk = token_dicts[i]
        if tk["is_mwt"]:
            # Move placeholder; compute range size from its original "a-b".
            a_str, b_str = str(tk["token_id"]).split("-")
            old_a, old_b = int(a_str), int(b_str)
            count = old_b - old_a + 1

            new_a = next_id
            new_b = new_a + count - 1

            mwt = dict(tk)
            mwt["token_id"] = f"{new_a}-{new_b}"
            new_list.append(mwt)

            # Map old subtokens, then emit them if they immediately follow.
            consumed = 0
            j = i + 1
            while consumed < count and j < len(token_dicts) and not token_dicts[j]["is_mwt"]:
                sub = token_dicts[j]
                if int(sub["token_id"]) == old_a + consumed:
                    new_id = new_a + consumed
                    old2new[old_a + consumed] = str(new_id)
                    sub2 = dict(sub)
                    sub2["token_id"] = new_id
                    new_list.append(sub2)
                    consumed += 1
                    j += 1
                else:
                    break

            next_id = new_b + 1
            i = j
            continue

        # regular token
        old_id = int(tk["token_id"])
        new_id = next_id
        old2new[old_id] = str(new_id)
        tk2 = dict(tk)
        tk2["token_id"] = new_id
        new_list.append(tk2)
        next_id += 1
        i += 1

    # Remap heads
    for tk in new_list:
        if tk["is_mwt"]:
            continue
        head = tk["head"]
        if isinstance(head, int):
            mapped = old2new.get(head)
            if mapped is not None:
                tk["head"] = int(mapped)

    return new_list


# ------------------- sentence I/O -------------------

def extract_sentences_from_file(file_path: str) -> List[Tuple[str, str, str, List[str], List[Dict[str, object]]]]:
    """
    Read a CoNLL-U file and return tuples:
    (sent_id, text, normalized_text, metadata_lines, parsed_tokens_including_MWT)
    """
    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    out: List[Tuple[str, str, str, List[str], List[Dict[str, object]]]] = []
    if not raw:
        return out

    for block in raw.split("\n\n"):
        lines = block.split("\n")
        metadata = [l for l in lines if l.startswith("#")]
        token_lines = [l for l in lines if l and not l.startswith("#")]

        sid_line = next((l for l in metadata if l.startswith("# sent_id")), None)
        text_line = next((l for l in metadata if l.startswith("# text")), None)
        if not sid_line or not text_line:
            # keep only fully annotated sentences for matching
            continue

        sent_id = sid_line.split("=", 1)[1].strip()
        text = text_line.split("=", 1)[1].strip()
        norm = normalize_text(text)
        parsed_tokens = parse_conllu_sentence(block)

        out.append((sent_id, text, norm, metadata, parsed_tokens))
    return out


# ------------------- your token-level hook -------------------

def process_and_modify_tokens(
    scraped_tokens: List[Dict[str, object]],
    parsed_tokens: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    """
    Place your custom, domain-specific edits here.
    Default: pass-through (keep parsed as-is).
    If you add insertions/deletions, always return a list of tokens
    (including any MWT lines you wish to preserve); final renumbering
    happens afterwards.
    """
    # TODO: implement your bespoke logic if/when needed.
    return list(parsed_tokens)


# ------------------- driver -------------------

def process_files(scraped_path: str, parsed_path: str, output_path: str) -> None:
    scraped_sents = extract_sentences_from_file(scraped_path)
    parsed_sents = extract_sentences_from_file(parsed_path)

    # Index scraped by normalized text for O(1) lookup
    scraped_by_norm: Dict[str, Tuple[str, str, str, List[str], List[Dict[str, object]]]] = {
        norm: tup for tup in scraped_sents for norm in [tup[2]]
    }

    matched = 0

    with open(output_path, "w", encoding="utf-8") as out_f:
        for parsed in parsed_sents:
            p_sid, p_text, p_norm, p_meta, p_tokens = parsed

            if p_norm in scraped_by_norm:
                s_sid, s_text, s_norm, s_meta, s_tokens = scraped_by_norm[p_norm]
                merged_tokens = process_and_modify_tokens(s_tokens, p_tokens)
                final_tokens = renumber_tokens(merged_tokens)
                out_f.write("\n".join(p_meta) + "\n")
                out_f.write(format_conllu_sentence(final_tokens) + "\n\n")
                matched += 1
            else:
                # no match -> write parsed unchanged
                out_f.write("\n".join(p_meta) + "\n")
                out_f.write(format_conllu_sentence(p_tokens) + "\n\n")

    print(f"[ok] Wrote: {output_path}  (matched: {matched}/{len(parsed_sents)})")


def main() -> None:
    process_files(INPUT_SCRAPED, INPUT_PARSED, OUTPUT_PATH)


if __name__ == "__main__":
    main()
