"""Run the retrieval eval over the committed corpus and print per-mode scores.

    env -u PYTHONPATH uv run python scripts/eval.py
"""
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from obsidian_librarian import eval as ev
from obsidian_librarian.config import Config
from obsidian_librarian.embed import EmbeddingClient

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "eval" / "corpus"
QUERIES = ROOT / "tests" / "eval" / "queries.yaml"


def main():
    load_dotenv()
    queries = ev.load_queries(QUERIES)
    cfg = Config()
    cfg.vault_path = str(CORPUS)
    cfg.index_path = tempfile.mkdtemp(prefix="obsidian-eval-")

    embedder = EmbeddingClient(cfg)
    n_chunks = ev.build_index(cfg, embedder)
    k = 5
    print(f"corpus: {len(queries)} queries, {n_chunks} chunks · k={k}\n")
    print(f"{'mode':8} {'Recall@k':9} {'MRR':6}")
    print("-" * 25)
    for mode in ("vector", "fts", "hybrid"):
        r = ev.evaluate(cfg, queries, mode, k=k, embedder=embedder)
        print(f"{mode:8} {r['recall_at_k']:<9.2f} {r['mrr']:.2f}")

    # subsets where keyword signal is expected to help dense-only
    for tag in ("acronym", "exact"):
        sub = ev.subset(queries, tag)
        if not sub:
            continue
        print(f"\n{tag} subset ({len(sub)} queries):")
        for mode in ("vector", "fts", "hybrid"):
            r = ev.evaluate(cfg, sub, mode, k=k, embedder=embedder)
            print(f"  {mode:8} Recall@k={r['recall_at_k']:.2f} MRR={r['mrr']:.2f}")


if __name__ == "__main__":
    main()
