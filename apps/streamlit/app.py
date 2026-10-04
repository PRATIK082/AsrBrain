"""Chatbox-like AUTOSAR copilot (ChatGPT-style). Self-contained Streamlit fallback:
talks to the same src/ engine in-process (no API server required).

- No corpus-filter sidebar: release/platform asked back only when missing,
  module auto-detected with Confirm/Change, doctype fully automatic.
- Provider: local Ollama model picker + OpenAI-compatible cloud (GPT/Gemini/
  Opencode/Cloud) with session-only API key.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root (…/apps/streamlit/app.py → …/)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import re
import streamlit as st
import streamlit.components.v1 as components


def _autoscroll():
    """ChatGPT-style follow: pin the view to the newest message after each run."""
    components.html(
        "<script>const el = window.parent.document.querySelector('section[data-testid=\"stMain\"]');"
        "if (el) el.scrollTop = el.scrollHeight;</script>", height=0)


def _split_sources(content: str) -> tuple[str, str]:
    if "\n## Sources\n" in content:
        body, src = content.split("\n## Sources\n", 1)
        return body, src
    return content, ""


def _compact_sources(src: str) -> list[str]:
    """One line per [E#] block: file · pages · release · section."""
    lines: list[str] = []
    for block in re.split(r"(?m)^(?=\[E\d+\])", src):
        block = block.strip()
        if not block.startswith("["):
            continue
        label = block.split("\n", 1)[0].strip()
        pdf = re.search(r"Source:\s*(.+)", block)
        pages = re.search(r"Pages:\s*(\S+)", block)
        rel = re.search(r"Release:\s*(.+)", block)
        sec = re.search(r"Section:\s*(.+)", block)
        lines.append(f"{label} `{pdf.group(1).strip() if pdf else '?'}` "
                     f"p.{pages.group(1) if pages else '?'} · "
                     f"{(rel.group(1).strip() if rel else '').strip() or '?'} · "
                     f"{(sec.group(1).strip() if sec else '').strip() or '—'}")
    return lines

from src.config.settings import settings
from src.indexing.hybrid import HybridIndex, load_chunks
from src.retrieval.pipeline import RetrievalPipeline
from src.workflows.stages import run_staged
from src.generation.providers import ProviderSpec, list_ollama_models
from src.chat.store import ChatStore
from src.ingestion.pipeline import run as run_ingest

st.set_page_config(page_title="AUTOSAR Copilot", page_icon="🚗", layout="wide")

store = ChatStore()

# ---------------- cached engine ----------------
@st.cache_resource
def _engine():
    chunks = load_chunks(settings.canonical_db)
    try:
        idx = HybridIndex.load("data/indexes/hybrid")
        if len(idx.chunk_ids) != len(chunks):
            raise ValueError("stale")
    except Exception:
        idx = HybridIndex()
        idx.build(chunks or [{"chunk_id": "empty", "normalized_text": "",
                              "section_title": "", "requirement_ids": [], "api_names": []}])
        idx.save("data/indexes/hybrid")
    return RetrievalPipeline(idx, chunks)


def _spec_from_session() -> ProviderSpec:
    if st.session_state.get("provider") == "cloud":
        return ProviderSpec(kind="openai_compat",
                            model=st.session_state.get("cloud_model", "gpt-4o-mini"),
                            base_url=st.session_state.get("cloud_base", "https://api.openai.com/v1"),
                            api_key=st.session_state.get("cloud_key", ""),
                            timeout_s=180.0)
    models = list_ollama_models(settings.ollama_base_url)
    want = st.session_state.get("ollama_model", "")
    model = want if want in models else (models[0] if models else settings.llm_model)
    return ProviderSpec(kind="ollama", model=model, base_url=settings.ollama_base_url, timeout_s=180.0)


def _cite_labels(text: str) -> list[str]:
    return sorted({m.group(0) for m in re.finditer(r"\[E\d+\]", text or "")},
                  key=lambda s: int(s[2:-1]))

# ---------------- session ----------------
if "cid" not in st.session_state:
    convs = store.list()
    st.session_state.cid = convs[0]["id"] if convs else store.create()["id"]
if "provider" not in st.session_state:
    st.session_state.provider = "ollama"
if "editing" not in st.session_state:
    st.session_state.editing = {}

# per-conversation model: opening a chat restores the model it used last,
# so different AI models keep their own context and can start work separately
_cid_slots = store.get_slots(st.session_state.cid)
if st.session_state.get("_model_cid") != st.session_state.cid:
    st.session_state.provider = _cid_slots.get("provider", st.session_state.provider)
    for _k in ("ollama_model", "cloud_model", "cloud_base"):
        if _cid_slots.get(_k):
            st.session_state[_k] = _cid_slots[_k]
    st.session_state._model_cid = st.session_state.cid
    st.session_state.pop("last", None)
    st.session_state.pop("last_evidence", None)
    st.session_state.pop("last_followups", None)
    st.session_state.pop("clarify", None)

# ---------------- sidebar: conversations + settings ----------------
with st.sidebar:
    st.header("💬 Conversations")
    if st.button("＋ New conversation", use_container_width=True):
        st.session_state.cid = store.create()["id"]
        st.rerun()
    q = st.text_input("Search conversations", placeholder="filter…")
    for conv in store.list():
        if q and q.lower() not in (conv["title"] or "").lower():
            continue
        cols = st.columns([4, 1])
        label = ("▶ " if conv["id"] == st.session_state.cid else "") + (conv["title"] or "Untitled")[:34]
        if cols[0].button(label, key=f"open_{conv['id']}", use_container_width=True):
            st.session_state.cid = conv["id"]
            st.rerun()
        if cols[1].button("🗑", key=f"del_{conv['id']}"):
            store.delete(conv["id"])
            st.session_state.cid = (store.list() or [{"id": store.create()["id"]}])[0]["id"]
            st.rerun()
    with st.expander("Rename current"):
        cur = store.get(st.session_state.cid) or {}
        name = st.text_input("Title", cur.get("title", ""))
        if st.button("Save title") and name:
            store.patch(st.session_state.cid, title=name)
            st.rerun()
    if st.button("⑂ Fork with another model", use_container_width=True,
                 help="Same release/platform/module slots, fresh history — pick a different model below and start work."):
        src_slots = store.get_slots(st.session_state.cid)
        new = store.create((store.get(st.session_state.cid) or {}).get("title", "") + " (fork)")
        import json as _j2, sqlite3 as _s2
        _c = _s2.connect("data/canonical/chat.db")
        _c.execute("UPDATE conversations SET slots_json = ? WHERE id = ?",
                   (_j2.dumps({k: v for k, v in src_slots.items()
                               if k in ("releases", "platforms", "modules", "skip_clarify")}), new["id"]))
        _c.commit()
        _c.close()
        st.session_state.cid = new["id"]
        st.session_state._model_cid = ""
        st.rerun()
    with st.expander("💾 Session save / resume"):
        st.caption("Portable save file: messages + slots + model. Resume here or on another machine — no re-ingest, no lost context.")
        _bundle = store.export_bundle(st.session_state.cid)
        st.download_button("⬇ Save session (.json)", json.dumps(_bundle or {}, indent=2),
                           file_name="autosar_session.json", use_container_width=True)
        _up = st.file_uploader("Resume a saved session", type=["json"], key="bundle_up")
        if _up is not None and st.button("Load session"):
            try:
                _imp = store.import_bundle(json.loads(_up.read().decode()))
                st.session_state.cid = _imp["id"]
                st.session_state._model_cid = ""
                st.success(f"Resumed {_imp['imported_messages']} messages.")
                st.rerun()
            except Exception as e:
                st.error(f"Not a valid session file: {e}")
    st.divider()
    st.header("🤖 Model")
    st.session_state.provider = st.radio("Provider", ["ollama", "cloud"],
                                         format_func=lambda x: "Local Ollama" if x == "ollama" else "Cloud (API key)",
                                         horizontal=True)
    if st.session_state.provider == "ollama":
        models = list_ollama_models(settings.ollama_base_url)
        if models:
            st.session_state.ollama_model = st.selectbox("Ollama model", models)
        else:
            st.warning("Ollama unreachable — answers use cited extractive fallback.")
            st.session_state.ollama_model = st.text_input("Model name", settings.llm_model)
    else:
        st.session_state.cloud_base = st.text_input("Base URL (OpenAI-compatible)",
            st.session_state.get("cloud_base", "https://api.openai.com/v1"),
            help="OpenAI, Gemini OpenAI-compat endpoint, Opencode/Cloud, OpenRouter…")
        st.session_state.cloud_model = st.text_input("Model", st.session_state.get("cloud_model", "gpt-4o-mini"))
        st.session_state.cloud_key = st.text_input("API key", type="password",
            help="Kept in session memory only — never logged or saved.")
    st.subheader("Answer speed / depth")
    depth = st.radio("Evidence depth", ["Eco (4)", "Balanced (8)", "Deep (12)"], index=1,
                     help="Fewer passages = faster answers on CPU. Retrieval breadth is unchanged.")
    st.session_state.depth = {"Eco (4)": 4, "Balanced (8)": 8, "Deep (12)": 12}[depth]
    length = st.radio("Response length", ["Concise", "Standard", "Detailed"], index=0,
                      help="Caps generated tokens: Concise ≈ 1–2 min on CPU, Detailed slower.")
    st.session_state.num_predict = {"Concise": 400, "Standard": 600, "Detailed": 1200}[length]
    with st.expander("Advanced overrides (optional)"):
        st.caption("Normally unnecessary: release/platform are asked back when missing, module auto-detected, document type automatic.")
        adv_rel = st.text_input("Force release (blank = auto)")
        adv_plat = st.selectbox("Force platform", ["", "Classic", "Adaptive", "Foundation"])
        adv_mod = st.text_input("Force module (blank = auto-detect)")
        skip_cl = st.checkbox("Answer generally without asking back", False)
        st.session_state.adv = {"rel": adv_rel, "plat": adv_plat, "mod": adv_mod, "skip": skip_cl}
    st.divider()
    st.header("📄 Documents")
    up = st.file_uploader("Upload AUTOSAR PDF", type=["pdf"])
    if up is not None and st.button("Ingest upload"):
        dest = f"pdf/uploads/{up.name}"
        import os
        import time as _t
        os.makedirs("pdf/uploads", exist_ok=True)
        with open(dest, "wb") as f:
            f.write(up.getbuffer())
        prog = st.progress(0, text="Saving…")
        try:
            t0 = _t.time()
            with st.spinner("Parsing + chunking (full corpus re-index; time scales with corpus size)…"):
                prog.progress(30, text="Parsing PDF…")
                res = run_ingest(settings.pdf_dir, "data/canonical")
            prog.progress(70, text="Rebuilding index…")
            chunks = load_chunks(settings.canonical_db)
            idx = HybridIndex()
            idx.build(chunks)
            idx.save("data/indexes/hybrid")
            _engine.clear()
            prog.progress(100, text="Done")
            st.success(f"Ingested {up.name} in {int(_t.time()-t0)}s — {res.get('documents', '?')} doc(s) indexed.")
        except Exception as e:
            st.error(f"Ingest failed: {e}")
    conv_now = store.get(st.session_state.cid) or {"messages": []}
    md_now = "\n\n---\n\n".join(f"**{m['role']}**:\n\n{m['content']}" for m in conv_now["messages"])
    st.download_button("⬇ Export conversation (.md)", md_now or "No messages yet.",
                       file_name="conversation.md", use_container_width=True)

# ---------------- main chat ----------------
st.title("🚗 AUTOSAR Knowledge Copilot")
conv = store.get(st.session_state.cid) or {"messages": [], "slots": {}}
slots = conv.get("slots", {})

# resume persisted working context (evidence/trace/follow-ups survive restarts)
if "last" not in st.session_state:
    _last_asst = next((m for m in reversed(conv.get("messages", []))
                       if m["role"] == "assistant" and m.get("meta", {}).get("trace")), None)
    _meta = (_last_asst or {}).get("meta", {})
    st.session_state.last = {"trace": _meta.get("trace", {}), "llm": _meta.get("llm", ""),
                             "plan": _meta.get("plan", {}), "graph": _meta.get("graph", [])}
    st.session_state.last_evidence = _meta.get("evidence", [])
    st.session_state.last_followups = _meta.get("followups", [])

def _apply_clarify(text: str, slot: str = ""):
    """Fold a chip click / typed clarification reply into conversation slots, then re-ask."""
    import json as _j
    import sqlite3 as _s
    from src.retrieval.query_understanding import parse
    conv = store.get(st.session_state.cid) or {}
    msgs = conv.get("messages", [])
    last_user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
    if slot == "modules" and text != "any release":
        merged = store.get_slots(st.session_state.cid)
        merged["modules"] = [text]
        merged["module_confirmed"] = True
    elif "any release" in text.lower():
        merged = store.get_slots(st.session_state.cid)
        merged["skip_clarify"] = True
    else:
        plan = parse(text)
        merged = store.merge_slots(st.session_state.cid, releases=plan.releases,
                                   platforms=plan.platforms, modules=plan.modules)
        if plan.modules:
            merged["module_confirmed"] = True
    c = _s.connect("data/canonical/chat.db")
    c.execute("UPDATE conversations SET slots_json = ? WHERE id = ?", (_j.dumps(merged), st.session_state.cid))
    c.commit()
    c.close()
    st.session_state.pop("clarify", None)
    st.session_state.pending = last_user
    st.rerun()


tab_chat, tab_ev, tab_trace, tab_graph = st.tabs(["Chat", "Evidence", "Trace", "Graph"])
with tab_chat:
    for i, m in enumerate(conv.get("messages", [])):
        with st.chat_message(m["role"]):
            if m["role"] == "assistant":
                body, src = _split_sources(m["content"])
                st.markdown(body)
                if src.strip():
                    with st.expander(f"📚 Sources ({len(_cite_labels(m['content']))})", expanded=False):
                        for line in _compact_sources(src):
                            st.markdown(f"- {line}")
            else:
                st.markdown(m["content"])
            if m["role"] == "assistant":
                c1, c2, c3 = st.columns([1, 1, 6])
                if c1.button("👍", key=f"up_{i}"):
                    store.add_feedback(st.session_state.cid, i, "up")
                    st.toast("Feedback recorded")
                if c2.button("👎", key=f"neg_{i}"):
                    store.add_feedback(st.session_state.cid, i, "down")
                    st.toast("Feedback recorded — add the gold answer to data/benchmarks/")
            else:
                if st.button("✏️ Edit & resend", key=f"edit_{i}"):
                    st.session_state.editing[i] = m["content"]
        if i in st.session_state.editing:
            new = st.text_area("Edit message", st.session_state.editing[i], key=f"ta_{i}")
            if st.button("Resend", key=f"resend_{i}"):
                del st.session_state.editing[i]
                st.session_state.pending = new
                st.rerun()

    prompt = st.chat_input("Ask about AUTOSAR… (release/platform asked back only if missing)")
    pending = st.session_state.pop("pending", None) or prompt
    if pending:
        st.session_state.last_followups = []
        with st.chat_message("user"):
            st.markdown(pending)
        store.add_message(st.session_state.cid, "user", pending)
        adv = st.session_state.get("adv", {})
        known = dict(slots)
        if adv.get("rel"):
            known["releases"] = [adv["rel"]]
        if adv.get("plat"):
            known["platforms"] = [adv["plat"]]
        if adv.get("mod"):
            known["modules"] = [adv["mod"]]
            known["module_confirmed"] = True
        if adv.get("skip"):
            known["skip_clarify"] = True
        spec = _spec_from_session()
        settings.llm_num_predict = st.session_state.get("num_predict", 600)
        depth_k = st.session_state.get("depth", 8)
        import queue as _queue
        import threading as _threading
        import time as _time
        q: _queue.Queue = _queue.Queue()

        def _pump():
            try:
                _hist = [{"role": m["role"], "content": m["content"]}
                         for m in conv.get("messages", [])]
                for _ev in run_staged(_engine(), pending, spec, {}, known,
                                      top_k=depth_k, history=_hist):
                    q.put(_ev)
            except Exception as e:  # never leave the UI spinning silently
                q.put({"event": "status", "stage": "error", "message": str(e)[:300]})
            finally:
                q.put(None)

        _threading.Thread(target=_pump, daemon=True).start()
        t0 = _time.time()
        with st.chat_message("assistant"):
            status = st.status("Working…", expanded=False)
            ph = st.empty()
            acc, final_ev = "", None
            ev_cards: list[dict] = []
            clarify_ev = None
            alive = True
            while alive:
                try:
                    ev = q.get(timeout=0.5)
                except _queue.Empty:
                    el = int(_time.time() - t0)
                    status.update(label=f"answer_drafting: generating… {el}s "
                                        f"(capped at {settings.llm_num_predict} tokens; "
                                        f"⏹ top-right menu stops the run)", state="running")
                    continue
                if ev is None:
                    alive = False
                    break
                kind = ev.get("event")
                if kind == "status":
                    status.update(label=f"{ev.get('stage')}: {ev.get('message')}", state="running")
                elif kind == "clarify":
                    clarify_ev = ev
                    alive = False
                elif kind == "token":
                    acc += ev.get("text", "")
                    ph.markdown(acc + "▌")
                elif kind == "evidence":
                    ev_cards.append(ev)
                elif kind == "complete":
                    final_ev = ev
            status.update(label="Done", state="complete")
            if clarify_ev is not None:
                st.session_state.clarify = clarify_ev
                st.markdown(clarify_ev["question"])
                store.add_message(st.session_state.cid, "assistant", clarify_ev["question"],
                                  {"clarify": clarify_ev.get("missing", [])})
                st.rerun()
            full = (final_ev or {}).get("answer", acc)
            body, src = _split_sources(full)
            ph.markdown(body)  # chat shows the answer; sources collapse below
            if src.strip():
                with st.expander(f"📚 Sources ({len(_cite_labels(full))})", expanded=False):
                    for line in _compact_sources(src):
                        st.markdown(f"- {line}")
            plan = (final_ev or {}).get("plan", {})
            if plan.get("corrections"):
                st.caption("Interpreted as: " + "; ".join(
                    f"“{a}” → “{b}”" for a, b in
                    [(c.get("from", ""), c.get("to", "")) for c in plan["corrections"]]))
            # persist model with the conversation: each chat keeps its own AI model
            _cur_model = {"provider": st.session_state.get("provider", "ollama"),
                          "ollama_model": st.session_state.get("ollama_model", ""),
                          "cloud_model": st.session_state.get("cloud_model", ""),
                          "cloud_base": st.session_state.get("cloud_base", "")}
            import sqlite3 as _s3
            _merged = store.get_slots(st.session_state.cid)
            _merged.update({k: v for k, v in _cur_model.items() if v})
            _c3 = _s3.connect("data/canonical/chat.db")
            _c3.execute("UPDATE conversations SET slots_json = ? WHERE id = ?",
                        (json.dumps(_merged), st.session_state.cid))
            _c3.commit()
            _c3.close()
            store.add_message(st.session_state.cid, "assistant", full,
                              {"trace": (final_ev or {}).get("trace", {}),
                               "llm": (final_ev or {}).get("llm", ""),
                               "plan": plan,
                               "graph": (final_ev or {}).get("graph", []),
                               "evidence": ev_cards,
                               "followups": (final_ev or {}).get("followups", [])})
            st.session_state.last = final_ev or {}
            st.session_state.last_evidence = ev_cards
            st.session_state.last_followups = (final_ev or {}).get("followups", [])
            st.rerun()

    # follow-up suggestions: continue the result or type your own next question
    fups = st.session_state.get("last_followups", [])
    if fups and not st.session_state.get("clarify"):
        st.caption("Continue exploring:")
        fcols = st.columns(len(fups))
        for k, f in enumerate(fups):
            if fcols[k].button(f, key=f"fup_{k}"):
                st.session_state.last_followups = []
                st.session_state.pending = f
                st.rerun()

    _autoscroll()

    # clarification chips (req. 1)
    cl = st.session_state.get("clarify")
    if cl:
        st.info(cl["question"])
        chips = st.columns(4)
        rels = ["4.4.0", "4.3.1", "R22-11", "any release"]
        for k, r in enumerate(rels):
            if chips[k % 4].button(r, key=f"chip_rel_{r}"):
                _apply_clarify(r)
        mods = cl.get("detected_modules", [])
        if mods:
            mcols = st.columns(len(mods) + 1)
            for k, m in enumerate(mods):
                if mcols[k].button(f"✓ {m}", key=f"chip_mod_{m}"):
                    _apply_clarify(m, slot="modules")
            new_mod = mcols[len(mods)].selectbox("Change module",
                ["", "CanIf", "CanDrv", "CanSM", "PduR", "Com", "SOME-IP", "ECUC", "Dcm", "Dem", "DoIP"])
            if new_mod and st.button("Use module", key="chip_mod_use"):
                _apply_clarify(new_mod, slot="modules")
        st.caption("To stop a running generation use Streamlit's ⏹ stop control (top-right running indicator); "
                   "the API/SSE path supports per-request /stop.")


with tab_ev:
    cards = st.session_state.get("last_evidence", [])
    st.caption("Exact retrieved passages for the last answer — each card links to its source page.")
    if not cards:
        st.info("Ask a question in Chat — evidence cards with page previews appear here.")
    for e in cards:
        with st.expander(f"{e.get('label')} · {e.get('source_pdf','')} p.{e.get('page')} · "
                         f"{e.get('release') or '?'} · rel={e.get('relevance', 0):.2f}", expanded=False):
            st.markdown(f"**Section:** {e.get('section') or '—'}  \n"
                        f"**Module:** {e.get('module') or '—'} · **Platform:** {e.get('platform') or '—'}  \n"
                        f"**Requirements:** {', '.join(e.get('requirement_ids', [])) or '—'}")
            st.text(e.get("snippet", ""))
with tab_trace:
    last = st.session_state.get("last", {})
    if last:
        st.json(last.get("trace", {}))
    else:
        st.caption("Safe operational summary (query plan, filters, counts, coverage, confidence) appears here.")
with tab_graph:
    last = st.session_state.get("last", {})
    edges = (last.get("graph", []) or [])
    if edges:
        for e in edges[:30]:
            flag = " (inferred)" if e.get("is_inferred") else ""
            st.markdown(f"`{e['subject']} → {e['object']}` *{e['predicate']}*{flag} — {e.get('source_pdf','')} p.{e.get('page')}")
    else:
        st.caption("Module/API relationship edges with source links appear here.")
