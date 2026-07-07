import os
import re
import json
import pandas as pd
import plotly.express as px
import streamlit as st

# Page Configuration for a premium dark aesthetics look
st.set_page_config(
    page_title="Kvasir - Meteorite Fall RADAR reflectivity Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Slate Dark / Neon Cyan CSS
st.markdown("""
<style>
    /* Styling for metric cards */
    .metric-card {
        background-color: #1E293B;
        border-radius: 10px;
        padding: 20px;
        border-left: 5px solid #00FFCC;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        margin-bottom: 15px;
    }
    .metric-value {
        font-size: 32px;
        font-weight: 700;
        color: #00FFCC;
        margin-bottom: 5px;
    }
    .metric-label {
        font-size: 13px;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }
    /* Section headers styling */
    .section-title {
        color: #00FFCC;
        font-family: 'Outfit', sans-serif;
        border-bottom: 2px solid #1E293B;
        padding-bottom: 5px;
        margin-top: 25px;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# Regex to match [State/Province] [meteorite name] [date DD MMM YYYY] [time UTC]
# State/Province is 2 or 3 letters.
# Date is DD MMM YYYY where year can be 2 or 4 digits.
# Time is a time string followed by UTC.
FOLDER_PATTERN = re.compile(
    r"^([A-Za-z]{2,3})\s+(.+?)\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+(?:\d{4}|\d{2}))\s+(\S+\s+UTC)$",
    re.IGNORECASE
)

def compute_total_reflectivity(radar_path):
    """
    Parses a RADAR_*.json file, converts dBZ reflectivity values of all pixels 
    to linear scale, and sums them up.
    
    Linear reflectivity Z = 10^(dBZ / 10)
    """
    if not radar_path or not os.path.exists(radar_path):
        return None
    try:
        with open(radar_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total_z = 0.0
        pixel_count = 0
        
        for sweep in data.get("sweeps", []):
            for pixel in sweep.get("pixels", []):
                ref = pixel.get("reflectivity")
                if ref is not None:
                    try:
                        dbz = float(ref)
                        lin_z = 10.0 ** (dbz / 10.0)
                        total_z += lin_z
                        pixel_count += 1
                    except (ValueError, TypeError):
                        pass
        return total_z if pixel_count > 0 else 0.0
    except Exception:
        return None

@st.cache_data
def load_fall_data(root_dir):
    """
    Scans the root folder recursively for meteorite fall directories.
    Classifies directories containing 'AAA probable' in their path as Probable falls,
    and all others as Known falls.
    Reads and computes total linear reflectivity from the RADAR_*.json files.
    """
    falls = []
    if not os.path.isdir(root_dir):
        return falls

    # Walk the tree. topdown=True allows us to prune dirnames in-place to avoid recursing deeper.
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip checking the root itself
        if dirpath == root_dir:
            continue
            
        dirname = os.path.basename(dirpath)
        match = FOLDER_PATTERN.match(dirname)
        if match:
            # We found a fall directory. Clear dirnames to avoid searching its subdirectories (DFM, RAOB, etc.)
            dirnames.clear()
            
            # Determine if this fall is under 'AAA probable'
            rel_path = os.path.relpath(dirpath, root_dir)
            path_parts = rel_path.split(os.sep)
            is_probable = any(part.lower() == "aaa probable" for part in path_parts)
            category = "Probable" if is_probable else "Known"
            
            state_prov = match.group(1).upper()
            meteorite_name = match.group(2)
            date_str = match.group(3)
            time_str = match.group(4)
            
            # Find the RADAR_*.json file in the folder
            radar_files = []
            try:
                for f in os.listdir(dirpath):
                    if f.upper().startswith("RADAR_") and not f.lower().startswith("radar_data_quality") and f.lower().endswith(".json"):
                        radar_files.append(os.path.join(dirpath, f))
            except Exception:
                pass
            
            radar_path = radar_files[0] if radar_files else None
            radar_filename = os.path.basename(radar_path) if radar_path else None
            
            # Compute linear reflectivity sum
            total_reflectivity = None
            if radar_path:
                total_reflectivity = compute_total_reflectivity(radar_path)
                
            falls.append({
                "Folder Name": dirname,
                "State/Province": state_prov,
                "Meteorite Name": meteorite_name,
                "Date": date_str,
                "Time": time_str,
                "Category": category,
                "Radar File": radar_filename,
                "Radar Path": radar_path,
                "Total Reflectivity (Linear Z)": total_reflectivity,
                "Folder Path": dirpath
            })
            
    return falls

# ----------------- UI Header -----------------
st.markdown("""
    <h1 style='text-align: center; color: #00FFCC; font-family: "Outfit", sans-serif; background: linear-gradient(45deg, #00FFCC, #00AAFF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 5px;'>
        Kvasir: Meteorite Fall RADAR reflectivity Dashboard
    </h1>
    <p style='text-align: center; color: #94A3B8; font-size: 16px; margin-bottom: 25px;'>
        Analyze and visualize total linear weather radar reflectivity across meteorite fall events
    </p>
""", unsafe_allow_html=True)

# ----------------- Sidebar Controls -----------------
st.sidebar.markdown("<h2 style='color: #00FFCC; font-family: sans-serif;'>Dashboard Controls</h2>", unsafe_allow_html=True)

# Path input
default_path = r"C:\Users\warra\Desktop\MFries_files\Doppler radar work\AAA falls"
root_folder = st.sidebar.text_input(
    "Meteorite Fall Repository Root Folder:",
    value=default_path,
    help="Absolute path to the root meteorite fall directory"
)

# Category selection
mode = st.sidebar.radio(
    "Select Meteorite Fall Category:",
    options=["Known Falls Only", "All Falls (Known and Probable)"],
    index=1,
    help="Filter processed directories by fall classification"
)

# Clear cache button
if st.sidebar.button("Force Clear Cache & Reload"):
    st.cache_data.clear()
    st.success("Cache cleared! Reloading...")
    st.rerun()

# ----------------- Processing Logic -----------------
if not os.path.exists(root_folder):
    st.error(f"The path `{root_folder}` does not exist. Please specify a valid directory on your system.")
else:
    with st.spinner("Scanning directories and parsing RADAR JSON data..."):
        all_falls = load_fall_data(root_folder)
        
    if not all_falls:
        st.warning("No directories matching the pattern `[State] [Meteorite] [Date] [Time UTC]` were found.")
    else:
        # Filter based on user selection
        if mode == "Known Falls Only":
            filtered_falls = [f for f in all_falls if f["Category"] == "Known"]
        else:
            # Include both Known and Probable
            filtered_falls = all_falls
            
        df = pd.DataFrame(filtered_falls)
        
        # ----------------- Metrics -----------------
        total_matching = len(df)
        with_radar = df["Total Reflectivity (Linear Z)"].notna().sum()
        no_radar = total_matching - with_radar
        
        known_count = (df["Category"] == "Known").sum()
        probable_count = (df["Category"] == "Probable").sum()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-value">{total_matching}</div>
                    <div class="metric-label">Total Falls Found</div>
                </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-value">{with_radar}</div>
                    <div class="metric-label">Falls with RADAR Data</div>
                </div>
            """, unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-value">{no_radar}</div>
                    <div class="metric-label">Falls Missing RADAR</div>
                </div>
            """, unsafe_allow_html=True)
            
        with col4:
            st.markdown(f"""
                <div class="metric-card" style="border-left-color: #00AAFF;">
                    <div class="metric-value">{known_count} K / {probable_count} P</div>
                    <div class="metric-label">Known vs Probable</div>
                </div>
            """, unsafe_allow_html=True)
            
        # ----------------- Graph Section -----------------
        st.markdown("<h3 class='section-title'>Total Reflectivity Distribution Histogram</h3>", unsafe_allow_html=True)
        
        # Filter for data points containing valid radar reflectivity
        plot_df = df[df["Total Reflectivity (Linear Z)"].notna()].copy()
        
        if plot_df.empty:
            st.info("No radar reflectivity data available to plot in this selection.")
        else:
            # Add options for log scale and bins in sidebar
            st.sidebar.markdown("---")
            st.sidebar.markdown("<h3 style='color: #00FFCC; font-size: 16px;'>Histogram Controls</h3>", unsafe_allow_html=True)
            
            use_log = st.sidebar.checkbox(
                "Use Logarithmic Reflectivity Axis", 
                value=True,
                help="Recommended since linear radar reflectivity spans multiple orders of magnitude"
            )
            
            nbins = st.sidebar.slider(
                "Number of Bins:",
                min_value=5,
                max_value=50,
                value=20,
                step=1
            )
            
            # Generate the histogram
            import math
            if use_log:
                # Pre-calculate log10 values in Python to avoid Plotly's log(0) = -inf rendering bug
                plot_df["Log10 Reflectivity"] = plot_df["Total Reflectivity (Linear Z)"].apply(
                    lambda val: math.log10(val) if val > 0 else 0.0
                )
                fig = px.histogram(
                    plot_df,
                    x="Log10 Reflectivity",
                    color="Meteorite Name",
                    nbins=nbins,
                    title=f"Total Linear Reflectivity Histogram ({mode})",
                    labels={
                        "Log10 Reflectivity": "Total Reflectivity (Z, mm⁶/m³)",
                        "count": "Number of Falls"
                    },
                    template="plotly_dark",
                    hover_data={
                        "Meteorite Name": True,
                        "State/Province": True,
                        "Date": True,
                        "Time": True,
                        "Category": True,
                        "Total Reflectivity (Linear Z)": ":.4e"
                    }
                )
                # Map the linear log10 axis to readable tick marks
                fig.update_xaxes(
                    tickvals=[0, 1, 2, 3, 4, 5, 6],
                    ticktext=["1", "10", "100", "1k", "10k", "100k", "1M"]
                )
            else:
                fig = px.histogram(
                    plot_df,
                    x="Total Reflectivity (Linear Z)",
                    color="Meteorite Name",
                    nbins=nbins,
                    title=f"Total Linear Reflectivity Histogram ({mode})",
                    labels={
                        "Total Reflectivity (Linear Z)": "Total Reflectivity (Linear Z, mm⁶/m³)",
                        "count": "Number of Falls"
                    },
                    template="plotly_dark",
                    hover_data={
                        "Meteorite Name": True,
                        "State/Province": True,
                        "Date": True,
                        "Time": True,
                        "Category": True,
                        "Total Reflectivity (Linear Z)": ":.4e"
                    }
                )
            
            # Improve visual layout
            fig.update_layout(
                height=500,
                margin=dict(l=40, r=40, t=50, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend_title_text="Fall Name",
                hovermode="closest",
                bargap=0.05
            )
            fig.update_xaxes(showgrid=True, gridcolor="#1E293B")
            fig.update_yaxes(showgrid=True, gridcolor="#1E293B")
            
            # Render using components.html to bypass version mismatch between Python Plotly 6.x and Streamlit's internal Plotly.js
            import streamlit.components.v1 as components
            html_str = fig.to_html(include_plotlyjs='cdn', full_html=False)
            components.html(html_str, height=550, scrolling=False)

        # ----------------- Tables / Details Section -----------------
        st.markdown("<h3 class='section-title'>Meteorite Falls Data Details</h3>", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["Active Dataset", "Folders Missing RADAR JSON"])
        
        with tab1:
            st.markdown("This table contains all falls matched by name filter. You can search, sort, and filter the table.")
            # Present DataFrame nicely formatted
            display_df = df[[
                "Meteorite Name", "State/Province", "Date", "Time", 
                "Category", "Radar File", "Total Reflectivity (Linear Z)"
            ]].copy()
            
            # Format the linear reflectivity column to scientific notation if not None
            display_df["Total Reflectivity (Linear Z)"] = display_df["Total Reflectivity (Linear Z)"].apply(
                lambda val: f"{val:.4e}" if pd.notna(val) else "N/A"
            )
            
            st.dataframe(display_df.reset_index(drop=True), use_container_width=True)
            
        with tab2:
            missing_df = df[df["Total Reflectivity (Linear Z)"].isna()].copy()
            if missing_df.empty:
                st.success("All identified falls contain a `RADAR_*.json` file!")
            else:
                st.warning(f"Found {len(missing_df)} directories matching naming format but missing a valid `RADAR_*.json` file.")
                display_missing = missing_df[[
                    "Meteorite Name", "State/Province", "Date", "Time", "Category", "Folder Path"
                ]]
                st.dataframe(display_missing.reset_index(drop=True), use_container_width=True)
