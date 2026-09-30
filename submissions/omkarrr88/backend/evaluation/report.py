"""Markdown tables from evaluation result files, for EVALUATION.md.

    uv run python -m evaluation.report evaluation/results/baseline.json [more result files...]

The first file is the main run: it gets the per-question table. All files go into one comparison
table, one column per run.
"""

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _get(summary: dict[str, Any], *keys: str) -> Any:
    value: Any = summary
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _fraction(summary: dict[str, Any], group: str, key: str) -> str:
    share, count = _get(summary, group, key), _get(summary, group, "count")
    if share is None or not count:
        return "n/a"
    return f"{_pct(share)} ({round(share * count)}/{count})"


def _latency(summary: dict[str, Any]) -> str:
    values = [_get(summary, "latency_ms", key) for key in ("mean", "p50", "p95")]
    return " / ".join("n/a" if value is None else str(value) for value in values) + " ms"


def _retries(summary: dict[str, Any]) -> str:
    count, wait_ms = (
        _get(summary, "provider_retries", "count"),
        _get(summary, "provider_retries", "wait_ms"),
    )
    return "n/a" if count is None else f"{count} ({(wait_ms or 0) / 1000:.0f} s)"


ROWS: list[tuple[str, Callable[[dict[str, Any]], str]]] = [
    ("Answerable: correct answer", lambda s: _fraction(s, "answerable", "correct")),
    ("Answerable: wrongly refused", lambda s: _fraction(s, "answerable", "wrongly_refused")),
    (
        "Answered, but a fact was wrong",
        lambda s: _pct(_get(s, "answerable", "wrong_when_answered")),
    ),
    (
        "Answers citing the evidence passage",
        lambda s: _pct(_get(s, "answerable", "cited_evidence")),
    ),
    ("Unanswerable: refused", lambda s: _fraction(s, "unanswerable", "refused")),
    ("Injection: handled correctly", lambda s: _fraction(s, "injection", "behaved")),
    ("Injection: forbidden text in answer", lambda s: str(_get(s, "injection", "leaked"))),
    ("Evidence retrieved in top k", lambda s: _pct(_get(s, "retrieval", "hit_rate"))),
    ("Retrieval MRR", lambda s: f"{_get(s, 'retrieval', 'mrr')}"),
    ("All questions handled correctly", lambda s: _pct(_get(s, "overall_behaved"))),
    ("Latency mean / p50 / p95", lambda s: _latency(s)),
    ("Provider retries (time waited)", lambda s: _retries(s)),
    ("Tokens per question", lambda s: f"{_get(s, 'tokens_per_question')}"),
    ("Estimated cost of the run", lambda s: f"${_get(s, 'cost_usd'):.4f}"),
]


def comparison_table(runs: list[dict[str, Any]]) -> str:
    header = "| Metric | " + " | ".join(
        f"{run['label']} (k={run['settings']['retrieval_top_k']})" for run in runs
    )
    lines = [header + " |", "|---" * (len(runs) + 1) + "|"]
    for name, render in ROWS:
        lines.append(f"| {name} | " + " | ".join(render(run["summary"]) for run in runs) + " |")
    return "\n".join(lines)


def question_table(run: dict[str, Any]) -> str:
    lines = [
        "| ID | Type | Question | Result | Found | Evidence rank | Latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in run["questions"]:
        scored = record["score"]
        question = record["question"]
        short = question if len(question) <= 70 else question[:67] + "..."
        result = "pass" if scored["behaved"] else "**fail**"
        found = "yes" if scored["found"] else "no"
        lines.append(
            f"| {record['id']} | {record['type']} | {short.replace('|', '/')} | {result} | "
            f"{found} | {scored['evidence_rank'] or '-'} | {scored['latency_ms']} ms |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Markdown tables from evaluation results.")
    parser.add_argument("results", nargs="+", type=Path)
    args = parser.parse_args(argv)
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in args.results]
    print(comparison_table(runs))
    print()
    print(question_table(runs[0]))


if __name__ == "__main__":
    main()
