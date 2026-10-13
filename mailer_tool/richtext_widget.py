"""Small rich-text (WYSIWYG) editor for Streamlit - no extra packages needed.
Returns the message as HTML. If custom components are unavailable in the installed
Streamlit version, falls back to a plain box for HTML source."""
from pathlib import Path

import streamlit as st

try:
    import streamlit.components.v1 as components
    _editor = components.declare_component("luaz_rich_editor", path=str(Path(__file__).parent / "richtext"))
except Exception:  # noqa: BLE001
    _editor = None


def rich_editor(value: str = "", key: str = "", placeholders=(), min_height: int = 160) -> str:
    if _editor is None:
        st.caption("Rich editor not available in this Streamlit version - edit the HTML directly "
                   "(e.g. <b>bold</b>, <i>italic</i>, <a href=\"https://...\">link</a>, <br> for a new line).")
        return st.text_area("Message (HTML)", value or "", height=min_height + 60, key=key)
    out = _editor(value=value or "", placeholders=list(placeholders), min_height=min_height,
                  key=key, default=value or "")
    return out if isinstance(out, str) else (value or "")
