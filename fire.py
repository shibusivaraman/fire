"""
fire_three_bucket_patched.py

FIRE 3-Bucket Simulator (patched)
- Single-file Streamlit app
- Features: Age, crash+recovery, refill visualization, rebalancing rules, CSV/PDF export, internal tests
- Fixes: avoids applying numeric format to string columns (resolves ValueError: Unknown format code 'f' for object of type 'str')
- Dependencies: streamlit, pandas, numpy, matplotlib
- Run:
    pip install streamlit pandas numpy matplotlib
    streamlit run fire_three_bucket_patched.py
"""
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="FIRE 3-Bucket Simulator (Patched)", layout="wide")
st.title("FIRE 3-Bucket Strategy Simulator — Patched")

# -------------------------
# Sidebar: Inputs + Tests
# -------------------------
with st.sidebar:
    st.header("Inputs")

    # Age inputs
    current_age = st.number_input("Current age", value=60, min_value=18, max_value=120, step=1)
    start_withdraw_age = st.number_input("Start withdrawals at age", value=60, min_value=18, max_value=120, step=1)

    # core financial inputs
    current_total = st.number_input("Current total retirement corpus", value=1_000_000.0, step=10_000.0, format="%.2f")
    annual_spend0 = st.number_input("Annual spending (first year)", value=40_000.0, step=1_000.0, format="%.2f")
    inflation = st.number_input("Inflation (%)", value=2.5, step=0.1) / 100.0

    st.markdown("**Expected annual returns (%)**")
    r1 = st.number_input("Bucket1 (Liquid)", value=1.0, step=0.1) / 100.0
    r2 = st.number_input("Bucket2 (Income)", value=3.0, step=0.1) / 100.0
    r3 = st.number_input("Bucket3 (Growth)", value=6.0, step=0.1) / 100.0

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

    st.markdown("**Crash scenario**")
    enable_crash = st.checkbox("Enable crash", value=True)
    crash_year = st.number_input("Crash year (relative to start, 0=start)", value=2, min_value=0, max_value=years)
    crash_drop = st.number_input("Crash drop (%)", value=30.0, step=1.0) / 100.0
    recovery_years = st.number_input("Recovery years (linear)", value=5, min_value=0, max_value=30)

    st.markdown("**Refill strategy**")
    refill_months = st.number_input("Bucket1 target months of spending", value=12, min_value=1)
    refill_priority = st.selectbox("Refill priority", ["Bucket 2 then 3", "Bucket 3 then 2"])
    refill_pct = st.number_input("Refill amount to target (%)", value=100.0, min_value=0.0, max_value=200.0) / 100.0

    st.markdown("**Rebalancing**")
    enable_rebal = st.checkbox("Enable rebalancing", value=True)
    rebalance_freq = st.number_input("Rebalance every N years", value=5, min_value=1)
    rebalance_tol = st.number_input("Tolerance (%)", value=10.0, min_value=0.0) / 100.0
    trans_cost = st.number_input("Transaction cost (%) when rebalancing", value=0.2, step=0.1) / 100.0

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
# Simulation function
# -------------------------
def simulate():
    # initialize buckets
    b1 = current_total * a1
    b2 = current_total * a2
    b3 = current_total * a3
    monthly_spend = annual_spend0 / 12.0
    target_b1 = monthly_spend * refill_months

    rows = []
    refill_records = []
    rebal_records = []

    annual_spend = annual_spend0
    orig_b3 = current_total * a3

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
            "Annual Spend": roundv(annual_spend if age >= start_withdraw_age else 0.0),
            "Withdrawn B1": 0.0,
            "Withdrawn B2": 0.0,
            "Withdrawn B3": 0.0,
            "Refill Inflow B1": 0.0,
            "Refill Outflow B2": 0.0,
            "Refill Outflow B3": 0.0,
            "Rebalance Net B1": 0.0,
            "Rebalance Net B2": 0.0,
            "Rebalance Net B3": 0.0,
            "Notes": ""
        })

        if year == years:
            break

        # Crash at start of crash_year
        if enable_crash and year == crash_year:
            drop_amt = b3 * crash_drop
            b3 -= drop_amt
            recovery_per_year = (orig_b3 * crash_drop) / max(1, recovery_years)
            rows[-1]["Notes"] += f"Crash applied: -{roundv(drop_amt)}; "
        else:
            recovery_per_year = 0.0

        # Apply returns
        b1 *= (1 + r1)
        b2 *= (1 + r2)
        b3 *= (1 + r3)

        # Add recovery if in window
        if enable_crash and recovery_years > 0 and crash_year < year <= crash_year + recovery_years:
            b3 += recovery_per_year

        # Escalate spending (apply withdrawal escalation)
        if year > 0:
            annual_spend *= (1 + withdraw_escalation)

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

        # Rebalancing at scheduled years
        if enable_rebal and (year % rebalance_freq == 0) and year > 0:
            total_now = b1 + b2 + b3
            if total_now <= 0:
                rows[-1]["Notes"] += "Total depleted; no rebalance. "
            else:
                targ = np.array([a1, a2, a3]) * total_now
                cur = np.array([b1, b2, b3])
                with np.errstate(divide='ignore', invalid='ignore'):
                    dev = np.abs(cur - targ) / np.where(targ != 0, targ, 1.0)
                if np.any(dev > rebalance_tol):
                    new_b1, new_b2, new_b3 = targ
                    moved_amount = np.sum(np.abs(np.array([new_b1, new_b2, new_b3]) - cur)) / 2.0
                    cost = moved_amount * trans_cost
                    # apply new balances
                    b1, b2, b3 = new_b1, new_b2, new_b3
                    # deduct cost proportionally from buckets
                    total_after = b1 + b2 + b3
                    if total_after > 0 and cost > 0:
                        prop = np.array([b1, b2, b3]) / total_after
                        b1 -= cost * prop[0]
                        b2 -= cost * prop[1]
                        b3 -= cost * prop[2]
                    rows[-1]["Rebalance Net B1"] = roundv(b1 - cur[0])
                    rows[-1]["Rebalance Net B2"] = roundv(b2 - cur[1])
                    rows[-1]["Rebalance Net B3"] = roundv(b3 - cur[2])
                    rebal_records.append({
                        "Year": year,
                        "From/To": "Rebalanced to target",
                        "Net B1": roundv(rows[-1]["Rebalance Net B1"]),
                        "Net B2": roundv(rows[-1]["Rebalance Net B2"]),
                        "Net B3": roundv(rows[-1]["Rebalance Net B3"]),
                        "Transaction Cost": roundv(cost)
                    })
                    rows[-1]["Notes"] += f"Rebalanced; cost {roundv(cost)}. "

    df = pd.DataFrame(rows)
    refill_df = pd.DataFrame(refill_records) if refill_records else pd.DataFrame(columns=["Year", "Source", "Amount"])
    rebal_df = pd.DataFrame(rebal_records) if rebal_records else pd.DataFrame(columns=["Year", "From/To", "Net B1", "Net B2", "Net B3", "Transaction Cost"])
    return df, refill_df, rebal_df

# Run simulation
df, refill_df, rebal_df = simulate()

# -------------------------
# Prepare display-safe DataFrame (patch for formatting error)
# -------------------------
df_display = df.copy()
# Round numeric columns only to avoid applying numeric format to strings
num_cols = df_display.select_dtypes(include=[np.number]).columns
df_display[num_cols] = df_display[num_cols].round(2)

# -------------------------
# Display outputs
# -------------------------
st.subheader("Projection Table (includes Age)")
st.dataframe(df_display, height=360)

st.subheader("Bucket Composition Over Time")
chart_df = df.set_index("Year")[["Bucket1", "Bucket2", "Bucket3"]]
fig, ax = plt.subplots(figsize=(9, 4))
ax.stackplot(chart_df.index, chart_df["Bucket1"], chart_df["Bucket2"], chart_df["Bucket3"],
             labels=["Bucket1 Liquid", "Bucket2 Income", "Bucket3 Growth"],
             colors=["#8dd3c7", "#ffffb3", "#bebada"])
ax.legend(loc="upper left")
ax.set_ylabel("Amount")
ax.set_xlabel("Year")
st.pyplot(fig)

st.subheader("Total Portfolio")
st.line_chart(df.set_index("Year")["Total"])

# Transfers visualization
st.subheader("Transfers Visualization")
transfer_choice = st.selectbox("Show transfers", ["Refill transfers", "Rebalancing summary"])
if transfer_choice == "Refill transfers":
    if not refill_df.empty:
        agg = refill_df.groupby("Year")["Amount"].sum()
        fig2, ax2 = plt.subplots(figsize=(8, 3))
        agg.plot(kind="bar", ax=ax2, color="#66c2a5")
        ax2.set_ylabel("Refill amount into Bucket1")
        ax2.set_xlabel("Year")
        st.pyplot(fig2)
        st.dataframe(refill_df, height=200)
        # Sankey-like simple flows (approx)
        st.markdown("**Approximate flows into Bucket1 (per year)**")
        fig_flow, axf = plt.subplots(figsize=(8, 3))
        years_idx = agg.index.astype(str)
        values = agg.values
        axf.bar(years_idx, values, color="#66c2a5")
        for i, v in enumerate(values):
            axf.annotate(f"{v:,.0f}", xy=(i, v), xytext=(0, 5), textcoords="offset points", ha='center')
        axf.set_ylabel("Amount")
        axf.set_xlabel("Year")
        st.pyplot(fig_flow)
    else:
        st.info("No refill transfers recorded.")
else:
    if not rebal_df.empty:
        st.dataframe(rebal_df, height=200)
        fig3, ax3 = plt.subplots(figsize=(6, 2))
        ax3.bar(rebal_df["Year"].astype(str), rebal_df["Transaction Cost"], color="#fc8d62")
        ax3.set_ylabel("Transaction Cost")
        ax3.set_xlabel("Year")
        st.pyplot(fig3)
    else:
        st.info("No rebalancing events recorded.")

# -------------------------
# Export: CSV and PDF
# -------------------------
st.subheader("Export")
csv_bytes = df.to_csv(index=False).encode("utf-8")
st.download_button("Download projection CSV", data=csv_bytes, file_name=f"fire_projection_{datetime.now().date()}.csv", mime="text/csv")

def create_pdf_bytes():
    pdf_buf = BytesIO()
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(pdf_buf) as pdf:
        # stacked area
        fig1 = plt.figure(figsize=(8, 4))
        ax = fig1.add_subplot(111)
        ax.stackplot(chart_df.index, chart_df["Bucket1"], chart_df["Bucket2"], chart_df["Bucket3"],
                     labels=["Bucket1", "Bucket2", "Bucket3"], colors=["#8dd3c7", "#ffffb3", "#bebada"])
        ax.legend(loc="upper left")
        ax.set_title("Bucket composition")
        pdf.savefig(fig1)
        plt.close(fig1)

        # refill bar
        if not refill_df.empty:
            fig2 = plt.figure(figsize=(8, 3))
            refill_df.groupby("Year")["Amount"].sum().plot(kind="bar", color="#66c2a5")
            plt.title("Refill transfers by year")
            plt.tight_layout()
            pdf.savefig(fig2)
            plt.close(fig2)

        # add a simple table page (first 12 rows)
        fig3 = plt.figure(figsize=(8, 6))
        plt.axis('off')
        sample = df.head(12).round(2)
        tbl = plt.table(cellText=sample.values, colLabels=sample.columns, loc='center', cellLoc='center')
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        pdf.savefig(fig3)
        plt.close(fig3)

    pdf_buf.seek(0)
    return pdf_buf.read()

pdf_bytes = create_pdf_bytes()
st.download_button("Download PDF report", data=pdf_bytes, file_name=f"fire_report_{datetime.now().date()}.pdf", mime="application/pdf")

st.markdown("**Notes:** Age is used to determine when withdrawals start. Model uses annual steps and a simple linear crash recovery.")

# -------------------------
# Built-in deterministic tests
# -------------------------
def run_internal_tests():
    results = []
    # Test 1: allocations normalized
    alloc_sum = a1 + a2 + a3
    results.append(("Allocations normalized to 1.0", np.isclose(alloc_sum, 1.0)))

    # Test 2: total conservation at year 0
    row0 = df.iloc[0]
    results.append(("Initial total equals current_total", np.isclose(row0["Total"], current_total)))

    # Test 3: crash applied when enabled
    if enable_crash and crash_year <= years:
        crash_note_present = any("Crash applied" in str(n) for n in df.loc[df["Year"] == crash_year, "Notes"].astype(str))
        results.append(("Crash applied at crash_year", bool(crash_note_present)))
    else:
        results.append(("Crash disabled or out of range", True))

    # Test 4: refill recorded when initial B1 < target
    monthly_spend = annual_spend0 / 12.0
    target_b1 = monthly_spend * refill_months
    initial_b1 = current_total * a1
    refill_happened = df["Refill Inflow B1"].sum() > 0
    if initial_b1 < target_b1:
        results.append(("Refill occurred when initial B1 < target", bool(refill_happened)))
    else:
        results.append(("Refill not required initially (B1 >= target)", True))

    # Test 5: rebalancing events recorded when enabled
    if enable_rebal and rebalance_freq <= years:
        rebal_events = len(rebal_df) > 0
        results.append(("Rebalancing events recorded when enabled", bool(rebal_events)))
    else:
        results.append(("Rebalancing disabled or out of range", True))

    # Test 6: final total finite
    final_total = df.iloc[-1]["Total"]
    results.append(("Final total is finite number", np.isfinite(final_total)))

    # Test 7: final total not NaN
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

