#!/usr/bin/env python3
"""Evaluate Atlas search against a user-provided JSONL golden corpus.

Each line must contain:
  {"query": "...", "relevant_video_keys": ["video-key", ...]}

The evaluator never invents labels. It reports recall@k, reciprocal rank, and
nDCG for the exact database and corpus supplied by the operator.
"""

from __future__ import annotations

import argparse
import json
import math
import sys


def _dcg(found, relevant):
    score = 0.0
    for rank, key in enumerate(found, 1):
        if key in relevant:
            score += 1.0 / math.log2(rank + 1)
    return score


def evaluate(db_path: str, corpus_path: str, ks=(1, 5, 10)) -> dict:
    from atlas import config, ingest, search
    config.DB_PATH = db_path
    conn = ingest.connect()
    ingest.ensure_meta(conn)
    rows = []
    with open(corpus_path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            query = str(item.get("query") or "").strip()
            relevant = [str(v) for v in (item.get("relevant_video_keys") or [])]
            if query and relevant:
                rows.append((query, relevant))
            elif query:
                raise ValueError(f"line {line_no}: relevant_video_keys is required")
    totals = {f"recall@{k}": 0.0 for k in ks}
    totals.update({f"ndcg@{k}": 0.0 for k in ks})
    totals["mrr"] = 0.0
    details = []
    for query, relevant in rows:
        out = search.search(conn, query, limit=max(ks), offset=0)
        found = [str(r.get("video_key")) for r in out.get("results", [])]
        relevant_set = set(relevant)
        first = next((i + 1 for i, key in enumerate(found)
                      if key in relevant_set), None)
        totals["mrr"] += 1.0 / first if first else 0.0
        ideal = _dcg(relevant[:max(ks)], relevant_set) or 1.0
        for k in ks:
            top = found[:k]
            totals[f"recall@{k}"] += (1.0 if any(x in relevant_set for x in top) else 0.0)
            totals[f"ndcg@{k}"] += _dcg(top, relevant_set) / ideal
        details.append({"query": query, "found": found[:max(ks)], "first_rank": first})
    n = max(len(rows), 1)
    metrics = {key: round(value / n, 6) for key, value in totals.items()}
    return {"queries": len(rows), "metrics": metrics, "details": details}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="Atlas database path")
    parser.add_argument("--corpus", required=True, help="Golden JSONL path")
    args = parser.parse_args(argv)
    print(json.dumps(evaluate(args.db, args.corpus), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
