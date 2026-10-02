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
sexes = sorted(data["sex"].dropna().astype(str).unique().tolist())

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
if total_climbers:
    average_grade = (
        filtered["avg_grade_numeric"] * filtered["climber_count"]
    ).sum() / total_climbers
else:
    average_grade = 0.0

metric_columns = st.columns(2)
metric_columns[0].metric("Climbers", f"{total_climbers:,}")
metric_columns[1].metric("Average grade", f"{average_grade:.2f}")

st.subheader("Climbers by country and sex")
if filtered.empty:
    st.info("No rows match the selected filters.")
else:
    chart_data = filtered.sort_values("climber_count", ascending=False)
    st.bar_chart(
        chart_data,
        x="country",
        y="climber_count",
        color="sex",
        stack=False,
        height=360,
    )

st.subheader("Country and sex details")
st.dataframe(
    filtered.sort_values(["country", "sex"]).reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
)