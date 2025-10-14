#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 07 — Split Armenian punctuation attached to words.

- Input  CoNLL-U:  ./input
- Output CoNLL-U:  ./output

What it does
------------
If a token FORM contains Armenian punctuation marks (ʼ=՛, !-like=՜, ?-like=՞)
attached to the word, e.g. «Աւա՜», the script rewrites it as:

  3-4   Աւա՜   _     _   _   _   _   _      _   _
  3     Աւա    ...   ... ... ... ... ...    ... ...
  4     ՜      ՜     PUNCT _   _   3   punct _   _

It handles:
- single or multiple punctuation marks (each mark becomes its own PUNCT token)
- tokens that are only punctuation (converted to PUNCT without MWT)
- consistent renumbering and head remapping

Notes
-----
- Only token lines are modified; comments and spacing are preserved.
- MWT placeholders get `_` in all fields as per CoNLL-U recommendations.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

INPUT_PATH = "input"
OUTPUT_PATH = "output"

# Armenian punctuation marks that may be attached to words
ARM_PUNCT = tuple("՛՜՞")  # (U+055B, U+055C, U+055E)


# ------------------------- I/O helpers -------------------------

def read_conllu_file(file_path: str) -> List[Tuple[str, List[str], List[str]]]:
    """Return a list of sentences as (sent_id, metadata_lines, token_lines)."""
    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    if not raw:
        return []

    sentences = []
    for block in raw.split("\n\n"):
        lines = block.split("\n")
        metadata = [l for l in lines if l.startswith("#")]
        token_lines = [l for l in lines if l and not l.startswith("#")]

        sent_id = None
        for m in metadata:
            if m.startswith("# sent_id"):
                sent_id = m.split("=", 1)[1].strip()
                break

        # accept even if sent_id is missing (but we try to keep it)
        sentences.append((sent_id or "", metadata, token_lines))

    return sentences


def parse_token_line(line: str) -> Dict[str, str] | None:
    """Parse a CoNLL-U token line -> dict of 10 columns."""
    cols = line.split("\t")
    if len(cols) < 10:
        return None
    return {
        "id": cols[0],
        "form": cols[1],
        "lemma": cols[2],
        "upostag": cols[3],
        "xpostag": cols[4],
        "feats": cols[5],
        "head": cols[6],
        "deprel": cols[7],
        "deps": cols[8],
        "misc": cols[9],
    }


def format_token(t: Dict[str, str]) -> str:
    """Format dict -> CoNLL-U token line (10 columns)."""
    cols = [
        t["id"], t["form"], t["lemma"], t["upostag"], t["xpostag"],
        t["feats"], t["head"], t["deprel"], t["deps"], t["misc"],
    ]
    # ensure exactly 10 columns
    if len(cols) < 10:
        cols += ["_"] * (10 - len(cols))
    elif len(cols) > 10:
        cols = cols[:10]
    return "\t".join(cols)


# ------------------------- core transformations -------------------------

def renumber_tokens(token_dicts: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Reassign IDs 1..N in order; remap heads accordingly.
    Supports MWT placeholders (e.g., "5-6") followed by the matching sub-tokens.
    """
    new_list: List[Dict[str, str]] = []
    old_id_map: Dict[int, str] = {}
    next_id = 1
    i = 0

    while i < len(token_dicts):
        tk = token_dicts[i]
        tid = tk["id"]

        if "-" in tid:
            # MWT line: map range
            old_start, old_end = map(int, tid.split("-"))
            count = old_end - old_start + 1

            new_start = next_id
            new_end = new_start + count - 1
            tk = dict(tk)
            tk["id"] = f"{new_start}-{new_end}"
            new_list.append(tk)

            # consume following sub-tokens matching the old range
            j = 0
            while j < count and i + 1 < len(token_dicts):
                sub = token_dicts[i + 1]
                if sub["id"].isdigit() and int(sub["id"]) == old_start + j:
                    new_id = new_start + j
                    old_id_map[old_start + j] = str(new_id)
                    sub = dict(sub)
                    sub["id"] = str(new_id)
                    new_list.append(sub)
                    i += 1
                    j += 1
                else:
                    break

            next_id = new_end + 1
            i += 1
            continue

        if tid.isdigit():
            old_num = int(tid)
            new_id = str(next_id)
            old_id_map[old_num] = new_id
            tk = dict(tk)
            tk["id"] = new_id
            new_list.append(tk)
            next_id += 1
        # else: ignore unexpected ids gracefully
        i += 1

    # remap heads
    for tk in new_list:
        if "-" in tk["id"]:
            continue
        hd = tk["head"]
        if hd.isdigit():
            mapped = old_id_map.get(int(hd))
            if mapped:
                tk["head"] = mapped

    return new_list


def split_attached_punct(tokens: List[Dict[str, str]]) -> tuple[List[Dict[str, str]], bool]:
    """
    If token FORM contains Armenian punctuation (ʼ=՛, ՜, ՞),
    split into MWT + base + one PUNCT token per mark.
    If the token is only punctuation, convert directly to PUNCT (no MWT).
    """
    new_tokens: List[Dict[str, str]] = []
    changed = False

    for tk in tokens:
        form = tk["form"]

        if not any(ch in form for ch in ARM_PUNCT):
            new_tokens.append(tk)
            continue

        # Separate base and punctuation marks (in order)
        base = "".join(ch for ch in form if ch not in ARM_PUNCT)
        puncts = [ch for ch in form if ch in ARM_PUNCT]

        # Only punctuation? -> convert this token to PUNCT(s), no MWT.
        if base == "":
            changed = True
            # If multiple marks, create one token per mark
            for idx, p in enumerate(puncts):
                out = dict(tk)
                out["form"] = p
                out["lemma"] = p
                out["upostag"] = "PUNCT"
                out["xpostag"] = "_"
                out["feats"] = "_"
                # keep original head/deprel; typical UD is punct with head to its host,
                # but with no base word we keep the existing head to avoid breaking tree.
                out["deprel"] = "punct"
                out["deps"] = "_"
                out["misc"] = "_"
                new_tokens.append(out)
            continue

        # Otherwise: create an MWT and split into base + punct tokens
        changed = True

        # MWT placeholder (id will be re-assigned later in renumbering)
        mwt = {
            "id": f"{tk['id']}-{int(tk['id']) + len(puncts)}",
            "form": form,
            "lemma": "_",
            "upostag": "_",
            "xpostag": "_",
            "feats": "_",
            "head": "_",
            "deprel": "_",
            "deps": "_",
            "misc": "_",
        }
        new_tokens.append(mwt)

        # Base token (inherit all fields except form)
        base_token = dict(tk)
        base_token["form"] = base
        new_tokens.append(base_token)

        # Punctuation tokens: each mark becomes a separate token,
        # each pointing to the base token as head with deprel=punct.
        # (renumbering will repair heads afterwards)
        curr_id_int = int(tk["id"])
        for offset, p in enumerate(puncts, start=1):
            punct_tk = {
                "id": str(curr_id_int + offset),
                "form": p,
                "lemma": p,
                "upostag": "PUNCT",
                "xpostag": "_",
                "feats": "_",
                "head": tk["id"],        # head will be remapped after renumber
                "deprel": "punct",
                "deps": "_",
                "misc": "_",
            }
            new_tokens.append(punct_tk)

    return new_tokens, changed


# ------------------------- pipeline driver -------------------------

def process_punctuation_fixing(input_path: str, output_path: str) -> None:
    """Run the punctuation splitting pass and write the fixed file."""
    sentences = read_conllu_file(input_path)
    modified_ids: List[str] = []

    with open(output_path, "w", encoding="utf-8") as out_f:
        for sent_id, metadata, token_lines in sentences:
            # parse token lines
            tokens = [t for ln in token_lines if (t := parse_token_line(ln))]

            # split attached punctuation
            split_tokens, changed = split_attached_punct(tokens)
            if changed and sent_id:
                modified_ids.append(sent_id)

            # renumber + remap heads
            final_tokens = renumber_tokens(split_tokens)

            # emit
            for m in metadata:
                out_f.write(m + "\n")
            for t in final_tokens:
                out_f.write(format_token(t) + "\n")
            out_f.write("\n")

    if modified_ids:
        print("Modified sentences:")
        for mid in modified_ids:
            print(f" - {mid}")
    else:
        print("No sentences were modified.")


def main() -> None:
    process_punctuation_fixing(INPUT_PATH, OUTPUT_PATH)
    print(f"[ok] Wrote: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
