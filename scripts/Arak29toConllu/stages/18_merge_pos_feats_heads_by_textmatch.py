#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
18_merge_pos_feats_heads_by_textmatch.py

Merge two CoNLL-U files by normalized # text. For each matched sentence:
- HEAD and DEPREL come from the parsed file.
- UPOS from parsed is accepted only if it appears in scraped's slash-separated UPOS list.
- FEATS are disambiguated: for ambiguous scraped keys prefer parser's single value.

I/O (fixed by project convention):
- Read:  ./input/scraped.conllu  and  ./input/parsed.conllu
- Write: ./output
"""

from __future__ import annotations
import os
import re
from typing import Dict, List, Tuple

# --------------------- I/O LOCATIONS (fixed names) --------------------- #
INPUT_DIR = "input"
SCRAPED_IN = os.path.join(INPUT_DIR, "scraped.conllu")
PARSED_IN  = os.path.join(INPUT_DIR, "parsed.conllu")
OUTPUT_OUT = "output"  # exact filename "output" in project root

# -------------------------- Normalization ------------------------------ #

_ws_re  = re.compile(r"\s+", flags=re.UNICODE)
# remove anything that's not a unicode word char or whitespace
# (Python's \w is Unicode-aware; this keeps letters/digits/underscore across scripts)
_strip_punct_re = re.compile(r"[^\w\s]+", flags=re.UNICODE)

def normalize_text(text: str) -> str:
    txt = text.lower()
    txt = _strip_punct_re.sub("", txt)
    txt = _ws_re.sub(" ", txt).strip()
    return txt

# -------------------------- CoNLL-U helpers ---------------------------- #

REQUIRED_COLS = 10

def parse_conllu_sentence(block: str) -> List[Dict[str, str]]:
    """Parse a single CoNLL-U sentence block (including comments) into token dicts.
    Keeps multiword IDs (e.g., '1-2'). Skips empty/comment lines."""
    tokens: List[Dict[str, str]] = []
    for line in block.strip().split("\n"):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < REQUIRED_COLS:
            # Defensive: skip malformed lines
            continue
        token = {
            "token_id": cols[0],
            "form":     cols[1],
            "lemma":    cols[2],
            "upostag":  cols[3],
            "xpostag":  cols[4],
            "feats":    cols[5],
            "head":     cols[6],
            "deprel":   cols[7],
            "deps":     cols[8],
            "misc":     cols[9],
        }
        tokens.append(token)
    return tokens

def format_conllu_sentence(tokens: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for t in tokens:
        # Ensure underscores for missing/empty fields
        row = [
            t.get("token_id", "_") or "_",
            t.get("form", "_") or "_",
            t.get("lemma", "_") or "_",
            t.get("upostag", "_") or "_",
            t.get("xpostag", "_") or "_",
            t.get("feats", "_") or "_",
            t.get("head", "_") or "_",
            t.get("deprel", "_") or "_",
            t.get("deps", "_") or "_",
            t.get("misc", "_") or "_",
        ]
        lines.append("\t".join(row))
    return "\n".join(lines)

def extract_sentences_from_file(path: str) -> List[Tuple[str, str, str, List[str], List[Dict[str, str]]]]:
    """Return list of tuples:
       (sent_id, raw_text, normalized_text, metadata_lines, tokens)"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        return []

    sentences = []
    for block in content.split("\n\n"):
        if not block.strip():
            continue
        lines = block.split("\n")
        meta = [ln for ln in lines if ln.startswith("#")]
        toks = parse_conllu_sentence(block)

        sent_id_line = next((ln for ln in meta if ln.startswith("# sent_id")), None)
        text_line    = next((ln for ln in meta if ln.startswith("# text")), None)

        if not sent_id_line or not text_line:
            # Require both to participate in matching
            continue

        sent_id = sent_id_line.split("=", 1)[1].strip()
        text    = text_line.split("=", 1)[1].strip()
        norm    = normalize_text(text)
        sentences.append((sent_id, text, norm, meta, toks))
    return sentences

# ----------------------- FEATS disambiguation -------------------------- #

def _parse_feats_to_dict(feats: str) -> Dict[str, List[str]]:
    """Parse FEATS string into dict: key -> list of values (preserves multiplicity)."""
    if not feats or feats == "_" or feats.strip() == "":
        return {}
    out: Dict[str, List[str]] = {}
    for item in feats.split("|"):
        if not item or item == "_" or "=" not in item:
            continue
        k, v = item.split("=", 1)
        out.setdefault(k, []).append(v)
    return out

def disambiguate_feats(scraped_feats: str, parsed_feats: str) -> str:
    """Prefer parser values to resolve ambiguity; otherwise keep scraped."""
    # If no scraped features, use parser verbatim
    if not scraped_feats or scraped_feats == "_":
        return parsed_feats if parsed_feats and parsed_feats.strip() else "_"

    scraped = _parse_feats_to_dict(scraped_feats)
    parsed  = _parse_feats_to_dict(parsed_feats)

    if not parsed:
        # Parser provides nothing -> keep scraped as-is
        return scraped_feats

    final_pairs: List[Tuple[str, str]] = []

    for key in sorted(scraped.keys()):
        values = scraped[key]
        uniq_values = sorted(set(values))
        if len(uniq_values) > 1:
            # ambiguous in scraped -> take parser's single value if present
            if key in parsed and len(set(parsed[key])) >= 1:
                # pick first (parser should be single-valued per key in CoNLL-U)
                final_pairs.append((key, parsed[key][0]))
            else:
                for v in uniq_values:
                    final_pairs.append((key, v))
        else:
            sv = uniq_values[0]
            if key in parsed:
                pv = parsed[key][0]
                if pv == sv:
                    final_pairs.append((key, sv))
                else:
                    # parser disagrees: keep scraped per spec
                    final_pairs.append((key, sv))
            else:
                final_pairs.append((key, sv))

    if not final_pairs:
        return "_"
    return "|".join(f"{k}={v}" for k, v in final_pairs)

# ---------------------------- Merge logic ------------------------------ #

def merge_sentences(scraped_tokens: List[Dict[str, str]],
                    parsed_tokens:  List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Merge token-by-token by matching token_id and case-insensitive form."""
    parsed_by_id: Dict[str, Dict[str, str]] = {
        t["token_id"]: t for t in parsed_tokens
    }
    merged: List[Dict[str, str]] = []

    for s_tok in scraped_tokens:
        p_tok = parsed_by_id.get(s_tok["token_id"])
        if p_tok and s_tok.get("form", "").lower() == p_tok.get("form", "").lower():
            # Override HEAD and DEPREL
            s_tok["head"]   = p_tok.get("head", s_tok.get("head", "_")) or "_"
            s_tok["deprel"] = p_tok.get("deprel", s_tok.get("deprel", "_")) or "_"

            # UPOS gating: only accept parser's tag if it's allowed by scraped's list
            scraped_pos_list = (s_tok.get("upostag") or "_").split("/")
            parsed_pos = p_tok.get("upostag") or "_"
            if parsed_pos in scraped_pos_list:
                s_tok["upostag"] = parsed_pos
                # FEATS: disambiguate with parser's feats
                s_tok["feats"] = disambiguate_feats(s_tok.get("feats") or "_",
                                                    p_tok.get("feats") or "_")
            # else: keep scraped UPOS/FEATS as-is
        # else: keep scraped token unchanged
        merged.append(s_tok)
    return merged

# ------------------------------ Driver -------------------------------- #

def process_files(scraped_path: str, parsed_path: str, output_path: str) -> None:
    scraped = extract_sentences_from_file(scraped_path)
    parsed  = extract_sentences_from_file(parsed_path)

    # Index parsed by normalized text (handle possible duplicates -> list)
    idx: Dict[str, List[Tuple[str, str, str, List[str], List[Dict[str, str]]]]] = {}
    for p in parsed:
        _, _, norm, _, _ = p
        idx.setdefault(norm, []).append(p)

    matched_ids: List[Tuple[str, str]] = []

    with open(output_path, "w", encoding="utf-8") as out:
        for s in scraped:
            s_id, s_text, s_norm, s_meta, s_toks = s
            candidates = idx.get(s_norm, [])
            if candidates:
                # if multiple parsed sentences share normalized text, take the first
                p_id, _, _, _, p_toks = candidates[0]
                merged_tokens = merge_sentences(s_toks, p_toks)
                merged_body = format_conllu_sentence(merged_tokens)
                out.write("\n".join(s_meta + [merged_body]) + "\n\n")
                matched_ids.append((s_id, p_id))
            else:
                # No match: write scraped unchanged
                out.write("\n".join(s_meta + [format_conllu_sentence(s_toks)]) + "\n\n")

    if matched_ids:
        print("Matched sentences (scraped_id, parsed_id):")
        for a, b in matched_ids:
            print(f"{a}, {b}")

if __name__ == "__main__":
    # Ensure input paths exist; raise clear errors otherwise
    if not os.path.isdir(INPUT_DIR):
        raise SystemExit(f"ERROR: '{INPUT_DIR}' directory not found. Create it and add 'scraped.conllu' and 'parsed.conllu'.")
    if not os.path.exists(SCRAPED_IN):
        raise SystemExit(f"ERROR: missing {SCRAPED_IN}")
    if not os.path.exists(PARSED_IN):
        raise SystemExit(f"ERROR: missing {PARSED_IN}")

    process_files(SCRAPED_IN, PARSED_IN, OUTPUT_OUT)
