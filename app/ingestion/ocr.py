"""Urdu OCR engines behind one interface, so they can be compared and swapped.

- tesseract: local, free baseline (needs the `urd` traineddata installed)
- gemini:    Gemini vision; strong on Nastaliq but sends page images to Google
- claude:    Claude vision; also sends page images to an outside API
- docai:     Google Document AI OCR processor; also an outside service
"""

import base64
import io
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageOps

from app.config import Settings


@dataclass
class OCRResult:
    text: str
    confidence: float | None  # 0-1, None when the engine gives no score


class OCREngine(Protocol):
    name: str

    def ocr(self, image: Image.Image) -> OCRResult: ...


class TesseractOCR:
    name = "tesseract"

    def __init__(self, settings: Settings):
        import pytesseract

        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        self._tess = pytesseract
        self.lang = settings.tesseract_lang
        self.config = settings.tesseract_config

    def ocr(self, image: Image.Image) -> OCRResult:
        gray = ImageOps.autocontrast(ImageOps.grayscale(image))
        data = self._tess.image_to_data(
            gray, lang=self.lang, config=self.config, output_type=self._tess.Output.DICT
        )
        # Rebuild text from word boxes so one OCR pass gives both text and confidence
        lines: dict[tuple[int, int, int], list[str]] = {}
        confs: list[float] = []
        for i, word in enumerate(data["text"]):
            word = word.strip()
            conf = float(data["conf"][i])
            if not word or conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
            confs.append(conf)

        out, prev_par = [], None
        for (block, par, _), words in lines.items():
            if prev_par is not None and (block, par) != prev_par:
                out.append("")
            out.append(" ".join(words))
            prev_par = (block, par)
        confidence = round(sum(confs) / len(confs) / 100, 3) if confs else 0.0
        return OCRResult(text="\n".join(out), confidence=confidence)


_VISION_PROMPT = (
    "Transcribe all text on this document page exactly as written, in reading order. "
    "The page is in Urdu (Nastaliq script), English, or both. Keep the original language and "
    "spelling; do not translate, summarize or correct anything. Put each line of the page on its "
    "own line and leave a blank line between paragraphs. Write tables row by row with cells "
    "separated by ' | '. Skip handwriting you cannot read, and output only the transcription."
)


def _jpeg(image: Image.Image) -> bytes:
    img = image.copy()
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class GeminiVisionOCR:
    name = "gemini"

    def __init__(self, settings: Settings):
        from app.generation.providers import GeminiProvider

        self.provider = GeminiProvider(settings, model=settings.gemini_ocr_model)

    def ocr(self, image: Image.Image) -> OCRResult:
        return OCRResult(text=self.provider.transcribe(_jpeg(image), _VISION_PROMPT), confidence=None)


class ClaudeVisionOCR:
    name = "claude"

    def __init__(self, settings: Settings):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        self.model = settings.anthropic_model
        self.fallbacks = settings.llm_fallbacks

    def ocr(self, image: Image.Image) -> OCRResult:
        img = image.copy()
        img.thumbnail((2000, 2000))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

        extra = (
            {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if self.fallbacks else {}
        )
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            output_config={"effort": "low"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
                        },
                        {"type": "text", "text": _VISION_PROMPT},
                    ],
                }
            ],
            **extra,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Vision OCR request was declined by the model.")
        text = "".join(b.text for b in response.content if b.type == "text")
        return OCRResult(text=text.strip(), confidence=None)


class DocumentAIOCR:
    name = "docai"

    def __init__(self, settings: Settings):
        from google.api_core.client_options import ClientOptions
        from google.cloud import documentai

        if not (settings.docai_project_id and settings.docai_processor_id):
            raise RuntimeError("Set DOCAI_PROJECT_ID and DOCAI_PROCESSOR_ID to use Document AI.")
        self._documentai = documentai
        self.client = documentai.DocumentProcessorServiceClient(
            client_options=ClientOptions(api_endpoint=f"{settings.docai_location}-documentai.googleapis.com")
        )
        self.name_path = self.client.processor_path(
            settings.docai_project_id, settings.docai_location, settings.docai_processor_id
        )

    def ocr(self, image: Image.Image) -> OCRResult:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        request = self._documentai.ProcessRequest(
            name=self.name_path,
            raw_document=self._documentai.RawDocument(content=buf.getvalue(), mime_type="image/png"),
        )
        document = self.client.process_document(request=request).document
        confs = [p.layout.confidence for p in document.pages if p.layout]
        return OCRResult(text=document.text, confidence=round(sum(confs) / len(confs), 3) if confs else None)


def make_ocr_engine(name: str, settings: Settings) -> OCREngine:
    engines = {
        "tesseract": TesseractOCR,
        "gemini": GeminiVisionOCR,
        "claude": ClaudeVisionOCR,
        "docai": DocumentAIOCR,
    }
    if name not in engines:
        raise ValueError(f"Unknown OCR engine {name!r}; choose from {sorted(engines)}")
    return engines[name](settings)
