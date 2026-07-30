"""Diet Settings — compare and edit all 5 diets side by side."""

import math
import pandas as pd
import streamlit as st
from config import DIETS, DIET_DESCRIPTIONS, DIET_COLORS, DIET_WEIGHTS
from settings_store import load_user_settings, save_user_settings, get_weights

# ── Column setup ──────────────────────────────────────────────────────────────
diet_names = list(DIETS.keys())
diet_keys  = list(DIETS.values())

_SHORT = {
    "who":           "WHO",
    "mediterranean": "Mediterranean",
    "blue_zone":     "Blue Zone",
    "eat_lancet":    "EAT-Lancet",
    "dge":           "DGE",
}
col_names = [_SHORT[dk] for dk in diet_keys]

# Collect union of param keys per section across all diets
def _all_keys(prefix):
    seen = {}
    for dk in diet_keys:
        for k in get_weights(dk):
            if k.startswith(prefix):
                seen[k] = True
    return sorted(seen)

W_KEYS    = _all_keys("w_")
PROT_KEYS = _all_keys("prot_")
THR_KEYS  = [k for k in _all_keys("") if not k.startswith("w_") and not k.startswith("prot_")]

def _label(k):
    return k.replace("w_", "").replace("prot_", "").replace("_", " ").title()

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(
    "Compare and edit scoring parameters for all 5 diets at a glance. "
    "Changes saved here become the defaults for the Recipe Finder sidebar."
)
st.caption("Session-only sidebar tweaks are not stored here — they reset each session.")
st.divider()

# ── Shared column widths ──────────────────────────────────────────────────────
COL_W = [2.2, 1, 1.3, 1.2, 1.2, 0.9]   # [label, WHO, Mediter, Blue, EAT, DGE]

def _diet_header_row():
    """Render the coloured diet-name header row."""
    cols = st.columns(COL_W)
    cols[0].markdown("")   # empty label column
    for i, (dk, cn) in enumerate(zip(diet_keys, col_names)):
        c = DIET_COLORS[dk]
        cols[i + 1].markdown(
            f"<div style='background:{c};color:#fff;border-radius:6px;"
            f"padding:4px 6px;text-align:center;font-size:12px;font-weight:700;'>{cn}</div>",
            unsafe_allow_html=True,
        )

def _param_row(section_label: str, param_keys: list, edits: dict,
               step_fn=None, max_fn=None, fmt=".2f"):
    """
    Render one section (header + one row per parameter).
    Returns nothing — writes directly into `edits[diet_key][param_key]`.
    """
    st.markdown(f"##### {section_label}")
    _diet_header_row()

    for k in param_keys:
        cols = st.columns(COL_W)
        cols[0].markdown(
            f"<span style='font-size:13px;line-height:2.2;'>{_label(k)}</span>",
            unsafe_allow_html=True,
        )
        for i, dk in enumerate(diet_keys):
            w = get_weights(dk)
            if k not in w:
                cols[i + 1].markdown(
                    "<span style='color:#bbb;font-size:12px;'>—</span>",
                    unsafe_allow_html=True,
                )
                continue
            val  = float(w[k])
            step = step_fn(val) if step_fn else 0.05
            mx   = max_fn(val) if max_fn else 1.0
            edits[dk][k] = cols[i + 1].number_input(
                label="",
                min_value=0.0,
                max_value=mx,
                value=val,
                step=step,
                format=f"%{fmt}",
                key=f"cmp_{dk}_{k}",
                label_visibility="collapsed",
            )

    st.markdown("---")

# ── Collect edits ─────────────────────────────────────────────────────────────
edits = {dk: dict(get_weights(dk)) for dk in diet_keys}

# ── Section 1 — Criterion Weights (all 0-1) ───────────────────────────────────
_param_row("⚖️ Criterion Weights", W_KEYS, edits,
           step_fn=lambda v: 0.05, max_fn=lambda v: 1.0, fmt=".2f")

# ── Section 2 — Protein Multipliers (all 0-1) ────────────────────────────────
_param_row("🥩 Protein Source Multipliers", PROT_KEYS, edits,
           step_fn=lambda v: 0.05, max_fn=lambda v: 1.0, fmt=".2f")

# ── Section 3 — Nutritional Thresholds (varying ranges) ─────────────────────
def _thr_step(v):
    if v == 0: return 0.5
    if v < 0.2: return 0.01
    if v < 5:   return 0.5
    return 10.0

def _thr_max(v):
    return max(float(v) * 5, 20.0)

_param_row("📊 Nutritional Thresholds", THR_KEYS, edits,
           step_fn=_thr_step, max_fn=_thr_max, fmt=".3g")

# ── Save / Reset row ─────────────────────────────────────────────────────────
st.markdown("##### 💾 Save or Reset")
save_cols = st.columns(COL_W)
save_cols[0].markdown(
    "<span style='font-size:12px;color:#666;'>Apply changes per diet:</span>",
    unsafe_allow_html=True,
)

for i, (dk, cn) in enumerate(zip(diet_keys, col_names)):
    c = DIET_COLORS[dk]
    with save_cols[i + 1]:
        if st.button(f"Save", key=f"save_{dk}", type="primary", use_container_width=True):
            current = load_user_settings()
            current[dk] = edits[dk]
            save_user_settings(current)
            st.session_state["_settings_saved"] = True
            st.success(f"✓ {cn}")

st.divider()

reset_cols = st.columns(COL_W)
reset_cols[0].markdown(
    "<span style='font-size:12px;color:#666;'>Reset to built-in defaults:</span>",
    unsafe_allow_html=True,
)
_any_reset = False
for i, (dk, cn) in enumerate(zip(diet_keys, col_names)):
    with reset_cols[i + 1]:
        if st.button(f"Reset", key=f"reset_{dk}", use_container_width=True):
            _any_reset = True
            current = load_user_settings()
            current.pop(dk, None)
            save_user_settings(current)
            for k in list(st.session_state.keys()):
                if k.startswith(f"cmp_{dk}_") or k.startswith(f"set_{dk}_"):
                    del st.session_state[k]
            st.session_state["_settings_saved"] = True
            st.toast(f"Reset to built-in defaults for {cn}.")

if _any_reset:
    st.rerun()

# ── Quick description footer ─────────────────────────────────────────────────
with st.expander("Diet descriptions"):
    cols = st.columns(len(diet_keys))
    for col, dk, dn in zip(cols, diet_keys, diet_names):
        c = DIET_COLORS[dk]
        col.markdown(
            f"<div style='border-left:4px solid {c};padding-left:8px;'>"
            f"<b style='color:{c};'>{dn}</b><br>"
            f"<span style='font-size:11px;color:#555;'>{DIET_DESCRIPTIONS[dk]}</span></div>",
            unsafe_allow_html=True,
        )
