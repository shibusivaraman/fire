"""
retirement_simulator_with_rupee_radio.py

Retirement Simulator — 3-Bucket Refill Strategy (Enhanced)
- Single-file Streamlit app
- Features: Age, refill visualization, CSV/PDF export, unit selector (Rupee symbol), Tax Rate, B1 default by Years of Expense
- UI change: Unit selector is now a radio button; display uses the Rupee symbol (₹)
- Enhanced Refill: Cascading refill strategy with B1←B2←B3 and minimum thresholds
- Inputs: Monthly spending (instead of annual)
- Defaults:
    - Current age and withdrawal start age = 50
    - Current retirement corpus = 5 Crore (50,000,000 Rs)
    - Inflation = 6%
    - Expected returns: B1=6%, B2=8%, B3=12%
- Dependencies: streamlit, pandas, numpy, matplotlib
- Run:
    pip install streamlit pandas numpy matplotlib
    streamlit run retirement_simulator_with_rupee_radio.py
"""
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime

# Page config
st.set_page_config(page_title="Retirement Simulator — 3-Bucket Refill Strategy", layout="wide")
st.title("Retirement Simulator — 3-Bucket Refill Strategy")

# Mobile layout toggle (helps mobile users who don't see sidebar easily)
use_mobile_layout = st.checkbox(
    "Use mobile-optimized layout (single-column inputs)",
    value=False,
    help="Check this to render all input controls in a single column suitable for small screens or mobile devices."
)

# -------------------------
# Top summary for users
# -------------------------
with st.expander("About this Retirement Simulator", expanded=False):
    st.markdown(
        """
**App summary**

This lightweight simulator models a **3‑Bucket Retirement strategy** to help you manage a retirement corpus:
- **Bucket 1 — Liquid**: cash and short-term instruments for near-term spending.
- **Bucket 2 — Income**: bonds, annuities, or income-generating assets.
- **Bucket 3 — Growth**: equities and long-term growth assets.

**What this app does**
- Projects yearly balances for each bucket and the total portfolio.
- Models annual returns and withdrawal escalation.
- Implements an **enhanced cascading refill strategy** that refills B1 from B2, and B2 from B3 with safety thresholds.
- Visualizes bucket composition, refill transfers, and the total portfolio using **Age** on the x-axis.
- Lets you **download** the projection as CSV or a simple PDF report.

**Refill Strategy (Enhanced)**
- **B1 refilled from B2** when B1 < target AND B2 has excess above its target
- **B2 refilled from B3** when B2 < target AND B3 remains above minimum threshold (preserves growth)
- **B1 refilled from B3** only when B2 cannot provide enough AND B3 is healthy
- Safety thresholds prevent over-draining any bucket

**Quick tips**
- Inputs for spending are **monthly** (enter monthly spending).
- Use the **B1 by years of expenses** option to set Bucket 1 initial amount as Yearly Expense × Years.
- Set **target months** for each bucket to control liquidity and income buffers.
- Adjust **refill thresholds** to control how much of each bucket is reserved (e.g., keep 40% in growth).
- Adjust returns, tax rate, and withdrawal escalation to test different scenarios.

Share this summary with others by copying the text above or by exporting the CSV/PDF report.
"""
    )

st.markdown("---")

# -------------------------
# Sidebar or main: Inputs + Unit selector (radio)
# -------------------------
# Choose container based on mobile toggle
inputs_container = st if use_mobile_layout else st.sidebar

with inputs_container:
    st.header("Inputs")

    # Unit selector as radio buttons with Rupee symbol
    st.markdown("**Display units**")
    unit_choice = st.radio(
        "Choose units for display and export",
        options=["₹ (Rupee)", "Lakhs (₹)", "Crores (₹)"],
        index=1
    )
    # Map radio labels to numeric factors and a short label for display
    unit_map = {"₹ (Rupee)": 1.0, "Lakhs (₹)": 1e5, "Crores (₹)": 1e7}
    unit_factor = float(unit_map.get(unit_choice, 1.0))
    # Short label for axis and captions (use symbol for rupee)
    if unit_choice.startswith("₹"):
        unit_label = "₹"
    elif "Lakhs" in unit_choice:
        unit_label = "Lakhs (₹)"
    else:
        unit_label = "Crores (₹)"

    # Age inputs (defaults set to 50)
    current_age = st.number_input("Current age", value=50, min_value=18, max_value=120, step=1)
    start_withdraw_age = st.number_input("Start withdrawals at age", value=50, min_value=18, max_value=120, step=1)

    # core financial inputs (entered in Rs)
    # Default corpus = 5 Crore = 50,000,000
    current_total = st.number_input("Current total retirement corpus (₹)", value=50_000_000.0, step=100_000.0, format="%.2f")
    # Monthly spending input (instead of annual)
    monthly_spend0 = st.number_input("Monthly spending (first month) (₹)", value=100_000.0, step=1_000.0, format="%.2f")

    inflation = st.number_input("Inflation (%)", value=6.0, step=0.1) / 100.0

    st.markdown("**Expected annual returns (%) and Tax (per bucket)**")
    # Defaults: B1=6%, B2=8%, B3=12%
    r1_input = st.number_input("Bucket1 (Liquid) return (%)", value=6.0, step=0.1)
    r2_input = st.number_input("Bucket2 (Income) return (%)", value=8.0, step=0.1)
    r3_input = st.number_input("Bucket3 (Growth) return (%)", value=12.0, step=0.1)
    st.markdown("_Tax rate on returns — specify per bucket_")
    tax1_input = st.number_input("Bucket1 tax rate on returns (%)", value=10.0, step=0.1)
    tax2_input = st.number_input("Bucket2 tax rate on returns (%)", value=10.0, step=0.1)
    tax3_input = st.number_input("Bucket3 tax rate on returns (%)", value=10.0, step=0.1)

    # convert to decimals for internal use
    r1 = r1_input / 100.0
    r2 = r2_input / 100.0
    r3 = r3_input / 100.0
    tax1 = tax1_input / 100.0
    tax2 = tax2_input / 100.0
    tax3 = tax3_input / 100.0

    # -------------------------
    # UNIFIED: Initial allocations & Bucket1 default option
    # -------------------------
    st.markdown("**Initial Bucket Allocations**")
    
    # Toggle: Use B1 default by years or manual input
    allocation_mode = st.radio(
        "Choose allocation method",
        options=["Manual allocation (%)", "B1 by years of expenses"],
        index=0
    )
    
    if allocation_mode == "B1 by years of expenses":
        st.caption("Bucket1 will be set based on years of yearly expense; B2 and B3 will be scaled proportionally.")
        b1_years = st.number_input("B1 buffer (years of yearly expense)", value=3.0, min_value=0.0, step=0.5, format="%.1f")
        a2_input = st.number_input("Bucket2 % (of remaining)", value=40.0, step=1.0)
        a3_input = st.number_input("Bucket3 % (of remaining)", value=40.0, step=1.0)
        use_b1_years = True
        a1_input = 0.0  # Will be computed below
    else:
        st.caption("Manually specify the % allocation for each bucket.")
        a1_input = st.number_input("Bucket1 % (Liquid)", value=20.0, step=1.0)
        a2_input = st.number_input("Bucket2 % (Income)", value=40.0, step=1.0)
        a3_input = st.number_input("Bucket3 % (Growth)", value=40.0, step=1.0)
        use_b1_years = False
        b1_years = 3.0

    years = st.number_input("Projection years", value=30, min_value=1, max_value=100, step=1)
    withdraw_escalation = st.number_input("Annual withdrawal escalation (%)", value=2.5, step=0.1) / 100.0

    st.markdown("**Refill Strategy (Enhanced Cascading)**")
    st.caption("Cascading: B1 ← B2 ← B3 with minimum thresholds to protect long-term growth")
    refill_months_b1 = st.number_input("Bucket1 target months of spending", value=12, min_value=1)
    refill_months_b2 = st.number_input("Bucket2 target months of spending", value=12, min_value=1)
    refill_pct = st.number_input("Refill amount to target (%)", value=100.0, min_value=0.0, max_value=200.0) / 100.0
    
    st.markdown("**Refill Thresholds (% of total portfolio)**")
    st.caption("Minimum % to keep in each bucket to protect portfolio structure")
    b2_min_pct = st.number_input("Bucket2 minimum (% of portfolio)", value=30.0, min_value=5.0, max_value=50.0, step=1.0) / 100.0
    b3_min_pct = st.number_input("Bucket3 minimum (% of portfolio)", value=40.0, min_value=20.0, max_value=70.0, step=1.0) / 100.0

# -------------------------
# Helper utilities
# -------------------------

def roundv(x):
    try:
        return float(np.round(x, 2))
    except Exception:
        return x

# -------------------------
# Compute allocations, applying B1 default if requested
# -------------------------
# Start with user-provided allocation inputs
a1_pct = float(a1_input)
a2_pct = float(a2_input)
a3_pct = float(a3_input)

if use_b1_years:
    # Compute desired B1 amount = yearly expense * years
    yearly_expense = monthly_spend0 * 12.0
    desired_b1_amount = yearly_expense * float(b1_years)
    # Convert to percent of current_total
    desired_a1_pct = (desired_b1_amount / current_total) * 100.0 if current_total > 0 else 0.0
    # Cap to 99% to leave room for other buckets
    desired_a1_pct = min(desired_a1_pct, 99.0)
    a1_pct = desired_a1_pct
    # Scale remaining user inputs (a2_input, a3_input) to fill remaining percent
    remaining_pct = 100.0 - a1_pct
    rem_inputs = a2_input + a3_input
    if rem_inputs <= 0:
        # default split 50/50 of remaining
        a2_pct = remaining_pct * 0.5
        a3_pct = remaining_pct * 0.5
    else:
        a2_pct = (a2_input / rem_inputs) * remaining_pct
        a3_pct = (a3_input / rem_inputs) * remaining_pct

# Normalize to fractions
total_alloc_pct = a1_pct + a2_pct + a3_pct
if total_alloc_pct <= 0:
    a1_pct, a2_pct, a3_pct = 20.0, 40.0, 40.0
    total_alloc_pct = 100.0

a1 = a1_pct / total_alloc_pct
a2 = a2_pct / total_alloc_pct
a3 = a3_pct / total_alloc_pct

# -------------------------
# Enhanced Refill Strategy Function
# -------------------------
def improved_refill_strategy(b1, b2, b3, target_b1, target_b2, refill_pct, year, total_portfolio, b2_min_pct, b3_min_pct):
    """
    Enhanced cascading refill strategy with conditions:
    1. B1 refilled from B2 (if B2 > target_b2 and B2_min threshold)
    2. B2 refilled from B3 (if B3 is healthy, above minimum)
    3. B1 refilled from B3 (only if B2 insufficient and B3 has excess)
    
    Args:
        b1, b2, b3: Current bucket balances
        target_b1, target_b2: Target balances for refill
        refill_pct: Percentage to refill toward target (0-1)
        year: Current year
        total_portfolio: Total portfolio value
        b2_min_pct: Minimum % of portfolio to keep in B2
        b3_min_pct: Minimum % of portfolio to keep in B3
    
    Returns:
        (b1, b2, b3, refill_records)
    """
    
    refill_records = []
    
    # Calculate minimum thresholds
    b2_min_threshold = total_portfolio * b2_min_pct
    b3_min_threshold = total_portfolio * b3_min_pct
    
    # TIER 1: Refill B1 from B2 (preferred, since B2 is for income/near-term)
    if b1 < target_b1:
        needed_b1 = (target_b1 - b1) * refill_pct
        
        # Condition: B2 must have excess above its own target AND minimum threshold
        b2_usable = max(0, b2 - max(target_b2, b2_min_threshold))
        
        take_from_b2 = min(b2_usable, needed_b1)
        
        if take_from_b2 > 0:
            b2 -= take_from_b2
            b1 += take_from_b2
            refill_records.append({
                "Year": year,
                "Source": "Bucket2",
                "Destination": "Bucket1",
                "Amount": roundv(take_from_b2),
                "Reason": "B1←B2 cascade (B2 excess)"
            })
            needed_b1 -= take_from_b2
        
        # TIER 2: Refill B1 from B3 (only if B2 insufficient)
        if needed_b1 > 0:
            # Condition: B3 must stay above minimum threshold (growth protection)
            b3_usable = max(0, b3 - b3_min_threshold)
            
            take_from_b3 = min(b3_usable, needed_b1)
            
            if take_from_b3 > 0:
                b3 -= take_from_b3
                b1 += take_from_b3
                refill_records.append({
                    "Year": year,
                    "Source": "Bucket3",
                    "Destination": "Bucket1",
                    "Amount": roundv(take_from_b3),
                    "Reason": "B1←B3 cascade (B2 insufficient)"
                })
    
    # TIER 3: Refill B2 from B3 (maintain income bucket health)
    if b2 < target_b2:
        needed_b2 = (target_b2 - b2) * refill_pct
        
        # Condition: B3 must remain above minimum threshold
        b3_usable = max(0, b3 - b3_min_threshold)
        
        take_from_b3 = min(b3_usable, needed_b2)
        
        if take_from_b3 > 0:
            b3 -= take_from_b3
            b2 += take_from_b3
            refill_records.append({
                "Year": year,
                "Source": "Bucket3",
                "Destination": "Bucket2",
                "Amount": roundv(take_from_b3),
                "Reason": "B2←B3 cascade (B2 below target)"
            })
    
    return b1, b2, b3, refill_records

# -------------------------
# Simulation function
# -------------------------
def simulate():
    # initialize buckets (inputs are in Rs)
    b1 = current_total * a1
    b2 = current_total * a2
    b3 = current_total * a3
    monthly_spend = monthly_spend0
    target_b1 = monthly_spend * refill_months_b1
    target_b2 = monthly_spend * refill_months_b2

    rows = []
    refill_records = []

    # annual spend derived from monthly input
    annual_spend = monthly_spend * 12.0

    # Effective returns after tax (apply bucket-level tax rates)
    r1_eff = r1 * (1.0 - tax1)
    r2_eff = r2 * (1.0 - tax2)
    r3_eff = r3 * (1.0 - tax3)

    for year in range(0, int(years) + 1):
        age = current_age + year
        total = b1 + b2 + b3
        rows.append({
            "Year": year,
            "Age": int(age),
            "Bucket1": roundv(b1),
            "Bucket2": roundv(b2),
            "Bucket3": roundv(b3),
            "Total": roundv(total),
            "Monthly Spend": roundv(monthly_spend if age >= start_withdraw_age else 0.0),
            "Annual Spend": roundv(annual_spend if age >= start_withdraw_age else 0.0),
            "Withdrawn B1": 0.0,
            "Withdrawn B2": 0.0,
            "Withdrawn B3": 0.0,
            "Refill Reason": ""
        })

        if year == years:
            break

        # Apply returns (annual) using effective (post-tax) returns
        b1 *= (1 + r1_eff)
        b2 *= (1 + r2_eff)
        b3 *= (1 + r3_eff)

        # Escalate spending annually (apply withdrawal escalation)
        if year > 0:
            monthly_spend *= (1 + withdraw_escalation)
            annual_spend = monthly_spend * 12.0

        # Only withdraw if age >= start_withdraw_age
        to_withdraw = annual_spend if (current_age + year) >= start_withdraw_age else 0.0

        # Withdraw from B1 first
        w1 = min(b1, to_withdraw)
        b1 -= w1
        to_withdraw -= w1
        rows[-1]["Withdrawn B1"] = roundv(w1)

        # Enhanced cascading refill strategy
        b1, b2, b3, tier_refills = improved_refill_strategy(
            b1, b2, b3, target_b1, target_b2, refill_pct, year, 
            b1 + b2 + b3, b2_min_pct, b3_min_pct
        )
        
        # Log refill reasons
        if tier_refills:
            reasons = [f"{r['Destination'].split('Bucket')[1]}←{r['Source'].split('Bucket')[1]}" for r in tier_refills]
            rows[-1]["Refill Reason"] = "; ".join(reasons)
            refill_records.extend(tier_refills)

        # If still need to withdraw, take from B2 then B3
        if to_withdraw > 0:
            # Withdraw from B2 first
            take = min(b2, to_withdraw)
            b2 -= take
            to_withdraw -= take
            rows[-1]["Withdrawn B2"] = roundv(rows[-1]["Withdrawn B2"] + take)
            
            # Then from B3
            if to_withdraw > 0:
                take = min(b3, to_withdraw)
                b3 -= take
                to_withdraw -= take
                rows[-1]["Withdrawn B3"] = roundv(rows[-1]["Withdrawn B3"] + take)

        # If still short, show shortfall
        if to_withdraw > 0:
            b1 -= to_withdraw
            rows[-1]["Withdrawn B1"] = roundv(rows[-1]["Withdrawn B1"] + to_withdraw)

    df = pd.DataFrame(rows)
    refill_df = pd.DataFrame(refill_records) if refill_records else pd.DataFrame(columns=["Year", "Source", "Destination", "Amount", "Reason"])
    return df, refill_df

# Run simulation
df, refill_df = simulate()

# -------------------------
# Summary metrics / KPIs (deterministic run)
# -------------------------
# Compute deterministic KPIs: years until depletion, final portfolio, peak year, max drawdown
total_series = df["Total"].astype(float)
ages = df["Age"].astype(int)

# Years until depletion: first year where total <= 0 (consider only years after withdrawals may start)
depletion_rows = df[df["Total"] <= 0]
if not depletion_rows.empty:
    first_depletion_row = depletion_rows.iloc[0]
    depletion_age = int(first_depletion_row["Age"])
    depletion_years_from_now = int(first_depletion_row["Year"])
    depletion_text = f"Age {depletion_age} (in {depletion_years_from_now} yr(s))"
else:
    depletion_age = None
    depletion_text = "No depletion within horizon"

# Final portfolio at horizon
final_total = float(total_series.iloc[-1])
final_total_scaled = roundv(final_total / unit_factor)

# Peak portfolio and peak age
peak_idx = int(total_series.idxmax())
peak_age = int(ages.iloc[peak_idx])
peak_value = float(total_series.iloc[peak_idx])
peak_value_scaled = roundv(peak_value / unit_factor)

# Max drawdown computation
running_max = total_series.cummax()
# avoid division by zero
with np.errstate(divide='ignore', invalid='ignore'):
    drawdowns = (running_max - total_series) / running_max.replace(0, np.nan)
max_drawdown = float(drawdowns.max()) if not drawdowns.empty else 0.0
max_drawdown_pct = roundv(max_drawdown * 100.0)

# Success rate: N/A for deterministic single-run (placeholder for Monte Carlo)
success_rate_text = "N/A (deterministic run)"

# Display KPI row above charts
st.subheader("Summary Metrics")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Years until depletion", depletion_text)
col2.metric(f"Final portfolio ({unit_label})", f"{final_total_scaled:,.2f}")
col3.metric("Peak age", f"{peak_age}")
col4.metric(f"Peak portfolio ({unit_label})", f"{peak_value_scaled:,.2f}")
col5.metric("Max drawdown (%)", f"{max_drawdown_pct:.2f}%")

# Also show success rate as info
st.caption(f"Success rate (Monte Carlo): {success_rate_text}")

# -------------------------
# Prepare display-safe DataFrame and scaled DataFrame (for display/export)
# -------------------------
df_display = df.copy()
# numeric columns to scale: all numeric except Year and Age
num_cols = df_display.select_dtypes(include=[np.number]).columns.tolist()
num_cols_to_scale = [c for c in num_cols if c not in ("Year", "Age")]
# scale numeric columns
df_display[num_cols_to_scale] = df_display[num_cols_to_scale] / unit_factor
df_display[num_cols_to_scale] = df_display[num_cols_to_scale].round(2)

# Rename Bucket columns to B1/B2/B3 for tables/exports
rename_map = {"Bucket1": "B1", "Bucket2": "B2", "Bucket3": "B3"}
df_display = df_display.rename(columns=rename_map)

# Also prepare a scaled DataFrame for CSV export (so CSV matches displayed units)
df_export = df.copy()
df_export[num_cols_to_scale] = df_export[num_cols_to_scale] / unit_factor
df_export[num_cols_to_scale] = df_export[num_cols_to_scale].round(2)
df_export = df_export.rename(columns=rename_map)

# -------------------------
# Display outputs (Total portfolio moved to top, Age on x-axis)
# -------------------------
st.subheader(f"Total Portfolio (in {unit_label})")
# use Age as x-axis and scale
total_by_age = df.set_index("Age")["Total"] / unit_factor
st.line_chart(total_by_age)

st.subheader("Projection Table (includes Age)")
st.caption(f"Monetary values shown in **{unit_label}**. Inputs are entered in ₹.")
# adjust table height for mobile
table_height = 320 if use_mobile_layout else 420
st.dataframe(df_display, height=table_height)

st.subheader("Bucket Composition Over Time")
# use Age as x-axis and scale (use original column names from df)
chart_df = df.set_index("Age")[['Bucket1', 'Bucket2', 'Bucket3']] / unit_factor
# adjust figure size for mobile
stack_figsize = (6, 3) if use_mobile_layout else (9, 4)
fig, ax = plt.subplots(figsize=stack_figsize)
ax.stackplot(chart_df.index, chart_df['Bucket1'], chart_df['Bucket2'], chart_df['Bucket3'],
             labels=["Bucket1 Liquid", "Bucket2 Income", "Bucket3 Growth"],
             colors=["#8dd3c7", "#ffffb3", "#bebada"])
ax.legend(loc="upper left", fontsize=8)
ax.set_ylabel(f"Amount ({unit_label})")
ax.set_xlabel("Age")
st.pyplot(fig)

# -------------------------
# Refill Transfers Visualization (IMPROVED: Stacked bar chart by source)
# -------------------------
st.subheader("Refill Transfers by Source")
if not refill_df.empty:
    # Pivot to show B2 and B3 amounts separately by year and destination
    refill_pivot = refill_df.pivot_table(
        index="Year", columns=["Source", "Destination"], values="Amount", aggfunc="sum"
    ).fillna(0)
    
    # Flatten multi-level columns for easier plotting
    refill_pivot.columns = [f"{dest} from {src}" for src, dest in refill_pivot.columns]
    
    # Scale to unit and convert Year to Age
    refill_pivot = refill_pivot / unit_factor
    refill_pivot.index = refill_pivot.index + current_age  # Convert to Age
    
    bar_figsize = (9, 3) if use_mobile_layout else (11, 4)
    fig, ax = plt.subplots(figsize=bar_figsize)
    refill_pivot.plot(kind="bar", stacked=True, ax=ax,
                      color={"Bucket1 from Bucket2": "#c2e8d4", 
                             "Bucket1 from Bucket3": "#bebada",
                             "Bucket2 from Bucket3": "#ffffb3"})
    ax.set_title(f"Refill Transfers by Source & Destination (in {unit_label})")
    ax.set_xlabel("Age")
    ax.set_ylabel(f"Amount ({unit_label})")
    ax.legend(title="Refill Flow", loc="upper right", fontsize=8)
    plt.xticks(rotation=45 if not use_mobile_layout else 30, ha='right')
    plt.tight_layout()
    st.pyplot(fig)
    
    # Detailed refill table with reasons
    st.markdown("**Refill Details (Year-by-Year with Reasons)**")
    refill_display = refill_df.copy()
    refill_display["Age"] = refill_display["Year"] + current_age
    refill_display["Amount"] = (refill_display["Amount"] / unit_factor).round(2)
    refill_display = refill_display[["Year", "Age", "Destination", "Source", "Amount", "Reason"]]
    refill_display = refill_display.rename(columns={
        "Amount": f"Amount ({unit_label})",
        "Destination": "Refilled To",
        "Source": "Refilled From"
    })
    # adjust refill table height for mobile
    refill_table_height = 220 if use_mobile_layout else 250
    st.dataframe(refill_display, height=refill_table_height)
    
    # Summary stats
    st.markdown("**Refill Summary by Type**")
    summary = refill_df.copy()
    summary["Flow"] = summary["Destination"] + " ← " + summary["Source"]
    summary_stats = summary.groupby("Flow")["Amount"].agg(["sum", "count", "mean"]).round(2)
    summary_stats.columns = [f"Total ({unit_label})", "# of Transfers", f"Avg per Transfer ({unit_label})"]
    summary_stats["Total ({})".format(unit_label)] = (summary_stats["Total ({})".format(unit_label)] / unit_factor).round(2)
    summary_stats["Avg per Transfer ({})".format(unit_label)] = (summary_stats["Avg per Transfer ({})".format(unit_label)] / unit_factor).round(2)
    st.dataframe(summary_stats)
else:
    st.info("No refill transfers recorded — Buckets maintained their targets without needing refills.")

# -------------------------
# Export: CSV and PDF (charts use Age and scaled units)
# -------------------------
st.subheader("Export")
csv_bytes = df_export.to_csv(index=False).encode("utf-8")
# sanitize unit_choice for filename
unit_fname = unit_choice.split()[0].lower().replace("(", "").replace(")", "")
st.download_button(
    f"Download projection CSV ({unit_label})",
    data=csv_bytes,
    file_name=f"retirement_projection_{unit_fname}_{datetime.now().date()}.csv",
    mime="text/csv"
)

def create_pdf_bytes():
    pdf_buf = BytesIO()
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(pdf_buf) as pdf:
        # total portfolio line (Age on x-axis, scaled)
        fig0 = plt.figure(figsize=(8, 3))
        ax0 = fig0.add_subplot(111)
        ax0.plot(df["Age"], df["Total"] / unit_factor, marker="o", color="#377eb8")
        ax0.set_title(f"Total Portfolio Over Time ({unit_label})")
        ax0.set_xlabel("Age")
        ax0.set_ylabel(f"Total ({unit_label})")
        pdf.savefig(fig0)
        plt.close(fig0)

        # stacked area (Age on x-axis, scaled)
        fig1 = plt.figure(figsize=(8, 4))
        ax = fig1.add_subplot(111)
        chart_df_pdf = df.set_index("Age")[['Bucket1', 'Bucket2', 'Bucket3']] / unit_factor
        ax.stackplot(chart_df_pdf.index, chart_df_pdf['Bucket1'], chart_df_pdf['Bucket2'], chart_df_pdf['Bucket3'],
                     labels=["Bucket1", "Bucket2", "Bucket3"], colors=["#8dd3c7", "#ffffb3", "#bebada"])
        ax.legend(loc="upper left")
        ax.set_title("Bucket Composition Over Time")
        ax.set_xlabel("Age")
        ax.set_ylabel(f"Amount ({unit_label})")
        pdf.savefig(fig1)
        plt.close(fig1)

        # refill stacked bar (Age on x-axis, scaled)
        if not refill_df.empty:
            refill_pivot_pdf = refill_df.pivot_table(
                index="Year", columns=["Source", "Destination"], values="Amount", aggfunc="sum"
            ).fillna(0)
            refill_pivot_pdf.columns = [f"{dest} from {src}" for src, dest in refill_pivot_pdf.columns]
            refill_pivot_pdf = refill_pivot_pdf / unit_factor
            refill_pivot_pdf.index = refill_pivot_pdf.index + current_age
            
            fig2 = plt.figure(figsize=(10, 4))
            refill_pivot_pdf.plot(kind="bar", stacked=True, ax=fig2.gca(),
                                  color={"Bucket1 from Bucket2": "#c2e8d4",
                                         "Bucket1 from Bucket3": "#bebada",
                                         "Bucket2 from Bucket3": "#ffffb3"})
            fig2.gca().set_title(f"Refill Transfers by Source & Destination ({unit_label})")
            fig2.gca().set_xlabel("Age")
            fig2.gca().set_ylabel(f"Amount ({unit_label})")
            fig2.gca().legend(title="Refill Flow", fontsize=8, loc="upper right")
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            pdf.savefig(fig2)
            plt.close(fig2)

        # add a simple table page (first 12 rows, scaled)
        fig3 = plt.figure(figsize=(8, 6))
        plt.axis('off')
        sample = df_export.head(12).round(2)
        tbl = plt.table(cellText=sample.values, colLabels=sample.columns, loc='center', cellLoc='center')
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(7)
        pdf.savefig(fig3)
        plt.close(fig3)

    pdf_buf.seek(0)
    return pdf_buf.read()

pdf_bytes = create_pdf_bytes()
st.download_button(
    f"Download PDF report ({unit_label})",
    data=pdf_bytes,
    file_name=f"retirement_report_{unit_fname}_{datetime.now().date()}.pdf",
    mime="application/pdf"
)

st.markdown(f"**Notes:** This simulator displays monetary values in **{unit_label}**. Inputs are entered in ₹; exports and charts reflect the selected unit. Monthly spending is escalated annually. E[...]")
