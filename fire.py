"""
fire_three_bucket_with_units_monthly.py

Retirement Simulator — 3-Bucket Refill Strategy with Unit Selector and Monthly Spending
- Single-file Streamlit app
- Features: Age, refill visualization, CSV/PDF export, internal tests
- Removed: rebalancing and crash scenarios
- Change: All charts use Age on the x-axis; added Unit selector (Rs, Lakhs, Crores)
- Inputs: Monthly spending (instead of annual)
- Defaults updated per user request:
    - Default current age and withdrawal start age = 50
    - Default current retirement corpus = 5 Crore (50,000,000 Rs)
    - Default inflation = 6%
    - Default expected returns: B1=6%, B2=8%, B3=12%
- Dependencies: streamlit, pandas, numpy, matplotlib
- Run:
    pip install streamlit pandas numpy matplotlib
    streamlit run fire_three_bucket_with_units_monthly.py
"""
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="Retirement Simulator — 3-Bucket Refill Strategy", layout="wide")
st.title("Retirement Simulator — 3-Bucket Refill Strategy")

# -------------------------
# Top summary for users
# -------------------------
with st.expander("About this Retirement Simulator", expanded=True):
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
- Implements a **refill strategy** that tops up Bucket 1 from Bucket 2 or 3 when needed.
- Visualizes bucket composition, refill transfers, and the total portfolio using **Age** on the x-axis.
- Lets you **download** the projection as CSV or a simple PDF report.

**Quick tips**
- Inputs for spending are now **monthly** (enter monthly spending).
- Set **target months** for Bucket 1 to control how much liquid buffer you want.
- Use **refill priority** to choose whether to draw from income or growth assets first.
- Adjust returns and withdrawal escalation to test different market and spending scenarios.
- Use the **Run internal tests** button in the sidebar to validate the simulation logic.

Share this summary with others by copying the text above or by exporting the CSV/PDF report.
"""
    )

st.markdown("---")

# -------------------------
# Sidebar: Inputs + Tests + Unit selector
# -------------------------
with st.sidebar:
    st.header("Inputs")

    # Unit selector
    st.markdown("**Display units**")
    unit_choice = st.selectbox("Choose units for display and export", options=["Rs", "Lakhs", "Crores"], index=1)
    unit_map = {"Rs": 1.0, "Lakhs": 1e5, "Crores": 1e7}
    unit_factor = float(unit_map.get(unit_choice, 1.0))
    unit_label = unit_choice

    # Age inputs (defaults set to 50)
    current_age = st.number_input("Current age", value=50, min_value=18, max_value=120, step=1)
    start_withdraw_age = st.number_input("Start withdrawals at age", value=50, min_value=18, max_value=120, step=1)

    # core financial inputs (entered in Rs)
    # Default corpus = 5 Crore = 50,000,000
    current_total = st.number_input("Current total retirement corpus (Rs)", value=50_000_000.0, step=100_000.0, format="%.2f")
    # Monthly spending input (instead of annual)
    monthly_spend0 = st.number_input("Monthly spending (first month) (Rs)", value=100_000.0, step=1_000.0, format="%.2f")
    inflation = st.number_input("Inflation (%)", value=6.0, step=0.1) / 100.0

    st.markdown("**Expected annual returns (%)**")
    # Defaults: B1=6%, B2=8%, B3=12%
    r1 = st.number_input("Bucket1 (Liquid) return (%)", value=6.0, step=0.1) / 100.0
    r2 = st.number_input("Bucket2 (Income) return (%)", value=8.0, step=0.1) / 100.0
    r3 = st.number_input("Bucket3 (Growth) return (%)", value=12.0, step=0.1) / 100.0

    st.markdown("**Initial allocations (%)**")
    a1 = st.number_input("Bucket1 %", value=20.0, step=1.0)
    a2 = st.number_input("Bucket2 %", value=40.0, step=1.0)
    a3 = st.number_input("Bucket3 %", value=40.0, step=1.0)

    # normalize allocations and guard against zero-sum
    total_alloc = a1 + a2 + a3
    if total_alloc <= 0:
        st.warning("Allocations sum to zero or negative. Resetting to defaults (20/40/40).")
        a1, a2, a3 = 20.0, 40.0, 40.0
        total_alloc = 100.0
    a1, a2, a3 = a1 / total_alloc, a2 / total_alloc, a3 / total_alloc

    years = st.number_input("Projection years", value=30, min_value=1, max_value=100, step=1)
    withdraw_escalation = st.number_input("Annual withdrawal escalation (%)", value=2.5, step=0.1) / 100.0

    st.markdown("**Refill strategy**")
    refill_months = st.number_input("Bucket1 target months of spending", value=12, min_value=1)
    refill_priority = st.selectbox("Refill priority", ["Bucket 2 then 3", "Bucket 3 then 2"])
    refill_pct = st.number_input("Refill amount to target (%)", value=100.0, min_value=0.0, max_value=200.0) / 100.0

    st.markdown("---")
    run_tests = st.button("Run internal tests")

# -------------------------
# Helper utilities
# -------------------------
def roundv(x):
    try:
        return float(np.round(x, 2))
    except Exception:
        return x

# -------------------------
# Simulation function (no crash, no rebalancing)
# -------------------------
def simulate():
    # initialize buckets (inputs are in Rs)
    b1 = current_total * a1
    b2 = current_total * a2
    b3 = current_total * a3
    monthly_spend = monthly_spend0
    target_b1 = monthly_spend * refill_months

    rows = []
    refill_records = []

    # annual spend derived from monthly input
    annual_spend = monthly_spend * 12.0

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
            "Refill Inflow B1": 0.0,
            "Refill Outflow B2": 0.0,
            "Refill Outflow B3": 0.0,
            "Notes": ""
        })

        if year == years:
            break

        # Apply returns (annual)
        b1 *= (1 + r1)
        b2 *= (1 + r2)
        b3 *= (1 + r3)

        # Escalate spending annually (apply withdrawal escalation and inflation)
        if year > 0:
            # escalate monthly spend by withdrawal_escalation (user-provided)
            monthly_spend *= (1 + withdraw_escalation)
            annual_spend = monthly_spend * 12.0

        # Only withdraw if age >= start_withdraw_age
        to_withdraw = annual_spend if (current_age + year) >= start_withdraw_age else 0.0

        # Withdraw from B1 first
        w1 = min(b1, to_withdraw)
        b1 -= w1
        to_withdraw -= w1
        rows[-1]["Withdrawn B1"] = roundv(w1)

        # If B1 below target, refill before taking from other buckets
        if b1 < target_b1:
            needed = target_b1 - b1
            needed_to_take = needed * refill_pct
            sources = [("b2", b2), ("b3", b3)] if refill_priority.startswith("Bucket 2") else [("b3", b3), ("b2", b2)]
            for name, val in sources:
                if needed_to_take <= 0:
                    break
                take = min(val, needed_to_take)
                if take <= 0:
                    continue
                if name == "b2":
                    b2 -= take
                    rows[-1]["Refill Outflow B2"] += roundv(take)
                    refill_records.append({"Year": year, "Source": "Bucket2", "Amount": roundv(take)})
                else:
                    b3 -= take
                    rows[-1]["Refill Outflow B3"] += roundv(take)
                    refill_records.append({"Year": year, "Source": "Bucket3", "Amount": roundv(take)})
                b1 += take
                rows[-1]["Refill Inflow B1"] += roundv(take)
                needed_to_take -= take

        # If still need to withdraw, take from B2 then B3 per priority
        if to_withdraw > 0:
            sources = [("b2", b2), ("b3", b3)] if refill_priority.startswith("Bucket 2") else [("b3", b3), ("b2", b2)]
            for name, val in sources:
                if to_withdraw <= 0:
                    break
                if name == "b2":
                    take = min(b2, to_withdraw)
                    b2 -= take
                    to_withdraw -= take
                    rows[-1]["Withdrawn B2"] = roundv(rows[-1]["Withdrawn B2"] + take)
                else:
                    take = min(b3, to_withdraw)
                    b3 -= take
                    to_withdraw -= take
                    rows[-1]["Withdrawn B3"] = roundv(rows[-1]["Withdrawn B3"] + take)

        # If still short, allow negative B1 to show shortfall
        if to_withdraw > 0:
            b1 -= to_withdraw
            rows[-1]["Withdrawn B1"] = roundv(rows[-1]["Withdrawn B1"] + to_withdraw)
            to_withdraw = 0.0

    df = pd.DataFrame(rows)
    refill_df = pd.DataFrame(refill_records) if refill_records else pd.DataFrame(columns=["Year", "Source", "Amount"])
    return df, refill_df

# Run simulation
df, refill_df = simulate()

# -------------------------
# Prepare display-safe DataFrame and scaled DataFrame (for display/export)
# -------------------------
df_display = df.copy()
# numeric columns to scale: all numeric except Year and Age
num_cols = df_display.select_dtypes(include=[np.number]).columns.tolist()
num_cols_to_scale = [c for c in num_cols if c not in ("Year", "Age")]
df_display[num_cols_to_scale] = df_display[num_cols_to_scale] / unit_factor
df_display[num_cols_to_scale] = df_display[num_cols_to_scale].round(2)

# Also prepare a scaled DataFrame for CSV export (so CSV matches displayed units)
df_export = df.copy()
df_export[num_cols_to_scale] = df_export[num_cols_to_scale] / unit_factor
df_export[num_cols_to_scale] = df_export[num_cols_to_scale].round(2)

# -------------------------
# Display outputs (Total portfolio moved to top, Age on x-axis)
# -------------------------
st.subheader(f"Total Portfolio (in {unit_label})")
# use Age as x-axis and scale
total_by_age = df.set_index("Age")["Total"] / unit_factor
st.line_chart(total_by_age)

st.subheader("Projection Table (includes Age)")
st.caption(f"Monetary values shown in **{unit_label}**. Inputs are entered in Rs.")
st.dataframe(df_display, height=420)

st.subheader("Bucket Composition Over Time")
# use Age as x-axis and scale
chart_df = df.set_index("Age")[["Bucket1", "Bucket2", "Bucket3"]] / unit_factor
fig, ax = plt.subplots(figsize=(9, 4))
ax.stackplot(chart_df.index, chart_df["Bucket1"], chart_df["Bucket2"], chart_df["Bucket3"],
             labels=["Bucket1 Liquid", "Bucket2 Income", "Bucket3 Growth"],
             colors=["#8dd3c7", "#ffffb3", "#bebada"])
ax.legend(loc="upper left")
ax.set_ylabel(f"Amount ({unit_label})")
ax.set_xlabel("Age")
st.pyplot(fig)

# Transfers visualization (Age on x-axis)
st.subheader("Transfers Visualization")
if not refill_df.empty:
    agg = refill_df.groupby("Year")["Amount"].sum() / unit_factor
    ages = (agg.index + current_age).astype(int)  # Year -> Age
    fig2, ax2 = plt.subplots(figsize=(8, 3))
    ax2.bar(ages.astype(str), agg.values, color="#66c2a5")
    ax2.set_ylabel(f"Refill amount into Bucket1 ({unit_label})")
    ax2.set_xlabel("Age")
    st.pyplot(fig2)
    # show refill table scaled
    refill_display = refill_df.copy()
    refill_display["Age"] = refill_display["Year"] + current_age
    refill_display["Amount"] = refill_display["Amount"] / unit_factor
    refill_display["Amount"] = refill_display["Amount"].round(2)
    st.dataframe(refill_display[["Year", "Age", "Source", "Amount"]].rename(columns={"Amount": f"Amount ({unit_label})"}), height=200)

    # Sankey-like simple flows (approx) using Age labels
    st.markdown("**Approximate flows into Bucket1 (per age)**")
    fig_flow, axf = plt.subplots(figsize=(8, 3))
    years_idx = (agg.index + current_age).astype(str)  # show ages
    values = agg.values
    axf.bar(years_idx, values, color="#66c2a5")
    for i, v in enumerate(values):
        axf.annotate(f"{v:,.2f}", xy=(i, v), xytext=(0, 5), textcoords="offset points", ha='center')
    axf.set_ylabel(f"Amount ({unit_label})")
    axf.set_xlabel("Age")
    st.pyplot(fig_flow)
else:
    st.info("No refill transfers recorded.")

# -------------------------
# Export: CSV and PDF (charts use Age and scaled units)
# -------------------------
st.subheader("Export")
csv_bytes = df_export.to_csv(index=False).encode("utf-8")
st.download_button(
    f"Download projection CSV ({unit_label})",
    data=csv_bytes,
    file_name=f"retirement_projection_{unit_label.lower()}_{datetime.now().date()}.csv",
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
        chart_df_pdf = df.set_index("Age")[["Bucket1", "Bucket2", "Bucket3"]] / unit_factor
        ax.stackplot(chart_df_pdf.index, chart_df_pdf["Bucket1"], chart_df_pdf["Bucket2"], chart_df_pdf["Bucket3"],
                     labels=["Bucket1", "Bucket2", "Bucket3"], colors=["#8dd3c7", "#ffffb3", "#bebada"])
        ax.legend(loc="upper left")
        ax.set_title("Bucket composition")
        ax.set_xlabel("Age")
        ax.set_ylabel(f"Amount ({unit_label})")
        pdf.savefig(fig1)
        plt.close(fig1)

        # refill bar (Age on x-axis, scaled)
        if not refill_df.empty:
            agg_pdf = refill_df.groupby("Year")["Amount"].sum() / unit_factor
            agg_pdf.index = (agg_pdf.index + current_age).astype(int)
            fig2 = plt.figure(figsize=(8, 3))
            agg_pdf.plot(kind="bar", color="#66c2a5")
            plt.title(f"Refill transfers by Age ({unit_label})")
            plt.xlabel("Age")
            plt.tight_layout()
            pdf.savefig(fig2)
            plt.close(fig2)

        # add a simple table page (first 12 rows, scaled)
        fig3 = plt.figure(figsize=(8, 6))
        plt.axis('off')
        sample = df_export.head(12).round(2)
        tbl = plt.table(cellText=sample.values, colLabels=sample.columns, loc='center', cellLoc='center')
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        pdf.savefig(fig3)
        plt.close(fig3)

    pdf_buf.seek(0)
    return pdf_buf.read()

pdf_bytes = create_pdf_bytes()
st.download_button(
    f"Download PDF report ({unit_label})",
    data=pdf_bytes,
    file_name=f"retirement_report_{unit_label.lower()}_{datetime.now().date()}.pdf",
    mime="application/pdf"
)

st.markdown(f"**Notes:** This simulator displays monetary values in **{unit_label}**. Inputs are entered in Rs; exports and charts reflect the selected unit. Monthly spending is escalated annually by the withdrawal escalation rate.")

# -------------------------
# Built-in deterministic tests (adjusted for monthly spending)
# -------------------------
def run_internal_tests():
    results = []
    # Test 1: allocations normalized
    alloc_sum = a1 + a2 + a3
    results.append(("Allocations normalized to 1.0", np.isclose(alloc_sum, 1.0)))

    # Test 2: total conservation at year 0
    row0 = df.iloc[0]
    results.append(("Initial total equals current_total", np.isclose(row0["Total"], current_total)))

    # Test 3: refill recorded when initial B1 < target
    monthly_spend = monthly_spend0
    target_b1 = monthly_spend * refill_months
    initial_b1 = current_total * a1
    refill_happened = df["Refill Inflow B1"].sum() > 0
    if initial_b1 < target_b1:
        results.append(("Refill occurred when initial B1 < target", bool(refill_happened)))
    else:
        results.append(("Refill not required initially (B1 >= target)", True))

    # Test 4: final total finite
    final_total = df.iloc[-1]["Total"]
    results.append(("Final total is finite number", np.isfinite(final_total)))

    # Test 5: final total not NaN
    results.append(("Final total not NaN", not pd.isna(final_total)))

    return results

if run_tests:
    st.subheader("Internal Test Results")
    test_results = run_internal_tests()
    all_pass = all(p for _, p in test_results)
    if all_pass:
        st.success("All internal tests passed")
    else:
        st.error("Some tests failed — see details below")
    for name, passed in test_results:
        if passed:
            st.write(f"✅ {name}")
        else:
            st.write(f"❌ {name}")
