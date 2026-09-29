from src.generation import answer


def test_generate_ollama_builds_prompt(monkeypatch):
    captured = {}

    class R:
        status_code = 200

        def json(self):
            return {"response": "hi [E1]"}

    def fake_post(url, json=None, timeout=None):
        captured.update(json or {})
        return R()

    monkeypatch.setattr(answer.httpx, "post", fake_post)
    ev = [{"chunk_id": "c", "source_pdf": "f.pdf", "page_start": 1, "page_end": 1,
           "autosar_release": "R24-11", "platform": "Foundation", "module": "SOME-IP",
           "document_type": "PRS", "section_number": "", "section_title": "",
           "requirement_ids": [], "normalized_text": "x", "compressed": "x"}]
    out = answer._generate_ollama("q?", ev, False)
    assert out["draft"] == "hi [E1]"
    assert "Question: q?" in captured["prompt"] and "Evidence" in captured["prompt"]
