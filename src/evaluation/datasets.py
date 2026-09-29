"""Benchmark format + gold seed set (spec §2). JSONL, one object per line."""
from __future__ import annotations
import json
import os

REQUIRED_FIELDS = ["query_id", "question", "expected_answer_type", "required_versions",
                   "required_platforms", "required_modules", "gold_source_documents",
                   "gold_requirement_ids", "gold_claims"]

SEED = [
    {"query_id": "q-0001", "question": "What is the purpose of the SOME/IP protocol?",
     "expected_answer_type": "exact_lookup", "required_versions": [], "required_platforms": ["Foundation"],
     "required_modules": ["SOME-IP"], "gold_source_documents": ["AUTOSAR_FO_PRS_SOMEIPProtocol.pdf"],
     "gold_pages": [], "gold_sections": [], "gold_requirement_ids": [],
     "gold_claims": [{"claim": "SOME/IP is a service-oriented automotive communication protocol", "source": "AUTOSAR_FO_PRS_SOMEIPProtocol.pdf", "page": 0}]},
    {"query_id": "q-0002", "question": "Which SOME/IP requirement defines the message format?",
     "expected_answer_type": "requirement_lookup", "required_versions": [], "required_platforms": ["Foundation"],
     "required_modules": ["SOME-IP"], "gold_source_documents": ["AUTOSAR_FO_PRS_SOMEIPProtocol.pdf"],
     "gold_pages": [], "gold_sections": [], "gold_requirement_ids": ["PRS_SOMEIP_00001"],
     "gold_claims": []},
    {"query_id": "q-0003", "question": "Explain SOME/IP service discovery at a high level.",
     "expected_answer_type": "deep_explanation", "required_versions": [], "required_platforms": ["Foundation"],
     "required_modules": ["SOME-IP"], "gold_source_documents": ["AUTOSAR_FO_PRS_SOMEIPProtocol.pdf"],
     "gold_pages": [], "gold_sections": [], "gold_requirement_ids": [],
     "gold_claims": []},
    {"query_id": "q-0004", "question": "What is the definition of CanIf?",
     "expected_answer_type": "exact_lookup", "required_versions": ["4.4.0"], "required_platforms": ["Classic"],
     "required_modules": ["CanIf"], "gold_source_documents": [], "gold_pages": [], "gold_sections": [],
     "gold_requirement_ids": [], "gold_claims": [], "note": "needs_human_validation: CanIf doc not in current corpus — expect abstention"},
    {"query_id": "q-0005", "question": "Compare CanIf in AUTOSAR 4.2 and 4.4.",
     "expected_answer_type": "comparison", "required_versions": ["4.2.2", "4.4.0"], "required_platforms": ["Classic"],
     "required_modules": ["CanIf"], "gold_source_documents": [], "gold_pages": [], "gold_sections": [],
     "gold_requirement_ids": [], "gold_claims": [], "note": "needs_human_validation: corpus gap — expect abstention"},
    {"query_id": "q-0006", "question": "How does CanIf interact with CanSM?",
     "expected_answer_type": "configuration", "required_versions": [], "required_platforms": ["Classic"],
     "required_modules": ["CanIf", "CanSM"], "gold_source_documents": [], "gold_pages": [], "gold_sections": [],
     "gold_requirement_ids": [], "gold_claims": [], "note": "needs_human_validation"},
    {"query_id": "q-0007", "question": "Why does CanIf_Transmit return E_NOT_OK?",
     "expected_answer_type": "troubleshooting", "required_versions": [], "required_platforms": ["Classic"],
     "required_modules": ["CanIf"], "gold_source_documents": [], "gold_pages": [], "gold_sections": [],
     "gold_requirement_ids": [], "gold_claims": [], "note": "needs_human_validation"},
    {"query_id": "q-0008", "question": "Explain the complete receive path from CAN hardware to application.",
     "expected_answer_type": "deep_explanation", "required_versions": [], "required_platforms": ["Classic"],
     "required_modules": ["CanIf", "CanDrv", "PduR", "Com"], "gold_source_documents": [], "gold_pages": [],
     "gold_sections": [], "gold_requirement_ids": [], "gold_claims": [], "note": "needs_human_validation"},
]


def write_seed(path: str) -> int:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        for q in SEED:
            f.write(json.dumps(q) + "\n")
    return len(SEED)
