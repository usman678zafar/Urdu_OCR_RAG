"""Urdu text normalization.

Documents and questions both pass through `normalize`, so the same word is
always stored and searched in one form regardless of keyboard, font or OCR engine.
"""

import re
import unicodedata

# Arabic-script letter variants -> the Urdu code point
_CHAR_MAP = {
    "ي": "ی",  # ي Arabic yeh        -> ی Farsi yeh
    "ى": "ی",  # ى alef maksura      -> ی
    "ك": "ک",  # ك Arabic kaf        -> ک keheh
    "ه": "ہ",  # ه Arabic heh        -> ہ heh goal
    "ە": "ہ",  # ە ae                -> ہ
    "ة": "ۃ",  # ة teh marbuta       -> ۃ teh marbuta goal
    "ۀ": "ۂ",  # ۀ heh with yeh      -> ۂ heh goal with hamza
    "ـ": "",  # ـ tatweel
    "\u200b": "",  # zero-width space
    "\u200d": "",  # zero-width joiner
    "\u200e": "",  # left-to-right mark
    "\u200f": "",  # right-to-left mark
    "\ufeff": "",  # byte order mark
    "\u00a0": " ",  # no-break space
}

# Urdu (۰-۹) and Arabic-Indic (٠-٩) digits -> ASCII, so "2024" matches "۲۰۲۴"
for _i in range(10):
    _CHAR_MAP[chr(0x06F0 + _i)] = str(_i)
    _CHAR_MAP[chr(0x0660 + _i)] = str(_i)

_TRANSLATE = str.maketrans(_CHAR_MAP)

# Harakat (zabar, zer, pesh, tanween, shadda, sukun ...) and other optional marks
_DIACRITICS = re.compile("[\u064b-\u0652\u0656-\u065f\u0670\u06d6-\u06ed]")

# ہ + hamza above written as two code points -> precomposed ۂ
_HEH_HAMZA = re.compile("ہ\u0654")
_YEH_HAMZA = re.compile("ی\u0654")

_URDU_PUNCT = "۔،؟؛!?.,:;"
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([" + re.escape(_URDU_PUNCT) + r"])")
_MISSING_SPACE_AFTER = re.compile(r"([۔،؟؛])(?=[^\s\d" + re.escape(_URDU_PUNCT) + r"])")
_SPACES = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


def normalize(text: str) -> str:
    """Return text with unified letters, digits and spacing."""
    if not text:
        return ""
    # NFKC turns Arabic presentation forms (common in PDF text layers) into base letters
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_TRANSLATE)
    text = _HEH_HAMZA.sub("ۂ", text)
    text = _YEH_HAMZA.sub("ئ", text)
    text = _DIACRITICS.sub("", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MISSING_SPACE_AFTER.sub(r"\1 ", text)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


_TOKEN = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Split normalized text into lowercase word tokens (for BM25 and heuristics)."""
    return [t.lower() for t in _TOKEN.findall(text)]
