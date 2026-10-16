"""Streamlit prototype UI. Run with: streamlit run ui/streamlit_app.py"""

import html
import os

import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
STATUS_ICON = {"uploaded": "⏳", "extracting": "📄", "indexing": "🧮", "ready": "✅", "failed": "❌"}

st.set_page_config(page_title="Urdu Document Q&A", page_icon="📚", layout="wide")
st.markdown(
    """
    <link rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu:wght@400;700&display=swap">
    <style>
      .rtl-auto { font-family: 'Noto Nastaliq Urdu', 'Segoe UI', sans-serif;
                  line-height: 2.2; unicode-bidi: plaintext; }
      .answer { font-size: 1.15rem; padding: 0.75rem 1rem; border-radius: 0.5rem;
                background: rgba(120,120,120,0.08); }
      .quote { font-size: 0.95rem; border-inline-start: 3px solid #6c8ebf;
               padding-inline-start: 0.6rem; margin: 0.4rem 0; }
      .passage { font-size: 0.85rem; opacity: 0.8; }
    </style>
    """,
    unsafe_allow_html=True,
)


def rtl(text: str, cls: str = "") -> str:
    """One element per paragraph with dir=auto, so Urdu and English lines each render correctly."""
    paragraphs = [p for p in text.split("\n") if p.strip()] or [""]
    return "".join(f'<p dir="auto" class="rtl-auto {cls}">{html.escape(p)}</p>' for p in paragraphs)


def api(method: str, path: str, **kwargs):
    try:
        r = requests.request(method, f"{API_URL}{path}", timeout=120, **kwargs)
    except requests.ConnectionError:
        st.error(f"Cannot reach the API at {API_URL}. Start it with: uvicorn app.main:app")
        st.stop()
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        st.error(f"{r.status_code}: {detail}")
        return None
    return r.json() if r.content else {}


@st.cache_data(ttl=3600, show_spinner=False)
def page_image(path: str) -> bytes | None:
    r = requests.get(f"{API_URL}{path}", timeout=30)
    return r.content if r.ok else None


# ---- sidebar: upload and documents ------------------------------------------

with st.sidebar:
    st.header("Documents")
    uploads = st.file_uploader(
        "Upload PDFs (Urdu or English, typed or scanned)", type=["pdf"], accept_multiple_files=True
    )
    if uploads and st.button("Upload", type="primary"):
        for f in uploads:
            res = api("POST", "/documents", files={"file": (f.name, f.getvalue(), "application/pdf")})
            if res:
                note = " (already uploaded)" if res["duplicate"] else ""
                st.success(f"{f.name}{note}")

    if st.button("Refresh status"):
        st.rerun()

    docs = api("GET", "/documents") or []
    ready = [d for d in docs if d["status"] == "ready"]
    for d in docs:
        icon = STATUS_ICON.get(d["status"], "")
        progress = (
            f" {d['pages_done']}/{d['page_count']}" if d["status"] in ("extracting", "indexing") else ""
        )
        with st.expander(f"{icon} {d['filename']}{progress}"):
            st.caption(f"Status: {d['status']} · {d['page_count']} pages")
            if d["error"]:
                st.error(d["error"])
            if st.button("Page details", key=f"detail-{d['id']}"):
                detail = api("GET", f"/documents/{d['id']}")
                if detail:
                    for p in detail["pages"]:
                        conf = f" · OCR {p['ocr_confidence']:.0%}" if p["ocr_confidence"] is not None else ""
                        flag = " ⚠️ low confidence" if p["low_confidence"] else ""
                        st.write(f"p.{p['page_no']}: **{p['method']}** ({p['reason']}){conf}{flag}")
            cols = st.columns(2)
            if d["status"] in ("ready", "failed") and cols[0].button("Reprocess", key=f"re-{d['id']}"):
                api("POST", f"/documents/{d['id']}/reprocess")
                st.rerun()
            if d["status"] in ("ready", "failed") and cols[1].button("Delete", key=f"del-{d['id']}"):
                api("DELETE", f"/documents/{d['id']}")
                st.rerun()

# ---- main: ask -------------------------------------------------------------

st.title("Urdu Document Q&A")
st.caption("Ask in Urdu or English. Every answer shows the file, page and passage it came from.")

selected = st.multiselect(
    "Limit to documents (optional)",
    options=[d["id"] for d in ready],
    format_func=lambda i: next(d["filename"] for d in ready if d["id"] == i),
)

with st.form("ask"):
    question = st.text_area("Question / سوال", height=90)
    submitted = st.form_submit_button("Ask", type="primary")

if submitted and question.strip():
    if not ready:
        st.warning("No documents are ready yet.")
    else:
        with st.spinner("Searching documents…"):
            res = api("POST", "/ask", json={"question": question, "document_ids": selected or None})
        if res:
            st.markdown(rtl(res["answer"], "answer"), unsafe_allow_html=True)
            meta = [f"{res['latency_ms'] / 1000:.1f}s"]
            if res["cached"]:
                meta.append("cached")
            if res["found"] and not res["grounded"]:
                meta.append("⚠️ some quotes could not be matched to their source; check the pages below")
            st.caption(" · ".join(meta))
            if res.get("note"):
                st.info(res["note"])

            for i, c in enumerate(res["citations"], 1):
                st.divider()
                left, right = st.columns([3, 2])
                with left:
                    mark = "" if c["quote_verified"] else " ⚠️ quote not found verbatim"
                    st.markdown(f"**[{i}] {c['filename']} — page {c['page_no']}**{mark}")
                    if c["quote"]:
                        st.markdown(rtl(c["quote"], "quote"), unsafe_allow_html=True)
                    with st.expander("Full passage"):
                        st.markdown(rtl(c["passage"], "passage"), unsafe_allow_html=True)
                with right:
                    img = page_image(c["image_url"])
                    if img:
                        st.image(img, caption=f"{c['filename']} · p.{c['page_no']}", width="stretch")
