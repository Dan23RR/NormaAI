#!/usr/bin/env python3
"""Export Qdrant knowledge base to JSONL training dataset for router fine-tuning.

Connects to Qdrant, scrolls all chunks from the eu_regulations collection,
and creates a classification dataset where each chunk maps to its framework label.

Also generates synthetic queries by paraphrasing chunk text.

Output: data/router_training.jsonl
"""

import json
import os
import random
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("QDRANT_COLLECTION", "eu_regulations")
OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "router_training.jsonl"
BATCH_SIZE = 100

ROUTER_SYSTEM = (
    "You are a regulatory intelligence router. Given a text about EU regulations, "
    "identify the framework(s) it belongs to and the complexity of the content. "
    "Return JSON: {\"frameworks\": [...], \"complexity\": \"simple|medium|complex\"}"
)

QUERY_TEMPLATES = [
    "What are the requirements of {framework}?",
    "Explain the obligations under {framework}.",
    "How does {framework} affect my company?",
    "What are the deadlines for {framework} compliance?",
    "Summarize {framework} Article {article}.",
]


def export_chunks():
    """Export all chunks from Qdrant to JSONL training format."""
    print(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60)

    try:
        info = client.get_collection(COLLECTION)
        total = info.points_count
        print(f"Collection '{COLLECTION}': {total} chunks")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    examples = []
    offset = None
    exported = 0

    while True:
        records, next_offset = client.scroll(
            collection_name=COLLECTION,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        if not records:
            break

        for record in records:
            payload = record.payload or {}
            text = payload.get("text", "")
            framework = payload.get("framework", "UNKNOWN")
            article = payload.get("article_number", "")

            if not text or len(text) < 50:
                continue

            # Classification example: chunk text → framework label
            snippet = text[:500] if len(text) > 500 else text
            expected = json.dumps({
                "frameworks": [framework],
                "complexity": "simple" if len(text) < 200 else "medium",
            })

            examples.append({
                "messages": [
                    {"role": "system", "content": ROUTER_SYSTEM},
                    {"role": "user", "content": snippet},
                    {"role": "assistant", "content": expected},
                ]
            })

            # Synthetic query examples
            for template in random.sample(QUERY_TEMPLATES, min(2, len(QUERY_TEMPLATES))):
                query = template.format(framework=framework, article=article or "1")
                expected_q = json.dumps({
                    "frameworks": [framework],
                    "complexity": "simple",
                })
                examples.append({
                    "messages": [
                        {"role": "system", "content": ROUTER_SYSTEM},
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": expected_q},
                    ]
                })

            exported += 1

        offset = next_offset
        print(f"  Exported {exported} chunks...")

        if next_offset is None:
            break

    # Shuffle and write
    random.shuffle(examples)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nDone! {len(examples)} training examples written to {OUTPUT_FILE}")
    print(f"  - {exported} chunks processed")
    print(f"  - {len(examples) - exported} synthetic queries generated")


if __name__ == "__main__":
    export_chunks()
