"""The best retrieval similarity for each question, used to choose RETRIEVAL_MIN_SIMILARITY.

    uv run python -m evaluation.floor --split dev

Only the embedding service is called, never the model. The floor is the first refusal gate: a
question whose best passage is less similar than the floor is refused without asking the model.
It must sit below every answerable question; whatever unanswerable questions it also stops are a
saving, the rest are left to the second gate. The result is written to
evaluation/results/floor-<split>.json.
"""

import argparse
import json
from typing import Any

from app.db.session import make_session_factory
from app.logging_config import configure_logging
from app.providers.factory import build_embedder
from app.qa.retrieval import search_chunks
from evaluation.corpus_db import ingest_corpus, prepare_database
from evaluation.dataset import load_questions
from evaluation.run import RESULTS_DIR, eval_settings

MARGIN = 0.05  # below the least similar answerable question, to leave room for rephrasings


def suggest_floor(rows: list[dict[str, Any]]) -> float | None:
    answerable = [row["top_similarity"] for row in rows if row["should_answer"]]
    return round(min(answerable) - MARGIN, 2) if answerable else None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Top similarity per question.")
    parser.add_argument("--split", default="dev", choices=["test", "dev", "all"])
    args = parser.parse_args(argv)

    settings = eval_settings(argparse.Namespace(top_k=None, min_similarity=None))
    configure_logging(settings.log_level)
    prepare_database(settings.database_url)
    session_factory = make_session_factory(settings)
    embedder = build_embedder(settings, for_worker=True)
    user_id = ingest_corpus(session_factory, settings, embedder)

    rows: list[dict[str, Any]] = []
    for question in load_questions().split(args.split):
        vector = embedder.embed_query(question.question)
        with session_factory() as session:
            [best] = search_chunks(session, user_id, vector, k=1)
        rows.append(
            {
                "id": question.id,
                "type": question.type,
                "should_answer": question.should_answer,
                "top_similarity": round(best.similarity, 4),
                "top_document": best.document_name,
            }
        )

    floor = suggest_floor(rows)
    for row in sorted(rows, key=lambda row: row["top_similarity"]):
        marker = "answer " if row["should_answer"] else "refuse "
        print(f"{row['top_similarity']:.3f}  {marker} {row['id']:<4} {row['top_document']}")
    stopped = sum(
        1 for row in rows if not row["should_answer"] and floor and row["top_similarity"] < floor
    )
    unanswerable = sum(1 for row in rows if not row["should_answer"])
    print(f"suggested floor: {floor} (stops {stopped} of {unanswerable} questions to refuse)")

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"floor-{args.split}.json"
    output = {"split": args.split, "margin": MARGIN, "suggested_floor": floor, "questions": rows}
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
