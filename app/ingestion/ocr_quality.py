"""Cheap check for garbled OCR output.

Tesseract on Nastaliq often returns a mix of broken Urdu and stray Latin letters
("SEL toy کی کے ew نے کرت"). Clean Urdu has almost no Latin letters, and clean
English almost no Arabic-script ones, so the share of Arabic-script letters
separates the three cases well.
"""

from dataclasses import dataclass

from app.config import Settings

_MIXED_FLOOR = 0.1  # below this share the page is treated as English, not garbled Urdu


def _is_arabic_letter(ch: str) -> bool:
    return "؀" <= ch <= "ۿ" and ch.isalpha()


@dataclass
class OCRQuality:
    letters: int
    urdu_share: float | None  # None when there are no letters

    def garbled(self, settings: Settings) -> bool:
        """Tesseract read nothing useful, or Urdu came out mixed with Latin noise."""
        if self.letters < settings.ocr_min_letters or self.urdu_share is None:
            return True
        return _MIXED_FLOOR <= self.urdu_share < settings.ocr_min_urdu_share

    def describe(self) -> str:
        if self.urdu_share is None:
            return "no letters read"
        return f"Urdu letters {self.urdu_share:.0%} of {self.letters}"


def ocr_quality(text: str) -> OCRQuality:
    arabic = sum(1 for ch in text if _is_arabic_letter(ch))
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    letters = arabic + latin
    return OCRQuality(letters=letters, urdu_share=round(arabic / letters, 3) if letters else None)
