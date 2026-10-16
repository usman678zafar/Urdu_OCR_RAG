from app.config import Settings
from app.ingestion.classifier import classify_text
from tests.conftest import ENGLISH_PARAGRAPH, URDU_PARAGRAPH

S = Settings(_env_file=None)


def test_clean_urdu_and_english_use_text_layer():
    assert classify_text(URDU_PARAGRAPH, 0.0, S).method == "text"
    assert classify_text(ENGLISH_PARAGRAPH, 0.0, S).method == "text"
    assert classify_text(URDU_PARAGRAPH + "\n" + ENGLISH_PARAGRAPH, 0.0, S).method == "text"


def test_empty_page_needs_ocr():
    d = classify_text("  \n 3 \n", 1.0, S)
    assert d.method == "ocr" and d.reason == "no usable text layer"


def test_reversed_urdu_needs_ocr():
    reversed_words = " ".join(w[::-1] for w in URDU_PARAGRAPH.split())
    d = classify_text(reversed_words, 0.0, S)
    assert d.method == "ocr" and "common Urdu words" in d.reason


def test_split_letters_need_ocr():
    split = " ".join(URDU_PARAGRAPH.replace(" ", ""))
    d = classify_text(split, 0.0, S)
    assert d.method == "ocr" and d.reason == "letters are split apart"


def test_inpage_mojibake_needs_ocr():
    mojibake = "ÇÓáÇã Úáíßã ÍßæãÊ ÈäÌÇÈ äÜ ØáÈÜ ßÜ áíÜ äÆí æÙíÝÜ ÇáíÓí ßÇ ÇÚáÇä ßíÇ ÜÜ " * 4
    d = classify_text(mojibake, 0.0, S)
    assert d.method == "ocr" and d.reason == "text layer is Latin-1 mojibake"


def test_private_use_glyphs_need_ocr():
    pua = "".join(chr(0xE000 + (i % 200)) for i in range(300))
    d = classify_text(pua + " abc", 0.0, S)
    assert d.method == "ocr" and "private-use" in d.reason


def test_scan_with_small_typed_header_needs_ocr():
    d = classify_text("Government of the Punjab, Social Welfare Department — Notice No. 45/2026", 0.95, S)
    assert d.method == "ocr" and "mostly an image" in d.reason


def test_ascii_gibberish_from_font_remapping_needs_ocr():
    gibberish = " ".join(["kdq", "wqb", "zxl", "mmrf", "plkj", "ghtr", "vbnx", "qwzr"] * 25)
    assert classify_text(gibberish, 0.0, S).method == "ocr"
