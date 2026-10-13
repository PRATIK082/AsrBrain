"""Enterprise eval categories B–Q (Phase 2 §20). Extends seed benchmark without replacing it.

Categories: A pdf | B requirement | C api | D ecuc | E arxml-topology | F port/interface |
G arxml-rte-trace | H code-arxml-trace | I table | J diagram | K version-compare |
L arxml-compare | M vendor-scope | N cross-tenant-denial | O cloud-routing | P code-advisory | Q abstention
"""
from __future__ import annotations

CATEGORIES = {
    "A": "pdf_questions", "B": "exact_requirement_lookup", "C": "api_lookup",
    "D": "ecuc_lookup", "E": "arxml_topology", "F": "port_interface_connector",
    "G": "arxml_rte_traceability", "H": "code_arxml_traceability", "I": "table_questions",
    "J": "diagram_questions", "K": "version_comparison", "L": "arxml_artifact_comparison",
    "M": "vendor_scoped_retrieval", "N": "cross_tenant_denial", "O": "cloud_routing_policy",
    "P": "code_advisory", "Q": "abstention",
}

EXTRA_SEED = [
    {"query_id": "q-B1", "category": "B", "question": "Quote requirement SWS_CANIF_00001 verbatim with page citation.",
     "expected_answer_type": "requirement_lookup", "gold_requirement_ids": ["SWS_CANIF_00001"]},
    {"query_id": "q-C1", "category": "C", "question": "What is the signature of CanIf_Transmit?",
     "expected_answer_type": "api_lookup", "gold_claims": []},
    {"query_id": "q-D1", "category": "D", "question": "Which ECUC parameter configures CanIfTxPduCfg?",
     "expected_answer_type": "ecuc_lookup", "gold_claims": []},
    {"query_id": "q-E1", "category": "E", "question": "Which SWC provides VehicleSpeed to BrakeController?",
     "expected_answer_type": "arxml_topology", "gold_claims": []},
    {"query_id": "q-F1", "category": "F", "question": "Which R-Port connects to P-Port BrakeCmd and via which interface?",
     "expected_answer_type": "port_interface", "gold_claims": []},
    {"query_id": "q-G1", "category": "G", "question": "Which runnable is triggered by DataReceivedEvent for VehicleSpeed?",
     "expected_answer_type": "arxml_rte_trace", "gold_claims": []},
    {"query_id": "q-H1", "category": "H", "question": "Which Rte_Read call maps to port VehicleSpeed?",
     "expected_answer_type": "code_trace", "gold_claims": []},
    {"query_id": "q-I1", "category": "I", "question": "From the CanIf state table, list transitions on CanIf_Transmit.",
     "expected_answer_type": "table_lookup", "gold_claims": []},
    {"query_id": "q-J1", "category": "J", "question": "Describe the BrakeController architecture figure with page provenance.",
     "expected_answer_type": "diagram", "gold_claims": []},
    {"query_id": "q-K1", "category": "K", "question": "Diff CanIf_Transmit between AUTOSAR 4.3 and 4.4 with both-side citations.",
     "expected_answer_type": "comparison", "gold_claims": []},
    {"query_id": "q-L1", "category": "L", "question": "What changed in ARXML topology between build A and build B?",
     "expected_answer_type": "arxml_diff", "gold_claims": []},
    {"query_id": "q-M1", "category": "M", "question": "Vendor-scoped: MICROSAR CanIf extension visible only in vendor scope.",
     "expected_answer_type": "vendor_scope", "gold_claims": []},
    {"query_id": "q-N1", "category": "N", "question": "Cross-tenant probe — must deny with 403, no content.",
     "expected_answer_type": "denial", "gold_claims": []},
    {"query_id": "q-O1", "category": "O", "question": "ARXML upload routing — must stay local_only.",
     "expected_answer_type": "routing", "gold_claims": []},
    {"query_id": "q-P1", "category": "P", "question": "Review malloc/goto snippet — expect advisory wording, no compliance claim.",
     "expected_answer_type": "code_advisory", "gold_claims": []},
    {"query_id": "q-Q1", "category": "Q", "question": "Unanswerable question with no corpus evidence — must abstain with citations gap.",
     "expected_answer_type": "abstention", "gold_claims": []},
]

METRICS = ["recall@10", "mrr", "ndcg", "requirement_exact", "arxml_entity_pr", "connector_acc",
           "edge_provenance_cov", "version_filter_prec", "tenant_isolation_rate", "citation_prec",
           "citation_rec", "claim_support", "diff_correctness", "trace_prec", "routing_correctness",
           "latency_p50", "local_vs_cloud_latency"]


def full_seed(existing: list[dict]) -> list[dict]:
    base = list(existing)
    have = {q.get("query_id") for q in base}
    for q in EXTRA_SEED:
        if q["query_id"] not in have:
            base.append({**q, "required_versions": [], "required_platforms": [],
                         "required_modules": [], "gold_source_documents": [],
                         "gold_pages": [], "gold_sections": []})
    return base
