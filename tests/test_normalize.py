from app.processing.language import detect_language, question_language
from app.processing.normalize import normalize, tokenize


def test_letter_variants_unified():
    # Arabic yeh, kaf and heh typed on an Arabic keyboard
    assert normalize("كيا") == normalize("کیا") == "کیا"
    assert normalize("مدرسه") == "مدرسہ"
    assert normalize("ى") == "ی"


def test_presentation_forms_become_base_letters():
    # ﻛﺘﺎﺏ written with Arabic presentation forms, as some PDF text layers do
    assert normalize("ﻛﺘﺎﺏ") == "کتاب"


def test_digits_and_diacritics():
    assert normalize("۲۰۲۶") == "2026"
    assert normalize("٣") == "3"
    assert normalize("م\u064fح\u064eم\u064e\u0651د") == "محمد"
    assert normalize("پاکستانــ") == "پاکستان"


def test_heh_hamza_composed():
    assert normalize("خانہ\u0654") == "خانۂ"


def test_spacing_and_punctuation():
    assert normalize("یہ  جملہ ہے ۔دوسرا") == "یہ جملہ ہے۔ دوسرا"
    assert normalize("line one\n\n\n\nline two") == "line one\n\nline two"
    assert normalize("  \u200fیہ\u200f  ") == "یہ"


def test_tokenize_mixed():
    assert tokenize(normalize("Policy 2026 کی آخری تاریخ")) == ["policy", "2026", "کی", "آخری", "تاریخ"]


def test_language_detection():
    assert detect_language("یہ اردو ہے") == "ur"
    assert detect_language("This is English") == "en"
    assert question_language("What is the deadline?") == "en"
    assert question_language("آخری تاریخ کیا ہے؟") == "ur"
