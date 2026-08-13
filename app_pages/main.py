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
  /* ── Recipe cards ── */
  .recipe-card {{ background:#fff; border-radius:16px; box-shadow:0 4px 16px rgba(0,0,0,.08); overflow:hidden; height:100%; transition:box-shadow .2s; }}
  .recipe-card:hover {{ box-shadow:0 8px 24px rgba(0,0,0,.13); }}
  .card-img {{ width:100%; height:140px; object-fit:cover; }}
  .card-img-placeholder {{ height:140px; background:#f0f0f0; display:flex; align-items:center; justify-content:center; font-size:40px; }}
  .card-body {{ padding:9px 11px 11px; }}
  .card-rank {{ font-size:10px; font-weight:600; color:#bbb; text-transform:uppercase; letter-spacing:.5px; margin-bottom:2px; }}
  .card-title {{ font-size:13px; font-weight:700; line-height:1.3; margin:0 0 1px;
                 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden; }}
  .card-sub {{ font-size:11px; color:#999; margin:0 0 5px;
               display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden; }}
  .score-badge {{ display:inline-block; border-radius:20px; padding:3px 11px; font-size:13px; font-weight:700; color:#fff; }}
  .nutrient-row {{ display:flex; gap:5px; flex-wrap:wrap; margin-top:8px; }}
  .nut {{ border-radius:6px; padding:2px 6px; font-size:10px; color:#fff; font-weight:600; }}
  .nut-neutral {{ background:#f0f0f0; color:#555; font-weight:400; }}
  .ing {{ font-size:10px; color:#aaa; margin-top:5px; line-height:1.4;
          display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden; }}
  .section-header {{ font-size:17px; font-weight:700; margin:24px 0 10px; padding:10px 18px; border-radius:12px; color:#fff; }}
  .runner-up-card {{ opacity:0.85; }}

  /* ── Selector panels (Lifesum/Oura-style clean tiles) ── */
  .sel-panel {{ background:#fff; border-radius:18px;
               box-shadow:0 2px 10px rgba(0,0,0,.07);
               border-top:3px solid #91C11E;
               padding:14px 14px 12px; text-align:center; margin-top:4px; }}
  .sel-icon  {{ font-size:34px; line-height:1.1; margin-bottom:2px; }}
  .sel-value {{ font-size:17px; font-weight:800; color:#222; line-height:1.25; margin-top:2px; }}
  .sel-sub   {{ font-size:11px; color:#aaa; margin-top:1px; }}
  .sel-label {{ font-size:10px; font-weight:700; letter-spacing:.8px; text-transform:uppercase;
               color:#c0c0c0; margin-top:6px; }}

  /* ── Diet result header ── */
  .diet-header {{ border-radius:14px; padding:14px 20px; margin-bottom:6px;
                 box-shadow:0 4px 16px rgba(0,0,0,.12);
                 display:flex; align-items:center; gap:14px; }}
  .diet-header-emoji {{ font-size:34px; flex-shrink:0; line-height:1; }}
  .diet-header-body  {{ flex:1; min-width:0; }}
  .diet-header-title {{ font-size:18px; font-weight:800; color:#fff; margin:0 0 3px; }}
  .diet-header-desc  {{ font-size:12px; color:rgba(255,255,255,.85); margin:0; letter-spacing:.2px; }}
  .diet-header-meta  {{ font-size:11px; color:rgba(255,255,255,.60); margin-top:4px; }}

  /* ── Expander accents ── */
  [data-testid="stAppViewContainer"] [data-testid="stExpander"]:nth-of-type(1) {{
    border-left:4px solid #91C11E !important;
    border-radius:10px !important;
    background:#FAFFF4 !important;
  }}
  [data-testid="stAppViewContainer"] [data-testid="stExpander"]:nth-of-type(2) {{
    border-left:4px solid #E06020 !important;
    border-radius:10px !important;
    background:#FFFAF7 !important;
  }}
</style>
""", unsafe_allow_html=True)

# ── Market flags ──────────────────────────────────────────────────────────────
_MARKET_FLAGS = {
    "Germany":            "🇩🇪  Germany",
    "Netherlands":        "🇳🇱  Netherlands",
    "United Kingdom":     "🇬🇧  United Kingdom",
    "France":             "🇫🇷  France",
    "Scandinavia (DKSE)": "🇸🇪  Scandinavia",
}
_MARKET_FLAG_ICON = {
    "Germany":            "🇩🇪",
    "Netherlands":        "🇳🇱",
    "United Kingdom":     "🇬🇧",
    "France":             "🇫🇷",
    "Scandinavia (DKSE)": "🇸🇪",
}
_FLAG_TO_MARKET = {v: k for k, v in _MARKET_FLAGS.items()}

# ── Avoidance options ─────────────────────────────────────────────────────────
_AVOID_OPTIONS = {
    "🥜 Peanuts":        "peanut",
    "🥛 Dairy":          "dairy",
    "🌾 Gluten":         "gluten",
    "🐷 Pork":           "pork",
    "🐄 Beef":           "beef",
    "🐟 Fish & Seafood": "fish",
}

def _apply_avoidances(df: pd.DataFrame, avoid_keys: list) -> pd.DataFrame:
    if not avoid_keys or df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    ing_text = df["ingredients"].apply(
        lambda x: " ".join(str(i) for i in (x or [])).lower()
    )
    title_text = df["title"].fillna("").str.lower()
    combined = ing_text + " " + title_text
    for key in avoid_keys:
        if key == "peanut":
            mask &= ~combined.str.contains(r"erdnuss|peanut", regex=True)
        elif key == "dairy":
            mask &= ~combined.str.contains(
                r"milch|käse|butter|sahne|joghurt|quark|feta|mozzarella|parmesan|"
                r"milk|cheese|cream|yogurt|cheddar|ricotta|halloumi", regex=True)
        elif key == "gluten":
            mask &= ~combined.str.contains(
                r"mehl|weizen|dinkel|pasta|nudel|spaghetti|tagliatelle|penne|fusilli|"
                r"brot|brötchen|flour|wheat|spelt|couscous|bulgur|bread|noodle", regex=True)
        elif key == "pork":
            mask &= ~combined.str.contains(
                r"schwein|speck|bacon|schinken|chorizo|salami|pancetta|pork|"
                r"pulled\s*pork|salsiccia|mortadella|coppa", regex=True)
        elif key == "beef":
            mask &= ~combined.str.contains(
                r"rind\w*|hack\w*|beef|roastbeef|hüftsteak|steak|burger|"
                r"bolognese|tartar|brisket", regex=True)
        elif key == "fish":
            mask &= ~combined.str.contains(
                r"lachs|salmon|kabeljau|cod|thunfisch|tuna|garnele|shrimp|prawn|"
                r"forelle|trout|dorade|pangasius|hake|seabass|fisch\b|fish\b|"
                r"muschel|mussel|squid|calamari|crevette", regex=True)
    return df[mask].reset_index(drop=True)


# ── App title ─────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='text-align:center;padding:28px 0 12px;'>"
    "<span style='font-size:32px;font-weight:800;letter-spacing:-1px;'>🥗 HF Diet Coach</span><br>"
    "<span style='color:#aaa;font-size:14px;'>Find the best HelloFresh recipes for any diet · v0.29</span>"
    "</div>",
    unsafe_allow_html=True,
)

# ── Personalisation (optional, persistent) ────────────────────────────────────
GOAL_LABEL     = dict(HEALTH_GOALS)
PREF_LABEL     = dict(NUTRITION_PREFS)
KEY_TO_DIET_LABEL  = {v: k for k, v in DIETS.items()}
_LABEL_TO_GOAL = {v: k for k, v in GOAL_LABEL.items()}
_LABEL_TO_PREF = {v: k for k, v in PREF_LABEL.items()}

with st.expander("🌱 Choose your individual health goals"):
    st.markdown(
        "<div style='background:linear-gradient(100deg,#EAF6D0,#F3FBE8);border-radius:10px;"
        "padding:10px 16px 8px;margin-bottom:10px;display:flex;align-items:center;gap:12px;'>"
        "<span style='font-size:28px;'>🥦🫀🏃</span>"
        "<span style='font-size:13px;color:#3A5A0A;line-height:1.5;'>"
        "<b>Personalise your recipe picks</b> — optional.<br>"
        "Your goals re-rank results within the diet framework. "
        "Stays active when you switch country, week, or diet.</span></div>",
        unsafe_allow_html=True,
    )
    _g_col, _p_col = st.columns(2)
    with _g_col:
        _goal_labels = st.multiselect(
            "Health goals (up to 3)",
            options=[lbl for _, lbl in HEALTH_GOALS],
            max_selections=MAX_GOALS,
            placeholder="What matters to you?",
            key="pers_goals",
        )
    with _p_col:
        _pref_labels = st.multiselect(
            "Nutrition preferences (up to 3)",
            options=[lbl for _, lbl in NUTRITION_PREFS],
            max_selections=MAX_PREFS,
            placeholder="Any specific focus?",
            key="pers_prefs",
        )
    _raw_goal_keys = [_LABEL_TO_GOAL[l] for l in _goal_labels]
    if len(_raw_goal_keys) >= 2:
        st.caption("Rank by priority — #1 counts most (50 %):")
        _shares = [f"{w:.0%}" for w in rank_weights(len(_raw_goal_keys))]
        _rank_cols = st.columns(len(_raw_goal_keys))
        _ranked, _taken = [], []
        for _i, (_col, _sh) in enumerate(zip(_rank_cols, _shares)):
            _opts = [l for l in _goal_labels if l not in _taken]
            _pick = _col.selectbox(f"#{_i+1} · {_sh}", _opts, key=f"pers_rank_{_i}")
            _taken.append(_pick)
            _ranked.append(_LABEL_TO_GOAL[_pick])
        goal_keys = _ranked
    else:
        goal_keys = _raw_goal_keys
    pref_keys = [_LABEL_TO_PREF[l] for l in _pref_labels]

# ── Country / Week / Diet selector ───────────────────────────────────────────

c1, c2, c3 = st.columns(3)

with c1:
    flag_label = st.selectbox("country", list(_MARKET_FLAGS.values()),
                               label_visibility="collapsed", key="country_sel")
    market_label = _FLAG_TO_MARKET[flag_label]
    mkt = MARKETS[market_label]
    _cur_icon = _MARKET_FLAG_ICON.get(market_label, "🌍")
    st.markdown(
        f"<div class='sel-panel'>"
        f"<div class='sel-icon'>{_cur_icon}</div>"
        f"<div class='sel-value'>{market_label}</div>"
        f"<div class='sel-label'>Country</div></div>",
        unsafe_allow_html=True,
    )

with c2:
    with st.spinner("Loading weeks…"):
        try:
            weeks = get_available_weeks(mkt["market"], mkt["region_code"])
        except Exception as e:
            st.error(f"Could not load weeks: {e}")
            st.stop()
    if not weeks:
        st.warning("No weeks found.")
        st.stop()
    week_idx = st.selectbox("week", range(len(weeks)),
                             format_func=lambda i: weeks[i]["label"],
                             label_visibility="collapsed", key="week_sel")
    selected_week = weeks[week_idx]
    _wk_num  = selected_week["week"]
    _wk_year = selected_week["year"]
    st.markdown(
        f"<div class='sel-panel'>"
        f"<div class='sel-icon'>📅</div>"
        f"<div class='sel-value'>W{_wk_num}</div>"
        f"<div class='sel-sub'>{_wk_year}</div>"
        f"<div class='sel-label'>Week</div></div>",
        unsafe_allow_html=True,
    )

with c3:
    diet_label = st.selectbox("diet", list(DIETS.keys()),
                               label_visibility="collapsed", key="diet_sel")
    diet_key = DIETS[diet_label]
    _diet_icon = diet_label.split()[0]
    _diet_name_short = " ".join(diet_label.split()[1:])
    st.markdown(
        f"<div class='sel-panel'>"
        f"<div class='sel-icon'>{_diet_icon}</div>"
        f"<div class='sel-value' style='font-size:13px;'>{_diet_name_short}</div>"
        f"<div class='sel-label'>Diet Framework</div></div>",
        unsafe_allow_html=True,
    )

# ── Avoid selector ────────────────────────────────────────────────────────────
with st.expander("🚫 Anything to avoid?"):
    st.markdown(
        "<div style='background:linear-gradient(100deg,#FFF0E6,#FFF8F3);border-radius:10px;"
        "padding:10px 16px 8px;margin-bottom:10px;display:flex;align-items:center;gap:12px;'>"
        "<span style='font-size:28px;'>🥜🥛🌾🐷🐄🐟</span>"
        "<span style='font-size:13px;color:#7A2E00;line-height:1.5;'>"
        "<b>Filter out ingredients you want to avoid</b> — optional.<br>"
        "Recipes containing the selected items will be excluded from results.</span></div>",
        unsafe_allow_html=True,
    )
    avoid_labels = st.multiselect(
        "avoid",
        list(_AVOID_OPTIONS.keys()),
        placeholder="Peanuts, Dairy, Gluten, Pork, Beef, Fish…",
        label_visibility="collapsed",
    )
avoid_keys = [_AVOID_OPTIONS[l] for l in avoid_labels]

# ── Find button ───────────────────────────────────────────────────────────────
_, btn_col, _ = st.columns([1, 2, 1])
with btn_col:
    run_btn = st.button("🔍  Find best recipes", use_container_width=True, type="primary")

st.divider()

# ── Sidebar — scoring params only ─────────────────────────────────────────────
with st.sidebar:
    if HF_LOGO_FILE.exists():
        st.image(str(HF_LOGO_FILE), width=170)
    st.title("HF Diet Coach")
    st.caption("Scoring parameters · v0.29")
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

if not run_btn:
    st.stop()

# ── Diet result header ────────────────────────────────────────────────────────
_diet_emoji = diet_label.split()[0]
_diet_name  = " ".join(diet_label.split()[1:])
st.markdown(
    f"<div class='diet-header' style='background:linear-gradient(120deg,{color}f0,{color}aa);'>"
    f"<div class='diet-header-emoji'>{_diet_emoji}</div>"
    f"<div class='diet-header-body'>"
    f"<div class='diet-header-title'>{_diet_name}</div>"
    f"<div class='diet-header-desc'>{DIET_DESCRIPTIONS.get(diet_key,'')}</div>"
    f"<div class='diet-header-meta'>{flag_label} &nbsp;·&nbsp; {selected_week['short']}"
    + (f" &nbsp;·&nbsp; 🚫 {', '.join(avoid_labels)}" if avoid_labels else "")
    + (f" &nbsp;·&nbsp; 🎯 {', '.join(GOAL_LABEL[k] for k in goal_keys)}" if goal_keys else "")
    + "</div></div></div>",
    unsafe_allow_html=True,
)

# ── Framework suggestion (only when goals are set) ────────────────────────────
if goal_keys or pref_keys:
    _ranked_fw = recommend_diets(goal_keys, pref_keys)
    if _ranked_fw:
        _best_key, _best_score = _ranked_fw[0]
        _best_label = KEY_TO_DIET_LABEL.get(_best_key, _best_key)
        _forced_key = forced_diet(goal_keys)
        _already = _best_key == diet_key
        if _forced_key:
            _fw_headline = f"🎯 Your #1 goal suggests: {_best_label}"
        else:
            _fw_headline = f"🏆 Best framework for your goals: {_best_label} ({_best_score:.0%} fit)"
        if not _already:
            _fw_headline += " — you're viewing a different one"
        st.markdown(
            f"<div style='background:#F8FFF0;border-left:3px solid {DIET_COLORS.get(_best_key, color)};"
            f"border-radius:8px;padding:7px 12px;font-size:12px;color:#555;margin-bottom:6px;'>"
            f"{_fw_headline}</div>",
            unsafe_allow_html=True,
        )

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

# ── Apply avoidances ──────────────────────────────────────────────────────────
if avoid_keys:
    df = _apply_avoidances(df, avoid_keys)
    if df.empty:
        st.warning("No recipes remain after applying your avoidances. Try removing some filters.")
        st.stop()

# ── Rules from the #1 goal ────────────────────────────────────────────────────
df, filter_note = apply_goal_filters(df, goal_keys)
if filter_note:
    st.info(f"🥖 {filter_note}")
if first_goal(goal_keys) in GOAL1_FIBRE_FIRST:
    st.info("🌾 Your top goal puts **fibre first** — recipes are ranked by fibre content ahead of the framework's own criteria.")

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
# Fallback: if diversity filtering left fewer than 5, fill up from the remaining
# pool by score — better to show a similar recipe than an empty slot.
if len(runner5) < 5 and len(remaining) > len(runner5):
    _id_col = "recipe_id" if "recipe_id" in runner5.columns else None
    _used   = set(runner5[_id_col].tolist()) if _id_col else set()
    _extra  = (remaining[~remaining[_id_col].isin(_used)] if _id_col
               else remaining.iloc[len(runner5):])
    runner5 = pd.concat([runner5, _extra.head(5 - len(runner5))], ignore_index=True)

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
    _tt_raw  = row.get("total_time")
    try:
        t_time = str(int(float(_tt_raw))) if _tt_raw and str(_tt_raw) not in ("", "nan", "None") else ""
    except (ValueError, TypeError):
        t_time = ""

    img_html = (
        f'<img class="card-img" src="{img_url}" onerror="this.outerHTML=\'<div class=&quot;card-img-placeholder&quot;>🍽️</div>\'">'
        if img_url else
        '<div class="card-img-placeholder">🍽️</div>'
    )
    ing_text  = ", ".join(str(i).title() for i in ings[:5]) if ings else ""
    meta_bits = [f"⚡ {diff}"] if diff else []

    outer_cls = "recipe-card runner-up-card" if dimmed else "recipe-card"

    # Prefer grams; fall back to the item count when no SKU states a weight
    veg_chip = (
        _nut_chip(f"🥦 {veg_g:.0f}g vegetables", veg_g, _REF["veggies"])
        if veg_g > 0 else
        _nut_chip(f"🥦 {veggies} vegetables", veggies, _REF["veggies_count"])
    )

    # Pre-compute conditional HTML — avoid blank lines inside the f-string,
    # which cause Streamlit's markdown parser to escape HTML mode.
    kcal_val = float(kcal) if kcal != "–" else 0.0
    kcal_str = f"{kcal_val:.0f}" if kcal != "–" else "–"
    time_html = (f"<span style='font-size:10px;color:#aaa;white-space:nowrap;'>⏱ {t_time} min</span>"
                 if t_time else "")
    ing_html  = f"<div class='ing'>{ing_text}</div>" if ing_text else ""
    meta_html = (f"<div style='font-size:11px;color:#aaa;margin-top:5px;'>{' · '.join(meta_bits)}</div>"
                 if meta_bits else "")
    chip_prot = _nut_chip(f"💪 {prot:.0f}g prot", prot, _REF["protein"])
    chip_fib  = _nut_chip(f"🌾 {fibre:.1f}g fibre", fibre, _REF["fibre"])
    chip_sfat = _nut_chip(f"🧈 {sfat:.1f}g sat.fat", sfat, _REF["sat_fat"], invert=True)

    st.markdown(
        f'<div class="{outer_cls}">'
        f'{img_html}'
        f'<div class="card-body">'
        f'<div class="card-rank">#{rank}</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;">'
        f'<div><div class="card-title">{title}</div><div class="card-sub">{subtitle}</div></div>'
        f'<div style="display:flex;flex-direction:column;align-items:flex-end;gap:3px;flex-shrink:0;">'
        f'<span class="score-badge" style="background:{color};">{score}/100</span>'
        f'{time_html}'
        f'</div></div>'
        f'<div class="nutrient-row">'
        f'<span class="nut nut-neutral">🔥 {kcal_str} kcal</span>'
        f'{chip_prot}{chip_fib}{chip_sfat}{veg_chip}'
        f'</div>'
        f'{ing_html}{meta_html}'
        f'</div></div>',
        unsafe_allow_html=True,
    )


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
           + (f' — nailing “{goal_label}”.' if goal_label else "."))
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


