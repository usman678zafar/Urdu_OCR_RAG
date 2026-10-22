from app.config import Settings
from app.ingestion.classifier import classify_text
from app.processing.bidi import (
    WordOrderVotes,
    document_is_reversed,
    fix_word_order,
    word_order_votes,
)
from tests.conftest import ENGLISH_PARAGRAPH, URDU_PARAGRAPH

LINES = [
    "حکومت پنجاب نے طلبہ کے لیے نئی وظیفہ پالیسی کا اعلان کیا ہے۔",
    "اس پالیسی کے تحت ہر مستحق طالب علم کو ماہانہ بارہ ہزار روپے دیے جائیں گے۔",
    "درخواستیں ضلعی دفتر میں جمع کی جائیں گی۔",
]


def visual_order(line: str) -> str:
    return " ".join(reversed(line.split()))


def test_reversed_lines_are_repaired():
    broken = "\n".join(visual_order(line) for line in LINES)
    fixed, flipped = fix_word_order(broken)
    assert flipped
    assert fixed.split("\n") == LINES


def test_correct_text_is_left_alone():
    text = "\n".join(LINES)
    assert fix_word_order(text) == (text, False)
    assert fix_word_order(URDU_PARAGRAPH) == (URDU_PARAGRAPH, False)
    assert fix_word_order(ENGLISH_PARAGRAPH) == (ENGLISH_PARAGRAPH, False)


def test_english_lines_in_a_reversed_page_are_not_touched():
    broken = "\n".join([visual_order(line) for line in LINES] + ["Reference No. 45/2026"])
    fixed, flipped = fix_word_order(broken)
    assert flipped and fixed.endswith("Reference No. 45/2026")


def test_full_stops_on_first_word_mark_a_page_reversed():
    # no listed bigram in these lines; only the position of "۔" gives the order away
    lines = [
        "کمپنی کا نام بانی کی والدہ محترمہ روشن آراء بیگم کے نام پر رکھا گیا۔",
        "کمپنی کا سرکاری رنگ گہرا نیلا اور سنہرا ہے۔",
    ]
    assert word_order_votes("\n".join(lines)) == WordOrderVotes(forward=2, backward=0)
    fixed, flipped = fix_word_order("\n".join(visual_order(line) for line in lines))
    assert flipped and fixed.split("\n") == lines


def test_document_level_order_decision():
    reversed_page, unsure_page, in_order_page = WordOrderVotes(0, 6), WordOrderVotes(0, 1), WordOrderVotes(5, 0)
    assert document_is_reversed([reversed_page, reversed_page, unsure_page])
    assert not document_is_reversed([unsure_page] * 5)  # too little evidence overall
    assert not document_is_reversed([reversed_page, reversed_page, in_order_page])  # mixed signals


def test_broken_ligatures_send_page_to_ocr():
    # lam ligatures mapped to Latin code points, as some PDF fonts do
    broken = URDU_PARAGRAPH.replace("ل", "Ǆ")
    d = classify_text(broken, 0.0, Settings(_env_file=None))
    assert d.method == "ocr" and "broken ligatures" in d.reason
