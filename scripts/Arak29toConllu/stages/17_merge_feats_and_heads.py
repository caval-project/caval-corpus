#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 17 — Merge FEATS and heads from parsed into scraped (per-token alignment).

What it does
------------
For each sentence, match scraped vs. parsed by normalized "# text".
Then, for each token (skipping MWT/empty nodes):
  • If token_id matches AND forms (case-insensitive) match:
      - copy HEAD and DEPREL from parsed → scraped
      - if parsed UPOS is one of scraped's UPOS options (scraped may be "NOUN/PROPN"):
          · set UPOS := parsed UPOS
          · FEATS := disambiguate(scraped FEATS by preferring parser’s single value when compatible)
        else:
          · keep scraped FEATS as-is
  • Otherwise, keep the scraped token unchanged.

Input/Output
------------
• Reads a single file named `input`
  The file must contain two sections separated by a delimiter line:
    ### SCRAPED
    (scraped CoNLL-U content)

    ### PARSED
    (parsed  CoNLL-U content)

• Writes `output` (merged CoNLL-U)

Notes
-----
- Multi-word tokens (e.g., "2-3") and empty nodes (e.g., "1.1") are ignored for token-level merging.
- FEATS disambiguation keeps the parser’s value when it belongs to the set of scraped alternatives for that key; otherwise it keeps all scraped values for the key.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import re
import sys


INPUT_PATH  = Path("input")
OUTPUT_PATH = Path("output")

DELIM_SCRAPED = "### SCRAPED"
DELIM_PARSED  = "### PARSED"


# ---------- Helpers ----------

def normalize_text(text: str) -> str:
    """Lowercase and strip punctuation for robust sentence matching."""
    return re.sub(r"[^\w\s]", "", text.lower())


def split_input_into_sections(raw: str) -> Tuple[str, str]:
    """
    Split the single `input` file into (scraped, parsed) sections using
    the explicit delimiters.
    """
    # Normalize line endings and split around our markers
    parts = re.split(rf"^{DELIM_SCRAPED}\s*$", raw, flags=re.MULTILINE)
    if len(parts) != 2:
        raise ValueError(
            "Could not find '### SCRAPED' delimiter in 'input'.\n"
            "Expected format:\n\n"
            "### SCRAPED\n"
            "<scraped conllu>\n"
            "\n### PARSED\n"
            "<parsed conllu>\n"
        )
    after_scraped = parts[1]
    parts2 = re.split(rf"^{DELIM_PARSED}\s*$", after_scraped, flags=re.MULTILINE)
    if len(parts2) != 2:
        raise ValueError("Could not find '### PARSED' delimiter in 'input'.")
    scraped, parsed = parts2[0].strip(), parts2[1].strip()
    if not scraped or not parsed:
        raise ValueError("One of the sections is empty. Please provide both scraped and parsed content.")
    return scraped, parsed


def read_conllu_blocks(text: str) -> List[str]:
    """Split CoNLL-U text into sentence blocks."""
    return [b for b in text.strip().split("\n\n") if b.strip()]


def extract_sentences(conllu_text: str) -> List[Tuple[str, str, List[str], List[str]]]:
    """
    Return a list of (sent_id, text, metadata_lines, token_lines).
    """
    out: List[Tuple[str, str, List[str], List[str]]] = []
    for block in read_conllu_blocks(conllu_text):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        meta  = [ln for ln in lines if ln.startswith("#")]
        toks  = [ln for ln in lines if not ln.startswith("#")]
        sid   = next((m.split("=", 1)[1].strip() for m in meta if m.startswith("# sent_id")), None)
        text  = next((m.split("=", 1)[1].strip() for m in meta if m.startswith("# text")),    None)
        if sid is not None and text is not None:
            out.append((sid, text, meta, toks))
    return out


def parse_token_line(line: str) -> Optional[Dict[str, str]]:
    """
    Parse a token line into a dict. Skip MWTs (ids with '-') and empty nodes (ids with '.').
    """
    cols = line.split("\t")
    if len(cols) != 10:
        return None
    tid = cols[0]
    if "-" in tid or "." in tid:
        return None
    return {
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


def format_token(t: Dict[str, str]) -> str:
    return "\t".join([
        t["token_id"],
        t["form"],
        t["lemma"],
        t["upostag"],
        t["xpostag"],
        t["feats"],
        t["head"],
        t["deprel"],
        t["deps"],
        t["misc"],
    ])


# ---------- FEATS disambiguation ----------

def disambiguate_feats(scraped_feats: str, parsed_feats: str) -> str:
    """
    Keep parser’s single value for a key if it appears among the scraped alternatives.
    Otherwise, keep all scraped alternatives for that key.
    """
    if not scraped_feats or scraped_feats == "_":
        return parsed_feats if
