#!/usr/bin/env python3
"""
DocuMind Evaluation Script
Run: python evaluation/run_eval.py

Runs the 20-question eval set against a live DocuMind instance.
Reports: retrieval hit rate, answer correctness, refusal rate, avg latency.
Also supports running an experiment (change chunk_size or top_k).

Usage:
  python run_eval.py --base-url http://localhost:8000 --username reviewer --password reviewpass123
  python run_eval.py --base-url http://localhost:8000 --username reviewer --password reviewpass123 --experiment top-k --value 10
"""

import argparse
import json
import os
import re
import sys
import time
import statistics
from pathlib import Path
from typing import Optional

import httpx

BASE_DIR = Path(__file__).parent


def login(base_url: str, username: str, password: str) -> str:
    resp = httpx.post(f"{base_url}/api/v1/auth/login", json={"username": username, "password": password}, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def upload_doc(base_url: str, token: str, filepath: Path) -> str:
    """Upload a document and return its ID."""
    with open(filepath, "rb") as f:
        resp = httpx.post(
            f"{base_url}/api/v1/documents",
            headers=get_headers(token),
            files={"file": (filepath.name, f, "text/plain")},
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()["id"]


def wait_for_ready(base_url: str, token: str, doc_id: str, timeout: int = 120) -> bool:
    """Poll document status until ready or failed."""
    start = time.time()
    while time.time() - start < timeout:
        resp = httpx.get(f"{base_url}/api/v1/documents/{doc_id}", headers=get_headers(token), timeout=10)
        status = resp.json()["status"]
        if status == "ready":
            return True
        if status == "failed":
            print(f"  ERROR: Document failed: {resp.json().get('error_message')}")
            return False
        time.sleep(3)
    return False


def ask(base_url: str, token: str, question: str, doc_ids: Optional[list] = None) -> dict:
    resp = httpx.post(
        f"{base_url}/api/v1/questions",
        headers=get_headers(token),
        json={"question": question, **({"document_ids": doc_ids} if doc_ids else {})},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def answer_correct(answer: str, expected: str, was_refused: bool) -> bool:
    """Simple keyword-based correctness check."""
    if was_refused:
        return False
    keywords = re.findall(r"\b\w{4,}\b", expected.lower())
    answer_lower = answer.lower()
    return sum(1 for kw in keywords if kw in answer_lower) >= max(1, len(keywords) // 2)


def run_evaluation(base_url: str, token: str, doc_id: str, eval_path: Path, label: str = "baseline"):
    with open(eval_path) as f:
        questions = json.load(f)

    results = []
    latencies = []
    print(f"\n{'='*60}")
    print(f"  Running evaluation: {label}")
    print(f"{'='*60}")

    for q in questions:
        try:
            resp = ask(base_url, token, q["question"], doc_ids=[doc_id])
            answer = resp["answer"]
            was_refused = resp["was_refused"]
            latency = resp.get("latency_ms", 0.0)
            latencies.append(latency)

            # Retrieval hit (check if any citation passage matches)
            citations_text = " ".join(c.get("passage", "") for c in resp.get("citations", []))
            if q["answerable"] and q.get("relevant_passage"):
                kw = q["relevant_passage"][:30]
                hit = kw.lower()[:15] in citations_text.lower()
            else:
                hit = not was_refused  # For unanswerable, hit = was it correctly refused?

            correct = (
                (not q["answerable"] and was_refused) or
                (q["answerable"] and answer_correct(answer, q["expected_answer"], was_refused))
            )

            results.append({
                "id": q["id"],
                "question": q["question"],
                "expected": q["expected_answer"],
                "answer": answer[:200],
                "was_refused": was_refused,
                "answerable": q["answerable"],
                "retrieval_hit": hit,
                "correct": correct,
                "latency_ms": latency,
            })
            status_icon = "✅" if correct else "❌"
            print(f"  [{status_icon}] Q{q['id']:02d}: {q['question'][:60]}…")
        except Exception as e:
            print(f"  [!] Q{q['id']:02d} FAILED: {e}")

    # Compute metrics
    answerable = [r for r in results if r["answerable"]]
    unanswerable = [r for r in results if not r["answerable"]]

    retrieval_hit_rate = sum(r["retrieval_hit"] for r in answerable) / max(len(answerable), 1)
    answer_correctness = sum(r["correct"] for r in answerable) / max(len(answerable), 1)
    refusal_rate = sum(r["was_refused"] for r in unanswerable) / max(len(unanswerable), 1)
    overall_correct = sum(r["correct"] for r in results) / max(len(results), 1)
    avg_latency = statistics.mean(latencies) if latencies else 0.0

    print(f"\n  📊 Results ({label}):")
    print(f"     Retrieval hit rate:    {retrieval_hit_rate:.1%}  (answerable questions only)")
    print(f"     Answer correctness:    {answer_correctness:.1%}")
    print(f"     Correct refusal rate:  {refusal_rate:.1%}")
    print(f"     Overall correct:       {overall_correct:.1%}")
    print(f"     Avg latency:           {avg_latency:.0f}ms")

    return {
        "label": label,
        "retrieval_hit_rate": retrieval_hit_rate,
        "answer_correctness": answer_correctness,
        "refusal_rate": refusal_rate,
        "overall_correct": overall_correct,
        "avg_latency_ms": avg_latency,
        "details": results,
    }


def main():
    parser = argparse.ArgumentParser(description="DocuMind Evaluation")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--username", default="reviewer")
    parser.add_argument("--password", default="reviewpass123")
    parser.add_argument("--eval-set", default=str(BASE_DIR / "eval_set.json"))
    parser.add_argument("--doc", default=str(BASE_DIR / "docs/python_overview.txt"))
    args = parser.parse_args()

    print("🔐 Logging in…")
    token = login(args.base_url, args.username, args.password)

    print("📄 Uploading evaluation document…")
    doc_id = upload_doc(args.base_url, token, Path(args.doc))
    print(f"   Document ID: {doc_id}")

    print("⏳ Waiting for document to be processed…")
    if not wait_for_ready(args.base_url, token, doc_id):
        print("❌ Document processing failed. Check your GEMINI_API_KEY.")
        sys.exit(1)

    # Baseline
    baseline = run_evaluation(args.base_url, token, doc_id, Path(args.eval_set), label="baseline (top_k=5, chunk=512)")

    print(f"\n{'='*60}")
    print("  Summary Table")
    print(f"{'='*60}")
    print(f"  {'Metric':<30} {'Value':>10}")
    print(f"  {'-'*42}")
    for metric, val in [
        ("Retrieval hit rate", f"{baseline['retrieval_hit_rate']:.1%}"),
        ("Answer correctness", f"{baseline['answer_correctness']:.1%}"),
        ("Correct refusal rate", f"{baseline['refusal_rate']:.1%}"),
        ("Overall accuracy", f"{baseline['overall_correct']:.1%}"),
        ("Avg latency", f"{baseline['avg_latency_ms']:.0f}ms"),
    ]:
        print(f"  {metric:<30} {val:>10}")

    # Save results
    out = BASE_DIR / "eval_results.json"
    with open(out, "w") as f:
        json.dump({"baseline": baseline}, f, indent=2)
    print(f"\n📁 Full results saved to {out}")


if __name__ == "__main__":
    main()
