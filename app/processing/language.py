"""Script and language detection for pages, chunks and questions."""

from typing import Literal

Language = Literal["ur", "en", "mixed"]


def is_arabic_script(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F or 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF
    )


def urdu_ratio(text: str) -> float:
    """Share of letters that are Arabic-script."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if is_arabic_script(c)) / len(letters)


def detect_language(text: str) -> Language:
    ratio = urdu_ratio(text)
    if ratio >= 0.7:
        return "ur"
    if ratio <= 0.3:
        return "en"
    return "mixed"


def question_language(text: str) -> Literal["ur", "en"]:
    """The language an answer should be written in."""
    return "ur" if urdu_ratio(text) >= 0.3 else "en"
