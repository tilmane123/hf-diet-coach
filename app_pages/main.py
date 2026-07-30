"""Main recipe-finder page."""

import io
import copy
import pandas as pd
import streamlit as st

from config import MARKETS, DIETS, DIET_DESCRIPTIONS, DIET_COLORS
from menu_data import get_available_weeks, fetch_menu, diverse_top_n, _base
from scoring import score_menu
from settings_store import get_weights

st.markdown("""
<style>
  .recipe-card { background:#fff; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.09); overflow:hidden; height:100%; }
  .card-img { width:100%; height:175px; object-fit:cover; }
  .card-img-placeholder { height:175px; background:#efefef; display:flex; align-items:center; justify-content:center; font-size:48px; }
  .card-body { padding:12px 14px 14px; }
  .card-rank { font-size:11px; font-weight:600; color:#999; text-transform:uppercase; letter-spacing:.5px; margin-bottom:3px; }
  .card-title { font-size:14px; font-weight:700; line-height:1.35; margin:0 0 2px; }
  .card-sub { font-size:12px; color:#777; margin:0 0 8px; }
  .score-badge { display:inline-block; border-radius:20px; padding:3px 11px; font-size:13px; font-weight:700; color:#fff; }
  .nutrient-row { display:flex; gap:5px; flex-wrap:wrap; margin-top:8px; }
  .nut { background:#f4f4f4; border-radius:6px; padding:2px 7px; font-size:11px; color:#444; }
  .ing { font-size:11px; color:#666; margin-top:7px; line-height:1.55; }
  .section-header { font-size:18px; font-weight:700; margin:24px 0 12px; padding:8px 14px; border-radius:8px; color:#fff; }
  .runner-up-card { opacity:0.88; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ae/HelloFresh_logo.svg/320px-HelloFresh_logo.svg.png",
        width=150,
    )
    st.title("HF Diet Coach")
    st.caption("Best-fit HelloFresh recipes for any diet. · v0.24")
    st.divider()

    market_label = st.selectbox("🌍 Market", list(MARKETS.keys()))
    mkt = MARKETS[market_label]

    diet_label = st.selectbox("🥗 Diet Framework", list(DIETS.keys()))
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

st.markdown(
    f"<div style='background:{color};color:#fff;border-radius:8px;padding:10px 16px;margin-bottom:4px;'>"
    f"<b style='font-size:18px;'>{diet_label}</b><br>"
    f"<span style='font-size:15px;'>{DIET_DESCRIPTIONS[diet_key]}</span></div>",
    unsafe_allow_html=True,
)
st.caption(f"{market_label} · {selected_week['label']}")

if not run_btn:
    st.info("Choose your settings in the sidebar and click **Find best recipes**.")
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

# ── Score & split ─────────────────────────────────────────────────────────────
with st.spinner("Scoring recipes…"):
    scored = score_menu(df, diet_key, weights=live_w)

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


# ── Card renderer ─────────────────────────────────────────────────────────────
def render_card(row, rank: int, color: str, dimmed: bool = False):
    score    = row.get("score", 0)
    title    = row.get("title") or "Untitled"
    subtitle = row.get("subtitle") or ""
    img_url  = row.get("image_url") or ""
    kcal     = row.get("calories") or "–"
    prot     = row.get("protein") or "–"
    fibre    = row.get("fibre") or "–"
    salt     = row.get("salt") or "–"
    ings     = row.get("ingredients") or []
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
          <span class="nut">🔥 {kcal} kcal</span>
          <span class="nut">💪 {prot}g prot</span>
          <span class="nut">🌾 {fibre}g fibre</span>
          <span class="nut">🧂 {salt}g salt</span>
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


def weekly_score_card(group: pd.DataFrame, diet_key: str, weights: dict, color: str):
    """Render a weekly compliance summary for the selected 5 recipes."""
    from config import DIET_WEIGHTS
    avg_score = group["score"].fillna(0).astype(float).mean()

    # Nutrient averages
    fibre_avg  = group["fibre"].fillna(0).astype(float).mean()
    kcal_avg   = group["calories"].fillna(0).astype(float).mean()
    sfat_avg   = group["sat_fat"].fillna(0).astype(float).mean()
    salt_avg   = group["salt"].fillna(0).astype(float).mean()
    sugar_avg  = group["sugars"].fillna(0).astype(float).mean()

    # Targets from active weights
    fibre_tgt  = float(weights.get("fibre_target_g", 10))
    salt_max   = float(weights.get("salt_max_g", 2.0))
    sfat_max_p = float(weights.get("sfat_max_pct", 0.10))
    sfat_max_g = (sfat_max_p * kcal_avg / 9) if kcal_avg > 0 else 5.0
    sugar_max_p = float(weights.get("sugar_max_pct", 0.10))
    sugar_max_g = (sugar_max_p * kcal_avg / 4) if kcal_avg > 0 else 15.0

    def pct_bar(val, target, invert=False):
        pct = min(val / target, 1.0) if target > 0 else 0
        score_pct = (1 - pct) if invert else pct
        fill_color = color if score_pct >= 0.6 else ("#e08000" if score_pct >= 0.35 else "#cc3333")
        bar_pct = int(pct * 100)
        return (
            f"<div style='background:#eee;border-radius:4px;height:8px;width:100%;margin-top:3px;'>"
            f"<div style='background:{fill_color};width:{bar_pct}%;height:8px;border-radius:4px;'></div></div>"
        )

    st.markdown(
        f"<div style='background:#f8f8f8;border:1.5px solid {color};border-radius:10px;"
        f"padding:14px 18px;margin-top:14px;'>"
        f"<div style='display:flex;align-items:center;gap:16px;margin-bottom:10px;'>"
        f"<div style='background:{color};color:#fff;border-radius:50%;width:56px;height:56px;"
        f"display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;flex-shrink:0;'>"
        f"{avg_score:.0f}</div>"
        f"<div><div style='font-size:15px;font-weight:700;'>Weekly diet score</div>"
        f"<div style='font-size:12px;color:#666;'>Average score if you cook these 5 recipes · out of 100</div></div>"
        f"</div>"
        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px;font-size:12px;'>"
        # Fibre
        f"<div><b>🌾 Fibre</b><br>{fibre_avg:.1f}g / {fibre_tgt:.0f}g target"
        f"{pct_bar(fibre_avg, fibre_tgt)}</div>"
        # Salt
        f"<div><b>🧂 Salt</b><br>{salt_avg:.2f}g / {salt_max:.1f}g max"
        f"{pct_bar(salt_avg, salt_max, invert=True)}</div>"
        # Sat fat
        f"<div><b>🧈 Sat. fat</b><br>{sfat_avg:.1f}g / {sfat_max_g:.1f}g max"
        f"{pct_bar(sfat_avg, sfat_max_g, invert=True)}</div>"
        # Sugars
        f"<div><b>🍬 Sugars</b><br>{sugar_avg:.1f}g / {sugar_max_g:.1f}g max"
        f"{pct_bar(sugar_avg, sugar_max_g, invert=True)}</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def render_row(group: pd.DataFrame, start_rank: int, color: str, dimmed: bool = False,
               diet_key: str = "", weights: dict = None, show_weekly_score: bool = False):
    cols = st.columns(5)
    for i, (_, recipe) in enumerate(group.iterrows()):
        with cols[i]:
            render_card(recipe, rank=start_rank + i, color=color, dimmed=dimmed)
    st.markdown(
        f"<div style='font-size:12px;color:#888;margin:6px 0 0 4px;'>{group_summary(group)}</div>",
        unsafe_allow_html=True,
    )
    if show_weekly_score and diet_key and weights is not None:
        weekly_score_card(group, diet_key, weights, color)


# ── Top 5 ─────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div class='section-header' style='background:{color};'>🏅 Top 5 — Best fit</div>",
    unsafe_allow_html=True,
)
render_row(top5, start_rank=1, color=color,
           diet_key=diet_key, weights=live_w, show_weekly_score=True)

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
    | DGE | Fibre, sat. fat <10 % kcal, salt, sugar, protein source |
    | EAT-Lancet | Plant/fish protein (red meat strongly penalised), fibre, sat. fat, calorie balance |
    | WHO | Salt <1.25 g, free sugars <5 %, sat. fat, fibre, diverse protein |
    | Mediterranean | Fish/seafood, legumes, wholegrains, fibre, low sat. fat/salt, no red meat |
    | Blue Zone | Plant protein, legumes, high fibre, very low sugar, low salt, low calorie density |

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


