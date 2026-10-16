from app.config import Settings
from app.ingestion.classifier import classify_text
from app.processing.bidi import fix_word_order
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


def test_broken_ligatures_send_page_to_ocr():
    # lam ligatures mapped to Latin code points, as some PDF fonts do
    broken = URDU_PARAGRAPH.replace("ل", "Ǆ")
    d = classify_text(broken, 0.0, Settings(_env_file=None))
    assert d.method == "ocr" and "broken ligatures" in d.reason
