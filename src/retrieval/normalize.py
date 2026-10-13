"""Query auto-correction (spell-tolerant input). Deterministic, bounded:

- AUTOSAR alias-aware (canif/Can If → CanIf, pdurout→PduR, some ip→SOME-IP…)
- fuzzy match against modules / doctypes / platforms / common technical verbs
- never rewrites requirement IDs, API names, version labels, or numbers
- returns (corrected, [(original, fixed)]) so the UI can show "Interpreted as …"
"""
from __future__ import annotations
import re
from difflib import get_close_matches

from ..ingestion.metadata import MODULE_ALIASES

# token-level vocabulary for fuzzy matching (lower-cased)
_TECH_WORDS = {
    # platforms / doctypes / releases words
    "classic", "adaptive", "foundation", "sws", "prs", "rs", "tps",
    # verbs / nouns users type often
    "configuration", "configure", "initialization", "initialize", "initialise",
    "transmit", "receive", "controller", "protocol", "requirement", "requirements",
    "parameter", "parameters", "interaction", "interact", "difference", "compare",
    "comparison", "diagnostic", "troubleshoot", "sequence", "behavior", "behaviour",
    "return", "error", "message", "communication", "service", "discovery",
    "definition", "purpose", "explain", "version", "release", "module", "between",
    # everyday words users mistype (fuzzy targets for the typo layer)
    "detailed", "details", "property", "properties", "required", "mapping",
    "analysis", "question", "questions", "example", "examples", "element",
    "elements", "derive", "derived", "need", "needs", "provide", "provided",
}
_VOCAB = sorted(set(MODULE_ALIASES) | {m.lower() for m in MODULE_ALIASES.values()} | _TECH_WORDS)

# Curated typo map from real user input (whole-word, case-insensitive).
# Runs BEFORE fuzzy matching so observed misspellings fix deterministically
# instead of depending on difflib cutoffs. Never touches identifiers —
# application order is: TYPO_MAP → ABBREV_MAP → multi-word merge → fuzzy.
_TYPO_MAP = {
    "alla": "all",
    "hot": "how",  # "hot to map" → "how to map"
    "teh": "the", "nad": "and", "wich": "which", "whch": "which",
    "requared": "required", "requried": "required", "requird": "required",
    "deatiled": "detailed", "detialed": "detailed", "detials": "details",
    "proparty": "property", "proparties": "properties", "propetry": "property",
    "queation": "question", "quear": "question", "quetion": "question",
    "anaylsis": "analysis", "analsysis": "analysis",
    "chnage": "change", "chaneg": "change",
    "speling": "spelling", "spelling": "spelling",
    "elemnt": "element", "elemnts": "elements", "elment": "element",
    "maping": "mapping", "mappping": "mapping",
    "configruation": "configuration", "configuraion": "configuration",
    "explane": "explain", "explan": "explain",
    "defination": "definition", "definations": "definitions",
    "exmaple": "example", "exmple": "example",
    "diagostic": "diagnostic", "diagnostc": "diagnostic",
    "communcation": "communication", "comunication": "communication",
    "intialization": "initialization", "initialisation": "initialization",
    "architecure": "architecture", "archietcture": "architecture",
    "topolgy": "topology", "topologie": "topology",
}

# Shorthand → full term so module/intent detection sees the real word.
# "diag" is the critical one: without it, diagnostic questions get no module
# filter and drown in Com-heavy corpus evidence.
_ABBREV_MAP = {
    "diag": "diagnostic",
    "diags": "diagnostics",
    "config": "configuration",
    "init": "initialization",
    "req": "requirement",
    "reqs": "requirements",
}
_SPACED_EXTRA = {"can if": "CanIf", "some ip": "SOME-IP", "can sm": "CanSM",
                 "can drv": "CanDrv", "pdu r": "PduR"}
_MULTI = {**{k: v for k, v in MODULE_ALIASES.items() if " " in k or "/" in k},
          **_SPACED_EXTRA}

_PROTECTED = re.compile(
    r"^(\[?(?:SWS|RS|PRS)_[A-Za-z0-9_\-]+R?\d*\]?|[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+"
    r"|R\d{2}-11|\d+\.\d+(?:\.\d+)?|E_[A-Z_]+|\[E\d+\])$")


def _apply_fixed_maps(text: str, changes: list) -> str:
    """Step 0: curated typo/abbrev fixes, per-token and identifier-safe.

    Skips protected identifiers (API names, requirement IDs, versions) and
    anything containing '_' so e.g. "Rte_Init" can never become
    "Rte_initialization".
    """
    parts = re.split(r"(\s+)", text)
    out: list[str] = []
    for tok in parts:
        if not tok.strip():
            out.append(tok)
            continue
        core = tok.strip(".,?:;!\"'()")
        if ("_" in core or len(core) <= 2
                or _PROTECTED.match(core) or core.lower() not in _FIXED_MAP):
            out.append(tok)
            continue
        fixed = _match_case(_FIXED_MAP[core.lower()], core)
        out.append(tok.replace(core, fixed))
        changes.append((core, fixed))
    return "".join(out)


_FIXED_MAP = {**_TYPO_MAP, **_ABBREV_MAP}


def _match_case(fixed_lower: str, original: str) -> str:
    for canon in list(MODULE_ALIASES.values()) + ["SOME-IP", "ECUC"]:
        if canon.lower() == fixed_lower:
            return canon
    if original[:1].isupper():
        return fixed_lower.capitalize()
    return fixed_lower


def correct_query(query: str) -> tuple[str, list[tuple[str, str]]]:
    changes: list[tuple[str, str]] = []
    text = re.sub(r"\s+", " ", query).strip()
    # 0. curated typo/shorthand fixes (identifier-safe)
    text = _apply_fixed_maps(text, changes)
    # 1. multi-word alias merge (case-insensitive)
    lowered = text.lower()
    for alias, canon in sorted(_MULTI.items(), key=lambda kv: -len(kv[0])):
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")
        if pat.search(lowered):
            text = pat.sub(canon, text)
            lowered = text.lower()
            changes.append((alias, canon))
    # 2. per-token fuzzy fix (skip protected identifiers / numbers / short tokens)
    parts = re.split(r"(\s+)", text)
    out: list[str] = []
    for tok in parts:
        if not tok.strip() or _PROTECTED.match(tok.strip(".,?:;!\"'()")):
            out.append(tok)
            continue
        core = tok.strip(".,?:;!\"'()")
        if len(core) <= 4:
            out.append(tok)
            continue
        low = core.lower()
        if low in _VOCAB:
            # canonicalise known aliases (canif → CanIf) even when "correct"
            canon = MODULE_ALIASES.get(low)
            if canon and core != canon:
                out.append(tok.replace(core, canon))
                changes.append((core, canon))
            else:
                out.append(tok)
            continue
        hit = get_close_matches(low, _VOCAB, n=1, cutoff=0.86)
        if hit:
            fixed = _match_case(hit[0], core)
            out.append(tok.replace(core, fixed))
            changes.append((core, fixed))
        else:
            out.append(tok)
    return "".join(out), changes
