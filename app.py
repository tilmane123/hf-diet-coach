"""HF Diet Coach — v0.23"""
import streamlit as st

_VERSION = "v0.23"
if st.session_state.get("_cache_version") != _VERSION:
    st.cache_data.clear()
    st.session_state["_cache_version"] = _VERSION

st.set_page_config(
    page_title="HF Diet Coach",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded",
)

page = st.navigation(
    {
        "": [
            st.Page("app_pages/main.py", title="Recipe Finder", icon=":material/restaurant:"),
        ],
        "Configuration": [
            st.Page("app_pages/settings.py", title="Diet Settings", icon=":material/tune:"),
        ],
    },
    position="sidebar",
)
page.run()
