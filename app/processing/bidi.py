"""Repair Urdu lines whose words were extracted in visual (left-to-right) order.

Many PDF generators draw right-to-left text left to right, so the text layer gives
each word correctly but each line's words reversed. We detect this by counting very
common two-word Urdu sequences in both directions: in correct text "کے تحت" and
"جائیں گے" appear as written; in reversed text they appear as "تحت کے", "گے جائیں".
"""

from app.processing.language import urdu_ratio
from app.processing.normalize import normalize, tokenize

# Frequent bigrams whose reverse is rare in real Urdu (normalized spelling)
ORDERED_BIGRAMS = {
    ("کے", "لیے"),
    ("کے", "تحت"),
    ("کے", "بعد"),
    ("کے", "ساتھ"),
    ("کے", "مطابق"),
    ("کے", "پاس"),
    ("کی", "طرف"),
    ("سے", "پہلے"),
    ("کیا", "ہے"),
    ("کیا", "گیا"),
    ("دیا", "گیا"),
    ("گیا", "ہے"),
    ("گئی", "ہے"),
    ("گئے", "ہیں"),
    ("جاتا", "ہے"),
    ("جاتی", "ہے"),
    ("جاتے", "ہیں"),
    ("سکتا", "ہے"),
    ("سکتی", "ہے"),
    ("سکتے", "ہیں"),
    ("رہا", "ہے"),
    ("رہی", "ہے"),
    ("رہے", "ہیں"),
    ("ہے", "کہ"),
    ("کی", "جائے"),
    ("کی", "جائیں"),
    ("کیا", "جائے"),
    ("کر", "دیا"),
    ("کر", "لیا"),
    ("ہو", "گا"),
    ("ہو", "گی"),
    ("ہوں", "گے"),
    ("جائیں", "گے"),
    ("جائیں", "گی"),
    ("جائے", "گا"),
    ("جائے", "گی"),
    ("کرتے", "ہیں"),
    ("کرتا", "ہے"),
    ("کرتی", "ہے"),
    ("ہوتا", "ہے"),
    ("ہوتی", "ہے"),
    ("ہوتے", "ہیں"),
    ("دی", "جائے"),
    ("دیے", "جائیں"),
    ("کریں", "گے"),
}
MIN_EVIDENCE = 2


def _bigram_counts(lines: list[str]) -> tuple[int, int]:
    forward = backward = 0
    for line in lines:
        tokens = tokenize(normalize(line))
        for a, b in zip(tokens, tokens[1:]):
            forward += (a, b) in ORDERED_BIGRAMS
            backward += (b, a) in ORDERED_BIGRAMS
    return forward, backward


def fix_word_order(text: str) -> tuple[str, bool]:
    """Return (text, reversed?) with Urdu lines put back in reading order when needed."""
    lines = text.split("\n")
    urdu_lines = [i for i, line in enumerate(lines) if line.strip() and urdu_ratio(line) >= 0.5]
    forward, backward = _bigram_counts([lines[i] for i in urdu_lines])
    if backward < MIN_EVIDENCE or backward <= 2 * forward:
        return text, False
    for i in urdu_lines:
        lines[i] = " ".join(reversed(lines[i].split()))
    return "\n".join(lines), True
