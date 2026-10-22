"""Repair Urdu lines whose words were extracted in visual (left-to-right) order.

Many PDF generators draw right-to-left text left to right, so the text layer gives
each word correctly but each line's words reversed. Two kinds of votes detect this:
- very common two-word Urdu sequences: in correct text "کے تحت" and "جائیں گے" appear
  as written; in reversed text they appear as "تحت کے", "گے جائیں";
- sentence-ending marks: the "۔" of a correct line sits on its last word; reversed,
  it lands on the first word ("گیا۔ رکھا پر نام کے ...").

A page with too few votes of its own follows the rest of its document (see
`document_is_reversed`), since one PDF generator writes every page the same way.
"""

from dataclasses import dataclass

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
SENTENCE_END = ("۔", "؟")
MIN_EVIDENCE = 2
# A document counts as reversed when its pages' votes, added up, clearly say so
MIN_DOCUMENT_EVIDENCE = 10


@dataclass
class WordOrderVotes:
    forward: int = 0  # signs the lines are in reading order
    backward: int = 0  # signs the lines are reversed

    def __add__(self, other: "WordOrderVotes") -> "WordOrderVotes":
        return WordOrderVotes(self.forward + other.forward, self.backward + other.backward)

    @property
    def reversed(self) -> bool:
        return self.backward >= MIN_EVIDENCE and self.backward > 2 * self.forward

    @property
    def in_order(self) -> bool:
        return self.forward >= MIN_EVIDENCE and self.forward > 2 * self.backward


def _urdu_lines(lines: list[str]) -> list[int]:
    return [i for i, line in enumerate(lines) if line.strip() and urdu_ratio(line) >= 0.5]


def word_order_votes(text: str) -> WordOrderVotes:
    votes = WordOrderVotes()
    lines = text.split("\n")
    for i in _urdu_lines(lines):
        tokens = tokenize(normalize(lines[i]))
        for a, b in zip(tokens, tokens[1:]):
            votes.forward += (a, b) in ORDERED_BIGRAMS
            votes.backward += (b, a) in ORDERED_BIGRAMS
        words = lines[i].split()
        if len(words) > 1:
            votes.forward += words[-1].endswith(SENTENCE_END)
            votes.backward += words[0].endswith(SENTENCE_END)
    return votes


def reverse_urdu_lines(text: str) -> str:
    """Reverse the word order of every Urdu line; other lines are left alone."""
    lines = text.split("\n")
    for i in _urdu_lines(lines):
        lines[i] = " ".join(reversed(lines[i].split()))
    return "\n".join(lines)


def fix_word_order(text: str) -> tuple[str, bool]:
    """Return (text, reversed?) with Urdu lines put back in reading order when the page
    alone shows they were reversed."""
    if not word_order_votes(text).reversed:
        return text, False
    return reverse_urdu_lines(text), True


def document_is_reversed(pages: list[WordOrderVotes]) -> bool:
    """Whether the document as a whole was written in visual order."""
    total = sum(pages, WordOrderVotes())
    return total.backward >= MIN_DOCUMENT_EVIDENCE and total.backward > 4 * total.forward
