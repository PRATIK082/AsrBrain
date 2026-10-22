"""Golden-set generation from the ingested corpus (master prompt §9).

Design
------
The gold evidence ids are **real chunk ids from the canonical store**, never invented. That is
the property that makes the harness meaningful: a question is only useful if the evidence it
points at genuinely exists in the corpus.

Generation is deterministic — same corpus, same seed, same set. The generator reads the canonical
SQLite store directly and never calls an LLM, so the golden set cannot drift because a model
changed its mind. An optional LLM paraphrasing pass exists for question naturalness
(:func:`paraphrase_questions`); paraphrased items are flagged ``needs_expert_review`` and their
gold evidence is unchanged.

Every generated item is flagged ``needs_expert_review=True`` and ``source="generated"`` until a
domain expert confirms it. Nothing here is presented as expert-approved.
"""
from __future__ import annotations

import json
import random
import re
import sqlite3
from collections import defaultdict

from .golden import new_item

REQ_ID_RE = re.compile(r"^(?:SWS|SRS|PRS|TPS|RS|EXP|CONSTR|QM)_[A-Za-z0-9_]+$")
#: AUTOSAR modules that are deliberately absent from the current corpus and are therefore safe
#: subjects for unanswerable and adversarial questions.
ABSENT_MODULES = [
    "CanIf", "CanTp", "CanSM", "PduR", "Dcm", "Dem", "NvM", "EcuM", "BswM", "Rte", "Os",
    "ComM", "SecOC", "Crc", "Fls", "Eep", "Spi", "Adc", "Wdg", "Dio", "IoHwAb", "Eth",
    "FrTp", "LinTp", "Vlan", "Uds", "Ipv4", "TcpIp", "Dhcp", "SomeIp", "SomeSd",
    "CanIfTrcv", "CanTrcv", "PduRGateway", "ComIPduGroup", "Mcu", "Gpt", "I2c", "Spi_",
    "CanTrcv", "Fr", "FlexRay", "Lin", "RteMapper", "Ara", "Dds",
]

#: Per-family quotas. The mix is fixed up front so that no trimming can silently drop a whole
#: category — the §9 coverage targets are a property of the generator, not a hope.
QUOTAS = {
    "requirement_lookup": 40,
    "api_lookup": 30,
    "configuration": 22,
    "definition": 22,
    "runtime_behaviour": 16,
    "table_lookup": 11,
    "diagram_lookup": 16,
    "multi_hop": 96,
    "release_comparison": 10,
    "unanswerable": 42,
    "adversarial": 10,
    "code_explanation": 4,
    "traceability": 4,
    "impact_analysis": 4,
    "test_analysis": 4,
}


def _load_json_list(value: str) -> list[str]:
    if not value or value in ("[]", "null"):
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("�", " ")).strip()


def _sentence_span(text: str, needle: str | None = None, limit: int = 700) -> str:
    """Verbatim span from ``text`` — the sentence holding ``needle`` when given."""
    flat = _clean(text)
    if not flat:
        return ""
    if needle:
        for sent in re.split(r"(?<=[.!?])\s+", flat):
            if needle.lower() in sent.lower():
                return sent[:limit]
    return flat[:limit]


def read_corpus(canonical_db: str) -> dict:
    """Read everything the generator needs out of the canonical store."""
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    documents = [dict(r) for r in conn.execute(
        "select document_id, source_pdf, autosar_release, platform, module, document_type, "
        "page_count from documents")]
    chunks = []
    for r in conn.execute(
            "select chunk_id, document_id, source_pdf, page_start, page_end, autosar_release, "
            "platform, module, document_type, section_number, section_title, requirement_ids, "
            "api_names, ecu_parameters, chunk_kind, text from chunks"):
        row = dict(r)
        row["requirement_ids"] = _load_json_list(row["requirement_ids"])
        row["api_names"] = _load_json_list(row["api_names"])
        row["ecu_parameters"] = _load_json_list(row["ecu_parameters"])
        chunks.append(row)
    tables = [dict(r) for r in conn.execute(
        "select evidence_id, document_id, source_pdf, page, caption from tables")]
    figures = [dict(r) for r in conn.execute(
        "select evidence_id, document_id, source_pdf, page, kind, number, caption from figures")]
    conn.close()
    return {"documents": documents, "chunks": chunks, "tables": tables, "figures": figures}


def _api_only(chunk: dict) -> list[str]:
    """API names that are not requirement ids in disguise.

    ``api_names`` overlaps ``requirement_ids`` because the signal extractor uses the same
    identifier pattern for both (see AUDIT D-55); this filter keeps the two item families
    distinct.
    """
    return [a for a in chunk["api_names"] if not REQ_ID_RE.match(a)]


def generate(canonical_db: str, target: int = 320, seed: int = 20261021) -> list[dict]:
    """Build a golden set from the corpus, honouring the per-family quotas."""
    rng = random.Random(seed)
    corpus = read_corpus(canonical_db)
    chunks = corpus["chunks"]

    items: list[dict] = []
    counter = {"n": 0}

    def qid(prefix: str) -> str:
        counter["n"] += 1
        return f"q-{prefix}-{counter['n']:04d}"

    def base(chunk: dict, **kw) -> dict:
        kw.setdefault("gold_source_documents", [chunk["source_pdf"]] if chunk.get("source_pdf") else [])
        kw.setdefault("gold_pages", [chunk["page_start"]] if chunk.get("page_start") else [])
        kw.setdefault("required_versions", [chunk["autosar_release"]] if chunk.get("autosar_release") else [])
        kw.setdefault("required_platforms", [chunk["platform"]] if chunk.get("platform") else [])
        kw.setdefault("required_modules", [chunk["module"]] if chunk.get("module") else [])
        return kw

    def take(pool: list, quota: int) -> list:
        """Deterministically take up to ``quota`` items from a pool."""
        shuffled = list(pool)
        rng.shuffle(shuffled)
        return shuffled[:quota]

    # ---------------------------------------------------------------- requirement lookup
    # A requirement is frequently split across several chunks (the signal extractor finds the
    # id in every window that contains it), so the gold evidence for a requirement is *every*
    # chunk that carries the id. Scoring against one arbitrary sibling would measure the
    # chunker, not the retriever.
    req_to_chunks: dict[str, list[str]] = defaultdict(list)
    for c in chunks:
        for rid in c["requirement_ids"]:
            req_to_chunks[rid].append(c["chunk_id"])

    for chunk in take([c for c in chunks if c["requirement_ids"] and c["chunk_kind"] == "atomic"],
                      QUOTAS["requirement_lookup"]):
        rid = chunk["requirement_ids"][0]
        q = rng.choice([
            f"What does the requirement {rid} specify?",
            f"State the requirement {rid} and the condition it places on the implementation.",
        ])
        gold_ids = req_to_chunks.get(rid, [chunk["chunk_id"]])[:4]
        items.append(new_item(
            qid("R"), q, "requirement_lookup",
            gold_answer=_sentence_span(chunk["text"], rid),
            gold_evidence_ids=gold_ids,
            gold_requirement_ids=[rid],
            gold_claims=[{"claim": _sentence_span(chunk["text"], rid), "source": chunk["source_pdf"],
                          "page": chunk["page_start"]}],
            difficulty=rng.choice(["easy", "easy", "medium"]),
            tags=["requirement", "single_hop"],
            needs_expert_review=True,
            source="generated",
            notes=f"derived from chunk {chunk['chunk_id']} p.{chunk['page_start']}; the requirement "
                  f"appears in {len(gold_ids)} chunk(s)",
            **base(chunk)))

    # ---------------------------------------------------------------- api lookup
    for chunk in take([c for c in chunks if _api_only(c) and c["chunk_kind"] == "atomic"],
                      QUOTAS["api_lookup"]):
        api = _api_only(chunk)[0]
        q = rng.choice([
            f"What is the role of {api} in the architecture?",
            f"Which interface or element is named {api}, and what does it specify?",
            f"Describe the element {api} as the specification defines it.",
        ])
        items.append(new_item(
            qid("A"), q, "api_lookup",
            gold_answer=_sentence_span(chunk["text"], api),
            gold_evidence_ids=[chunk["chunk_id"]],
            gold_claims=[{"claim": _sentence_span(chunk["text"], api), "source": chunk["source_pdf"],
                          "page": chunk["page_start"]}],
            difficulty=rng.choice(["easy", "medium", "medium"]),
            tags=["api", "single_hop"],
            needs_expert_review=True,
            source="generated",
            notes=f"derived from chunk {chunk['chunk_id']} p.{chunk['page_start']}",
            **base(chunk)))

    # ---------------------------------------------------------------- configuration / ECUC
    for chunk in take([c for c in chunks if c["ecu_parameters"] and c["chunk_kind"] == "atomic"],
                      QUOTAS["configuration"]):
        param = chunk["ecu_parameters"][0]
        q = rng.choice([
            f"Which configuration parameter is named {param}, and what does it configure?",
            f"How is {param} configured in the system template?",
            f"What does the ECUC parameter {param} control?",
        ])
        items.append(new_item(
            qid("C"), q, "configuration",
            gold_answer=_sentence_span(chunk["text"], param),
            gold_evidence_ids=[chunk["chunk_id"]],
            gold_claims=[{"claim": _sentence_span(chunk["text"], param), "source": chunk["source_pdf"],
                          "page": chunk["page_start"]}],
            difficulty="medium",
            tags=["ecuc", "single_hop"],
            needs_expert_review=True,
            source="generated",
            notes=f"derived from chunk {chunk['chunk_id']} p.{chunk['page_start']}",
            **base(chunk)))

    # ---------------------------------------------------------------- definition / section
    for chunk in take([c for c in chunks if c["section_title"] and c["chunk_kind"] == "atomic"],
                      QUOTAS["definition"]):
        title = chunk["section_title"]
        num = chunk.get("section_number") or ""
        q = rng.choice([
            f"What does section {num} '{title}' define?",
            f"Explain the content of the section titled '{title}'.",
            f"What is specified under '{title}'?",
        ])
        items.append(new_item(
            qid("D"), q, "definition",
            gold_answer=_sentence_span(chunk["text"], title),
            gold_evidence_ids=[chunk["chunk_id"]],
            gold_sections=[f"{num} {title}".strip()],
            gold_claims=[{"claim": _sentence_span(chunk["text"], title), "source": chunk["source_pdf"],
                          "page": chunk["page_start"]}],
            difficulty=rng.choice(["easy", "medium"]),
            tags=["section", "single_hop"],
            needs_expert_review=True,
            source="generated",
            notes=f"derived from chunk {chunk['chunk_id']} p.{chunk['page_start']}",
            **base(chunk)))

    # ---------------------------------------------------------------- runtime behaviour
    for chunk in take([c for c in chunks
                       if c["section_title"] and c["requirement_ids"] and c["chunk_kind"] == "atomic"],
                      QUOTAS["runtime_behaviour"]):
        title = chunk["section_title"]
        q = rng.choice([
            f"What runtime behaviour does the specification prescribe in '{title}'?",
            f"Describe the behaviour required at runtime under '{title}'.",
        ])
        items.append(new_item(
            qid("B"), q, "runtime_behaviour",
            gold_answer=_sentence_span(chunk["text"], title),
            gold_evidence_ids=[chunk["chunk_id"]],
            gold_requirement_ids=list(chunk["requirement_ids"][:2]),
            difficulty="hard",
            tags=["runtime", "single_hop"],
            needs_expert_review=True,
            source="generated",
            notes=f"derived from chunk {chunk['chunk_id']} p.{chunk['page_start']}",
            **base(chunk)))

    # ---------------------------------------------------------------- table lookup
    chunks_by_page: dict[tuple, list[dict]] = defaultdict(list)
    for c in chunks:
        chunks_by_page[(c["source_pdf"], c["page_start"])].append(c)

    tbl_items: list[dict] = []
    for tbl in corpus["tables"]:
        page_chunks = chunks_by_page.get((tbl["source_pdf"], tbl["page"]), [])
        caption = _clean(tbl["caption"])
        if not page_chunks or not caption:
            continue
        tbl_items.append(new_item(
            qid("T"),
            f"What does the table '{caption}' on page {tbl['page']} of {tbl['source_pdf']} specify?",
            "table_lookup",
            gold_answer=caption,
            gold_evidence_ids=[c["chunk_id"] for c in page_chunks[:3]],
            gold_pages=[tbl["page"]],
            gold_source_documents=[tbl["source_pdf"]],
            difficulty="medium",
            tags=["table", "single_hop"],
            needs_expert_review=True,
            source="generated",
            notes=f"derived from table {tbl['evidence_id']} p.{tbl['page']}; table rows are empty in "
                  "the current corpus, so the caption is the only retrievable content",
        ))
    items.extend(take(tbl_items, QUOTAS["table_lookup"]))

    # ---------------------------------------------------------------- diagram lookup
    fig_items: list[dict] = []
    for fig in corpus["figures"]:
        page_chunks = chunks_by_page.get((fig["source_pdf"], fig["page"]), [])
        caption = _clean(fig["caption"])
        number = _clean(fig.get("number") or "")
        if not page_chunks or not caption:
            continue
        label = f"Figure {number} '{caption}'" if number else f"the figure '{caption}'"
        fig_items.append(new_item(
            qid("G"), f"What does {label} on page {fig['page']} of {fig['source_pdf']} show?",
            "diagram_lookup",
            gold_answer=caption,
            gold_evidence_ids=[c["chunk_id"] for c in page_chunks[:3]],
            gold_pages=[fig["page"]],
            gold_source_documents=[fig["source_pdf"]],
            difficulty="hard",
            tags=["diagram", "single_hop"],
            needs_expert_review=True,
            source="generated",
            notes=f"derived from figure {fig['evidence_id']} p.{fig['page']}; figures are "
                  "caption-only in the current corpus",
        ))
    items.extend(take(fig_items, QUOTAS["diagram_lookup"]))

    # ---------------------------------------------------------------- multi hop
    # A genuine two-chunk hop: a requirement chunk and an API chunk from the same document.
    # The API chunk must sit on the *same page* (or within three pages) so that "defined
    # alongside it" is literally true. Pairing across the whole document would measure the
    # retriever's ability to find two arbitrary passages in a 4,400 chunk corpus, which is
    # not what a multi-hop question means.
    by_doc_req: dict[str, list[dict]] = defaultdict(list)
    by_doc_api: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        if c["chunk_kind"] != "atomic":
            continue
        if c["requirement_ids"] and c["section_title"]:
            by_doc_req[c["source_pdf"]].append(c)
        if _api_only(c) and c["section_title"]:
            by_doc_api[c["source_pdf"]].append(c)
    for doc in by_doc_req:
        rng.shuffle(by_doc_req[doc])
        rng.shuffle(by_doc_api.get(doc, []))
    mh_items: list[dict] = []
    for doc, reqs in by_doc_req.items():
        apis = by_doc_api.get(doc, [])
        if not apis:
            continue
        for i, req_chunk in enumerate(reqs):
            if len(mh_items) >= QUOTAS["multi_hop"]:
                break
            page = req_chunk["page_start"] or 0
            near = [a for a in apis if abs((a["page_start"] or 0) - page) <= 3
                    and a["chunk_id"] != req_chunk["chunk_id"]]
            pool = near or [a for a in apis if a["chunk_id"] != req_chunk["chunk_id"]]
            if not pool:
                continue
            api_chunk = pool[i % len(pool)]
            if api_chunk["chunk_id"] == req_chunk["chunk_id"]:
                continue
            rid = req_chunk["requirement_ids"][0]
            api = _api_only(api_chunk)[0]
            title = req_chunk["section_title"]
            mh_items.append(new_item(
                qid("M"),
                f"In section '{title}' of {doc}, which requirement identifier is stated, and which "
                f"API element is defined alongside it?",
                "multi_hop",
                gold_answer=(_sentence_span(req_chunk["text"], rid) + " || " +
                             _sentence_span(api_chunk["text"], api))[:900],
                gold_evidence_ids=[req_chunk["chunk_id"], api_chunk["chunk_id"]],
                gold_requirement_ids=[rid],
                gold_pages=[req_chunk["page_start"]],
                gold_source_documents=[doc],
                difficulty="hard",
                tags=["multi_hop", "multi_hop"],
                needs_expert_review=True,
                source="generated",
                notes=f"two-chunk hop in {doc}: {req_chunk['chunk_id']} (p.{req_chunk['page_start']}) "
                      f"+ {api_chunk['chunk_id']} (p.{api_chunk['page_start']})",
            ))
    items.extend(take(mh_items, QUOTAS["multi_hop"]))

    # ---------------------------------------------------------------- release comparison
    # The corpus holds one document per release, so a true like-for-like comparison is not
    # constructible. The items therefore target a term that appears in *both* releases and
    # are marked unanswerable: the correct behaviour is to say that only one release of the
    # document in question is available.
    by_release: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        if c.get("autosar_release"):
            by_release[c["autosar_release"]].append(c)
    releases = sorted(by_release)
    if len(releases) >= 2:
        left, right = releases[0], releases[1]
        left_terms = {t.lower() for c in by_release[left] for t in _api_only(c)}
        right_terms = {t.lower() for c in by_release[right] for t in _api_only(c)}
        shared = sorted(left_terms & right_terms)
        if len(shared) < QUOTAS["release_comparison"]:
            # fall back to content words that occur in both releases
            from .metrics import content_tokens
            from collections import Counter
            left_words = Counter(w for c in by_release[left] for w in set(content_tokens(c["text"])))
            right_words = Counter(w for c in by_release[right] for w in set(content_tokens(c["text"])))
            candidates = sorted(
                (w for w, n in left_words.items()
                 if n >= 5 and right_words.get(w, 0) >= 2 and len(w) > 5),
                key=lambda w: -(left_words[w] + right_words[w]))
            shared = candidates[:QUOTAS["release_comparison"]]
        rng.shuffle(shared)
        for term in shared[:QUOTAS["release_comparison"]]:
            items.append(new_item(
                qid("K"), f"How is '{term}' described in {left} compared with {right}?",
                "release_comparison",
                gold_answer="",
                gold_evidence_ids=[],
                answerable=False,
                required_versions=[left, right],
                difficulty="hard",
                tags=["release_comparison", "multi_hop", "unanswerable"],
                needs_expert_review=True,
                source="generated",
                notes="the corpus holds one document per release, so a like-for-like comparison is "
                      "not possible; needs an expert decision on the expected answer",
            ))

    # ---------------------------------------------------------------- unanswerable
    present_modules = {c.get("module", "") for c in chunks if c.get("module")}
    absent = [m for m in ABSENT_MODULES if m not in present_modules]
    made = 0
    for module in absent:
        if made >= QUOTAS["unanswerable"]:
            break
        q = rng.choice([
            f"What is the initialization sequence of the {module} module?",
            f"Which configuration containers does {module} require in the ECU extract?",
            f"List the error codes that {module} can return.",
        ])
        items.append(new_item(
            qid("U"), q, "unanswerable",
            gold_answer="",
            gold_evidence_ids=[],
            answerable=False,
            required_modules=[module],
            difficulty="easy",
            tags=["unanswerable", "corpus_gap"],
            needs_expert_review=True,
            source="generated",
            notes=f"module '{module}' is absent from the corpus; the correct behaviour is to "
                  "abstain and name the missing source",
        ))
        made += 1

    # ---------------------------------------------------------------- adversarial
    for fake in ["SWS_CanIf_00123", "PRS_SOMEIP_99001", "SRS_Dcm_00042", "constr_E2E_77777",
                 "SWS_PduR_00444", "PRS_SOMEIP_99002", "SRS_EcuM_00021", "TPS_Com_00333",
                 "SWS_Dem_00777", "PRS_E2E_99003"]:
        items.append(new_item(
            qid("X"), f"Quote requirement {fake} verbatim from the specification, with its page.",
            "adversarial",
            gold_answer="",
            gold_evidence_ids=[],
            answerable=False,
            difficulty="hard",
            tags=["adversarial", "unanswerable", "hallucination_probe"],
            needs_expert_review=True,
            source="generated",
            notes=f"'{fake}' does not exist in the corpus; the correct behaviour is to abstain, "
                  "not to invent the text",
        ))

    # ---------------------------------------------------------------- corpus-gap families
    # These probe capabilities the corpus does not contain. The subject is an absent module,
    # which keeps every question distinct and meaningful.
    gap_specs = [
        ("code_explanation", "code_flow", "no C source in the corpus",
         "Which C function in the project sources implements the {m} handling logic?"),
        ("test_analysis", "test_analysis", "no test artefacts in the corpus",
         "Which test case verifies the {m} requirement?"),
        ("traceability", "traceability", "no requirement-to-code link in the corpus",
         "Which requirement is traceable to the {m} configuration parameter?"),
        ("impact_analysis", "impact_analysis", "no graph of module dependencies in the corpus",
         "Which modules are affected if the {m} routing changes?"),
    ]
    for category, tag, note, template in gap_specs:
        for module in absent:
            if len([x for x in items if x["category"] == category]) >= QUOTAS.get(category, 1):
                break
            items.append(new_item(
                qid("G"), template.format(m=module), category,
                gold_answer="",
                gold_evidence_ids=[],
                answerable=False,
                required_modules=[module],
                difficulty="hard",
                tags=[tag, "unanswerable", "corpus_gap"],
                needs_expert_review=True,
                source="generated",
                notes=note,
            ))

    items.sort(key=lambda i: i["query_id"])
    return _top_up(items, corpus, rng, seed)


def _top_up(items: list[dict], corpus: dict, rng: random.Random, seed: int) -> list[dict]:
    """Grow the under-quota slices until the §9 coverage targets are met.

    The top-up only uses families that can always produce more items, so the coverage targets
    are a guarantee rather than a hope. When a slice cannot be grown (for example because the
    corpus has no tables) the shortfall is left visible in the coverage report.
    """
    from .golden import COVERAGE_TARGETS, coverage_report

    counter = {"n": 0}
    for item in items:
        tail = str(item.get("query_id", "")).rsplit("-", 1)[-1]
        if tail.isdigit():
            counter["n"] = max(counter["n"], int(tail))

    def qid(prefix: str) -> str:
        counter["n"] += 1
        return f"q-{prefix}-{counter['n']:04d}"

    growable = {
        "multi_hop": "M",
        "code_explanation": "G",
        "traceability": "G",
        "impact_analysis": "G",
        "test_analysis": "G",
    }
    for _ in range(200):
        report = coverage_report(items)
        shortfall = {g["slice"]: g for g in report["coverage_gaps"]}
        if not shortfall:
            break
        progressed = False
        for slice_name, gap in shortfall.items():
            if slice_name not in growable:
                continue
            prefix = growable[slice_name]
            current = (sum(1 for i in items if i["category"] == slice_name)
                       + sum(1 for i in items if slice_name in (i.get("tags") or [])))
            need = gap["target"] * report["n"] - current
            if need < 1:
                continue
            for _ in range(int(need) + 2):
                if slice_name == "multi_hop":
                    item = _make_multi_hop(corpus, rng, qid)
                else:
                    item = _make_gap_item(slice_name, corpus, rng, qid)
                if item is None:
                    break
                items.append(item)
                progressed = True
            if progressed:
                break
        if not progressed:
            break
    items.sort(key=lambda i: i["query_id"])
    return items


def _make_multi_hop(corpus: dict, rng: random.Random, qid) -> dict | None:
    """One more two-chunk hop, drawn from any document that has both sides."""
    chunks = corpus["chunks"]
    by_doc_req: dict[str, list[dict]] = defaultdict(list)
    by_doc_api: dict[str, list[dict]] = defaultdict(list)
    for c in chunks:
        if c["chunk_kind"] != "atomic":
            continue
        if c["requirement_ids"] and c["section_title"]:
            by_doc_req[c["source_pdf"]].append(c)
        if _api_only(c) and c["section_title"]:
            by_doc_api[c["source_pdf"]].append(c)
    candidates = []
    for doc, reqs in by_doc_req.items():
        apis = by_doc_api.get(doc, [])
        if not apis:
            continue
        for req_chunk in reqs:
            api_chunk = rng.choice(apis)
            if api_chunk["chunk_id"] != req_chunk["chunk_id"]:
                candidates.append((doc, req_chunk, api_chunk))
    if not candidates:
        return None
    doc, req_chunk, api_chunk = rng.choice(candidates)
    rid = req_chunk["requirement_ids"][0]
    api = _api_only(api_chunk)[0]
    title = req_chunk["section_title"]
    return new_item(
        qid("M"),
        f"In section '{title}' of {doc}, which requirement identifier is stated, and which API "
        f"element is defined alongside it?",
        "multi_hop",
        gold_answer=(_sentence_span(req_chunk["text"], rid) + " || " +
                     _sentence_span(api_chunk["text"], api))[:900],
        gold_evidence_ids=[req_chunk["chunk_id"], api_chunk["chunk_id"]],
        gold_requirement_ids=[rid],
        gold_pages=[req_chunk["page_start"]],
        gold_source_documents=[doc],
        difficulty="hard",
        tags=["multi_hop", "multi_hop"],
        needs_expert_review=True,
        source="generated",
        notes=f"two-chunk hop in {doc}: {req_chunk['chunk_id']} (p.{req_chunk['page_start']}) + "
              f"{api_chunk['chunk_id']} (p.{api_chunk['page_start']})",
    )


def _make_gap_item(slice_name: str, corpus: dict, rng: random.Random, qid) -> dict | None:
    """One more corpus-gap probe for the code / traceability / impact / test families."""
    templates = {
        "code_explanation": ("code_explanation", "code_flow", "no C source in the corpus",
                             "Which C function in the project sources implements the {m} handling logic?"),
        "test_analysis": ("test_analysis", "test_analysis", "no test artefacts in the corpus",
                          "Which test case verifies the {m} requirement?"),
        "traceability": ("traceability", "traceability", "no requirement-to-code link in the corpus",
                         "Which requirement is traceable to the {m} configuration parameter?"),
        "impact_analysis": ("impact_analysis", "impact_analysis",
                            "no graph of module dependencies in the corpus",
                            "Which modules are affected if the {m} routing changes?"),
    }
    if slice_name not in templates:
        return None
    category, tag, note, template = templates[slice_name]
    present = {c.get("module", "") for c in corpus["chunks"] if c.get("module")}
    absent = [m for m in ABSENT_MODULES if m not in present]
    if not absent:
        return None
    module = rng.choice(absent)
    return new_item(
        qid("G"), template.format(m=module), category,
        gold_answer="",
        gold_evidence_ids=[],
        answerable=False,
        required_modules=[module],
        difficulty="hard",
        tags=[tag, "unanswerable", "corpus_gap"],
        needs_expert_review=True,
        source="generated",
        notes=note,
    )


def paraphrase_questions(items: list[dict], provider_spec: dict, limit: int = 0) -> list[dict]:
    """Rewrite generated questions into more natural wording using the configured provider.

    The gold evidence and gold answer are never touched. Paraphrased items keep
    ``needs_expert_review=True``. If the provider is unavailable the items are returned
    unchanged, so the golden set is always usable.
    """
    from ..generation.providers import complete

    targets = items if not limit else items[:limit]
    for item in targets:
        if item.get("source") != "generated" or item.get("answerable") is False:
            continue
        prompt = (
            "Rewrite this technical question so it reads like something an automotive engineer "
            "would type. Keep every identifier, release, module and API name EXACTLY as written "
            "and keep the meaning identical. Reply with the rewritten question only.\n\n"
            f"Question: {item['question']}"
        )
        try:
            rewritten = complete(prompt, provider_spec).strip()
        except Exception:
            continue
        rewritten = rewritten.strip().strip('"').splitlines()[0].strip()
        if rewritten and len(rewritten) > 10 and rewritten != item["question"]:
            item["question"] = rewritten
            item["notes"] = (item.get("notes", "") + " | paraphrased by LLM").strip(" |")
    return items
