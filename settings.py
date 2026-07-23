"""Diet Settings page — define permanent default scoring parameters per diet."""

import streamlit as st
from config import DIETS, DIET_DESCRIPTIONS, DIET_COLORS, DIET_WEIGHTS
from settings_store import load_user_settings, save_user_settings, get_weights

st.markdown("Configure the **default** scoring parameters for each diet. These values become the starting point for sidebar sliders on the Recipe Finder page.")
st.caption("Session-only tweaks made in the sidebar are not affected — they reset each session. Only changes saved here persist.")

saved = load_user_settings()

diet_names  = list(DIETS.keys())
diet_keys   = list(DIETS.values())
tab_objects = st.tabs(diet_names)

for tab, diet_label, diet_key in zip(tab_objects, diet_names, diet_keys):
    with tab:
        color = DIET_COLORS[diet_key]
        st.markdown(
            f"<div style='background:{color};color:#fff;border-radius:8px;padding:8px 14px;margin-bottom:12px;'>"
            f"<b>{diet_label}</b><br>"
            f"<span style='font-size:12px;'>{DIET_DESCRIPTIONS[diet_key]}</span></div>",
            unsafe_allow_html=True,
        )

        base = get_weights(diet_key)

        w_keys    = sorted([k for k in base if k.startswith("w_")])
        thr_keys  = sorted([k for k in base if not k.startswith("w_") and not k.startswith("prot_")])
        prot_keys = sorted([k for k in base if k.startswith("prot_")])

        edits = {}

        with st.expander("Criterion weights", expanded=True):
            st.caption("Relative importance of each criterion. Auto-normalised to sum = 1 when scoring.")
            for k in w_keys:
                label = k.replace("w_", "").replace("_", " ").title()
                default_val = float(base[k])
                edits[k] = st.slider(label, 0.0, 1.0, default_val, 0.05, key=f"set_{diet_key}_{k}")

        with st.expander("Nutritional thresholds"):
            st.caption("Reference values used to compute per-nutrient sub-scores.")
            for k in thr_keys:
                label = k.replace("_", " ").title()
                default_val = float(base[k])
                step = 0.5 if default_val >= 1 else 0.01
                max_val = max(default_val * 4, 20.0)
                edits[k] = st.slider(label, 0.0, max_val, default_val, step, key=f"set_{diet_key}_{k}")

        with st.expander("Protein source multipliers"):
            st.caption("Score multiplier per protein type detected in recipe (0 = strongly avoid, 1 = ideal).")
            for k in prot_keys:
                label = k.replace("prot_", "").replace("_", " ").title()
                default_val = float(base[k])
                edits[k] = st.slider(label, 0.0, 1.0, default_val, 0.05, key=f"set_{diet_key}_{k}")

        col_save, col_reset, _ = st.columns([1, 1, 3])

        with col_save:
            if st.button(":material/save: Save defaults", key=f"save_{diet_key}", type="primary"):
                current = load_user_settings()
                current[diet_key] = edits
                save_user_settings(current)
                # Signal main page to reset its slider keys for this diet
                st.session_state["_settings_saved"] = True
                st.success(f"Defaults saved for **{diet_label}**. They will apply the next time you open Recipe Finder.")

        with col_reset:
            if st.button(":material/restart_alt: Reset to built-in", key=f"reset_{diet_key}"):
                current = load_user_settings()
                current.pop(diet_key, None)
                save_user_settings(current)
                # Clear widget keys so sliders re-init from built-in defaults
                for k in list(st.session_state.keys()):
                    if k.startswith(f"set_{diet_key}_"):
                        del st.session_state[k]
                st.session_state["_settings_saved"] = True
                st.success(f"Reset to built-in defaults for **{diet_label}**.")
                st.rerun()
