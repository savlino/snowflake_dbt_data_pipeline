import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session


st.set_page_config(page_title="Climber statistics", layout="wide")
st.title("Climber country and sex statistics")

try:
    session = get_active_session()
    data = session.sql(
        """
        SELECT
            COUNTRY,
            SEX,
            CLIMBER_COUNT,
            AVG_AGE,
            AVG_GRADE_NUMERIC,
            MEDIAN_HEIGHT,
            MAX_GRADE_NUMERIC,
            MAX_GRADE_LABEL,
            MAX_GRADE_CLIMBER_COUNT
        FROM CLIMBERS_DB.ANALYTICS.CLIMBER_COUNTRY_SEX_STATS
        """
    ).to_pandas()
except Exception:
    st.error("Could not read the analytics mart. Check app access to the warehouse and table.")
    st.stop()

data.columns = data.columns.str.lower()
countries = sorted(data["country"].dropna().astype(str).unique().tolist())
available_sexes = set(data["sex"].dropna().astype(str).unique().tolist())
sexes = [sex for sex in ("M", "F") if sex in available_sexes]
sexes.extend(sorted(available_sexes - set(sexes)))

with st.sidebar:
    st.header("Filters")
    selected_countries = st.multiselect(
        "Country", options=countries, default=countries
    )
    selected_sexes = st.multiselect("Sex", options=sexes, default=sexes)

filtered = data.loc[
    data["country"].isin(selected_countries)
    & data["sex"].isin(selected_sexes)
].copy()

total_climbers = int(filtered["climber_count"].sum())
num_countries = filtered["country"].nunique()

metric_columns = st.columns(2)
metric_columns[0].metric("Climbers", f"{total_climbers:,}")
metric_columns[1].metric("Countries", f"{num_countries:,}")

st.subheader("Climbers by country and sex")
if filtered.empty:
    st.info("No rows match the selected filters.")
else:
    chart_sexes = [sex for sex in sexes if sex in selected_sexes]
    chart_data = filtered.pivot_table(
        index="country",
        columns="sex",
        values="climber_count",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=chart_sexes, fill_value=0)
    chart_data = chart_data.reset_index()
    country_totals = data.groupby("country")["climber_count"].sum()
    chart_data["country_total"] = chart_data["country"].map(country_totals)
    chart_colors = [
        {"M": "#0072B2", "F": "#D55E00"}.get(sex, "#666666")
        for sex in chart_sexes
    ]
    st.bar_chart(
        chart_data,
        x="country",
        y=chart_sexes,
        color=chart_colors,
        horizontal=True,
        stack=False,
        sort="-country_total",
        height=360,
    )

st.subheader("Country and sex details")
table_data = filtered.copy()
table_data["sex"] = pd.Categorical(table_data["sex"], categories=sexes, ordered=True)
st.dataframe(
    table_data.sort_values(["country", "sex"]).reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
)