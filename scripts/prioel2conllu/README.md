# prioel2conllu

Pipeline to convert **PRIOEL treebank** of the Classical Armenian Gospels (XML format: https://github.com/proiel/proiel-treebank/blob/master/armenian-nt.xml) into **UD treebank** (CoNLL-U format: https://github.com/UniversalDependencies/UD_Classical_Armenian-CAVaL) developed for the purposes of the CAVaL: Classical Armenian Valency Lexicon project. Besides a rule-based convertion of tagsets, the pipeline includes linguistic normalization, and enrich the target treebank with the original Armenian spelling, English translations of lemmas and verses and syntactic annotation for punctuation. The UD morphological annotation is further converted into Leipzig-style grammatical glosses (**Leipzig-style gloss list**).

## Highlights

- ~50 deterministic stages, each a small CLI script
- Robust regex/XML-like line processing (no external XML libs required)
- UD-style relation normalization (adv/atr/apos/etc.)
- Morphology folding into `FEATS`
- Multi-word tokens, empty nodes, punctuation & `SpaceAfter=No`
- Armenian transliteration round-trip
- Enrichment from CAVAL glosses + verse translations
- Final CoNLL-U reconstruction with `# text` / `# transliterated_text` / `# translated_text`

## Quickstart

```bash
# 1) Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) Run the full pipeline (reads from data/input, writes to data/output)
make pipeline

