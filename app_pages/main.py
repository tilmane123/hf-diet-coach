"""Main recipe-finder page."""

import io
import copy
import base64
from pathlib import Path
import pandas as pd
import streamlit as st

from config import (MARKETS, DIETS, DIET_DESCRIPTIONS, DIET_COLORS,
                    HEALTH_GOALS, NUTRITION_PREFS, MAX_GOALS, MAX_PREFS)
from menu_data import get_available_weeks, fetch_menu, diverse_top_n, _base
from scoring import score_menu
from goals import (rank_weights, recommend_diets, recommendation_reason,
                   forced_diet, apply_goal_filters, first_goal,
                   GOAL1_FIBRE_FIRST, GOAL1_MAX_CARBS)
from settings_store import get_weights

ASSETS = Path(__file__).resolve().parent.parent / "assets"
HF_LOGO_FILE = ASSETS / "hellofresh_logo.png"


@st.cache_data
def _logo_data_uri(path_str: str) -> str:
    """Inline the logo so the page carries no external image dependency."""
    p = Path(path_str)
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


HF_LOGO = _logo_data_uri(str(HF_LOGO_FILE))

# HelloFresh green palette
HF_GREEN      = "#91C11E"   # brand lime
HF_GREEN_DARK = "#5C8A0F"
HF_GREEN_DEEP = "#2F4F0B"
HF_LEAF_BG    = "#F1F8E5"   # pale leaf wash

st.markdown(f"""
<style>
  /* ── Fresh green base ─────────────────────────────────────────────── */
  .stApp {{
    background:
      radial-gradient(900px 420px at 8% -8%, rgba(145,193,30,.16), transparent 60%),
      radial-gradient(760px 380px at 105% 0%, rgba(46,125,50,.10), transparent 55%),
      #FCFEF8;
  }}
  section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {HF_LEAF_BG} 0%, #FFFFFF 55%);
    border-right: 1px solid rgba(145,193,30,.35);
  }}
  h1, h2, h3, h4 {{ color: {HF_GREEN_DEEP}; letter-spacing:-.2px; }}

  /* ── Brand header ─────────────────────────────────────────────────── */
  .hf-header {{
    display:flex; align-items:center; gap:16px;
    background: linear-gradient(120deg, {HF_GREEN} 0%, #7CB518 45%, #4E8C0A 100%);
    border-radius:16px; padding:16px 22px; margin:0 0 16px;
    box-shadow:0 6px 20px rgba(92,138,15,.28);
    position:relative; overflow:hidden;
  }}
  .hf-header::after {{
    content:"🥬"; position:absolute; right:-10px; bottom:-26px;
    font-size:104px; opacity:.16; transform:rotate(-12deg);
  }}
  /* White chip keeps the lime + black wordmark legible on the green header */
  .hf-header .hf-logo {{
    background:#fff; border-radius:10px; padding:9px 14px; flex-shrink:0;
    box-shadow:0 2px 8px rgba(0,0,0,.14); line-height:0;
  }}
  .hf-header .hf-logo img {{ height:30px; display:block; }}
  .hf-header .hf-divider {{ width:1px; height:34px; background:rgba(255,255,255,.45); }}
  .hf-header .hf-title {{ color:#fff; font-size:21px; font-weight:800; line-height:1.15; }}
  .hf-header .hf-sub {{ color:rgba(255,255,255,.92); font-size:13px; margin-top:2px; }}

  /* ── Recipe cards ─────────────────────────────────────────────────── */
  .recipe-card {{
    background:#fff; border-radius:14px; overflow:hidden; height:100%;
    border:1px solid rgba(145,193,30,.30);
    box-shadow:0 3px 14px rgba(47,79,11,.09);
    transition:transform .16s ease, box-shadow .16s ease;
  }}
  .recipe-card:hover {{ transform:translateY(-3px); box-shadow:0 10px 26px rgba(47,79,11,.17); }}
  .card-img {{ width:100%; height:175px; object-fit:cover; }}
  .card-img-placeholder {{
    height:175px; background:linear-gradient(135deg,{HF_LEAF_BG},#DCEFC0);
    display:flex; align-items:center; justify-content:center; font-size:48px;
  }}
  .card-body {{ padding:12px 14px 14px; }}
  .card-rank {{
    font-size:11px; font-weight:700; color:{HF_GREEN_DARK}; text-transform:uppercase;
    letter-spacing:.6px; margin-bottom:3px;
  }}
  .card-title {{ font-size:14px; font-weight:700; line-height:1.35; margin:0 0 2px; color:{HF_GREEN_DEEP}; }}
  .card-sub {{ font-size:12px; color:#7A8A6A; margin:0 0 8px; }}
  .score-badge {{
    display:inline-block; border-radius:20px; padding:3px 11px;
    font-size:13px; font-weight:700; color:#fff;
  }}
  .nutrient-row {{ display:flex; gap:5px; flex-wrap:wrap; margin-top:8px; }}
  .nut {{ border-radius:6px; padding:2px 7px; font-size:11px; color:#fff; font-weight:600; }}
  .nut-neutral {{ background:{HF_LEAF_BG}; color:#4A5A3A; font-weight:500; }}
  .ing {{ font-size:11px; color:#6B7A5C; margin-top:7px; line-height:1.55; }}
  .section-header {{
    font-size:18px; font-weight:700; margin:24px 0 12px; padding:9px 16px;
    border-radius:10px; color:#fff; box-shadow:0 3px 10px rgba(47,79,11,.16);
  }}
  .runner-up-card {{ opacity:0.9; }}

  /* ── Buttons ──────────────────────────────────────────────────────── */
  .stButton > button {{ border-radius:9px; font-weight:600; }}
  .stButton > button[kind="primary"] {{
    background:linear-gradient(120deg,{HF_GREEN},#6FA512); border:none;
    box-shadow:0 3px 10px rgba(92,138,15,.32);
  }}
  .stButton > button[kind="primary"]:hover {{ filter:brightness(1.06); }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="hf-header">
  <div class="hf-logo"><img src="{HF_LOGO}" alt="HelloFresh"></div>
  <div class="hf-divider"></div>
  <div>
    <div class="hf-title">Diet Coach 🥗</div>
    <div class="hf-sub">The freshest picks from this week's menu, matched to how you want to eat</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    if HF_LOGO_FILE.exists():
        st.image(str(HF_LOGO_FILE), width=170)
    st.title("HF Diet Coach")
    st.caption("Best-fit HelloFresh recipes for any diet. · v0.28")
    st.divider()

    market_label = st.selectbox("🌍 Market", list(MARKETS.keys()))
    mkt = MARKETS[market_label]

    diet_label = st.selectbox("🥗 Diet Framework", list(DIETS.keys()), key="diet_select")
    diet_key = DIETS[diet_label]

    with st.spinner(f"Loading weeks for {market_label}… (may take ~30s on first load)"):
        try:
            weeks = get_available_weeks(mkt["market"], mkt["region_code"])
        except Exception as e:
            st.error(f"Could not load weeks: {e}")
            st.stop()

    if not weeks:
        st.warning("No weeks found for this market.")
        st.stop()

    week_idx = st.selectbox(
        "📅 Week",
        range(len(weeks)),
        format_func=lambda i: weeks[i]["label"],
    )
    selected_week = weeks[week_idx]

    run_btn = st.button("🔍 Find best recipes", use_container_width=True, type="primary")

    st.divider()

    # ── Scoring weights editor ──────────────────────────────────────────────
    st.markdown("#### ⚙️ Scoring Parameters")
    st.caption("Adjust weights for this session. Edit permanent defaults on the **Diet Settings** page.")

    # If settings were just saved, clear stale slider keys so they re-init from new defaults
    if st.session_state.pop("_settings_saved", False):
        for k in list(st.session_state.keys()):
            if k.startswith(f"w_{diet_key}_") or k.startswith(f"thr_{diet_key}_") or k.startswith(f"prot_{diet_key}_"):
                del st.session_state[k]

    base_w = get_weights(diet_key)

    w_keys    = sorted([k for k in base_w if k.startswith("w_")])
    thr_keys  = sorted([k for k in base_w if not k.startswith("w_") and not k.startswith("prot_")])
    prot_keys = sorted([k for k in base_w if k.startswith("prot_")])

    live_w = {}

    with st.expander("Criterion weights", expanded=True):
        st.caption("Higher = more important. Auto-normalised to sum = 1.")
        for k in w_keys:
            label = k.replace("w_", "").replace("_", " ").title()
            live_w[k] = st.slider(label, 0.0, 1.0, float(base_w[k]), 0.05, key=f"w_{diet_key}_{k}")

    with st.expander("Nutritional thresholds"):
        st.caption("Reference values used to compute sub-scores.")
        for k in thr_keys:
            label = k.replace("_", " ").title()
            default = float(base_w[k])
            step = 0.5 if default >= 1 else 0.01
            max_val = max(default * 4, 20.0)
            live_w[k] = st.slider(label, 0.0, max_val, default, step, key=f"thr_{diet_key}_{k}")

    with st.expander("Protein source multipliers"):
        st.caption("Score per protein type (0 = avoid, 1 = ideal).")
        for k in prot_keys:
            label = k.replace("prot_", "").replace("_", " ").title()
            live_w[k] = st.slider(label, 0.0, 1.0, float(base_w[k]), 0.05, key=f"prot_{diet_key}_{k}")


# ── Main ──────────────────────────────────────────────────────────────────────
color = DIET_COLORS[diet_key]

# ── Pre-section questionnaire ─────────────────────────────────────────────────
# Three steps, gating the results: goals → priority → nutrition preferences.
GOAL_LABEL = dict(HEALTH_GOALS)
PREF_LABEL = dict(NUTRITION_PREFS)
KEY_TO_DIET_LABEL = {v: k for k, v in DIETS.items()}

ss = st.session_state
ss.setdefault("ob_step", 1)          # 1, 2, 3 or "done"
ss.setdefault("ob_goals", [])        # selected goal keys
ss.setdefault("ob_goals_ranked", []) # goal keys in priority order
ss.setdefault("ob_prefs", [])        # selected preference keys


def _restart_onboarding():
    ss["ob_step"] = 1
    ss["ob_goals_ranked"] = []


def _multi_select_block(options, chosen, max_n, key_prefix):
    """Checkbox list capped at max_n. Returns the newly selected keys."""
    picked = []
    for k, label in options:
        at_cap = len(chosen) >= max_n and k not in chosen
        if st.checkbox(label, value=(k in chosen), key=f"{key_prefix}_{k}",
                       disabled=at_cap):
            picked.append(k)
    return picked


if ss["ob_step"] != "done":
    st.markdown("#### Let's personalise your week")
    st.caption("Three quick questions. Your answers re-rank the menu — "
               "they don't replace the diet framework.")

    # ── Q1: health goals ──────────────────────────────────────────────────────
    if ss["ob_step"] == 1:
        st.markdown(f"**1 · What is your health goal?**  \n"
                    f"<span style='color:#777;font-size:13px;'>please select max "
                    f"{MAX_GOALS}</span>", unsafe_allow_html=True)
        picked = _multi_select_block(HEALTH_GOALS, ss["ob_goals"], MAX_GOALS, "goal")
        ss["ob_goals"] = picked[:MAX_GOALS]

        st.caption(f"{len(ss['ob_goals'])} of {MAX_GOALS} selected")
        c1, c2 = st.columns([1, 4])
        if c1.button("Continue →", type="primary", disabled=not ss["ob_goals"]):
            # One goal needs no ranking — skip straight past the priority step
            if len(ss["ob_goals"]) == 1:
                ss["ob_goals_ranked"] = list(ss["ob_goals"])
                ss["ob_step"] = 3
            else:
                ss["ob_step"] = 2
            st.rerun()
        if not ss["ob_goals"]:
            c2.caption("Pick at least one goal to continue.")
        st.stop()

    # ── Q2: prioritise the goals ──────────────────────────────────────────────
    if ss["ob_step"] == 2:
        n = len(ss["ob_goals"])
        shares = [f"{w:.0%}" for w in rank_weights(n)]
        st.markdown("**2 · Which matters most?**  \n"
                    "<span style='color:#777;font-size:13px;'>rank your goals — "
                    "higher priority counts for more</span>", unsafe_allow_html=True)

        remaining = [GOAL_LABEL[k] for k in ss["ob_goals"]]
        order, taken = [], []
        for i in range(n):
            opts = [lbl for lbl in remaining if lbl not in taken]
            choice = st.selectbox(
                f"Priority {i + 1} — counts for {shares[i]}",
                opts, key=f"rank_{i}",
            )
            taken.append(choice)
            order.append(choice)

        dupes = len(set(order)) != len(order)
        c1, c2 = st.columns([1, 4])
        if c1.button("Continue →", type="primary", disabled=dupes):
            label_to_key = {v: k for k, v in GOAL_LABEL.items()}
            ss["ob_goals_ranked"] = [label_to_key[lbl] for lbl in order]
            ss["ob_step"] = 3
            st.rerun()
        if c2.button("← Back"):
            ss["ob_step"] = 1
            st.rerun()
        st.stop()

    # ── Q3: nutrition preferences ─────────────────────────────────────────────
    if ss["ob_step"] == 3:
        st.markdown(f"**3 · Do you have nutrition preferences?**  \n"
                    f"<span style='color:#777;font-size:13px;'>please select max "
                    f"{MAX_PREFS}</span>", unsafe_allow_html=True)
        picked = _multi_select_block(NUTRITION_PREFS, ss["ob_prefs"], MAX_PREFS, "pref")
        ss["ob_prefs"] = picked[:MAX_PREFS]

        st.caption(f"{len(ss['ob_prefs'])} of {MAX_PREFS} selected · optional")
        def _finish_onboarding():
            """Callback: runs before the rerun, so writing diet_select is legal
            here even though the sidebar widget already exists this run."""
            ss["ob_step"] = "done"
            # A #1 goal that mandates a framework switches to it automatically
            _forced = forced_diet(ss["ob_goals_ranked"] or ss["ob_goals"])
            if _forced:
                ss["diet_select"] = KEY_TO_DIET_LABEL[_forced]

        c1, c2 = st.columns([1, 4])
        c1.button("See my recipes →", type="primary", on_click=_finish_onboarding)
        if c2.button("← Back"):
            ss["ob_step"] = 2 if len(ss["ob_goals"]) > 1 else 1
            st.rerun()
        st.stop()

# ── Answer summary strip ──────────────────────────────────────────────────────
goal_keys = ss["ob_goals_ranked"] or ss["ob_goals"]
pref_keys = ss["ob_prefs"]

_shares = rank_weights(len(goal_keys))
_goal_txt = " · ".join(
    f"{i + 1}. {GOAL_LABEL[k]} ({_shares[i]:.0%})" for i, k in enumerate(goal_keys)
)
_pref_txt = ", ".join(PREF_LABEL[k] for k in pref_keys) or "none"

sc1, sc2 = st.columns([6, 1])
with sc1:
    st.markdown(
        f"<div style='background:{HF_LEAF_BG};border-left:4px solid {color};border-radius:8px;"
        f"padding:9px 13px;font-size:13px;line-height:1.7;'>"
        f"<b>🎯 Your goals</b> &nbsp;{_goal_txt}<br>"
        f"<b>🍽️ Preferences</b> &nbsp;{_pref_txt}</div>",
        unsafe_allow_html=True,
    )
with sc2:
    st.button("Change", on_click=_restart_onboarding, use_container_width=True)

# ── Best-match framework ──────────────────────────────────────────────────────
ranked = recommend_diets(goal_keys, pref_keys)
if ranked:
    best_key, best_score = ranked[0]
    best_label = KEY_TO_DIET_LABEL[best_key]
    runner_key, runner_score = ranked[1]

    forced_key = forced_diet(goal_keys)
    if forced_key:
        headline = "🎯 Framework set by your #1 goal"
        why = f" — “{GOAL_LABEL[first_goal(goal_keys)]}”"
    else:
        headline = "🏆 Best match for your answers"
        why_goal = recommendation_reason(best_key, goal_keys)
        why = f" — driven mostly by “{GOAL_LABEL[why_goal]}”" if why_goal else ""
    already = best_key == diet_key

    rc1, rc2 = st.columns([6, 1])
    with rc1:
        st.markdown(
            f"<div style='background:linear-gradient(100deg,#FAFDF2,#EEF7DE);"
            f"border-left:4px solid {DIET_COLORS[best_key]};"
            f"border-radius:8px;padding:9px 13px;font-size:13px;line-height:1.7;'>"
            f"<b>{headline}: {best_label}</b> "
            f"<span style='color:#666;'>({best_score:.0%} fit){why}</span><br>"
            f"<span style='color:#777;'>Runner-up: {KEY_TO_DIET_LABEL[runner_key]} "
            f"({runner_score:.0%})"
            + ("  ·  <b>you're viewing it now</b>" if already else "")
            + "</span></div>",
            unsafe_allow_html=True,
        )
    with rc2:
        if not already:
            def _apply_recommended(label=best_label):
                ss["diet_select"] = label
            st.button("Use it", on_click=_apply_recommended,
                      type="primary", use_container_width=True)

    with st.expander("How every framework scored against your answers"):
        for k, sc in ranked:
            bar = int(round(sc * 100))
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px;'>"
                f"<span style='width:190px;'>{KEY_TO_DIET_LABEL[k]}</span>"
                f"<span style='flex:1;background:#eee;border-radius:4px;height:9px;'>"
                f"<span style='display:block;width:{bar}%;background:{DIET_COLORS[k]};"
                f"height:9px;border-radius:4px;'></span></span>"
                f"<span style='width:38px;text-align:right;color:#666;'>{sc:.0%}</span></div>",
                unsafe_allow_html=True,
            )
        st.caption("Fit combines your ranked goals (50/30/20) with your nutrition "
                   "preferences, which count for half as much.")

st.write("")

# ── Diet framework ────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='background:{color};color:#fff;border-radius:8px;padding:10px 16px;margin-bottom:4px;'>"
    f"<b style='font-size:18px;'>{diet_label}</b><br>"
    f"<span style='font-size:15px;'>{DIET_DESCRIPTIONS[diet_key]}</span></div>",
    unsafe_allow_html=True,
)
st.caption(f"{market_label} · {selected_week['label']}")

# ── Run ───────────────────────────────────────────────────────────────────────
# Same action as the sidebar button, repeated here so the flow finishes where
# the questions end. Latched in session state so results survive a rerun
# (moving a slider no longer wipes them).
bc1, bc2 = st.columns([2, 5])
main_run = bc1.button("🔍 Find best recipes", type="primary",
                      use_container_width=True, key="run_main")

if run_btn or main_run:
    ss["run_search"] = True

if not ss.get("run_search"):
    bc2.caption("👈 Click to score this week's menu against your answers.")
    st.stop()

# ── Fetch ─────────────────────────────────────────────────────────────────────
with st.spinner(f"Fetching {market_label} menu for {selected_week['label']}…"):
    try:
        df = fetch_menu(
            market=mkt["market"],
            region_code=mkt["region_code"],
            locale=mkt["locale"],
            segment=mkt["segment"],
            week=selected_week["week"],
            year=selected_week["year"],
        )
    except Exception as e:
        import traceback
        st.error(f"Error fetching data: {e}")
        st.code(traceback.format_exc())
        st.stop()

if df.empty:
    st.warning("No recipes with nutritional data found for this market/week.")
    st.stop()

# ── Rules from the #1 goal ────────────────────────────────────────────────────
df, filter_note = apply_goal_filters(df, goal_keys)
if filter_note:
    st.info(f"🥖 {filter_note}")
if first_goal(goal_keys) in GOAL1_FIBRE_FIRST:
    st.info("🌾 Your top goal puts **fibre first** — recipes are ranked by fibre "
            "content ahead of the framework's own criteria.")

# ── Score & split ─────────────────────────────────────────────────────────────
with st.spinner("Scoring recipes…"):
    scored = score_menu(df, diet_key, weights=live_w,
                        goal_keys=goal_keys, pref_keys=pref_keys)

if scored.empty or scored["score"].max() == 0:
    st.warning("Recipes were found but none could be scored — nutritional data may be missing for this market/week.")
    st.stop()

# Top 5: strict similarity threshold (0.55)
top5 = diverse_top_n(scored, n=5, max_per_flavor=1, sim_threshold=0.55)

# Runner-up 5: relaxed threshold (0.40), seeded with top-5 bases so no duplicates
top5_ids    = set(top5["recipe_id"].tolist()) if "recipe_id" in top5.columns else set()
top5_bases  = [_base(str(t)) for t in top5["title"].tolist()]
remaining   = scored[~scored["recipe_id"].isin(top5_ids)].reset_index(drop=True)
runner5     = diverse_top_n(remaining, n=5, max_per_flavor=1, sim_threshold=0.40,
                             seed_bases=top5_bases)

total_recipes = len(scored)
st.caption(f"Scored {total_recipes} recipes · showing top 10")


# ── Nutrient helpers ──────────────────────────────────────────────────────────
def _count_veggies(row) -> int:
    """Read pre-computed PHF fresh-produce count from fetch_menu()."""
    return int(row.get("veggie_count") or 0)

def _veggie_grams(row) -> float:
    """Grams of PHF produce per serving, summed in fetch_menu()."""
    return float(row.get("veggie_grams") or 0)

# Fixed per-recipe reference values (one dinner out of ~3 meals/day)
# veggies is grams of PHF produce per serving (WHO 400 g/day ÷ ~2 main meals)
_REF = {"fibre": 8.0, "protein": 20.0, "sat_fat": 7.0,
        "veggies": 200.0, "veggies_count": 3}

def _chip_color(val: float, ref: float, invert: bool = False) -> str:
    """
    Traffic-light colour for a nutrient chip.
    invert=False (good nutrient — more is better): green ≥ ref, amber ≥ 50%, red < 50%
    invert=True  (bad nutrient — less is better):  green ≤ ref, amber ≤ 2× ref, red > 2× ref
    Red reserved for >2× the recommended — matches user preference.
    """
    if ref <= 0:
        return "#888"
    ratio = val / ref
    if not invert:
        if ratio >= 1.0: return "#2e7d32"
        if ratio >= 0.5: return "#e08000"
        return "#cc3333"
    else:
        if ratio <= 1.0: return "#2e7d32"
        if ratio <= 2.0: return "#e08000"
        return "#cc3333"

def _nut_chip(label: str, val: float, ref: float, invert: bool = False) -> str:
    c = _chip_color(val, ref, invert)
    return f"<span class='nut' style='background:{c};'>{label}</span>"


# ── Card renderer ─────────────────────────────────────────────────────────────
def render_card(row, rank: int, color: str, dimmed: bool = False):
    score    = row.get("score", 0)
    title    = row.get("title") or "Untitled"
    subtitle = row.get("subtitle") or ""
    img_url  = row.get("image_url") or ""
    kcal     = row.get("calories") or "–"
    prot     = float(row.get("protein") or 0)
    fibre    = float(row.get("fibre") or 0)
    sfat     = float(row.get("sat_fat") or 0)
    ings     = row.get("ingredients") or []
    veggies  = _count_veggies(row)
    veg_g    = _veggie_grams(row)
    diff     = row.get("difficulty") or ""
    t_time   = row.get("total_time") or ""

    img_html = (
        f'<img class="card-img" src="{img_url}" onerror="this.outerHTML=\'<div class=&quot;card-img-placeholder&quot;>🍽️</div>\'">'
        if img_url else
        '<div class="card-img-placeholder">🍽️</div>'
    )
    ing_text  = ", ".join(str(i).title() for i in ings[:8]) if ings else ""
    meta_bits = [x for x in [
        f"⚡ {diff}" if diff else "",
        f"⏱ {t_time} min" if t_time else "",
    ] if x]

    outer_cls = "recipe-card runner-up-card" if dimmed else "recipe-card"

    # Prefer grams; fall back to the item count when no SKU states a weight
    veg_chip = (
        _nut_chip(f"🥦 {veg_g:.0f}g vegetables", veg_g, _REF["veggies"])
        if veg_g > 0 else
        _nut_chip(f"🥦 {veggies} vegetables", veggies, _REF["veggies_count"])
    )

    st.markdown(f"""
    <div class="{outer_cls}">
      {img_html}
      <div class="card-body">
        <div class="card-rank">#{rank}</div>
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;">
          <div>
            <div class="card-title">{title}</div>
            <div class="card-sub">{subtitle}</div>
          </div>
          <span class="score-badge" style="background:{color};flex-shrink:0;">{score}/100</span>
        </div>
        <div class="nutrient-row">
          <span class="nut nut-neutral">🔥 {kcal:.0f} kcal</span>
          {_nut_chip(f"💪 {prot:.0f}g prot", prot, _REF["protein"])}
          {_nut_chip(f"🌾 {fibre:.1f}g fibre", fibre, _REF["fibre"])}
          {_nut_chip(f"🧈 {sfat:.1f}g sat.fat", sfat, _REF["sat_fat"], invert=True)}
          {veg_chip}
        </div>
        {"<div class='ing'>" + ing_text + "</div>" if ing_text else ""}
        {"<div style='font-size:11px;color:#aaa;margin-top:5px;'>" + " · ".join(meta_bits) + "</div>" if meta_bits else ""}
      </div>
    </div>
    """, unsafe_allow_html=True)


def group_summary(group: pd.DataFrame) -> str:
    from scoring import _detect_protein
    red_meat_n = sum(1 for _, r in group.iterrows() if _detect_protein(r) == "red_meat")
    fibre_avg  = group["fibre"].fillna(0).astype(float).mean()
    kcal_avg   = group["calories"].fillna(0).astype(float).mean()
    prot_avg   = group["protein"].fillna(0).astype(float).mean()
    rm_label   = f"🥩 Red meat: {red_meat_n}/5"
    return f"{rm_label} &nbsp;|&nbsp; 🌾 Avg fibre: {fibre_avg:.1f}g &nbsp;|&nbsp; 🔥 Avg kcal: {kcal_avg:.0f} &nbsp;|&nbsp; 💪 Avg protein: {prot_avg:.1f}g"


_GREEN = "#2e7d32"   # what _chip_color() returns when a value is on target


def _celebration_banner(goal_label: str) -> str:
    """Loud congratulations ribbon, rendered inside the weekly score card."""
    sub = (f"Every one of your four weekly targets is in the green"
           + (f" — nailing “{goal_label}”." if goal_label else "."))
    return (
        f"<div style='background:linear-gradient(115deg,{HF_GREEN} 0%,#6FA512 55%,#3E7A0A 100%);"
        f"border-radius:12px;padding:14px 18px;margin:0 0 14px;color:#fff;"
        f"display:flex;align-items:center;gap:14px;"
        f"box-shadow:0 5px 18px rgba(92,138,15,.34);position:relative;overflow:hidden;'>"
        f"<div style='font-size:34px;line-height:1;flex-shrink:0;'>🎉</div>"
        f"<div><div style='font-size:18px;font-weight:800;letter-spacing:-.2px;'>"
        f"You rock your health goal with this menu!</div>"
        f"<div style='font-size:13px;opacity:.95;margin-top:2px;'>{sub}</div></div>"
        f"<div style='position:absolute;right:-8px;bottom:-30px;font-size:96px;"
        f"opacity:.17;transform:rotate(-10deg);'>🥗</div>"
        f"</div>"
    )


def _celebration_toast(group: pd.DataFrame, diet_key: str):
    """Fires once per selection — it would otherwise replay on every rerun."""
    ids = tuple(sorted(str(x) for x in group.get("recipe_id", pd.Series(dtype=str))))
    once_key = f"_celebrated_{diet_key}_{hash(ids)}"
    if not st.session_state.get(once_key):
        st.session_state[once_key] = True
        st.toast("🥳 You rock your health goal with this menu!", icon="🎉")


def weekly_score_card(group: pd.DataFrame, diet_key: str, weights: dict, color: str,
                      celebrate: bool = False, goal_label: str = "") -> bool:
    """Render a weekly compliance summary for the selected 5 recipes."""
    avg_score  = group["score"].fillna(0).astype(float).mean()
    kcal_avg   = group["calories"].fillna(0).astype(float).mean()
    fibre_avg  = group["fibre"].fillna(0).astype(float).mean()
    prot_avg   = group["protein"].fillna(0).astype(float).mean()
    sfat_avg   = group["sat_fat"].fillna(0).astype(float).mean()
    veggie_avg = group.apply(_veggie_grams, axis=1).mean()

    # Targets — diet-specific where available, else sensible defaults
    fibre_tgt  = float(weights.get("fibre_target_g", 8.0))
    prot_tgt   = 20.0  # g per recipe
    sfat_max_p = float(weights.get("sfat_max_pct", 0.10))
    sfat_max_g = (sfat_max_p * kcal_avg / 9) if kcal_avg > 0 else 7.0
    veggie_tgt = _REF["veggies"]   # g of PHF produce per serving

    def _bar(val, ref, invert=False):
        """Progress bar coloured by the same traffic-light logic as chip colours."""
        fill = _chip_color(val, ref, invert)
        # Bar width: for good nutrients show progress to target; for bad show consumption vs 2× max
        if not invert:
            bar_pct = min(int(val / ref * 100), 100) if ref > 0 else 0
        else:
            bar_pct = min(int(val / (ref * 2) * 100), 100) if ref > 0 else 0
        return (
            f"<div style='background:#e0e0e0;border-radius:4px;height:8px;width:100%;margin-top:4px;'>"
            f"<div style='background:{fill};width:{bar_pct}%;height:8px;border-radius:4px;'></div></div>"
        )

    all_green = all(c == _GREEN for c in (
        _chip_color(prot_avg, prot_tgt),
        _chip_color(fibre_avg, fibre_tgt),
        _chip_color(sfat_avg, sfat_max_g, True),
        _chip_color(veggie_avg, veggie_tgt),
    ))

    show_party = all_green and celebrate
    if show_party:
        _celebration_toast(group, diet_key)

    st.markdown(
        f"<div style='background:linear-gradient(150deg,#FFFFFF,{HF_LEAF_BG});"
        f"border:{'2.5px solid ' + HF_GREEN if show_party else '1.5px solid ' + color};"
        f"border-radius:12px;"
        f"padding:14px 18px;margin-bottom:14px;"
        f"box-shadow:{'0 6px 22px rgba(92,138,15,.28)' if show_party else '0 3px 12px rgba(47,79,11,.08)'};'>"
        + (_celebration_banner(goal_label) if show_party else "")
        + f"<div style='display:flex;align-items:center;gap:16px;margin-bottom:12px;'>"
        f"<div style='background:{color};color:#fff;border-radius:50%;width:56px;height:56px;"
        f"display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;flex-shrink:0;'>"
        f"{avg_score:.0f}</div>"
        f"<div><div style='font-size:15px;font-weight:700;'>Weekly diet score</div>"
        f"<div style='font-size:12px;color:#666;'>Average across these 5 recipes · "
        f"🟢 on target &nbsp;🟡 below &nbsp;🔴 >2× limit</div></div>"
        f"</div>"
        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:12px;font-size:12px;'>"
        f"<div><b>💪 Protein</b><br><span style='color:{_chip_color(prot_avg,prot_tgt)};font-weight:700;'>{prot_avg:.1f}g</span> / {prot_tgt:.0f}g"
        f"{_bar(prot_avg, prot_tgt)}</div>"
        f"<div><b>🌾 Fibre</b><br><span style='color:{_chip_color(fibre_avg,fibre_tgt)};font-weight:700;'>{fibre_avg:.1f}g</span> / {fibre_tgt:.0f}g"
        f"{_bar(fibre_avg, fibre_tgt)}</div>"
        f"<div><b>🧈 Sat. fat</b><br><span style='color:{_chip_color(sfat_avg,sfat_max_g,True)};font-weight:700;'>{sfat_avg:.1f}g</span> / {sfat_max_g:.1f}g max"
        f"{_bar(sfat_avg, sfat_max_g, invert=True)}</div>"
        f"<div><b>🥦 Vegetables</b><br><span style='color:{_chip_color(veggie_avg,veggie_tgt)};font-weight:700;'>{veggie_avg:.0f}g</span> / {veggie_tgt:.0f}g"
        f"{_bar(veggie_avg, veggie_tgt)}</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )
    return all_green


def render_row(group: pd.DataFrame, start_rank: int, color: str, dimmed: bool = False,
               diet_key: str = "", weights: dict = None, show_weekly_score: bool = False,
               celebrate: bool = False, goal_label: str = ""):
    if show_weekly_score and diet_key and weights is not None:
        weekly_score_card(group, diet_key, weights, color,
                          celebrate=celebrate, goal_label=goal_label)
    cols = st.columns(5)
    for i, (_, recipe) in enumerate(group.iterrows()):
        with cols[i]:
            render_card(recipe, rank=start_rank + i, color=color, dimmed=dimmed)
    st.markdown(
        f"<div style='font-size:12px;color:#888;margin:6px 0 0 4px;'>{group_summary(group)}</div>",
        unsafe_allow_html=True,
    )


# ── Top 5 ─────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='section-header' style='background:{color};'>🏅 Top 5 — Best fit</div>",
    unsafe_allow_html=True,
)
_g1 = first_goal(goal_keys)
render_row(top5, start_rank=1, color=color,
           diet_key=diet_key, weights=live_w, show_weekly_score=True,
           celebrate=True, goal_label=GOAL_LABEL.get(_g1, ""))

# ── Runner-up 5 ───────────────────────────────────────────────────────────────
if not runner5.empty:
    runner_color = "#888"
    st.markdown(
        f"<div class='section-header' style='background:{runner_color};'>🥈 Runner-up 5 — Second best fit</div>",
        unsafe_allow_html=True,
    )
    render_row(runner5, start_rank=6, color=runner_color, dimmed=True,
               diet_key=diet_key, weights=live_w, show_weekly_score=True)

# ── How scores work ───────────────────────────────────────────────────────────
with st.expander("How are scores calculated?"):
    st.markdown(f"""
    Scores are 0–100 per recipe, computed from per-serving nutritional data.
    Weights and thresholds are fully editable in the sidebar (session only) or saved permanently on the **Diet Settings** page.

    | Framework | Key criteria |
    |---|---|
    | Health conscious choices | Salt <1.25 g, free sugars <5 %, sat. fat, fibre, diverse protein |
    | Maximized vegetables | Grams of fresh produce per serving, fibre, plant protein, calorie balance |
    | Improve Sports Performance | Protein grams (30 g target), energy, fibre, sat. fat, salt |
    | Mediterranean | Fish/seafood, legumes, wholegrains, fibre, low sat. fat/salt, no red meat |
    | Blue Zone | Plant protein, legumes, high fibre, very low sugar, low salt, low calorie density |
    | EAT-Lancet | Plant/fish protein (red meat strongly penalised), fibre, sat. fat, calorie balance |

    Health conscious choices, Maximized vegetables and Improve Sports Performance also
    take **CPS tags** into account — recipes carrying the framework's tags (high-protein,
    calorie-smart, extra-vegetables, family-friendly …) are lifted up the ranking.
    Tag vocabularies differ per market, so this is a boost rather than a filter.

    Recipes with missing nutritional data are excluded from ranking.
    """)

# ── Export ────────────────────────────────────────────────────────────────────
st.divider()


def build_excel(df_scored: pd.DataFrame) -> bytes:
    col_map = {
        "title": "Recipe", "subtitle": "Description", "score": "Score",
        "calories": "Kcal", "protein": "Protein (g)", "fibre": "Fibre (g)",
        "fat": "Fat (g)", "sat_fat": "Sat. Fat (g)", "sugars": "Sugars (g)",
        "salt": "Salt (g)", "difficulty": "Difficulty", "total_time": "Time (min)",
        "slot": "Menu Slot", "recipe_id": "Recipe ID",
    }
    out = df_scored[[c for c in col_map if c in df_scored.columns]].rename(columns=col_map)
    buf = io.BytesIO()
    import openpyxl
    from openpyxl.styles import Font
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        out.iloc[:5].to_excel(writer, index=False, sheet_name="Top 5")
        out.iloc[5:10].to_excel(writer, index=False, sheet_name="Runner-up 5")
        out.to_excel(writer, index=False, sheet_name="All Scored")
        for sheet_name in ["Top 5", "Runner-up 5", "All Scored"]:
            ws = writer.sheets[sheet_name]
            ws.column_dimensions["A"].width = 34
            ws.column_dimensions["B"].width = 36
            for cell in ws[1]:
                cell.font = Font(bold=True)
    buf.seek(0)
    return buf.getvalue()


c1, c2 = st.columns([3, 1])
with c1:
    st.write(f"**Top 5** + **Runner-up 5** recipes · {diet_label} · {market_label} · {selected_week['label']}")
with c2:
    st.download_button(
        label="⬇️ Export to Excel",
        data=build_excel(scored),
        file_name=f"hf_diet_coach_{diet_key}_{market_label.replace(' ','_')}_{selected_week['label']}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ── Methodology footnote ──────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<p style='font-size:11px;color:#aaa;margin-bottom:2px;'>* How scores are calculated</p>",
    unsafe_allow_html=True,
)
with st.expander("", expanded=False):
    fibre_tgt  = live_w.get("fibre_target_g", 10)
    salt_max   = live_w.get("salt_max_g", 2.0)
    sfat_max_p = live_w.get("sfat_max_pct", 0.10)
    sugar_max_p = live_w.get("sugar_max_pct", 0.10)
    w_keys_disp = {k.replace("w_","").replace("_"," ").title(): round(float(live_w[k]),2)
                   for k in sorted(live_w) if k.startswith("w_")}
    prot_disp = {k.replace("prot_","").replace("_"," ").title(): round(float(live_w[k]),2)
                 for k in sorted(live_w) if k.startswith("prot_")}

    st.markdown(f"""
**Recipe score (0–100)**

Each recipe is scored individually against the **{diet_label}** framework using per-serving nutritional data.
The score is a weighted sum of sub-scores, each normalised to 0–1:

| Criterion | Weight | How it's measured |
|---|---|---|
""" + "\n".join(f"| {k} | {v} | see threshold below |" for k, v in w_keys_disp.items()) + f"""

Weights are auto-normalised so they always sum to 1. You can edit them in the sidebar.

**Nutritional thresholds (active values)**

| Threshold | Value | Meaning |
|---|---|---|
| Fibre target | {fibre_tgt} g | Per-serving fibre needed for a full score |
| Salt max | {salt_max} g | Per-serving salt above which score drops to 0 |
| Sat. fat max | {sfat_max_p*100:.0f} % of kcal | Saturated fat as % of calories |
| Sugar max | {sugar_max_p*100:.0f} % of kcal | Free sugars as % of calories |

**Protein source multipliers (active values)**

The protein sub-score is multiplied by the type of protein detected in the recipe name and ingredients:

| Protein type | Multiplier |
|---|---|
""" + "\n".join(f"| {k} | {v} |" for k, v in prot_disp.items()) + f"""

Red meat is additionally hard-capped at a maximum score of **{int(live_w.get('red_meat_cap', 100))} / 100** for the {diet_label} framework.

**Group rules**

After individual scoring, the Top 5 and Runner-up 5 are each checked as a group:
- Max red meat recipes per group: **{__import__('config').DIET_GROUP_RULES.get(diet_key, {}).get('max_red_meat', '–')} / 5**

If the group exceeds the limit, the lowest-scoring red meat recipe is replaced by the next-best alternative from the remaining pool.

**Weekly diet score**

The weekly score shown below each group is the **simple average** of the 5 individual recipe scores.
The progress bars compare average per-serving nutrients against the active thresholds above.
A green bar means the group is on target; amber/red means it falls short (fibre) or exceeds the limit (salt, sat. fat, sugar).

*All data sourced from HelloFresh Databricks. Nutritional values are per serving as published.*
    """)


