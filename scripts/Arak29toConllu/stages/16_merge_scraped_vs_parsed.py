#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 16 — Merge scraped and parsed CoNLL-U by sentence text and fix tokenization.

What this does
--------------
For each sentence, we match scraped vs. parsed by normalized "# text" (lowercased, punctuation-stripped).
When matched, we apply token-edit rules to the parsed tokens to reconcile differences:

Rules
1) Parsed form ends with one extra suffix (ս/դ/ն) vs. scraped:
   - Remove last char from parsed FORM
   - Ensure MISC includes SpaceAfter=No
   - Insert a separate suffix token right after, depending on the host token
     (temporary IDs are renumbered at the end)

2) Scraped form has one extra suffix (ս/դ/ն) vs. parsed:
   - Append the missing letter to parsed FORM and LEMMA
   - Remove SpaceAfter=No from parsed MISC (if present)
   - Skip next parsed token (treated as merged)

3) Scraped starts with յ/զ/ց, parsed token is exactly that single letter:
   - Prefix the next parsed token’s FORM/LEMMA with that letter
   - Remove the single-letter parsed token

4) Scraped token is exactly յ/զ/ց, parsed token starts with that letter:
   - Split parsed token: insert single-letter token before
   - Mark single-letter token with SpaceAfter=No

After modifications:
- IDs are renumbered consecutively
- HEAD values are remapped accordingly
- Non-token lines (comments/metadata) are preserved

I/O
---
- Reads:  ./input.scraped   (scraped CoNLL-U)
- Reads:  ./input.parsed    (parsed CoNLL-U)
- Writes: ./output
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import re
import sys


SCRAPED_PATH = Path("input.scraped")
PARSED_PATH  = Path("input.parsed")
OUTPUT_PATH  = Path("output")


# ---------- Utilities ----------

def normalize_text(text: str) -> str:
    """Lowercase and remove punctuation for robust matching."""
    return re.sub(r"[^\w\s]", "", text.lower())


def parse_conllu_sentence_all_lines(sentence_block: str) -> Tuple[List[str], List[str]]:
    """
    Return (metadata_lines, token_lines) without filtering anything out.
    """
    lines = [ln for ln in sentence_block.strip().split("\n") if ln.strip() != ""]
    meta = [ln for ln in lines if ln.startswith("#")]
    toks = [ln for ln in lines if not ln.startswith("#")]
    return meta, toks


def read_conllu(file_path: Path) -> List[Tuple[str, str, List[str], List[str]]]:
    """
    Read a CoNLL-U file and return a list of tuples:
    (sent_id, text, metadata_lines, token_lines)
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Missing file: {file_path.resolve()}")

    with file_path.open("r", encoding="utf-8") as f:
        blocks = [b for b in f.read().strip().split("\n\n") if b.strip()]

    out = []
    for blk in blocks:
        meta, toks = parse_conllu_sentence_all_lines(blk)
        sent_id = next((m.split("=", 1)[1].strip() for m in meta if m.startswith("# sent_id")), None)
        text    = next((m.split("=", 1)[1].strip() for m in meta if m.startswith("# text")),    None)
        if sent_id is not None and text is not None:
            out.append((sent_id, text, meta, toks))
    return out


def parse_token_line(line: str) -> Optional[Dict[str, object]]:
    cols = line.split("\t")
    if len(cols) != 10:
        return None
    tid = cols[0]
    if "-" in tid or "." in tid:
        return None  # skip MWTs and empty nodes for our edit logic
    return {
        "token_id": int(tid),
        "form": cols[1],
        "lemma": cols[2],
        "upostag": cols[3],
        "xpostag": cols[4],
        "feats": cols[5],
        "head": int(cols[6]) if cols[6].isdigit() else None,
        "deprel": cols[7],
        "deps": cols[8],
        "misc": cols[9],
    }


def format_token(t: Dict[str, object]) -> str:
    return "\t".join([
        str(t["token_id"]),
        t["form"],
        t["lemma"],
        t["upostag"],
        t["xpostag"],
        t["feats"],
        str(t["head"]) if t["head"] is not None else "_",
        t["deprel"],
        t["deps"],
        t["misc"],
    ])


def renumber_tokens(tokens: List[Dict[str, object]]) -> List[Dict[str, object]]:
    id_map: Dict[int, int] = {}
    out: List[Dict[str, object]] = []
    for i, tok in enumerate(tokens, start=1):
        old = tok["token_id"]
        id_map[int(old)] = i
        nt = dict(tok)
        nt["token_id"] = i
        out.append(nt)
    # remap heads
    for t in out:
        if isinstance(t["head"], int) and t["head"] in id_map:
            t["head"] = id_map[t["head"]]
    return out


def ensure_misc_flag(misc: str, flag: str) -> str:
    if not misc or misc == "_":
        return flag
    parts = misc.split("|")
    if flag not in parts:
        parts.insert(0, flag) if flag == "SpaceAfter=No" else parts.append(flag)
    return "|".join(p for p in parts if p) or "_"


# ---------- Core merge logic ----------

SUFFIXES = "սդն"
LEADING_LETTERS = "յզց"


def process_and_modify_tokens(scraped: List[Dict[str, object]],
                              parsed:  List[Dict[str, object]]) -> List[Dict[str, object]]:
    """
    Apply the four reconciliation rules described in the module docstring.
    """
    modified = [dict(p) for p in parsed]  # deep copy
    max_iters = 1000
    iteration = 0

    while iteration < max_iters:
        iteration += 1
        changes = False
        new_list: List[Dict[str, object]] = []
        i = 0
        # Work on the shorter zip; beyond that, copy remainder
        for i, (s_tok, p_tok) in enumerate(zip(scraped, modified)):
            s_form = s_tok["form"]
            p_form = p_tok["form"]

            s_low = s_form.lower()
            p_low = p_form.lower()

            # Rule 1: parsed has one extra suffix (ս/դ/ն)
            if len(p_low) >= 2 and s_low == p_low[:-1] and p_low[-1] in SUFFIXES:
                removed = p_form[-1]  # preserve case
                host = dict(p_tok)
                host["form"] = p_form[:-1]
                host["misc"] = ensure_misc_flag(host["misc"], "SpaceAfter=No")
                new_list.append(host)

                suffix_tok = {
                    "token_id": host["token_id"] + 1,  # temporary
                    "form": removed,
                    "lemma": removed,
                    "upostag": "_",
                    "xpostag": "_",
                    "feats": "_",
                    "head": host["token_id"],  # attach to host
                    "deprel": "_",
                    "deps": "_",
                    "misc": "_",
                }
                new_list.append(suffix_tok)
                changes = True
                continue

            # Rule 2: scraped has one extra suffix (ս/դ/ն)
            if len(s_low) >= 2 and s_low[-1] in SUFFIXES and s_low == p_low + s_low[-1]:
                missing = s_form[-1]
                merged = dict(p_tok)
                merged["form"]  = p_tok["form"]  + missing
                merged["lemma"] = p_tok["lemma"] + missing
                if "SpaceAfter=No" in (merged["misc"] or ""):
                    # If there were other flags, remove only the SA=No cleanly
                    parts = [x for x in merged["misc"].split("|") if x and x != "SpaceAfter=No"]
                    merged["misc"] = "|".join(parts) if parts else "_"
                new_list.append(merged)
                # Skip the next parsed token (assumed to be that suffix token)
                if i + 1 < len(modified):
                    # drop modified[i+1] by skipping it in the carry-over below
                    pass
                # Mark that we consumed the next parsed token:
                # We'll skip it when copying the tail below.
                changes = True
                # We mimic "skip-next" by remembering index; simpler approach: copy the tail carefully later.
                # For now, we also push a marker:
                new_list.append({"__SKIP_NEXT__": True})  # marker
                continue

            # Rule 3: scraped starts with (յ/զ/ց) and parsed token IS that single letter
            if s_low and s_low[0] in LEADING_LETTERS and len(s_low) > 1 and p_low in LEADING_LETTERS and len(p_low) == 1:
                # Prefix next parsed token if it exists
                if i + 1 < len(modified):
                    pref = p_tok["form"]  # preserve case
                    nxt  = dict(modified[i + 1])
                    nxt["form"]  = pref + nxt["form"]
                    nxt["lemma"] = pref + nxt["lemma"]
                    # Do not keep the single-letter parsed token:
                    # We'll push only the updated next token when its turn comes.
                    # Here, push nothing for the current token.
                    # We will also mark current to be dropped by not appending.
                    # Leave 'changes' flag
                    changes = True
                    # We don't append current; let the loop continue
                    continue

            # Rule 4: scraped token is the single letter (յ/զ/ց), parsed starts with that letter
            if s_form in LEADING_LETTERS and len(s_form) == 1 and p_form.startswith(s_form) and len(p_form) > 1:
                # Insert single-letter token before, with SA=No
                single = {
                    "token_id": p_tok["token_id"],  # temporary
                    "form": s_form,
                    "lemma": s_form,
                    "upostag": "_",
                    "xpostag": "_",
                    "feats": "_",
                    "head": "_",
                    "deprel": "_",
                    "deps": "_",
                    "misc": "SpaceAfter=No",
                }
                trimmed = dict(p_tok)
                trimmed["form"]  = p_form[1:]
                trimmed["lemma"] = p_tok["lemma"][1:] if len(p_tok["lemma"]) > 0 else p_tok["lemma"]

                new_list.append(single)
                new_list.append(trimmed)
                changes = True
                continue

            # Default: carry original parsed token
            new_list.append(p_tok)

        # Copy any leftover parsed tokens beyond zip length
        tail_start = len(list(zip(scraped, modified)))
        if tail_start < len(modified):
            new_list.extend(modified[tail_start:])

        # Remove the skip-next markers by skipping the immediately following token
        cleaned: List[Dict[str, object]] = []
        skip = False
        for t in new_list:
            if skip:
                skip = False
                continue
            if "__SKIP_NEXT__" in t:
                skip = True
                continue
            cleaned.append(t)

        if not changes:
            break
        modified = cleaned

    if iteration >= max_iters:
        print("[warn] Max iterations reached; stopping to avoid infinite loop.", file=sys.stderr)

    return renumber_tokens(modified)


def format_sentence(metadata: List[str], tokens: List[Dict[str, object]]) -> str:
    lines = list(metadata)
    lines.extend(format_token(t) for t in tokens)
    return "\n".join(lines)


# ---------- Orchestration ----------

def main() -> None:
    scraped = read_conllu(SCRAPED_PATH)
    parsed  = read_conllu(PARSED_PATH)

    # Build fast lookup for scraped by normalized text
    scraped_map: Dict[str, Tuple[str, str, List[str], List[str]]] = {
        normalize_text(text): (sid, text, meta, toks) for sid, text, meta, toks in scraped
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as out:
        for p_sid, p_text, p_meta, p_tok_lines in parsed:
            norm = normalize_text(p_text)

            # parse token dicts for parsed
            p_tokens = [tk for ln in p_tok_lines if (tk := parse_token_line(ln))]

            if norm in scraped_map:
                s_sid, s_text, _s_meta, s_tok_lines = scraped_map[norm]
                s_tokens = [tk for ln in s_tok_lines if (tk := parse_token_line(ln))]
                merged = process_and_modify_tokens(s_tokens, p_tokens)
                out.write(format_sentence(p_meta, merged) + "\n\n")
            else:
                # No match, write parsed as-is
                out.write("\n".join(p_meta + p_tok_lines) + "\n\n")

    print(f"[ok] Wrote: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
