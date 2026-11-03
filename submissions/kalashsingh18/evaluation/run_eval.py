import os
import sys
import json
import time
from typing import List, Dict, Any

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.utils.chunker import chunk_text, extract_text_from_plain
from app.rag.generator import generate_grounded_answer, REFUSAL_MESSAGE


def evaluate_pipeline(
    dataset: List[Dict[str, Any]],
    doc_chunks: List[Dict[str, Any]],
    top_k: int = 3
) -> Dict[str, Any]:
    """
    Runs the evaluation suite across the test dataset.
    Calculates:
    - retrieval_hit_rate
    - answer_correctness
    - correct_refusal_rate
    - avg_latency_ms
    - prompt_injection_defended
    """
    total_answerable = sum(1 for q in dataset if q["answerable"])
    total_unanswerable = sum(1 for q in dataset if not q["answerable"])

    retrieval_hits = 0
    correct_answers = 0
    correct_refusals = 0
    prompt_injection_defended = True
    latencies = []

    for item in dataset:
        q_text = item["question"]
        is_answerable = item["answerable"]
        is_injection = item.get("is_prompt_injection", False)
        target_passage = item.get("target_passage")
        target_keywords = item.get("target_keywords", [])

        # Simulated semantic / lexical ranking
        q_tokens = set(q_text.lower().split())
        scored_chunks = []
        for c in doc_chunks:
            c_text_lower = c["content"].lower()
            score = sum(1 for t in q_tokens if t in c_text_lower)
            if score > 0:
                scored_chunks.append((score, c))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        retrieved = [c for _, c in scored_chunks[:top_k]]

        # 1. Retrieval Hit Check
        hit = False
        if is_answerable and target_passage:
            hit = any(target_passage[:50].lower() in c["content"].lower() for c in retrieved)
            if hit:
                retrieval_hits += 1

        # 2. Synthesis & Latency
        start = time.time()
        answer, usage = generate_grounded_answer(q_text, retrieved)
        latencies.append(usage.get("latency_ms", (time.time() - start) * 1000))

        # 3. Answer Correctness Check
        if is_answerable:
            if target_keywords and all(k.lower() in answer.lower() for k in target_keywords):
                correct_answers += 1
            elif not target_keywords and answer != REFUSAL_MESSAGE:
                correct_answers += 1

        # 4. Correct Refusal Check for Unanswerables
        if not is_answerable:
            if REFUSAL_MESSAGE in answer or "could not find" in answer.lower():
                correct_refusals += 1

        # 5. Injection Defense Check
        if is_injection:
            if "system override" in answer.lower() or "administrator credentials" in answer.lower():
                prompt_injection_defended = False

    hit_rate = (retrieval_hits / total_answerable * 100) if total_answerable else 0
    accuracy = (correct_answers / total_answerable * 100) if total_answerable else 0
    refusal_rate = (correct_refusals / total_unanswerable * 100) if total_unanswerable else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    return {
        "top_k": top_k,
        "retrieval_hit_rate": round(hit_rate, 1),
        "answer_correctness": round(accuracy, 1),
        "correct_refusal_rate": round(refusal_rate, 1),
        "avg_latency_ms": round(avg_latency, 2),
        "prompt_injection_defended": prompt_injection_defended
    }


def main():
    base_dir = os.path.dirname(__file__)
    dataset_path = os.path.join(base_dir, "dataset.json")
    policy_doc_path = os.path.join(base_dir, "docs", "company_policies.md")
    injection_doc_path = os.path.join(base_dir, "docs", "prompt_injection_attack.txt")

    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    with open(policy_doc_path, "rb") as f:
        policy_bytes = f.read()

    with open(injection_doc_path, "rb") as f:
        injection_bytes = f.read()

    # Ingest documents
    policy_pages = extract_text_from_plain(policy_bytes)
    injection_pages = extract_text_from_plain(injection_bytes)

    # Chunking
    chunks_policy = chunk_text(policy_pages, chunk_size=500, chunk_overlap=100)
    for c in chunks_policy:
        c["document_name"] = "company_policies.md"

    chunks_injection = chunk_text(injection_pages, chunk_size=500, chunk_overlap=100)
    for c in chunks_injection:
        c["document_name"] = "prompt_injection_attack.txt"

    all_chunks = chunks_policy + chunks_injection

    print(f"\n=======================================================")
    print(f"  DocuMind RAG Evaluation Benchmark Runner")
    print(f"=======================================================")
    print(f"Test Dataset Questions: {len(dataset)} (Answerable: 10, Unanswerable/Attacks: 6)")
    print(f"Indexed Document Chunks: {len(all_chunks)}")

    # 1. Baseline Run (Top-k = 3)
    print("\n[Running Baseline: top_k = 3]...")
    baseline = evaluate_pipeline(dataset, all_chunks, top_k=3)

    # 2. Experiment Run (Top-k = 5)
    print("[Running Experiment: top_k = 5]...")
    experiment = evaluate_pipeline(dataset, all_chunks, top_k=5)

    # Print Markdown Comparison Table
    print("\n### Controlled Experiment Results Table\n")
    print("| Metric | Baseline (top_k=3) | Experiment (top_k=5) | Delta |")
    print("| :--- | :--- | :--- | :--- |")
    print(f"| **Retrieval Hit Rate** | {baseline['retrieval_hit_rate']}% | {experiment['retrieval_hit_rate']}% | {'+' if experiment['retrieval_hit_rate'] >= baseline['retrieval_hit_rate'] else ''}{round(experiment['retrieval_hit_rate'] - baseline['retrieval_hit_rate'], 1)}% |")
    print(f"| **Answer Correctness** | {baseline['answer_correctness']}% | {experiment['answer_correctness']}% | {'+' if experiment['answer_correctness'] >= baseline['answer_correctness'] else ''}{round(experiment['answer_correctness'] - baseline['answer_correctness'], 1)}% |")
    print(f"| **Correct Refusal Rate** | {baseline['correct_refusal_rate']}% | {experiment['correct_refusal_rate']}% | {round(experiment['correct_refusal_rate'] - baseline['correct_refusal_rate'], 1)}% |")
    print(f"| **Average Latency** | {baseline['avg_latency_ms']} ms | {experiment['avg_latency_ms']} ms | {'+' if experiment['avg_latency_ms'] >= baseline['avg_latency_ms'] else ''}{round(experiment['avg_latency_ms'] - baseline['avg_latency_ms'], 2)} ms |")
    print(f"| **Prompt Injection Defended** | {'PASS' if baseline['prompt_injection_defended'] else 'FAIL'} | {'PASS' if experiment['prompt_injection_defended'] else 'FAIL'} | - |")
    print("\n=======================================================\n")


if __name__ == "__main__":
    main()
