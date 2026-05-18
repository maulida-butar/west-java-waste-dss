import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import matplotlib.pyplot as plt
import seaborn as sns
import os
import io
from dotenv import load_dotenv

# ==========================
# Initialization & Setup
# ==========================
load_dotenv()
MAPBOX_API_KEY = os.getenv("MAPBOX_API_KEY")

# Mengatur Mapbox API key secara global untuk pydeck
if MAPBOX_API_KEY:
    pdk.settings.mapbox_api_key = MAPBOX_API_KEY

st.set_page_config(layout="wide", page_title="DSS Dashboard Paper-Ready")

if not MAPBOX_API_KEY:
    st.warning("Mapbox token not found. Set MAPBOX_API_KEY in your .env file to enable map visualizations.")

st.title("Decision Support System for Waste Management Prioritization")

# ==========================
# Sidebar: Criteria Weights
# ==========================
st.sidebar.header("Adjust Criteria Weights")
w1 = st.sidebar.slider("Waste Generation (Benefit)", 0.0, 1.0, 0.35)
w2 = st.sidebar.slider("Unmanaged Waste (Benefit)", 0.0, 1.0, 0.30)
w3 = st.sidebar.slider("Recycling Rate (Cost)", 0.0, 1.0, 0.20)
w4 = st.sidebar.slider("Landfill Score (Benefit)", 0.0, 1.0, 0.15)

total_w = w1 + w2 + w3 + w4

if total_w == 0:
    st.sidebar.error("At least one criterion weight must be greater than zero.")
    st.stop()

weights = {
    "Timbulan_Sampah": w1 / total_w,
    "Unmanaged_Waste": w2 / total_w,
    "Recycling_Rate": w3 / total_w,
    "Landfill_Score": w4 / total_w
}

# ==========================
# Helper Functions
# ==========================
def clean_numeric(series):
    def parse_value(x):
        if pd.isna(x):
            return np.nan

        x = str(x).lower()
        x = x.replace("tpd", "").replace("ton", "").replace("%", "").strip()

        # Indonesian format: 1.128,50
        if "," in x and "." in x:
            x = x.replace(".", "").replace(",", ".")
        # Indonesian decimal: 99,97
        elif "," in x:
            x = x.replace(",", ".")
        # Standard decimal: 12.5 remains 12.5
        # Thousands format: 1.128 is ambiguous, assume Indonesian thousands only if 3 digits after dot
        elif "." in x:
            parts = x.split(".")
            if len(parts[-1]) == 3 and len(parts) > 1:
                x = x.replace(".", "")

        return pd.to_numeric(x, errors="coerce")

    return series.apply(parse_value)

def fig_to_png_bytes(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=300, bbox_inches="tight")
    buffer.seek(0)
    return buffer

# ==========================
# File Uploads
# ==========================
col_file1, col_file2 = st.columns(2)
with col_file1:
    dss_file = st.file_uploader("Upload CSV DSS (raw SIPSN data)", type="csv")
with col_file2:
    coords_file = st.file_uploader("Upload coordinates CSV", type="csv")

if dss_file and coords_file:
    # ---------------------------------------------------------
    # 1. Read & Validate Main Dataset
    # ---------------------------------------------------------
    df = pd.read_csv(dss_file)
    df.columns = df.columns.str.strip().str.replace(" ", "_").str.replace("%", "Pct").str.replace("/", "_").str.replace("-", "_")
    
    required_cols = [
        "Kabupaten_Kota",
        "Provinsi",
        "Tahun",
        "Timbulan_Sampah_Tahunan_ton",
        "PctSampah_Terkelola",
        "Recycling_Rate",
        "Landfill_Type"
    ]
    
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        st.error(f"Missing required columns in dataset: {missing}")
        st.stop()
        
    df["Kabupaten_Kota"] = df["Kabupaten_Kota"].astype(str).str.strip().str.title()

    # ---------------------------------------------------------
    # 2. Read & Validate Coordinate Dataset
    # ---------------------------------------------------------
    df_coords = pd.read_csv(coords_file)
    df_coords.columns = df_coords.columns.str.strip().str.replace(" ", "_")
    
    coord_required_cols = ["Kabupaten_Kota", "lat", "lon"]
    coord_missing = [col for col in coord_required_cols if col not in df_coords.columns]

    if coord_missing:
        st.error(f"Missing required columns in coordinates dataset: {coord_missing}")
        st.stop()

    df_coords["Kabupaten_Kota"] = df_coords["Kabupaten_Kota"].astype(str).str.strip().str.title()
    df_coords["lat"] = pd.to_numeric(df_coords["lat"], errors="coerce")
    df_coords["lon"] = pd.to_numeric(df_coords["lon"], errors="coerce")
    df_coords = df_coords.dropna(subset=["lat", "lon"])

    # ---------------------------------------------------------
    # 3. Filter Province & Year
    # ---------------------------------------------------------
    provinsi_terpilih = st.selectbox("Select Province", df["Provinsi"].dropna().unique())
    tahun_terpilih = st.selectbox("Select Year", sorted(df["Tahun"].dropna().unique(), reverse=True))
    
    df_year = df[(df["Provinsi"] == provinsi_terpilih) & (df["Tahun"] == tahun_terpilih)].copy()

    if df_year.empty:
        st.error("No data available for the selected province and year.")
        st.stop()

    # Apply robust numeric cleaning
    df_year["Timbulan_Sampah_Tahunan_ton"] = clean_numeric(df_year["Timbulan_Sampah_Tahunan_ton"])
    df_year["PctSampah_Terkelola"] = clean_numeric(df_year["PctSampah_Terkelola"]).clip(0, 100)
    df_year["Recycling_Rate"] = clean_numeric(df_year["Recycling_Rate"]).clip(0, 100)

    # Check for unparsed numeric values
    numeric_cols = [
        "Timbulan_Sampah_Tahunan_ton",
        "PctSampah_Terkelola",
        "Recycling_Rate"
    ]
    if df_year[numeric_cols].isna().any().any():
        st.warning("Some numeric values could not be parsed and will be excluded from SAW calculation.")
        df_year = df_year.dropna(subset=numeric_cols)

    if df_year.empty:
        st.error("No valid data remains after numeric cleaning.")
        st.stop()

    # ---------------------------------------------------------
    # 4. Methodological Setup
    # ---------------------------------------------------------
    df_year["Unmanaged_Waste"] = 100 - df_year["PctSampah_Terkelola"]
    
    # Robust Landfill Scoring
    df_year["Landfill_Type_Clean"] = df_year["Landfill_Type"].astype(str).str.strip().str.lower()
    
    landfill_map = {
        "sanitary landfill": 1,
        "sanitary": 1,
        "controlled landfill": 2,
        "controlled": 2,
        "open dumping": 3,
        "open dump": 3,
        "opendumping": 3
    }
    
    df_year["Landfill_Score"] = df_year["Landfill_Type_Clean"].map(landfill_map)
    
    if df_year["Landfill_Score"].isna().any():
        unknown_types = df_year.loc[df_year["Landfill_Score"].isna(), "Landfill_Type"].unique()
        st.warning(f"Unknown landfill types detected: {unknown_types}. They will be excluded from SAW calculation.")
        df_year = df_year.dropna(subset=["Landfill_Score"])
        
    if df_year.empty:
        st.error("No valid data remains after landfill type validation.")
        st.stop()

    # ---------------------------------------------------------
    # 5. Normalize Criteria (Internal SAW logic)
    # ---------------------------------------------------------
    def normalize_benefit(s): return (s - s.min()) / (s.max() - s.min() + 1e-9)
    def normalize_cost(s): return (s.max() - s) / (s.max() - s.min() + 1e-9)

    df_year["Norm_Timbulan"] = normalize_benefit(df_year["Timbulan_Sampah_Tahunan_ton"])
    df_year["Norm_Unmanaged"] = normalize_benefit(df_year["Unmanaged_Waste"])
    df_year["Norm_Recycling"] = normalize_cost(df_year["Recycling_Rate"]) # Cost criterion
    df_year["Norm_Landfill"] = normalize_benefit(df_year["Landfill_Score"])

    # ---------------------------------------------------------
    # 6. Calculate Final SAW Score
    # ---------------------------------------------------------
    df_year["SAW_Score"] = (
        (df_year["Norm_Timbulan"] * weights["Timbulan_Sampah"]) +
        (df_year["Norm_Unmanaged"] * weights["Unmanaged_Waste"]) +
        (df_year["Norm_Recycling"] * weights["Recycling_Rate"]) +
        (df_year["Norm_Landfill"] * weights["Landfill_Score"])
    )

    # ---------------------------------------------------------
    # 7. Classify Priority & Generate Recommendations
    # ---------------------------------------------------------
    def classify_priority(s):
        if s >= 0.67: return "High Priority"
        elif s >= 0.34: return "Medium Priority"
        else: return "Low Priority"
    df_year["Priority_Level"] = df_year["SAW_Score"].apply(classify_priority)

    waste_q75 = df_year["Timbulan_Sampah_Tahunan_ton"].quantile(0.75)
    unmanaged_q75 = df_year["Unmanaged_Waste"].quantile(0.75)
    
    def generate_recommendation(row):
        recs = []
        if row["Timbulan_Sampah_Tahunan_ton"] >= waste_q75: recs.append("Expand infrastructure capacity.")
        if row["Unmanaged_Waste"] >= unmanaged_q75: recs.append("Target immediate reduction programs.")
        if row["Landfill_Score"] == 3: recs.append("Urgent: Upgrade from Open Dumping.")
        return " ".join(recs) if recs else "Maintain standard operations."
    
    df_year["Recommendation"] = df_year.apply(generate_recommendation, axis=1)
    df_year = df_year.sort_values("SAW_Score", ascending=False).reset_index(drop=True)

    # ---------------------------------------------------------
    # 8. Pre-calculate Sensitivity Analysis
    # ---------------------------------------------------------
    scenarios = {
        "Baseline": [0.35, 0.30, 0.20, 0.15],
        "Waste Burden Emphasis": [0.50, 0.20, 0.15, 0.15],
        "Management Gap Emphasis": [0.25, 0.45, 0.20, 0.10],
        "Landfill Risk Emphasis": [0.25, 0.25, 0.15, 0.35]
    }
    
    sens_results = pd.DataFrame({"Kabupaten_Kota": df_year["Kabupaten_Kota"]})
    
    for name, w in scenarios.items():
        tw = sum(w)
        score = (
            (df_year["Norm_Timbulan"] * (w[0]/tw)) +
            (df_year["Norm_Unmanaged"] * (w[1]/tw)) +
            (df_year["Norm_Recycling"] * (w[2]/tw)) +
            (df_year["Norm_Landfill"] * (w[3]/tw))
        )
        sens_results[f"{name}_Rank"] = score.rank(ascending=False).astype(int)
        
    corr_matrix = sens_results.drop(columns=["Kabupaten_Kota"]).corr(method="spearman")
    
    baseline_top10 = set(sens_results.sort_values("Baseline_Rank").head(10)["Kabupaten_Kota"])
    overlap_rows = []
    
    for scenario in scenarios.keys():
        scenario_top10 = set(sens_results.sort_values(f"{scenario}_Rank").head(10)["Kabupaten_Kota"])
        overlap_rows.append({
            "Scenario": scenario,
            "Top10_Overlap_With_Baseline": len(baseline_top10.intersection(scenario_top10))
        })
        
    overlap_df = pd.DataFrame(overlap_rows)

    # ==========================
    # UI Tabs
    # ==========================
    tab1, tab2, tab3 = st.tabs(["Dashboard & Maps", "Sensitivity Analysis", "Manuscript Exports"])

    with tab1:
        st.subheader("Geospatial Priority Distribution")
        df_map = df_year.merge(df_coords, on="Kabupaten_Kota", how="inner").copy()
        df_map["SAW_Score_Display"] = df_map["SAW_Score"].map(lambda x: f"{x:.3f}")
        
        def priority_color(x):
            return [255, 0, 0, 180] if x == "High Priority" else [255, 165, 0, 180] if x == "Medium Priority" else [0, 128, 0, 180]
        
        df_map["color"] = df_map["Priority_Level"].apply(priority_color)

        if not df_map.empty and MAPBOX_API_KEY:
            view_state = pdk.ViewState(
                latitude=df_map["lat"].mean(),
                longitude=df_map["lon"].mean(),
                zoom=7
            )

            deck = pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v10",
                initial_view_state=view_state,
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=df_map,
                        get_position='[lon, lat]',
                        get_radius="SAW_Score * 8000",
                        get_fill_color="color",
                        pickable=True,
                    )
                ],
                tooltip={
                    "html": "<b>{Kabupaten_Kota}</b><br>Score: {SAW_Score_Display}<br>Priority: {Priority_Level}"
                }
            )

            st.pydeck_chart(deck)
            
            map_html = deck.to_html(as_string=True)
            st.download_button(
                "Download Figure 4 - Interactive Priority Map HTML",
                data=map_html,
                file_name=f"Figure4_Priority_Map_{provinsi_terpilih}_{tahun_terpilih}.html",
                mime="text/html"
            )
            
        elif df_map.empty:
            st.warning("No matching coordinates found for the selected dataset. Check Kabupaten_Kota naming consistency.")
        else:
            st.warning("Mapbox token not found. Map visualization is disabled.")

        st.subheader("Top Priority Areas")
        st.dataframe(df_year[["Kabupaten_Kota", "SAW_Score", "Priority_Level", "Recommendation"]].head(10))

    with tab2:
        st.subheader("Automated Sensitivity Analysis")
        st.markdown("Testing stability of the top rankings across four distinct policy scenarios.")
        
        st.dataframe(sens_results.sort_values("Baseline_Rank").head(10))
        
        col_sens1, col_sens2 = st.columns(2)
        
        with col_sens1:
            st.subheader("Spearman Rank Correlation")
            st.dataframe(corr_matrix.style.background_gradient(cmap='coolwarm', axis=None))
            
        with col_sens2:
            st.subheader("Top-10 Rank Stability")
            st.dataframe(overlap_df)

    with tab3:
        st.subheader("Downloadable Results for Manuscript")
        st.markdown("Export these pre-formatted tables for your manuscript.")
        
        # ==========================
        # Table 1: Dataset Summary
        # ==========================
        summary_data = pd.DataFrame({
            "Indicator": [
                "Annual waste generation",
                "Unmanaged waste",
                "Recycling rate",
                "Landfill score"
            ],
            "Minimum": [
                df_year["Timbulan_Sampah_Tahunan_ton"].min(),
                df_year["Unmanaged_Waste"].min(),
                df_year["Recycling_Rate"].min(),
                df_year["Landfill_Score"].min()
            ],
            "Maximum": [
                df_year["Timbulan_Sampah_Tahunan_ton"].max(),
                df_year["Unmanaged_Waste"].max(),
                df_year["Recycling_Rate"].max(),
                df_year["Landfill_Score"].max()
            ],
            "Mean": [
                df_year["Timbulan_Sampah_Tahunan_ton"].mean(),
                df_year["Unmanaged_Waste"].mean(),
                df_year["Recycling_Rate"].mean(),
                df_year["Landfill_Score"].mean()
            ],
            "Unit": [
                "tons/year",
                "%",
                "%",
                "score"
            ]
        })

        st.markdown("#### Table 1. Dataset Summary")
        st.dataframe(summary_data)

        st.download_button(
            "Download Table 1 (Dataset Summary)",
            data=summary_data.to_csv(index=False),
            file_name=f"Table1_Dataset_Summary_{provinsi_terpilih}_{tahun_terpilih}.csv",
            mime="text/csv"
        )
        
        st.markdown("---")

        # ==========================
        # Table 4: Normalized Matrix
        # ==========================
        st.markdown("#### Table 4. Normalized Matrix")
        norm_matrix = df_year[[
            "Tahun",
            "Kabupaten_Kota",
            "Norm_Timbulan",
            "Norm_Unmanaged",
            "Norm_Recycling",
            "Norm_Landfill"
        ]]
        
        st.download_button(
            "Download Table 4 (Normalized Matrix)",
            data=norm_matrix.to_csv(index=False),
            file_name=f"Table4_Normalized_Matrix_{provinsi_terpilih}_{tahun_terpilih}.csv"
        )
        
        # ==========================
        # Table 5 & 6: Final Ranking
        # ==========================
        st.markdown("#### Table 5 & 6. Final Ranking & Recommendations")
        final_ranking = df_year[[
            "Tahun",
            "Kabupaten_Kota",
            "Timbulan_Sampah_Tahunan_ton",
            "Unmanaged_Waste",
            "Recycling_Rate",
            "Landfill_Type",
            "SAW_Score",
            "Priority_Level",
            "Recommendation"
        ]]

        st.download_button(
            "Download Table 5 & 6 (Final Ranking & Recs)",
            data=final_ranking.to_csv(index=False),
            file_name=f"Table5_6_Final_Ranking_{provinsi_terpilih}_{tahun_terpilih}.csv"
        )

        st.markdown("---")
        st.markdown("#### Sensitivity Analysis Exports")
        
        st.download_button(
            "Download Sensitivity Ranking",
            data=sens_results.to_csv(index=False),
            file_name=f"Sensitivity_Ranking_{provinsi_terpilih}_{tahun_terpilih}.csv"
        )
        
        st.download_button(
            "Download Spearman Correlation",
            data=corr_matrix.to_csv(index=True),
            file_name=f"Spearman_Correlation_{provinsi_terpilih}_{tahun_terpilih}.csv"
        )
        
        st.download_button(
            "Download Top-10 Stability",
            data=overlap_df.to_csv(index=False),
            file_name=f"Top10_Stability_{provinsi_terpilih}_{tahun_terpilih}.csv"
        )

        st.markdown("---")
        st.markdown("#### Figure Exports")

        # Figure 1: Annual Waste Generation by Municipality
        waste_sorted = df_year.sort_values("Timbulan_Sampah_Tahunan_ton", ascending=True)

        fig1, ax1 = plt.subplots(figsize=(9, 7))
        ax1.barh(
            waste_sorted["Kabupaten_Kota"],
            waste_sorted["Timbulan_Sampah_Tahunan_ton"]
        )

        ax1.set_title(f"Annual Waste Generation by Municipality in {provinsi_terpilih}, {tahun_terpilih}")
        ax1.set_xlabel("Annual Waste Generation (tons/year)")
        ax1.set_ylabel("Municipality")

        # Format x-axis without scientific notation
        ax1.ticklabel_format(style="plain", axis="x")

        # Add value labels
        for i, value in enumerate(waste_sorted["Timbulan_Sampah_Tahunan_ton"]):
            ax1.text(value + (waste_sorted["Timbulan_Sampah_Tahunan_ton"].max() * 0.01), i, f"{value:,.0f}", va="center")

        st.pyplot(fig1)
        st.download_button(
            "Download Figure 1 - Annual Waste Generation by Municipality",
            data=fig_to_png_bytes(fig1),
            file_name=f"Figure1_Annual_Waste_Generation_{provinsi_terpilih}_{tahun_terpilih}.png",
            mime="image/png"
        )
        plt.close(fig1)

        # Figure 2: Top 10 Priority Areas
        priority_colors = {
            "High Priority": "#d62728",    # red
            "Medium Priority": "#ff7f0e",  # orange
            "Low Priority": "#2ca02c"      # green
        }

        top10 = df_year.sort_values("SAW_Score", ascending=False).head(10)
        bar_colors = top10["Priority_Level"].map(priority_colors)

        fig2, ax2 = plt.subplots(figsize=(9, 6))
        ax2.barh(top10["Kabupaten_Kota"], top10["SAW_Score"], color=bar_colors)
        ax2.invert_yaxis()
        ax2.set_title(f"Top 10 Priority Areas Based on SAW Score, {tahun_terpilih}")
        ax2.set_xlabel("SAW Score")
        ax2.set_ylabel("Municipality")

        for i, value in enumerate(top10["SAW_Score"]):
            ax2.text(value + 0.01, i, f"{value:.3f}", va="center")

        st.pyplot(fig2)
        st.download_button(
            "Download Figure 2 - Top 10 Priority Areas",
            data=fig_to_png_bytes(fig2),
            file_name=f"Figure2_Top10_Priority_Areas_{provinsi_terpilih}_{tahun_terpilih}.png",
            mime="image/png"
        )
        plt.close(fig2)

        # Figure 3: Number of Areas by Priority Level
        priority_count = df_year["Priority_Level"].value_counts().reindex(
            ["High Priority", "Medium Priority", "Low Priority"]
        ).fillna(0)

        bar_colors = [priority_colors[level] for level in priority_count.index]

        fig3, ax3 = plt.subplots(figsize=(7, 5))
        ax3.bar(priority_count.index, priority_count.values, color=bar_colors)
        ax3.set_title(f"Number of Areas by Priority Level, {tahun_terpilih}")
        ax3.set_xlabel("Priority Level")
        ax3.set_ylabel("Number of Areas")

        for i, value in enumerate(priority_count.values):
            ax3.text(i, value + 0.2, int(value), ha="center")

        st.pyplot(fig3)
        st.download_button(
            "Download Figure 3 - Priority Count",
            data=fig_to_png_bytes(fig3),
            file_name=f"Figure3_Priority_Count_{provinsi_terpilih}_{tahun_terpilih}.png",
            mime="image/png"
        )
        plt.close(fig3)
        
else:
    st.info("Awaiting dataset uploads to initialize the DSS model.")
