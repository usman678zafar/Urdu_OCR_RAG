from app.generation.citations import build_citations, quote_in_passage
from app.processing.chunking import chunk_page, chunk_pages
from app.processing.cleanup import strip_headers_footers
from app.processing.normalize import normalize
from app.retrieval.hybrid import RetrievedChunk, rrf_fuse
from tests.conftest import ENGLISH_PARAGRAPH, URDU_PARAGRAPH


def test_chunks_stay_on_their_page_and_respect_size():
    pages = [(1, normalize(URDU_PARAGRAPH * 4)), (2, ENGLISH_PARAGRAPH * 3)]
    chunks = chunk_pages(pages, size=300, overlap=80)
    assert {c.page_no for c in chunks} == {1, 2}
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(len(c.text) <= 300 + 120 for c in chunks)
    assert {c.language for c in chunks if c.page_no == 1} == {"ur"}
    assert {c.language for c in chunks if c.page_no == 2} == {"en"}


def test_chunk_overlap_carries_last_sentence():
    text = normalize(URDU_PARAGRAPH)
    chunks = chunk_page(text, 1, size=150, overlap=100)
    assert len(chunks) > 1
    last_sentence_of_first = chunks[0].text.split("۔")[-2].strip()
    assert last_sentence_of_first in chunks[1].text


def test_long_sentence_without_punctuation_is_split():
    chunks = chunk_page("word " * 500, 1, size=200, overlap=0)
    assert len(chunks) > 5 and all(len(c.text) <= 200 for c in chunks)


def test_headers_footers_and_page_numbers_removed():
    topics = ["admissions", "stipends", "transport", "hostels"]
    pages = [
        f"Government of Punjab\nWelfare Department\nBody text about {t}.\nClosing line on {t}.\nPage {n} of 4"
        for n, t in enumerate(topics, 1)
    ]
    pages[2] = pages[2].replace("Body text", "صفحہ کا متن") + "\n۳"
    cleaned = strip_headers_footers(pages)
    for text, topic in zip(cleaned, topics):
        assert "Government of Punjab" not in text
        assert "Page" not in text
        assert f"Closing line on {topic}." in text
    assert "۳" not in cleaned[2]


def test_short_document_keeps_lines():
    pages = ["Title\nBody one", "Title\nBody two"]
    assert strip_headers_footers(pages) == pages


def _chunk(cid, text, page=1):
    return RetrievedChunk(
        chunk_id=cid,
        document_id=1,
        filename="a.pdf",
        page_no=page,
        text=text,
        score=1.0,
        dense_rank=0,
        bm25_rank=0,
    )


def test_citations_verified_and_unknown_ids_dropped():
    chunks = [_chunk(10, normalize(URDU_PARAGRAPH)), _chunk(11, ENGLISH_PARAGRAPH, page=2)]
    raw = [
        {"source_id": "S1", "quote": "ماہانہ بارہ ہزار روپے دیے جائیں گے"},
        {"source_id": "S2", "quote": "a monthly stipend of Rs. 12,000"},
        {"source_id": "S2", "quote": "duplicate"},
        {"source_id": "S7", "quote": "no such source"},
    ]
    cites = build_citations(raw, chunks)
    assert [(c.chunk_id, c.page_no) for c in cites] == [(10, 1), (11, 2)]
    assert all(c.quote_verified for c in cites)


def test_quote_matching_tolerates_variants_but_rejects_inventions():
    passage = normalize(URDU_PARAGRAPH)
    assert quote_in_passage("ماهانه بارہ ہزار روپے", passage)  # Arabic heh variants
    assert not quote_in_passage("وظیفہ صرف لڑکیوں کے لیے ہے اور پچاس ہزار روپے", passage)


def test_rrf_rewards_agreement():
    fused = [cid for cid, _ in rrf_fuse([1, 2, 3], [3, 4, 1])]
    assert fused[:2] == [1, 3] or fused[:2] == [3, 1]
    assert set(fused) == {1, 2, 3, 4}
