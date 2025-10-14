#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scrape Classical Armenian sentences + English translations from
https://historians.armeniancathedral.org/ and emit sentence-level CoNLL-U blocks.

- Builds # sent_id from section prefix + in-page <b> numbering
- Extracts Armenian word tokens from <a> tags; pulls lemma/POS/features from the 'title' attribute
- Emits well-formed 10-column CoNLL-U lines (tab-separated)
- Adds punctuation as separate PUNCT tokens with 'punct' relation
- Writes one output file per subheading (the <h4> group) in the chosen out directory

Notes:
- Keeps the original feature string as FEATS (unchanged)
- Maps common tag shorthands (adj, adv, noun, verb, …) to UD UPOS; if unmapped, falls back to X
- Stores the original POS tag into MISC as OrigPOS=...
"""

from __future__ import annotations

import argparse
import html
import os
import re
import time
from pathlib import Path
from typing import Iterable, List, Tuple, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Config: supported POS tags in source + UD mapping ------------------------

POSSIBLE_POS: List[str] = [
    "adj", "adv", "conj", "intj", "noun", "part", "post", "prep",
    "prop.gntl", "prop.adv", "prop.adj", "prop",
    "verb.pot", "verb.prpt", "verb.res", "verb",
    "pron", "for", "num.ord", "num", "pron.adj"
]

# Regex to capture the above tags as atomic pieces (with optional trailing '.')
POS_PATTERN = re.compile(r'\b(?:' + '|'.join(re.escape(p) for p in POSSIBLE_POS) + r')\.?\b', flags=re.I)

# Map source tag(s) → UD UPOS (best-effort); fallback is "X"
UD_MAP = {
    "adj": "ADJ",
    "adv": "ADV",
    "conj": "CCONJ",        # source often uses 'conj' for coord. conj
    "intj": "INTJ",
    "noun": "NOUN",
    "part": "PART",
    "post": "ADP",
    "prep": "ADP",
    "prop": "PROPN",
    "prop.adj": "ADJ",
    "prop.adv": "ADV",
    "prop.gntl": "PROPN",   # gentilics -> proper-ish in these pages
    "verb": "VERB",
    "verb.pot": "VERB",
    "verb.prpt": "VERB",
    "verb.res": "VERB",
    "pron": "PRON",
    "pron.adj": "DET",
    "num": "NUM",
    "num.ord": "ADJ",       # Ordinals are adjectives in UD
    "for": "X",             # unknown/foreign tag in source -> X
}

# Punctuation to split/attach as individual tokens
PUNCT_RE = re.compile(r'[`:.,;՛՞՜«»]')

# --- HTTP helpers -------------------------------------------------------------

def build_session(verify_tls: bool, retries: int = 3, backoff: float = 0.5) -> requests.Session:
    """Create a session with retry + UA headers; optionally disable TLS verify."""
    sess = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; Arak29ToConllu/1.0; +https://github.com/)",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    })
    sess.verify = verify_tls
    return sess

# --- Core parsing -------------------------------------------------------------

def map_ud_upos(raw_pos: str) -> Tuple[str, Optional[str]]:
    """Map source POS string (possibly 'adj.' or 'prop.adj') to UD; returns (UD, orig_pos_or_none)."""
    rp = raw_pos.strip().rstrip(".").lower()
    if not rp:
        return "_", None
    ud = UD_MAP.get(rp, "X")
    return ud, rp if ud != rp else None

def extract_sentence(td_html: str, lang: str) -> Tuple[str, List[str]]:
    """
    Extracts the surface sentence and CoNLL-U token lines from a <td> cell.
    For Armenian cells: builds token lines.
    For English cells: only reconstructs the sentence string.
    """
    words: List[str] = []
    conllu_lines: List[str] = []
    row_number = 1

    def add_punct(punct: str) -> None:
        nonlocal row_number
        conllu_lines.append("\t".join([
            str(row_number), punct, punct,
            "PUNCT", "_", "_",
            "_", "punct", "_", "_"
        ]))
        words.append(punct)
        row_number += 1

    # Split around <a ...>text</a> or <b>...</b> (keep delimiters)
    parts = re.split(r'(<a [^>]+>[^<]+</a>|<b>[^<]+</b>)', td_html)

    for part in parts:
        if not part:
            continue
        if part.startswith("<a "):
            a = BeautifulSoup(part, "html.parser").find("a")
            if not a:
                continue
            word_text = a.get_text(strip=True)
            words.append(word_text)  # always contributes to the visible sentence

            if lang == "arm":
                title = a.get("title", "")
                # Expected format like: "lemma : features, Eng: gloss"
                base_form, features, orig_pos, gloss = parse_title(title, fallback_lemma=word_text)

                # UD UPOS from orig_pos; keep original in MISC if we change it or if unknown.
                upos, orig_pos_norm = map_ud_upos(orig_pos or "")

                misc_fields = []
                if gloss:
                    misc_fields.append(f"Gloss={gloss}")
                if orig_pos_norm and UD_MAP.get(orig_pos_norm, "X") != upos:
                    misc_fields.append(f"OrigPOS={orig_pos_norm}")
                misc = "|".join(misc_fields) if misc_fields else "_"

                # FEATS: keep as-is (already a cleaned string or "_")
                feats = features if features and features != "." else "_"

                conllu_lines.append("\t".join([
                    str(row_number),      # ID
                    word_text,            # FORM
                    base_form,            # LEMMA
                    upos,                 # UPOS
                    "_",                  # XPOS
                    feats,                # FEATS
                    "_",                  # HEAD
                    "_",                  # DEPREL
                    "_",                  # DEPS
                    misc,                 # MISC
                ]))
            row_number += 1

        elif part.startswith("<b>"):
            # Skip the numbering tag itself (we read numbering elsewhere)
            continue

        else:
            # Any in-between text: add punctuation tokens found there
            for punct in PUNCT_RE.findall(part):
                add_punct(punct)

    # Build display sentence (spacing, then tighten around punctuation)
    sentence = " ".join(words)
    sentence = re.sub(r" +", " ", sentence)
    sentence = re.sub(r" ([\.,:;`՜։»«?!])", r"\1", sentence)
    return sentence, conllu_lines

def parse_title(title: str, fallback_lemma: str) -> Tuple[str, str, str, str]:
    """
    Parse the Armenian <a title="..."> info.
    Expected shape: "<lemma> : <features>, Eng: <gloss>"
    Returns: (lemma, features, raw_pos, gloss)
    """
    title = html.unescape(title or "").strip()
    if not title:
        return fallback_lemma, "_", "", ""

    # Split English gloss part
    parts = title.split(", Eng:")
    eng_part = (parts[1].strip() if len(parts) > 1 else "")
    gloss = eng_part

    # Left piece: "lemma : features"
    left = parts[0]
    if ":" in left:
        lemma = left.split(":")[0].strip()
        feats = left.split(":")[1].strip()
    else:
        lemma = fallback_lemma
        feats = "_"

    # Extract and remove POS tags from feats (single or combined)
    pos_matches = POS_PATTERN.findall(feats)
    # Normalize matches and strip trailing dots
    raw_pos = "/".join([m.rstrip(".").strip().lower() for m in pos_matches]) if pos_matches else ""

    # Remove the POS fragments from feats string
    cleaned_feats = POS_PATTERN.sub("", feats).strip()
    if re.fullmatch(r"[./]*", cleaned_feats) or not cleaned_feats:
        cleaned_feats = "_"

    return lemma or fallback_lemma, cleaned_feats, raw_pos, gloss

def ensure_conllu_10cols(lines: Iterable[str]) -> bool:
    ok = True
    for i, ln in enumerate(lines, 1):
        cols = ln.split("\t")
        if len(cols) != 10:
            print(f"[warn] line {i} has {len(cols)} columns (expected 10): {ln}")
            ok = False
    return ok

# --- Page walkers -------------------------------------------------------------

def extract_sentences_from_subpage(session: requests.Session, subpage_url: str, subheading_prefix: str, delay: float) -> str:
    r = session.get(subpage_url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")

    sentences: List[str] = []

    armenian_tds = soup.find_all("td", class_="arm")
    english_tds = soup.find_all("td", class_="eng")
    for arm_td, eng_td in zip(armenian_tds, english_tds):
        b_tag = arm_td.find("b")
        if not (b_tag and b_tag.get_text(strip=True)):
            continue

        sent_id = f"# sent_id = {subheading_prefix}_{b_tag.get_text(strip=True)}"
        arm_sentence, conllu_lines = extract_sentence(str(arm_td), "arm")
        eng_sentence, _ = extract_sentence(str(eng_td), "eng")

        if ensure_conllu_10cols(conllu_lines):
            block = f"{sent_id}\n# text = {arm_sentence}\n# translated_text = {eng_sentence}\n" + "\n".join(conllu_lines)
            sentences.append(block)

    # be polite
    if delay > 0:
        time.sleep(delay)

    return "\n\n".join(sentences)

def scrape_index(index_url: str, out_dir: Path, verify_tls: bool, delay: float) -> List[Path]:
    session = build_session(verify_tls=verify_tls)
    r = session.get(index_url, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.content, "html.parser")
    saved: List[Path] = []

    # All top-level <h2> sections; we only keep specific Armenian authors
    for h2 in soup.find_all("h2"):
        txt = h2.get_text(strip=True)
        if "Ագաթանգեղոս" not in txt and "Խորենացի" not in txt:
            # Skip to next <h2> by ignoring unrelated siblings
            continue

        # Within this section, find divs holding sub-groups (style=padding:15px;)
        divs = h2.find_all_next("div", style=re.compile(r"padding:15px;"))
        for container in divs:
            # stop when we reach the next h2
            next_h2 = container.find_previous_sibling("h2")
            cur_h2 = h2 if next_h2 == h2 else None
            if not cur_h2:
                break

            for h4 in container.find_all("h4"):
                h4_text = h4.get_text(strip=True)
                if not h4_text:
                    continue
                subheading_prefix = h4_text.split(" - ")[0]
                safe_name = re.sub(r"[^\w\-\.]+", "_", h4_text).strip("_")
                out_path = out_dir / f"{safe_name}.txt"

                # Gather links within this container that match expected pattern
                links = container.find_all("a", href=re.compile(r"^book/t02Agat3_.*\.htm$"))
                # If you also need Khorēnac‘i pages later, adjust the regex accordingly.

                with out_path.open("w", encoding="utf-8") as fh:
                    for a in links:
                        sub_url = urljoin(index_url, a.get("href", ""))
                        try:
                            sentences = extract_sentences_from_subpage(session, sub_url, subheading_prefix, delay)
                        except requests.HTTPError as e:
                            print(f"[warn] {e} while fetching {sub_url}")
                            continue
                        if sentences:
                            fh.write(sentences + "\n\n")
                saved.append(out_path)

    return saved

# --- CLI ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Arak29 pages and emit CoNLL-U blocks per subsection.")
    p.add_argument("--index", default="https://historians.armeniancathedral.org/index.htm",
                   help="Index page to start from.")
    p.add_argument("--out-dir", type=Path, default=Path("data/output/arak29"),
                   help="Directory to write output *.txt files.")
    p.add_argument("--no-verify-tls", action="store_true", help="Skip TLS verification (not recommended).")
    p.add_argument("--delay", type=float, default=0.25, help="Delay between subpage requests (seconds).")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    saved = scrape_index(args.index, args.out_dir, verify_tls=not args.no_verify_tls, delay=args.delay)
    print(f"[ok] wrote {len(saved)} files to {args.out_dir}")

if __name__ == "__main__":
    main()
