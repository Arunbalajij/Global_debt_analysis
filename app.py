import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import seaborn as sns
from sqlalchemy import create_engine
import streamlit as st

# ==========================================================
# 1. PAGE CONFIG & MYSQL CONNECTION
# ==========================================================
st.set_page_config(
    page_title="World Bank International Debt Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_engine():
    DB_USER = "root"
    DB_PASS = "root"  # <-- Replace with your MySQL password
    DB_HOST = "localhost"
    DB_PORT = "3306"
    DB_NAME = "world_bank_ids"
    return create_engine(
        f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )


engine = get_engine()


# ==========================================================
# 2. CACHED SQL DATA LOADERS
# ==========================================================
@st.cache_data(ttl=600)
def load_countries():
    query = """
    SELECT country_code, short_name, region, income_group, lending_category, currency_unit
    FROM countries
    ORDER BY short_name;
    """
    return pd.read_sql(query, con=engine)


@st.cache_data(ttl=600)
def load_indicators():
    query = """
    SELECT series_code, indicator_name, topic, long_definition
    FROM indicators
    ORDER BY indicator_name;
    """
    return pd.read_sql(query, con=engine)


@st.cache_data(ttl=600)
def load_debt_by_indicator(series_code):
    query = f"""
    SELECT 
        d.country_code,
        c.short_name AS country,
        c.region,
        c.income_group,
        c.lending_category,
        d.year,
        d.debt_value
    FROM debt_data d
    JOIN countries c ON d.country_code = c.country_code
    WHERE d.series_code = '{series_code}'
      AND d.year <= 2024;
    """
    return pd.read_sql(query, con=engine)


@st.cache_data(ttl=600)
def load_country_profile(country_code):
    query = f"""
    SELECT 
        d.series_code,
        i.indicator_name,
        i.topic,
        d.year,
        d.debt_value
    FROM debt_data d
    JOIN indicators i ON d.series_code = i.series_code
    WHERE d.country_code = '{country_code}'
      AND d.year <= 2024;
    """
    return pd.read_sql(query, con=engine)


df_countries = load_countries()
df_indicators = load_indicators()

# ==========================================================
# 3. SIDEBAR FILTERS
# ==========================================================
st.sidebar.title("🌍 Debt Analytics Controls")

# Default to Total External Debt Stocks (DT.DOD.DECT.CD)
default_ind_idx = 0
if "DT.DOD.DECT.CD" in df_indicators["series_code"].values:
    default_ind_idx = int(
        df_indicators[df_indicators["series_code"] == "DT.DOD.DECT.CD"].index[0]
    )

selected_indicator_name = st.sidebar.selectbox(
    "Select Debt Indicator",
    options=df_indicators["indicator_name"],
    index=default_ind_idx,
)
selected_series_code = df_indicators.loc[
    df_indicators["indicator_name"] == selected_indicator_name, "series_code"
].values[0]

selected_year = st.sidebar.slider(
    "Select Analysis Year", min_value=2000, max_value=2024, value=2023
)

regions = ["All Regions"] + sorted(
    df_countries["region"].dropna().unique().tolist()
)
selected_region = st.sidebar.selectbox("Filter by Region", options=regions)

# Load filtered indicator dataset from MySQL
df_ind_data = load_debt_by_indicator(selected_series_code)
if selected_region != "All Regions":
    df_ind_data = df_ind_data[df_ind_data["region"] == selected_region]

# ==========================================================
# 4. HEADER & KPI SUMMARY CARDS
# ==========================================================
st.title("📊 International Debt Statistics — SQL Visual Dashboard")
st.caption(
    f"**Indicator:** {selected_indicator_name} (`{selected_series_code}`) | **Year:** {selected_year}"
)

df_year = df_ind_data[df_ind_data["year"] == selected_year].copy()

col1, col2, col3, col4 = st.columns(4)
total_val = df_year["debt_value"].sum()
avg_val = df_year["debt_value"].mean()
top_country = (
    df_year.sort_values("debt_value", ascending=False).iloc[0]["country"]
    if not df_year.empty
    else "N/A"
)
active_countries = df_year["country_code"].nunique()

col1.metric("Aggregate Indicator Total", f"{total_val:,.2f}")
col2.metric(
    "Country Average", f"{avg_val:,.2f}" if pd.notna(avg_val) else "N/A"
)
col3.metric("Highest Country", top_country)
col4.metric("Reporting Countries", f"{active_countries}")

st.divider()

# ==========================================================
# 5. TABS: INDICATOR-WISE VS. COUNTRY-WISE ANALYSIS
# ==========================================================
tab1, tab2 = st.tabs(
    ["📈 Indicator & Regional Analysis (Plotly)", "🏳️ Country-Wise Deep Dive"]
)

# --- TAB 1: INDICATOR & REGIONAL VISUALS (PLOTLY) ---
with tab1:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader(f"Top 10 Countries ({selected_year})")
        top10 = df_year.sort_values("debt_value", ascending=False).head(10)
        fig_bar = px.bar(
            top10,
            x="debt_value",
            y="country",
            color="region",
            orientation="h",
            labels={
                "debt_value": selected_indicator_name,
                "country": "Country",
            },
            template="plotly_white",
        )
        fig_bar.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_bar, use_container_width=True)

    with c2:
        st.subheader(f"Share by Region & Income Group ({selected_year})")
        fig_sun = px.sunburst(
            df_year.dropna(subset=["region", "income_group", "debt_value"]),
            path=["region", "income_group"],
            values="debt_value",
            color="region",
            template="plotly_white",
        )
        st.plotly_chart(fig_sun, use_container_width=True)

    st.subheader("Historical Trend (2000–2024) — Top 5 Countries")
    top5_codes = (
        df_year.sort_values("debt_value", ascending=False)
        .head(5)["country_code"]
        .tolist()
    )
    df_trend = df_ind_data[df_ind_data["country_code"].isin(top5_codes)]
    fig_line = px.line(
        df_trend,
        x="year",
        y="debt_value",
        color="country",
        markers=True,
        labels={"year": "Year", "debt_value": selected_indicator_name},
        template="plotly_white",
    )
    st.plotly_chart(fig_line, use_container_width=True)

# --- TAB 2: COUNTRY-WISE DEEP DIVE (PLOTLY + SEABORN) ---
with tab2:
    selected_country = st.selectbox(
        "Choose a Country for Multi-Indicator Breakdown",
        options=df_countries["short_name"],
        index=(
            int(df_countries[df_countries["country_code"] == "IND"].index[0])
            if "IND" in df_countries["country_code"].values
            else 0
        ),
    )
    c_code = df_countries.loc[
        df_countries["short_name"] == selected_country, "country_code"
    ].values[0]
    df_c_data = load_country_profile(c_code)

    left, right = st.columns(2)

    with left:
        st.subheader(f"{selected_country}: Debt Stock vs. Debt Service")
        comp_codes = ["DT.DOD.DECT.CD", "DT.TDS.DECT.CD"]
        df_comp = df_c_data[df_c_data["series_code"].isin(comp_codes)]
        fig_comp = px.area(
            df_comp,
            x="year",
            y="debt_value",
            color="indicator_name",
            labels={"year": "Year", "debt_value": "USD (Current)"},
            template="plotly_white",
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    with right:
        st.subheader(f"{selected_country}: New Debt Commitment Terms (Seaborn)")
        term_codes = ["DT.INR.DPPG", "DT.GPA.DPPG", "DT.MAT.DPPG"]
        df_terms = df_c_data[df_c_data["series_code"].isin(term_codes)].pivot(
            index="year", columns="series_code", values="debt_value"
        )

        if not df_terms.empty:
            fig_sns, ax = plt.subplots(figsize=(7, 4.2))
            sns.lineplot(data=df_terms, markers=True, ax=ax)
            ax.set_title(
                f"Interest Rate (%), Grace Period & Maturity (Yrs) — {selected_country}"
            )
            ax.set_ylabel("Value (% or Years)")
            ax.set_xlabel("Year")
            ax.grid(True, linestyle="--", alpha=0.5)
            st.pyplot(fig_sns)
        else:
            st.info(
                "No commitment term records available for the selected country."
            )