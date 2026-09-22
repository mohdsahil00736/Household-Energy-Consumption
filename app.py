"""
Household Energy Consumption Analytics Dashboard
=================================================
Purely EDA + Business Metrics — no ML models.
Stack: Streamlit · Pandas · Plotly
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

# ──────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Energy Consumption Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# THEME / COLOUR PALETTE
# ──────────────────────────────────────────────
COLOURS = {
    "kitchen":   "#EF553B",
    "laundry":   "#00CC96",
    "climate":   "#636EFA",
    "other":     "#FFA15A",
    "power":     "#19D3F3",
}

# ──────────────────────────────────────────────
# DATA LOADING (cached so it runs only once)
# ──────────────────────────────────────────────
@st.cache_data(show_spinner="⚡ Loading dataset — this may take a moment on first run…")
def load_data(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(
        filepath,
        sep=";",
        na_values="?",
        low_memory=False,
        dtype={
            "Global_active_power":    "float32",
            "Global_reactive_power":  "float32",
            "Voltage":                "float32",
            "Global_intensity":       "float32",
            "Sub_metering_1":         "float32",
            "Sub_metering_2":         "float32",
            "Sub_metering_3":         "float32",
        },
    )

    # Parse Date + Time into a single DatetimeIndex
    df["Datetime"] = pd.to_datetime(
        df["Date"] + " " + df["Time"], format="%d/%m/%Y %H:%M:%S"
    )
    df.drop(columns=["Date", "Time"], inplace=True)
    df.set_index("Datetime", inplace=True)
    df.sort_index(inplace=True)

    # Drop rows where the key measurement is missing
    df.dropna(subset=["Global_active_power"], inplace=True)

    # Derived column: unmonitored energy (watt-hours per minute → same unit as sub-meterings)
    df["Sub_metering_remainder"] = (
        (df["Global_active_power"] * 1000.0 / 60.0)
        - df["Sub_metering_1"]
        - df["Sub_metering_2"]
        - df["Sub_metering_3"]
    ).clip(lower=0).astype("float32")

    return df


# ──────────────────────────────────────────────
# AGGREGATION HELPER
# ──────────────────────────────────────────────
RESAMPLE_MAP = {"Hourly": "h", "Daily": "D", "Monthly": "ME"}

def resample_df(df: pd.DataFrame, granularity: str) -> pd.DataFrame:
    rule = RESAMPLE_MAP[granularity]
    agg = {
        "Global_active_power":   "mean",
        "Global_reactive_power": "mean",
        "Voltage":               "mean",
        "Global_intensity":      "mean",
        "Sub_metering_1":        "sum",
        "Sub_metering_2":        "sum",
        "Sub_metering_3":        "sum",
        "Sub_metering_remainder":"sum",
    }
    return df.resample(rule).agg(agg).dropna(subset=["Global_active_power"])


# ──────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────
DATA_FILE = "household_power_consumption.txt"

try:
    raw_df = load_data(DATA_FILE)
except FileNotFoundError:
    st.error(
        f"**Dataset not found.**  \n"
        f"Place `{DATA_FILE}` in the same directory as `app.py` and restart."
    )
    st.stop()

# ──────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("⚡ Energy Dashboard")
    st.markdown("---")

    st.subheader("📅 Date Range")
    min_date = raw_df.index.min().date()
    max_date = raw_df.index.max().date()

    start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date)
    end_date   = st.date_input("End date",   value=max_date, min_value=min_date, max_value=max_date)

    if start_date > end_date:
        st.error("Start date must be before end date.")
        st.stop()

    st.markdown("---")
    st.subheader("📊 Aggregation")
    granularity = st.radio("Granularity", ["Hourly", "Daily", "Monthly"], index=1)

    st.markdown("---")
    st.subheader("💰 Electricity Rate")
    rate = st.number_input(
        "Rate (currency / kWh)",
        min_value=0.01,
        max_value=10.0,
        value=0.12,
        step=0.01,
        format="%.3f",
        help="Enter your local electricity tariff per kWh to compute estimated cost.",
    )

    st.markdown("---")
    st.caption(
        "Dataset: UCI *Individual household electric power consumption*  \n"
        "Minute-level readings, Dec 2006 – Nov 2010."
    )

# ──────────────────────────────────────────────
# FILTER DATA
# ──────────────────────────────────────────────
filtered_df = raw_df.loc[str(start_date): str(end_date)]

if filtered_df.empty:
    st.warning("No data available for the selected date range.")
    st.stop()

resampled_df = resample_df(filtered_df, granularity)

# ──────────────────────────────────────────────
# KPI COMPUTATIONS  (from minute-level data for accuracy)
# ──────────────────────────────────────────────
# kWh = kW × (1 min / 60)  → sum over all minutes
total_kwh        = float((filtered_df["Global_active_power"] / 60.0).sum())
peak_power_val   = float(filtered_df["Global_active_power"].max())
peak_power_ts    = filtered_df["Global_active_power"].idxmax()
num_days         = max((filtered_df.index[-1] - filtered_df.index[0]).days, 1)
avg_daily_kwh    = total_kwh / num_days
estimated_cost   = total_kwh * rate

# ──────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📈  Executive Overview",
    "🍩  Appliance Breakdown",
    "🕐  Usage Patterns",
])

# ══════════════════════════════════════════════
# TAB 1 — EXECUTIVE KPI OVERVIEW
# ══════════════════════════════════════════════
with tab1:
    st.header("Executive KPI Overview")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("⚡ Total Energy", f"{total_kwh:,.1f} kWh")
    k2.metric(
        "🔋 Peak Demand",
        f"{peak_power_val:.3f} kW",
        help=f"Occurred at {peak_power_ts.strftime('%Y-%m-%d %H:%M')}",
    )
    k3.metric("📅 Avg Daily Use", f"{avg_daily_kwh:.2f} kWh/day")
    k4.metric("💵 Est. Cost", f"${estimated_cost:,.2f}", help=f"@ ${rate:.3f} / kWh")

    st.caption(f"Peak demand occurred on **{peak_power_ts.strftime('%A, %d %b %Y at %H:%M')}**.")
    st.markdown("---")

    # ── Global Active Power Trend ──────────────────
    st.subheader(f"Global Active Power Trend ({granularity})")

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=resampled_df.index,
        y=resampled_df["Global_active_power"],
        mode="lines",
        name="Active Power (kW)",
        line=dict(color=COLOURS["power"], width=1.5),
        hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Power: %{y:.3f} kW<extra></extra>",
    ))
    fig_trend.update_layout(
        xaxis_title="Date / Time",
        yaxis_title="Active Power (kW)",
        hovermode="x unified",
        height=420,
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#fafafa",
        xaxis=dict(gridcolor="#2a2d35"),
        yaxis=dict(gridcolor="#2a2d35"),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    # ── Voltage trend side-by-side ──────────────────
    with st.expander("🔌 Voltage & Intensity trends"):
        col_v, col_i = st.columns(2)

        fig_volt = px.line(
            resampled_df, y="Voltage",
            title="Average Voltage (V)",
            color_discrete_sequence=["#FECB52"],
            height=300,
        )
        fig_volt.update_layout(
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font_color="#fafafa",
            margin=dict(l=5, r=5, t=40, b=5),
            xaxis=dict(gridcolor="#2a2d35"), yaxis=dict(gridcolor="#2a2d35"),
        )
        col_v.plotly_chart(fig_volt, use_container_width=True)

        fig_int = px.line(
            resampled_df, y="Global_intensity",
            title="Average Current Intensity (A)",
            color_discrete_sequence=["#AB63FA"],
            height=300,
        )
        fig_int.update_layout(
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font_color="#fafafa",
            margin=dict(l=5, r=5, t=40, b=5),
            xaxis=dict(gridcolor="#2a2d35"), yaxis=dict(gridcolor="#2a2d35"),
        )
        col_i.plotly_chart(fig_int, use_container_width=True)


# ══════════════════════════════════════════════
# TAB 2 — APPLIANCE BREAKDOWN
# ══════════════════════════════════════════════
with tab2:
    st.header("Appliance Energy Breakdown")

    # Totals (watt-hours, converted from minute-level sums)
    sm1_total   = float(filtered_df["Sub_metering_1"].sum())
    sm2_total   = float(filtered_df["Sub_metering_2"].sum())
    sm3_total   = float(filtered_df["Sub_metering_3"].sum())
    smr_total   = float(filtered_df["Sub_metering_remainder"].sum())
    grand_total = sm1_total + sm2_total + sm3_total + smr_total or 1.0

    labels  = ["Kitchen", "Laundry", "AC & Water Heating", "Other / Unmetered"]
    values  = [sm1_total, sm2_total, sm3_total, smr_total]
    colours = [COLOURS["kitchen"], COLOURS["laundry"], COLOURS["climate"], COLOURS["other"]]

    col_pie, col_stats = st.columns([1.4, 1])

    with col_pie:
        fig_donut = go.Figure(go.Pie(
            labels=labels,
            values=values,
            hole=0.45,
            marker_colors=colours,
            textinfo="label+percent",
            hovertemplate="%{label}<br>%{value:,.0f} Wh<br>%{percent}<extra></extra>",
        ))
        fig_donut.update_layout(
            title="Share of Total Energy by Zone",
            height=420,
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font_color="#fafafa",
            legend=dict(orientation="v", x=1.0, y=0.5),
            margin=dict(l=10, r=10, t=50, b=10),
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_stats:
        st.markdown("### Zone Totals")
        for lbl, val, col in zip(labels, values, colours):
            pct = val / grand_total * 100
            st.markdown(
                f"<span style='color:{col}; font-weight:600'>{lbl}</span>"
                f"&nbsp;&nbsp;**{val/1000:,.1f} kWh** ({pct:.1f} %)",
                unsafe_allow_html=True,
            )
            st.progress(int(pct))
        st.markdown(f"\n**Grand total:** {grand_total/1000:,.1f} kWh")

    st.markdown("---")

    # ── Stacked Area Chart ──────────────────────────
    st.subheader(f"Sub-metering Over Time ({granularity}) — Stacked Area")

    fig_area = go.Figure()
    area_data = [
        ("Kitchen",            "Sub_metering_1",         COLOURS["kitchen"]),
        ("Laundry",            "Sub_metering_2",         COLOURS["laundry"]),
        ("AC & Water Heating", "Sub_metering_3",         COLOURS["climate"]),
        ("Other / Unmetered",  "Sub_metering_remainder", COLOURS["other"]),
    ]
    for name, col, colour in area_data:
        fig_area.add_trace(go.Scatter(
            x=resampled_df.index,
            y=resampled_df[col],
            mode="lines",
            name=name,
            stackgroup="one",
            line=dict(width=0.5, color=colour),
            fillcolor=colour,
            hovertemplate=f"{name}: %{{y:,.1f}} Wh<extra></extra>",
        ))

    fig_area.update_layout(
        xaxis_title="Date / Time",
        yaxis_title="Energy (Wh)",
        hovermode="x unified",
        height=400,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font_color="#fafafa",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(gridcolor="#2a2d35"),
        yaxis=dict(gridcolor="#2a2d35"),
    )
    st.plotly_chart(fig_area, use_container_width=True)


# ══════════════════════════════════════════════
# TAB 3 — USAGE PATTERNS & PEAK HOURS
# ══════════════════════════════════════════════
with tab3:
    st.header("Usage Patterns & Peak Hours")

    # ── Heatmap: Hour-of-Day × Day-of-Week ─────────
    st.subheader("Hourly Consumption Heatmap (Hour of Day vs. Day of Week)")

    hmap_df = filtered_df[["Global_active_power"]].copy()
    hmap_df["hour"]    = hmap_df.index.hour
    hmap_df["weekday"] = hmap_df.index.day_name()

    DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = (
        hmap_df.groupby(["weekday", "hour"])["Global_active_power"]
        .mean()
        .unstack("hour")
        .reindex(DOW_ORDER)
    )

    fig_heat = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h:02d}:00" for h in pivot.columns],
        y=pivot.index.tolist(),
        colorscale="Plasma",
        colorbar=dict(title="Avg kW"),
        hovertemplate="Day: %{y}<br>Hour: %{x}<br>Avg Power: %{z:.3f} kW<extra></extra>",
    ))
    fig_heat.update_layout(
        xaxis_title="Hour of Day",
        yaxis_title="Day of Week",
        height=380,
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font_color="#fafafa",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown("---")

    # ── Correlation / Scatter ───────────────────────
    st.subheader("Correlation: Active Power vs. Voltage & Current Intensity")

    # Sample for scatter to avoid rendering millions of points
    SCATTER_SAMPLE = 8_000
    scatter_src = (
        filtered_df[["Global_active_power", "Voltage", "Global_intensity"]]
        .dropna()
        .sample(min(SCATTER_SAMPLE, len(filtered_df)), random_state=42)
    )

    col_s1, col_s2 = st.columns(2)

    with col_s1:
        fig_sc1 = px.scatter(
            scatter_src,
            x="Voltage",
            y="Global_active_power",
            title="Active Power vs. Voltage",
            opacity=0.25,
            color_discrete_sequence=[COLOURS["power"]],
            trendline="ols",
            trendline_color_override="#FECB52",
            height=380,
            labels={
                "Voltage": "Voltage (V)",
                "Global_active_power": "Active Power (kW)",
            },
        )
        fig_sc1.update_layout(
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font_color="#fafafa",
            xaxis=dict(gridcolor="#2a2d35"),
            yaxis=dict(gridcolor="#2a2d35"),
            margin=dict(l=5, r=5, t=50, b=5),
        )
        col_s1.plotly_chart(fig_sc1, use_container_width=True)

    with col_s2:
        fig_sc2 = px.scatter(
            scatter_src,
            x="Global_intensity",
            y="Global_active_power",
            title="Active Power vs. Current Intensity",
            opacity=0.25,
            color_discrete_sequence=[COLOURS["climate"]],
            trendline="ols",
            trendline_color_override="#FECB52",
            height=380,
            labels={
                "Global_intensity": "Current Intensity (A)",
                "Global_active_power": "Active Power (kW)",
            },
        )
        fig_sc2.update_layout(
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font_color="#fafafa",
            xaxis=dict(gridcolor="#2a2d35"),
            yaxis=dict(gridcolor="#2a2d35"),
            margin=dict(l=5, r=5, t=50, b=5),
        )
        col_s2.plotly_chart(fig_sc2, use_container_width=True)

    st.markdown("---")

    # ── Numeric Correlation Matrix ──────────────────
    with st.expander("📐 Full Correlation Matrix (numeric heatmap)"):
        corr_cols = [
            "Global_active_power", "Global_reactive_power",
            "Voltage", "Global_intensity",
            "Sub_metering_1", "Sub_metering_2", "Sub_metering_3",
        ]
        corr = (
            filtered_df[corr_cols]
            .sample(min(50_000, len(filtered_df)), random_state=0)
            .corr()
        )
        fig_corr = go.Figure(go.Heatmap(
            z=corr.values,
            x=corr.columns.tolist(),
            y=corr.index.tolist(),
            colorscale="RdBu",
            zmid=0,
            text=np.round(corr.values, 2),
            texttemplate="%{text}",
            colorbar=dict(title="r"),
            hovertemplate="%{y} × %{x}<br>r = %{z:.3f}<extra></extra>",
        ))
        fig_corr.update_layout(
            height=480,
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font_color="#fafafa",
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(fig_corr, use_container_width=True)

# ──────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────
st.markdown(
    "<hr style='border:1px solid #2a2d35; margin-top:40px'>"
    "<p style='text-align:center; color:#57606a; font-size:12px'>"
    "Household Energy Consumption Analytics Dashboard &nbsp;·&nbsp; "
    "Built with Streamlit &amp; Plotly"
    "</p>",
    unsafe_allow_html=True,
)
