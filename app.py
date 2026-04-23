import streamlit as st
import base64
import re
import os
from groq import Groq

try:
    import fitz
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

st.set_page_config(page_title="Invoice Processor | HUBRIS", page_icon="🧾", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    #MainMenu, footer { visibility: hidden; }
    .hubris-footer { text-align: center; padding: 2rem 0 0.5rem; color: #9ca3af; font-size: 0.85rem; }
    .hubris-footer span { color: #3b82f6; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="display:flex; justify-content:space-between; align-items:center; padding-bottom: 0.25rem;">
    <h2 style="margin:0;">🧾 Invoice Processing — Fully Automated</h2>
    <a href="https://www.hubris.at" target="_blank" style="color:#3b82f6; font-weight:600; font-size:0.9rem; text-decoration:none;">Built by HUBRIS 💙 &nbsp;·&nbsp;</a>
</div>
""", unsafe_allow_html=True)

st.markdown("""
- **Your data never leaves your company** — runs locally, no cloud service sees your invoices
- **Drop-in ERP integration** — structured JSON & XML output feeds directly into your approval workflows
- **Zero touch processing** — an email comes with an invoice, this tool processes it as shown, and uploads to ERP (that's why the format is JSON/XML). Fully automated.
""")
st.divider()


@st.cache_resource
def get_client():
    api_key = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
    if not api_key:
        st.error("GROQ_API_KEY not found.")
        st.stop()
    return Groq(api_key=api_key)


def to_data_url(file_bytes: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(file_bytes).decode()}"


def pdf_to_images(pdf_bytes: bytes) -> list:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return [page.get_pixmap(dpi=150).tobytes("png") for page in doc]


def extract_blocks(text: str):
    json_match = re.search(r"```json\s*([\s\S]*?)```", text)
    xml_match  = re.search(r"```xml\s*([\s\S]*?)```",  text)
    return (
        json_match.group(1).strip() if json_match else "",
        xml_match.group(1).strip()  if xml_match  else "",
    )


def process_invoice(data_urls: list) -> str:
    completion = get_client().chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "system",
                "content": "You are a meticulous invoice processor. Extract data from invoices and return it in both JSON and XML formats. Cleanly formatted.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all invoice data and return it in JSON and XML formats."},
                    *[{"type": "image_url", "image_url": {"url": url}} for url in data_urls],
                ],
            },
        ],
        temperature=1,
        max_tokens=2048,
        top_p=1,
        stream=False,
    )
    return completion.choices[0].message.content


# ── Upload ────────────────────────────────────────────────────────────────────
accepted = ["jpg", "jpeg", "png", "webp", "gif"] + (["pdf"] if PDF_SUPPORT else [])
uploaded = st.file_uploader("Upload invoice", type=accepted, label_visibility="collapsed")

if uploaded:
    # Use filename+size as cache key so re-uploads of a new file re-process
    file_key = f"{uploaded.name}_{uploaded.size}"

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown(f"**{uploaded.name}** — {uploaded.size / 1024:.1f} KB")
    with col2:
        if uploaded.type == "application/pdf" and PDF_SUPPORT:
            pages = pdf_to_images(uploaded.getvalue())
            st.image(pages[0], caption=f"Page 1 of {len(pages)}", use_column_width=True)
        else:
            st.image(uploaded.getvalue(), use_column_width=True)

    # Only process if this file hasn't been processed yet
    if st.session_state.get("file_key") != file_key:
        with st.spinner("Processing invoice…"):
            file_bytes = uploaded.getvalue()
            if uploaded.type == "application/pdf" and PDF_SUPPORT:
                data_urls = [to_data_url(img, "image/png") for img in pdf_to_images(file_bytes)]
            else:
                data_urls = [to_data_url(file_bytes, uploaded.type)]

            raw = process_invoice(data_urls)
            st.session_state["file_key"]  = file_key
            st.session_state["raw"]       = raw
            st.session_state["fname"]     = uploaded.name.rsplit(".", 1)[0]

    # ── Results ───────────────────────────────────────────────────────────────
    st.divider()
    json_str, xml_str = extract_blocks(st.session_state["raw"])
    fname = st.session_state["fname"]

    tab_json, tab_xml = st.tabs(["JSON", "XML"])

    with tab_json:
        if json_str:
            st.code(json_str, language="json")
            st.download_button("⬇️ Download JSON", data=json_str, file_name=f"{fname}.json", mime="application/json")
        else:
            st.warning("No JSON found in response.")

    with tab_xml:
        if xml_str:
            st.code(xml_str, language="xml")
            st.download_button("⬇️ Download XML", data=xml_str, file_name=f"{fname}.xml", mime="application/xml")
        else:
            st.warning("No XML found in response.")

