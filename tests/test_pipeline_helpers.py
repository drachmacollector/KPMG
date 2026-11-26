import json

import pytest

import scoring
import web_resolver as wr
from extractor import parse_llm_json


# --- web_resolver ---------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Government Medical College",
    "Government Dental College",
    "B J Medical College",
])
def test_short_real_names_are_not_generic(name):
    assert not wr._is_generic_name(name)


@pytest.mark.parametrize("name", ["Medical College", "Ayurvedic College & Hospital", ""])
def test_purely_generic_names_are_rejected(name):
    assert wr._is_generic_name(name)


def test_clean_address_dedups_pin_and_noise():
    out = wr.clean_address("Rajapeth, Amravati 444606, Phone No. 12345, Amravati 444606")
    assert out.count("444606") == 1
    assert "Phone" not in out


def test_unverifiable_stops_model_chain(monkeypatch):
    calls = []

    class FakeModels:
        def generate_content(self, model, **_):
            calls.append(model)

            class R:
                text = json.dumps({"verified": False})
            return R()

        def list(self):
            return [type("M", (), {"name": f"models/{m}"}) for m in wr.GEMINI_MODELS]

    resolver = wr.GeminiResolver.__new__(wr.GeminiResolver)
    resolver._client = type("C", (), {"models": FakeModels()})()
    monkeypatch.setattr(wr, "_available_models", None)
    with pytest.raises(wr.LLMUnverifiableError):
        resolver.resolve("X College", "Pune")
    assert len(calls) == 1


def test_unknown_models_are_skipped(monkeypatch):
    class FakeModels:
        def list(self):
            return [type("M", (), {"name": "models/" + wr.GEMINI_MODELS[1]})]

    monkeypatch.setattr(wr, "_available_models", None)
    client = type("C", (), {"models": FakeModels()})()
    assert wr._usable_models(client) == [wr.GEMINI_MODELS[1]]


def test_cache_save_is_atomic_and_corrupt_cache_is_backed_up(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wr._save_cache({"a": {"official_name": "A"}})
    assert wr._load_cache() == {"a": {"official_name": "A"}}
    (tmp_path / wr.CACHE_PATH).write_text("{broken", encoding="utf-8")
    assert wr._load_cache() == {}
    assert any(p.name.startswith(wr.CACHE_PATH + ".corrupt-") for p in tmp_path.iterdir())


# --- scoring --------------------------------------------------------------

def _page(doc, name, conf=0.9, relevant=True, lines=5):
    return {"document": doc, "college_name": name, "avg_confidence": conf,
            "is_relevant": relevant, "line_count": lines}


OK = {"resolution_failed": False, "match_confidence": 100}


def test_two_agreeing_documents_get_full_cross_doc_score():
    pages = [_page("bonafide", "Govt Medical College Nagpur"),
             _page("college_id", "Government Medical College, Nagpur")]
    assert scoring.compute_accuracy(pages, None, OK) == 27 + 40 + 30


def test_two_pages_of_one_document_count_once():
    pages = [_page("bonafide", "X"), _page("bonafide", "X")]
    assert scoring.compute_accuracy(pages, None, OK) == 27 + 40 + 15


def test_disagreeing_documents_get_no_cross_doc_score():
    pages = [_page("bonafide", "Alpha Dental College"), _page("college_id", "Zeta Ayurved Institute")]
    assert scoring.compute_accuracy(pages, None, OK) == 27 + 40


def test_irrelevant_pages_do_not_dilute_ocr_score():
    pages = [_page("bonafide", "X", conf=1.0), _page("aadhaar", "", conf=0.0, relevant=False)]
    assert scoring.compute_accuracy(pages, None, None) == 30 + 0 + 15


def test_failed_resolution_scores_no_verification_points():
    assert scoring.compute_accuracy([], None, {"resolution_failed": True, "match_confidence": 90}) == 0


# --- extractor ------------------------------------------------------------

def test_parse_llm_json_handles_fences_and_garbage():
    assert parse_llm_json('```json\n{"relevant": true, "college_name": "A {x}"}\n```')["college_name"] == "A {x}"
    assert parse_llm_json("nonsense")["parse_error"] is True


# --- document_processor ---------------------------------------------------

def test_sniff_extension(tmp_path):
    from document_processor import sniff_extension
    cases = {b"%PDF-1.7": ".pdf", b"\xff\xd8\xff\xe0": ".jpg", b"\x89PNG\r\n\x1a\nxxxx": ".png", b"hello": ""}
    for i, (head, ext) in enumerate(cases.items()):
        f = tmp_path / f"f{i}"
        f.write_bytes(head + b"\0" * 16)
        assert sniff_extension(str(f)) == ext


# --- verify_colleges ------------------------------------------------------

def test_normalize_ack():
    import verify_colleges as v
    assert v.normalize_ack(12345.0) == "12345"
    assert v.normalize_ack("123.0") == "123"
    assert v.normalize_ack(float("nan")) == ""
    assert v.normalize_ack(" A12 ") == "A12"


def test_document_links_are_absolute():
    import verify_colleges as v
    html = '<label>Bonafide Certificate</label><a href="/f/x.pdf">x</a>'
    assert v.extract_document_links(html, "https://iwbms.mahabocw.in/c/1") == {
        "bonafide": "https://iwbms.mahabocw.in/f/x.pdf"}
