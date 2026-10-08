"""Release / platform normalisation (spec §6). Deterministic, no LLM."""
from __future__ import annotations
import re

CLASSIC_LABELS = {"4.2.2": ("Classic_4.x", 4, 2, 2), "4.3.0": ("Classic_4.x", 4, 3, 0),
                  "4.3.1": ("Classic_4.x", 4, 3, 1), "4.4.0": ("Classic_4.x", 4, 4, 0)}
ADAPTIVE_LABELS = {"R19-11", "R20-11", "R21-11", "R22-11", "R23-11", "R24-11"}

MODULE_ALIASES = {
    "canif": "CanIf", "can interface": "CanIf",
    "pdurouter": "PduR", "pdu router": "PduR", "pdur": "PduR",
    "candrv": "CanDrv", "can driver": "CanDrv",
    "cansm": "CanSM", "can state manager": "CanSM",
    "com": "Com", "autosar com": "Com",
    "someip": "SOME-IP", "some-ip": "SOME-IP", "some/ip": "SOME-IP",
    "ecuc": "ECUC", "ecu configuration": "ECUC",
    "ara::com": "ara::com",
    "doip": "DoIP", "xcp": "XCP", "dcm": "Dcm", "dem": "Dem",
    # RTE / software-component world
    "rte": "RTE", "run-time environment": "RTE", "runtime environment": "RTE",
    "runnable": "RTE", "runnables": "RTE",
    "swc": "RTE", "software component": "RTE", "software components": "RTE",
    "vfb": "RTE", "virtual functional bus": "RTE",
    # Diagnostics: DTC / event memory lives in Dem, protocol/services in Dcm
    "dtc": "Dem", "diagnostic trouble code": "Dem", "diagnostic event": "Dem",
    "debounce": "Dem", "freeze frame": "Dem", "obd": "Dem",
    "uds": "Dcm", "unified diagnostic services": "Dcm",
    "det": "Det", "default error tracer": "Det",
    "bsw": "BSW", "basic software": "BSW",
    "mcal": "MCAL", "microcontroller abstraction": "MCAL",
}

# Generic umbrella words that legitimately span several modules. Values are
# tuples so the query parser can keep evidence from ALL of them (OR filter).
MODULE_GROUPS = {
    "diagnostic": ("Dcm", "Dem"),
    "diagnostics": ("Dcm", "Dem"),
}


def word_hit(text_lower: str, phrase: str) -> bool:
    """True when phrase occurs as whole word(s), never as a substring.

    This is the fix for the classic false positive where the alias ``com``
    matched inside "communication", "component", "complete" or "compare"
    and forced every such question through a Com-only evidence filter.
    """
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])",
                     text_lower) is not None


def module_for_api(api_name: str) -> str:
    """Infer the owning module from an AUTOSAR API name prefix (Dem_Xxx→Dem).

    Returns "" when the prefix is not a known module — no filter is always
    safer than a wrong filter.
    """
    prefix = (api_name or "").split("_")[0].strip().lower()
    if not prefix:
        return ""
    canon = MODULE_ALIASES.get(prefix, "")
    known = set(MODULE_ALIASES.values()) | {m for g in MODULE_GROUPS.values() for m in g}
    return canon if canon in known else ""

PLATFORM_WORDS = {"classic": "Classic", "adaptive": "Adaptive", "foundation": "Foundation"}


def normalize_release(label: str) -> dict:
    l = label.strip()
    if l in CLASSIC_LABELS:
        fam, maj, minor, patch = CLASSIC_LABELS[l]
        return {"release_family": fam, "release_label": l, "release_year": None,
                "platform": "Classic", "major": maj, "minor": minor, "patch": patch}
    m = re.fullmatch(r"R(\d{2})-11", l)
    if m:
        return {"release_family": "Adaptive_R", "release_label": l,
                "release_year": 2000 + int(m.group(1)), "platform": "Adaptive"}
    return {"release_family": "unknown", "release_label": l, "platform": "unknown"}


def detect_release_platform(text: str, filename: str) -> tuple[str, str, str]:
    """Return (release, platform, document_type) inferred deterministically."""
    blob = f"{filename}\n{text[:6000]}"
    # document type from AUTOSAR filename convention AUTOSAR_<RS|PRS|SWS|TPS|TR>_...
    doctype = "unknown"
    m = re.search(r"AUTOSAR_(FO_)?(PRS|RS|SWS|TPS|TR|EXP)", filename)
    if m:
        doctype = m.group(2)
    # platform / release hints
    platform = "unknown"
    if re.search(r"AUTOSAR_FO_", filename) or "foundation" in blob.lower():
        platform = "Foundation"
    release = ""
    mr = re.search(r"R(\d{2})-11", blob)
    if mr:
        release = f"R{mr.group(1)}-11"
        if platform == "unknown":
            platform = "Adaptive" if "adaptive" in blob.lower() else "Foundation"
    mc = re.search(r"\b4\.[2-4]\.\d\b", blob)
    if mc and not release:
        release = mc.group(0)
        platform = "Classic"
    return release, platform, doctype


def canonical_module(name: str) -> str:
    return MODULE_ALIASES.get(name.strip().lower(), name.strip())


def infer_module(text: str) -> str:
    """Frequency-based module inference from alias mentions (deterministic)."""
    import re as _re
    sample = text[:20000].lower()
    scores: dict[str, int] = {}
    for alias, canon in MODULE_ALIASES.items():
        n = len(_re.findall(r"(?<![a-z0-9])" + _re.escape(alias) + r"(?![a-z0-9])", sample))
        if n:
            scores[canon] = scores.get(canon, 0) + n
    if not scores:
        return ""
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] >= 3 else ""
