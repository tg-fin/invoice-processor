import streamlit as st
import base64
import re
import os
import json
import pandas as pd
from groq import Groq

try:
    import fitz
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

st.set_page_config(page_title="Invoice Processor | HUBRIS", page_icon="🧾", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    #MainMenu, footer { visibility: hidden; }

    .step-label {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #3b82f6;
        margin-bottom: 0.15rem;
    }
    .step-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #111827;
        margin-bottom: 1rem;
    }
    .email-card {
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 1.25rem 1.5rem;
        background: #f9fafb;
    }
    .email-from {
        font-size: 0.78rem;
        color: #6b7280;
        margin-bottom: 0.3rem;
    }
    .email-subject {
        font-weight: 700;
        font-size: 1rem;
        color: #111827;
        margin-bottom: 0.6rem;
    }
    .email-body {
        font-size: 0.9rem;
        color: #374151;
        line-height: 1.6;
        margin-bottom: 1rem;
    }
    .email-attachment {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        padding: 0.45rem 0.85rem;
        font-size: 0.85rem;
        color: #374151;
        font-weight: 500;
    }
    .erp-record {
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        overflow: hidden;
    }
    .erp-row {
        display: flex;
        border-bottom: 1px solid #f3f4f6;
    }
    .erp-row:last-child { border-bottom: none; }
    .erp-key {
        width: 38%;
        padding: 0.55rem 1rem;
        font-size: 0.82rem;
        font-weight: 600;
        color: #6b7280;
        background: #f9fafb;
        border-right: 1px solid #f3f4f6;
    }
    .erp-val {
        width: 62%;
        padding: 0.55rem 1rem;
        font-size: 0.88rem;
        color: #111827;
        background: #ffffff;
        word-break: break-word;
    }
    .erp-val-highlight {
        background: #fffbeb;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:0.5rem;">
    <h2 style="margin:0;">🧾 Invoice Processing — Fully Automated</h2>
    <a href="https://www.hubris.at" target="_blank"
       style="color:#3b82f6;font-weight:600;font-size:0.9rem;text-decoration:none;">
       Built by HUBRIS 💙
    </a>
</div>
""", unsafe_allow_html=True)

st.markdown("""
- **Your data never leaves your company** — runs locally, no cloud service sees your invoices
- **Drop-in ERP integration** — structured output feeds directly into your approval workflows
- **Zero touch processing** — an email arrives, this tool processes and uploads to ERP automatically
""")
st.divider()


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def flatten_json(obj, prefix=""):
    """Recursively flatten a dict; returns (scalar_fields, list_fields)."""
    scalars = {}
    lists = {}
    for k, v in obj.items():
        full_key = f"{prefix}{k}" if not prefix else f"{prefix} › {k}"
        if isinstance(v, dict):
            s, l = flatten_json(v, full_key)
            scalars.update(s)
            lists.update(l)
        elif isinstance(v, list):
            if v and isinstance(v[0], dict):
                lists[full_key] = v
            else:
                scalars[full_key] = ", ".join(str(i) for i in v)
        else:
            scalars[full_key] = v if v is not None else ""
    return scalars, lists


# ── Upload ────────────────────────────────────────────────────────────────────

accepted = ["jpg", "jpeg", "png", "webp", "gif"] + (["pdf"] if PDF_SUPPORT else [])
uploaded = st.file_uploader("Upload invoice", type=accepted, label_visibility="collapsed")

if uploaded:
    file_key = f"{uploaded.name}_{uploaded.size}"

    # ── Step 1: Email ─────────────────────────────────────────────────────────
    st.markdown('<div class="step-label">Step 1 of 4</div>', unsafe_allow_html=True)
    st.markdown('<div class="step-title">Invoice received by email</div>', unsafe_allow_html=True)

    col_email, col_preview = st.columns([3, 2])

    with col_email:
        st.markdown(f"""
        <div class="email-card">
            <div class="email-from">📧 From: accounts@supplier.com &nbsp;·&nbsp; To: ap@yourcompany.com</div>
            <div class="email-subject">Invoice attached — please process</div>
            <div class="email-body">
                Hi,<br><br>
                Please find our invoice attached for services rendered. Let us know if you have any questions.<br><br>
                Best regards,<br>Accounts Receivable
            </div>
            <div class="email-attachment">📎 {uploaded.name}</div>
        </div>
        """, unsafe_allow_html=True)

    with col_preview:
        if uploaded.type == "application/pdf" and PDF_SUPPORT:
            pages = pdf_to_images(uploaded.getvalue())
            st.image(pages[0], use_column_width=True)
        else:
            st.image(uploaded.getvalue(), use_column_width=True)

    st.divider()

    # ── Processing (hidden from demo flow) ───────────────────────────────────
    if st.session_state.get("file_key") != file_key:
        with st.spinner("Processing invoice…"):
            file_bytes = uploaded.getvalue()
            if uploaded.type == "application/pdf" and PDF_SUPPORT:
                data_urls = [to_data_url(img, "image/png") for img in pdf_to_images(file_bytes)]
            else:
                data_urls = [to_data_url(file_bytes, uploaded.type)]

            raw = process_invoice(data_urls)
            st.session_state["file_key"] = file_key
            st.session_state["raw"]      = raw
            st.session_state["fname"]    = uploaded.name.rsplit(".", 1)[0]

    json_str, xml_str = extract_blocks(st.session_state["raw"])
    fname = st.session_state["fname"]

    # ── Step 2: ERP spreadsheet ───────────────────────────────────────────────
    st.markdown('<div class="step-label">Step 2 of 3</div>', unsafe_allow_html=True)
    st.markdown('<div class="step-title">Data lands in your ERP — automatically</div>', unsafe_allow_html=True)

    parsed = None
    if json_str:
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            pass

    if parsed:
        scalar_fields, list_fields = flatten_json(parsed)

        # Main fields table (one row, all scalar fields as columns)
        if scalar_fields:
            df_main = pd.DataFrame([scalar_fields])
            st.dataframe(df_main, use_container_width=True, hide_index=True)

        # Line-item tables
        for list_name, rows in list_fields.items():
            if rows:
                st.markdown(f"**{list_name}**")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No structured data to display yet.")

    st.divider()

    # ── Step 3: ERP search ────────────────────────────────────────────────────
    st.markdown('<div class="step-label">Step 3 of 3</div>', unsafe_allow_html=True)
    st.markdown('<div class="step-title">Find anything instantly — just like in your ERP</div>', unsafe_allow_html=True)

    if parsed:
        search = st.text_input("Search fields or values…", placeholder="e.g. total, VAT, vendor name")

        if scalar_fields:
            query = search.strip().lower()

            # Build display rows — optionally filtered
            display_rows = [
                (k, str(v))
                for k, v in scalar_fields.items()
                if not query or query in k.lower() or query in str(v).lower()
            ]

            if display_rows:
                rows_html = ""
                for k, v in display_rows:
                    highlight = "erp-val-highlight" if query and query in v.lower() else ""
                    rows_html += f"""
                    <div class="erp-row">
                        <div class="erp-key">{k}</div>
                        <div class="erp-val {highlight}">{v}</div>
                    </div>"""
                st.markdown(
                    f'<div class="erp-record">{rows_html}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("No fields match your search.")

        for list_name, rows in list_fields.items():
            if rows:
                df = pd.DataFrame(rows)
                if query:
                    mask = df.apply(
                        lambda col: col.astype(str).str.lower().str.contains(query, na=False)
                    ).any(axis=1)
                    df = df[mask]
                if not df.empty:
                    st.markdown(f"**{list_name}**")
                    st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("ERP record view will appear once data is extracted.")

    # ── IT export (collapsed) ─────────────────────────────────────────────────
    st.divider()
    with st.expander("🔧 For the IT department — raw JSON & XML output"):
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
