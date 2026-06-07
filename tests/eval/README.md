# Retrieval evaluation set

A small, committed corpus with labelled `query → expected note` pairs, used to score
retrieval quality with **Recall@k** and **MRR** — turning "search feels good" into numbers.

- `corpus/` — ~13 short notes (finance, ML, Korean, distractors, near-duplicate ID pairs).
- `queries.yaml` — `query → expect` pairs, tagged (`acronym`, `exact`, `korean`, `paraphrase`).

## Run it

```bash
env -u PYTHONPATH uv run python scripts/eval.py     # per-mode Recall@k + MRR (needs VOYAGE_API_KEY)
env -u PYTHONPATH uv run pytest tests/test_eval.py  # offline fts gate + key-gated hybrid baseline
```

## What it's for (and a caveat)

Primary use is a **regression gate**: any change to chunking, modes, or merge weighting must not
drop the score. As of 2026-06-08, every mode (vector / fts / hybrid) scores **1.00** here —
`voyage-4-large` is strong enough that dense alone already saturates this small corpus, so the eval
does **not** yet demonstrate hybrid beating dense (the BM25 advantage is expected to show only at
larger scale / messier data). It is a perfect-score baseline to guard against regressions, not proof
of hybrid's edge. Grow the corpus with real notes to make it more discriminating.
