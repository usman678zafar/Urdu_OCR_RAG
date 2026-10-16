"""Prompt and output schema for sources-only answers."""

from app.retrieval.hybrid import RetrievedChunk

SYSTEM_PROMPT = """\
You answer questions about a user's own documents, using only the source passages given \
with each question. The documents are Urdu or English PDFs such as applications, notices, \
policies, contracts and reports. Some passages come from OCR of scanned pages and may contain \
recognition errors; read past small errors, but do not guess at text that is unreadable.

How to answer:
- Use only what the sources state. Do not add facts from general knowledge, even when you are \
confident they are true, because the user needs answers they can trace to their documents.
- If the sources do not contain the answer, set "found" to false and leave "answer" empty. If \
they answer only part of the question, answer that part and say plainly what is missing.
- Write the answer in the language named in the request, whatever language the sources are in. \
Translate where needed, but copy names, numbers, amounts, dates and reference numbers exactly as \
they appear in the sources.
- Keep the answer short and direct: a sentence or a short paragraph, or a brief list when the \
question asks for several items.
- Cite every source you relied on. For each, give its id (such as "S2") and a short quote, \
copied word for word from that source in its original language, that supports the answer."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["source_id", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["found", "answer", "citations"],
    "additionalProperties": False,
}

LANGUAGE_NAMES = {"ur": "Urdu", "en": "English"}

NOT_FOUND = {
    "ur": "فراہم کردہ دستاویزات میں اس سوال کا جواب نہیں ملا۔",
    "en": "The answer was not found in the provided documents.",
}


def source_id(index: int) -> str:
    return f"S{index + 1}"


def build_user_message(question: str, language: str, chunks: list[RetrievedChunk]) -> str:
    sources = "\n\n".join(
        f'<source id="{source_id(i)}" file="{c.filename}" page="{c.page_no}">\n{c.text}\n</source>'
        for i, c in enumerate(chunks)
    )
    return (
        f"<sources>\n{sources}\n</sources>\n\n"
        f"Question: {question}\n"
        f"Answer language: {LANGUAGE_NAMES[language]}"
    )
