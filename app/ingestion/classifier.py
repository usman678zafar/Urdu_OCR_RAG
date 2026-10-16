"""Decide per page whether to trust the PDF text layer or run OCR.

InPage-exported PDFs often have a text layer that looks present but extracts as
gibberish: private-use glyphs, Latin-1 mojibake, letters split apart, or words in
reverse order. Each check below catches one of those failure modes.
"""

from dataclasses import asdict, dataclass
from typing import Literal

from app.config import Settings
from app.processing.language import is_arabic_script
from app.processing.normalize import normalize, tokenize

Method = Literal["text", "ocr"]

# Very frequent Urdu function words; real Urdu prose is roughly 25-35% these
URDU_COMMON = {
    "کے",
    "کی",
    "کا",
    "میں",
    "ہے",
    "ہیں",
    "اور",
    "سے",
    "کو",
    "نے",
    "پر",
    "یہ",
    "وہ",
    "تھا",
    "تھی",
    "تھے",
    "گا",
    "گی",
    "گے",
    "بھی",
    "کہ",
    "جو",
    "ایک",
    "اس",
    "ان",
    "لیے",
    "کر",
    "ہو",
    "تک",
    "یا",
    "نہیں",
    "جس",
    "کیا",
    "گیا",
    "دیا",
    "ہوں",
    "آپ",
    "ہم",
}
ENGLISH_COMMON = {
    "the",
    "of",
    "and",
    "to",
    "in",
    "is",
    "for",
    "on",
    "with",
    "by",
    "that",
    "this",
    "be",
    "are",
    "as",
    "at",
    "from",
    "or",
    "an",
    "it",
    "was",
    "will",
    "shall",
    "not",
    "has",
    "have",
    "which",
    "a",
    "all",
    "any",
    "his",
    "her",
    "their",
    "may",
    "under",
    "such",
}


@dataclass
class PageStats:
    letters: int
    urdu_ratio: float
    garbage_ratio: float
    latin_ext_ratio: float
    mixed_script_ratio: float
    single_letter_ratio: float
    common_word_ratio: float
    image_coverage: float


@dataclass
class PageDecision:
    method: Method
    reason: str
    stats: PageStats

    def to_dict(self) -> dict:
        return {"method": self.method, "reason": self.reason, "stats": asdict(self.stats)}


def _is_garbage(ch: str) -> bool:
    cp = ord(ch)
    return (
        0xE000 <= cp <= 0xF8FF  # private use area (custom font glyph codes)
        or cp == 0xFFFD  # replacement character
        or (cp < 0x20 and ch not in "\n\t\r")
    )


def page_stats(text: str, image_coverage: float = 0.0) -> PageStats:
    visible = [c for c in text if not c.isspace()]
    letters = [c for c in text if c.isalpha()]
    n_letters = len(letters)
    urdu = sum(1 for c in letters if is_arabic_script(c))
    latin_ext = sum(1 for c in letters if 0x00C0 <= ord(c) <= 0x024F)

    urdu_dominant = n_letters > 0 and urdu / n_letters >= 0.5
    tokens = tokenize(normalize(text))
    if urdu_dominant:
        words = [t for t in tokens if any(is_arabic_script(c) for c in t)]
        common = URDU_COMMON
    else:
        words = [t for t in tokens if t.isalpha()]
        common = ENGLISH_COMMON
    arabic_words = [t for t in tokens if any(is_arabic_script(c) for c in t)]
    # Urdu words with a stray Latin letter inside: a ligature mapped to the wrong code point
    mixed = sum(1 for t in arabic_words if any(c.isalpha() and not is_arabic_script(c) for c in t))
    single = sum(1 for w in words if len(w) == 1 and w not in {"و", "a", "i"})

    return PageStats(
        letters=n_letters,
        urdu_ratio=round(urdu / n_letters, 3) if n_letters else 0.0,
        garbage_ratio=round(sum(1 for c in visible if _is_garbage(c)) / len(visible), 3) if visible else 0.0,
        latin_ext_ratio=round(latin_ext / n_letters, 3) if n_letters else 0.0,
        mixed_script_ratio=round(mixed / len(arabic_words), 3) if arabic_words else 0.0,
        single_letter_ratio=round(single / len(words), 3) if words else 0.0,
        common_word_ratio=round(sum(1 for w in words if w in common) / len(words), 3) if words else 0.0,
        image_coverage=round(image_coverage, 3),
    )


def classify_text(text: str, image_coverage: float, settings: Settings) -> PageDecision:
    s = page_stats(text, image_coverage)
    word_count_ok = s.letters >= 150  # ratio checks need enough text to be meaningful

    if s.garbage_ratio > settings.max_garbage_ratio:
        return PageDecision("ocr", "text layer uses private-use glyphs", s)
    if s.letters < settings.min_text_chars:
        return PageDecision("ocr", "no usable text layer", s)
    if s.latin_ext_ratio > settings.max_latin_ext_ratio:
        return PageDecision("ocr", "text layer is Latin-1 mojibake", s)
    if s.mixed_script_ratio > settings.max_mixed_script_ratio:
        return PageDecision("ocr", "Urdu words contain stray Latin letters (broken ligatures)", s)
    if s.image_coverage >= settings.image_coverage_threshold and s.letters < settings.image_page_max_chars:
        return PageDecision("ocr", "page is mostly an image with little text", s)
    if word_count_ok and s.single_letter_ratio > settings.max_single_letter_ratio:
        return PageDecision("ocr", "letters are split apart", s)
    if word_count_ok and s.common_word_ratio < settings.min_common_word_ratio:
        lang = "Urdu" if s.urdu_ratio >= 0.5 else "English"
        return PageDecision("ocr", f"no common {lang} words (garbled or reversed text)", s)
    return PageDecision("text", "clean text layer", s)
