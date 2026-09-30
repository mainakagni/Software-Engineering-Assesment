"""Runs the evaluation set through the answering pipeline the API uses.

    uv run python -m evaluation.run --label baseline
    uv run python -m evaluation.run --label top-k-3 --top-k 3

Settings come from the environment (.env), exactly as for the API; --top-k and --min-similarity
override one value for an experiment. The corpus is processed once into its own database
(EVAL_DATABASE_URL, default: a documind_eval database on the DATABASE_URL server). Each run writes
evaluation/results/<label>.json with the settings, every answer, what it cited and retrieved, and
the scores; `python -m evaluation.report` turns result files into tables.
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.db.session import make_session_factory
from app.errors import ServiceUnavailableError
from app.logging_config import configure_logging
from app.providers.factory import build_embedder, build_llm
from app.qa.service import AnswerResult, answer_question
from evaluation.corpus_db import ingest_corpus, prepare_database
from evaluation.dataset import EVALUATION_DIR, EvalQuestion, load_questions
from evaluation.metrics import Scored, contains_evidence, score, summarise

logger = logging.getLogger("evaluation")

RESULTS_DIR = EVALUATION_DIR / "results"
# Retries sit out per-minute rate limits: nobody is waiting on an evaluation run.
EVAL_RETRY_SETTINGS = {"provider_max_retries": 4, "provider_max_retry_wait_seconds": 65}


def eval_settings(args: argparse.Namespace) -> Settings:
    base = get_settings()
    database_url = os.environ.get("EVAL_DATABASE_URL") or make_url(base.database_url).set(
        database="documind_eval"
    ).render_as_string(hide_password=False)
    overrides: dict[str, Any] = {"database_url": database_url, **EVAL_RETRY_SETTINGS}
    if args.top_k is not None:
        overrides["retrieval_top_k"] = args.top_k
    if args.min_similarity is not None:
        overrides["retrieval_min_similarity"] = args.min_similarity
    return base.model_copy(update=overrides)


class RetryCounter(logging.Handler):
    """Counts provider retries and the time waited on them, so slow answers can be explained."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.retries = 0
        self.wait_seconds = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() == "provider.retry":
            self.retries += 1
            self.wait_seconds += float(getattr(record, "delay_seconds", 0.0))

    def take(self) -> dict[str, int]:
        """The counts since the last call, which start again from zero."""
        counts = {"retries": self.retries, "retry_wait_ms": round(self.wait_seconds * 1000)}
        self.retries, self.wait_seconds = 0, 0.0
        return counts


def to_record(question: EvalQuestion, result: AnswerResult) -> dict[str, Any]:
    """Everything about one answer, with full passage texts (needed for scoring)."""
    return {
        "id": question.id,
        "split": question.split,
        "type": question.type,
        "question": question.question,
        "found": result.grounded.found,
        "answer": result.grounded.answer,
        "refused_by": result.refused_by,
        "model_said_found": result.reply.found if result.reply else None,
        "citations": [
            {
                "document_name": c.chunk.document_name,
                "page_start": c.chunk.page_start,
                "page_end": c.chunk.page_end,
                "section": c.chunk.section,
                "quote": c.quote,
                "quote_verified": c.quote_verified,
                "passage": c.chunk.text,
            }
            for c in result.grounded.citations
        ],
        "retrieved": [
            {
                "document_name": chunk.document_name,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section": chunk.section,
                "similarity": round(chunk.similarity, 4),
                "text": chunk.text,
            }
            for chunk in result.retrieved
        ],
        "usage": result.usage,
    }


def compact(record: dict[str, Any], evidence: str | None) -> dict[str, Any]:
    """The record as saved: passage texts are replaced by whether they hold the evidence."""

    def holds(passage: str) -> bool | None:
        return contains_evidence(passage, evidence) if evidence else None

    return {
        **record,
        "citations": [
            {
                **{k: v for k, v in c.items() if k != "passage"},
                "holds_evidence": holds(c["passage"]),
            }
            for c in record["citations"]
        ],
        "retrieved": [
            {**{k: v for k, v in r.items() if k != "text"}, "holds_evidence": holds(r["text"])}
            for r in record["retrieved"]
        ],
    }


def git_commit() -> str | None:
    """The commit the run was made from, recorded next to the results."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        return subprocess.run(  # noqa: S603 - fixed arguments, no user input
            [git, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--label", required=True, help="name of the result file")
    parser.add_argument("--split", default="test", choices=["test", "dev", "all"])
    parser.add_argument("--top-k", type=int, dest="top_k")
    parser.add_argument("--min-similarity", type=float, dest="min_similarity")
    parser.add_argument(
        "--pause", type=float, default=4.0, help="seconds between questions (free-tier limits)"
    )
    parser.add_argument("--only", nargs="*", help="question IDs to run (default: the whole split)")
    parser.add_argument("--out-dir", type=Path, default=RESULTS_DIR, dest="out_dir")
    args = parser.parse_args(argv)

    settings = eval_settings(args)
    configure_logging(settings.log_level)
    prepare_database(settings.database_url)
    session_factory = make_session_factory(settings)
    embedder = build_embedder(settings, for_worker=True)
    llm = build_llm(settings)
    user_id = ingest_corpus(session_factory, settings, embedder)

    evalset = load_questions()
    questions = evalset.split(args.split)
    if args.only:
        questions = [q for q in questions if q.id in set(args.only)]
    records: list[dict[str, Any]] = []
    scores: list[Scored] = []
    stopped_early = None
    retry_counter = RetryCounter()
    logging.getLogger("app.providers.retry").addHandler(retry_counter)
    retry_counter.take()  # retries while processing the corpus are not part of any answer
    for number, question in enumerate(questions, start=1):
        try:
            with session_factory() as session:
                result = answer_question(
                    session, user_id, question.question, None,
                    embedder=embedder, llm=llm, settings=settings,
                )  # fmt: skip
        except ServiceUnavailableError as exc:
            stopped_early = f"{question.id}: {exc.message}"
            logger.error("evaluation.stopped", extra={"reason": stopped_early})
            break
        record = {**to_record(question, result), **retry_counter.take()}
        scored = score(question, record)
        scores.append(scored)
        records.append({**compact(record, question.evidence), "score": asdict(scored)})
        print(
            f"[{number}/{len(questions)}] {question.id} {question.type:<12} "
            f"{'ok ' if scored.behaved else 'BAD'} found={scored.found} "
            f"rank={scored.evidence_rank} {result.usage['latency_ms']} ms",
            flush=True,
        )
        if number < len(questions) and result.reply is not None:
            time.sleep(args.pause)

    output = {
        "label": args.label,
        "split": args.split,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "stopped_early": stopped_early,
        "settings": {
            "llm_model": settings.llm_model if settings.llm_provider == "gemini" else "fake",
            "llm_thinking_level": settings.llm_thinking_level,
            "llm_temperature": settings.llm_temperature,
            "embedding_model": (
                settings.embedding_model if settings.embedding_provider == "gemini" else "fake"
            ),
            "retrieval_top_k": settings.retrieval_top_k,
            "retrieval_min_similarity": settings.retrieval_min_similarity,
            "chunk_size_chars": settings.chunk_size_chars,
            "chunk_overlap_chars": settings.chunk_overlap_chars,
        },
        "summary": summarise(scores, settings.retrieval_top_k),
        "questions": records,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"{args.label}.json"
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))
    print(f"wrote {path}")
    return 1 if stopped_early else 0


if __name__ == "__main__":
    sys.exit(main())
