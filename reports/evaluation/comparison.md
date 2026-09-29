# Evaluation comparison (measured — not a target)

Date: 2026-09-30 · Corpus: 1 PDF (`AUTOSAR_FO_PRS_SOMEIPProtocol.pdf`, detected R24-11/Foundation/PRS/SOME-IP, 169 atomic+context chunks, 15 tables, 14 figures) · LLM: qwen3:14b via Ollama · Retrieval: local hybrid (BM25 + TF-IDF, RRF k=60, rerank, parent-expand, compression) + modality indexes.

## validated.json summary (LLM-backed)

| Metric | Value | Meaning |
|---|---|---|
| n | 8 | benchmark queries (spec §2 classes A–H) |
| hit_rate | 1.0 | every query whose gold doc is indexed retrieved it |
| abstention_rate | 0.625 | 5/8 abstained — CanIf/Classic items with no indexed doc (correct; `needs_human_validation`) |
| mean_claim_support | 0.375 | LLM drafts cite key claims but not every sentence; per-claim verdicts in payload |
| mean_req_recall | 0.0 | gold requirement IDs in the seed are placeholders (`PRS_SOMEIP_00001` not in corpus) — needs human gold IDs |
| version_precision | 1.0 | no silent version mixing (wrong-version or abstain) |
| module_precision | 1.0 | module auto-inference (SOME-IP) + filters consistent |
| p50_latency_s | 21.4 | LLM-bound; retrieval stage <0.5 s |

## What this does NOT say

- Not "95% accurate". Report named metrics + slices only.
- Ablation arms A–J defined (`src/evaluation/ablation.py`); only the full pipeline run so far.
- Next highest-value improvement: index Classic SWS CanIf 4.4.0 + real gold requirement IDs,
  then re-run `make eval` to unlock comparison/dependency slices and req_recall.
