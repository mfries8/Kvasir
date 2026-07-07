import os
import re
import json
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

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

# Mapping of user-friendly names to internal dataframe columns
PARAM_MAP = {
    "Total Reflectivity (Linear Z)": "Total Reflectivity (Linear Z)",
    "Terminus Altitude (m)": "Terminus Altitude (altitude_m)",
    "Density (kg/m³)": "Density (kg/m^3)",
    "Pre-Atmospheric Mass (kg)": "Pre-Atmospheric Mass (kg)",
    "Cosmic Velocity (km/s)": "Cosmic Velocity (km/s)",
    "Toughness Index": "Toughness Index",
    "Radar Detection Duration (s)": "Radar Detection Duration (s)",
    "Radar Detection Duration NEXRAD (s)": "Radar Detection Duration NEXRAD (s)",
    "Radar Sum (kg)": "Radar Sum (kg)",
    "Global Top Down (kg)": "Global Top Down (kg)",
    "Max Size Stat N1 (kg)": "Max Size Stat N1 (kg)",
    "Max Size Budget Radar (kg)": "Max Size Budget Radar (kg)",
    "Max Size Budget Global (kg)": "Max Size Budget Global (kg)",
    "Median Offset (m)": "Median Offset (m)",
    "P90 Radius (m)": "P90 Radius (m)",
    "b-Slope": "b-Slope",
    "R-Squared": "R-Squared"
}

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
                
            # Parse event.json if it exists
            event_path = os.path.join(dirpath, "event.json")
            terminus_altitude = None
            density = None
            pre_atmospheric_mass = None
            cosmic_velocity = None
            toughness_index = None
            has_event_data = False
            event_id = None
            
            if os.path.exists(event_path):
                try:
                    with open(event_path, "r", encoding="utf-8") as ef:
                        event_data = json.load(ef)
                    has_event_data = True
                    event_id = event_data.get("event_id")
                    luminous_end = event_data.get("luminous_end", {})
                    terminus_altitude = luminous_end.get("altitude_m")
                    density = event_data.get("Meteorite Density (kg/m^3)")
                    pre_atmospheric_mass = event_data.get("Pre-Atmospheric Mass (kg)")
                    cosmic_velocity = event_data.get("Cosmic Velocity (km/s)")
                    toughness_index = event_data.get("Toughness Index")
                except Exception:
                    pass
                
            # Parse comprehensive.json if it exists
            comp_path = os.path.join(dirpath, "comprehensive.json")
            radar_det_dur = None
            radar_det_dur_nexrad = None
            radar_sum_kg = None
            global_top_down_kg = None
            max_size_stat_n1 = None
            max_size_budget_radar = None
            max_size_budget_global = None
            median_offset_m = None
            p90_radius_m = None
            has_comp_data = False
            
            if os.path.exists(comp_path):
                try:
                    with open(comp_path, "r", encoding="utf-8") as cf:
                        comp_data = json.load(cf)
                    has_comp_data = True
                    
                    analysis_metadata = comp_data.get("analysis_metadata", {})
                    radar_det_dur = analysis_metadata.get("radar_detection_duration_seconds")
                    radar_det_dur_nexrad = analysis_metadata.get("radar_detection_duration_seconds_nexrad")
                    
                    forensics = comp_data.get("forensics", {})
                    total_mass = forensics.get("total_mass_estimates", {})
                    radar_sum_kg = total_mass.get("radar_sum_kg")
                    global_top_down_kg = total_mass.get("global_top_down_kg")
                    
                    max_size = forensics.get("max_size_predictions_kg", {})
                    max_size_stat_n1 = max_size.get("statistical_n1")
                    max_size_budget_radar = max_size.get("budget_radar_based")
                    max_size_budget_global = max_size.get("budget_global_based")
                    
                    rev_velocity = comp_data.get("reverse_velocity_cloud", {})
                    median_offset_m = rev_velocity.get("median_offset_m")
                    p90_radius_m = rev_velocity.get("p90_radius_m")
                except Exception:
                    pass
                
            # Check for reference b-slope in falls_b_slopes.json
            b_slopes_path = r"C:\Users\warra\Desktop\MFries_files\repos\Jormungandr_Official\Jormungandr\refs\falls_b_slopes.json"
            slope_val = None
            r2_val = None
            has_slope_data = False
            
            if os.path.exists(b_slopes_path):
                try:
                    with open(b_slopes_path, "r", encoding="utf-8") as bf:
                        b_slopes_data = json.load(bf)
                    
                    name_key = meteorite_name.replace(" ", "")
                    match_key = None
                    if name_key in b_slopes_data:
                        match_key = name_key
                    elif event_id and event_id in b_slopes_data:
                        match_key = event_id
                        
                    if match_key:
                        has_slope_data = True
                        entry = b_slopes_data[match_key]
                        if isinstance(entry, dict):
                            slope_val = entry.get("slope")
                            r2_val = entry.get("r2")
                        else:
                            slope_val = entry
                except Exception:
                    pass
                
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
                "Has Event Data": has_event_data,
                "Terminus Altitude (altitude_m)": terminus_altitude,
                "Density (kg/m^3)": density,
                "Pre-Atmospheric Mass (kg)": pre_atmospheric_mass,
                "Cosmic Velocity (km/s)": cosmic_velocity,
                "Toughness Index": toughness_index,
                "Has Comp Data": has_comp_data,
                "Radar Detection Duration (s)": radar_det_dur,
                "Radar Detection Duration NEXRAD (s)": radar_det_dur_nexrad,
                "Radar Sum (kg)": radar_sum_kg,
                "Global Top Down (kg)": global_top_down_kg,
                "Max Size Stat N1 (kg)": max_size_stat_n1,
                "Max Size Budget Radar (kg)": max_size_budget_radar,
                "Max Size Budget Global (kg)": max_size_budget_global,
                "Median Offset (m)": median_offset_m,
                "P90 Radius (m)": p90_radius_m,
                "Has Slope Data": has_slope_data,
                "b-Slope": slope_val,
                "R-Squared": r2_val,
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
        
        # Initialize session state variables for dynamic plots
        if "hist_param" not in st.session_state:
            st.session_state.hist_param = "Total Reflectivity (Linear Z)"
        if "hist_bins" not in st.session_state:
            st.session_state.hist_bins = 20
        if "hist_log" not in st.session_state:
            st.session_state.hist_log = True

        if "xy_x" not in st.session_state:
            st.session_state.xy_x = "Pre-Atmospheric Mass (kg)"
        if "xy_y" not in st.session_state:
            st.session_state.xy_y = "Radar Sum (kg)"
            
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

        # ----------------- Sidebar Control Layout -----------------
        # Add options for log scale and bins in sidebar
        st.sidebar.markdown("---")
        st.sidebar.markdown("<h3 style='color: #00FFCC; font-size: 16px;'>Histogram Controls</h3>", unsafe_allow_html=True)
        
        param_list = list(PARAM_MAP.keys())
        default_hist_idx = param_list.index(st.session_state.hist_param) if st.session_state.hist_param in param_list else 0
        
        selected_hist_param = st.sidebar.selectbox(
            "Select Histogram Parameter:",
            options=param_list,
            index=default_hist_idx,
            help="Choose which variable to bin in the histogram"
        )
        
        selected_hist_log = st.sidebar.checkbox(
            "Use Logarithmic Axis",
            value=st.session_state.hist_log,
            help="Apply log10 scaling to positive values of the selected parameter"
        )
        
        selected_hist_bins = st.sidebar.slider(
            "Number of Bins:",
            min_value=5,
            max_value=50,
            value=st.session_state.hist_bins,
            step=1
        )
        
        if st.sidebar.button("Compute Histogram"):
            st.session_state.hist_param = selected_hist_param
            st.session_state.hist_bins = selected_hist_bins
            st.session_state.hist_log = selected_hist_log
            st.rerun()

        st.sidebar.markdown("---")
        st.sidebar.markdown("<h3 style='color: #00FFCC; font-size: 16px;'>Graph Controls (X-Y Plot)</h3>", unsafe_allow_html=True)
        
        default_xy_x_idx = param_list.index(st.session_state.xy_x) if st.session_state.xy_x in param_list else 0
        default_xy_y_idx = param_list.index(st.session_state.xy_y) if st.session_state.xy_y in param_list else 0
        
        selected_xy_x = st.sidebar.selectbox(
            "Select X Axis Parameter:",
            options=param_list,
            index=default_xy_x_idx,
            help="Independent variable for the scatter plot"
        )
        
        selected_xy_y = st.sidebar.selectbox(
            "Select Y Axis Parameter:",
            options=param_list,
            index=default_xy_y_idx,
            help="Dependent variable for the scatter plot"
        )
        
        if st.sidebar.button("Compute Graph"):
            st.session_state.xy_x = selected_xy_x
            st.session_state.xy_y = selected_xy_y
            st.rerun()
            
        # ----------------- Histogram Section -----------------
        st.markdown(f"<h3 class='section-title'>Histogram: {st.session_state.hist_param} Distribution</h3>", unsafe_allow_html=True)
        
        hist_col = PARAM_MAP[st.session_state.hist_param]
        # Filter for data points containing valid values
        plot_df = df[df[hist_col].notna()].copy()
        
        if plot_df.empty:
            st.info(f"No valid data points available to plot for {st.session_state.hist_param} in this selection.")
        else:
            import math
            bins = st.session_state.hist_bins
            use_log = st.session_state.hist_log
            
            if use_log:
                # Pre-calculate log10 values in Python to avoid Plotly's log(0) = -inf rendering bug
                plot_df["Log10 Plot Value"] = plot_df[hist_col].apply(
                    lambda val: math.log10(val) if (pd.notna(val) and val > 0) else None
                )
                plot_df = plot_df[plot_df["Log10 Plot Value"].notna()].copy()
                
            if plot_df.empty:
                st.info(f"No positive data points available for logarithmic plot of {st.session_state.hist_param}.")
            else:
                if use_log:
                    fig = px.histogram(
                        plot_df,
                        x="Log10 Plot Value",
                        color="Meteorite Name",
                        nbins=bins,
                        title=f"{st.session_state.hist_param} Distribution ({mode}) - Log₁₀ Scale",
                        labels={
                            "Log10 Plot Value": f"Log₁₀({st.session_state.hist_param})",
                            "count": "Number of Falls"
                        },
                        template="plotly_dark",
                        hover_data={
                            "Meteorite Name": True,
                            "State/Province": True,
                            "Date": True,
                            "Time": True,
                            "Category": True,
                            hist_col: True
                        }
                    )
                    
                    min_val = plot_df["Log10 Plot Value"].min()
                    max_val = plot_df["Log10 Plot Value"].max()
                    start_tick = int(math.floor(min_val))
                    end_tick = int(math.ceil(max_val))
                    tick_vals = list(range(start_tick, end_tick + 1))
                    
                    tick_text = []
                    for t in tick_vals:
                        val = 10**t
                        if val >= 1000000:
                            tick_text.append(f"{val:.0e}")
                        elif val >= 1000:
                            tick_text.append(f"{val/1000:.0f}k")
                        elif val >= 1:
                            tick_text.append(f"{val:.0f}")
                        elif val > 0:
                            tick_text.append(f"{val:.4g}")
                        else:
                            tick_text.append("0")
                            
                    fig.update_xaxes(
                        tickvals=tick_vals,
                        ticktext=tick_text
                    )
                else:
                    fig = px.histogram(
                        plot_df,
                        x=hist_col,
                        color="Meteorite Name",
                        nbins=bins,
                        title=f"{st.session_state.hist_param} Distribution ({mode}) - Linear Scale",
                        labels={
                            hist_col: st.session_state.hist_param,
                            "count": "Number of Falls"
                        },
                        template="plotly_dark",
                        hover_data={
                            "Meteorite Name": True,
                            "State/Province": True,
                            "Date": True,
                            "Time": True,
                            "Category": True,
                            hist_col: True
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
                
                html_str = fig.to_html(include_plotlyjs='cdn', full_html=False)
                components.html(html_str, height=550, scrolling=False)

        # ----------------- X-Y Plot Section -----------------
        st.markdown(f"<h3 class='section-title'>X-Y Graph: {st.session_state.xy_y} vs {st.session_state.xy_x}</h3>", unsafe_allow_html=True)
        
        x_col = PARAM_MAP[st.session_state.xy_x]
        y_col = PARAM_MAP[st.session_state.xy_y]
        
        # Filter for rows that have valid data for both X and Y
        xy_df = df[df[x_col].notna() & df[y_col].notna()].copy()
        
        if xy_df.empty:
            st.info(f"No valid data points available where both {st.session_state.xy_x} and {st.session_state.xy_y} are defined.")
        else:
            st.markdown(f"This scatter plot visualizes the correlation between **{st.session_state.xy_x}** (X-Axis) and **{st.session_state.xy_y}** (Y-Axis).")
            
            fig_xy = px.scatter(
                xy_df,
                x=x_col,
                y=y_col,
                color="Meteorite Name",
                title=f"{st.session_state.xy_y} vs {st.session_state.xy_x} ({mode})",
                labels={
                    x_col: st.session_state.xy_x,
                    y_col: st.session_state.xy_y
                },
                template="plotly_dark",
                hover_data={
                    "Meteorite Name": True,
                    "State/Province": True,
                    "Category": True,
                    "Date": True,
                    "Time": True,
                    x_col: True,
                    y_col: True
                }
            )
            
            fig_xy.update_layout(
                height=500,
                margin=dict(l=40, r=40, t=50, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend_title_text="Fall Name",
                hovermode="closest"
            )
            
            fig_xy.update_traces(marker=dict(size=12, line=dict(width=1, color="DarkSlateGrey")))
            
            fig_xy.update_xaxes(showgrid=True, gridcolor="#1E293B")
            fig_xy.update_yaxes(showgrid=True, gridcolor="#1E293B")
            
            html_str_xy = fig_xy.to_html(include_plotlyjs='cdn', full_html=False)
            components.html(html_str_xy, height=550, scrolling=False)

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

        # ----------------- Event Metadata Section -----------------
        st.markdown("<h3 class='section-title'>Meteorite Event Metadata (from event.json)</h3>", unsafe_allow_html=True)
        
        # Filter for rows that have event data
        event_df = df[df["Has Event Data"]].copy()
        
        if event_df.empty:
            st.info("No event metadata available for this selection.")
        else:
            st.markdown("This table summarizes atmospheric flight and meteorite physical properties compiled from `event.json` in each fall directory.")
            
            # Select and rename columns for display
            display_event_df = event_df[[
                "Meteorite Name", "State/Province", "Category",
                "Terminus Altitude (altitude_m)", "Density (kg/m^3)",
                "Pre-Atmospheric Mass (kg)", "Cosmic Velocity (km/s)",
                "Toughness Index"
            ]].copy()
            
            # Rename columns to look professional
            display_event_df = display_event_df.rename(columns={
                "Terminus Altitude (altitude_m)": "Terminus Altitude (m)",
                "Density (kg/m^3)": "Density (kg/m³)",
                "Pre-Atmospheric Mass (kg)": "Pre-Atmospheric Mass (kg)",
                "Cosmic Velocity (km/s)": "Cosmic Velocity (km/s)",
                "Toughness Index": "Toughness Index"
            })
            
            # Reset index to avoid index out of range bugs
            st.dataframe(display_event_df.reset_index(drop=True), use_container_width=True)

        # ----------------- Comprehensive Metadata Section -----------------
        st.markdown("<h3 class='section-title'>Meteorite Comprehensive Analysis (from comprehensive.json)</h3>", unsafe_allow_html=True)
        
        # Filter for rows that have comprehensive data
        comp_df = df[df["Has Comp Data"]].copy()
        
        if comp_df.empty:
            st.info("No comprehensive analysis metadata available for this selection.")
        else:
            st.markdown("This table summarizes advanced atmospheric flight modeling and mass distribution estimates compiled from `comprehensive.json`.")
            
            # Select and rename columns for display
            display_comp_df = comp_df[[
                "Meteorite Name", "State/Province", "Category",
                "Radar Detection Duration (s)", "Radar Detection Duration NEXRAD (s)",
                "Radar Sum (kg)", "Global Top Down (kg)",
                "Max Size Stat N1 (kg)", "Max Size Budget Radar (kg)", "Max Size Budget Global (kg)",
                "Median Offset (m)", "P90 Radius (m)"
            ]].copy()
            
            # Format numeric columns to look professional (e.g. 2 decimal places or scientific)
            for col in ["Radar Sum (kg)", "Global Top Down (kg)", "Max Size Stat N1 (kg)", 
                        "Max Size Budget Radar (kg)", "Max Size Budget Global (kg)", 
                        "Median Offset (m)", "P90 Radius (m)"]:
                display_comp_df[col] = display_comp_df[col].apply(
                    lambda val: f"{val:.2f}" if pd.notna(val) else "N/A"
                )
                
            for col in ["Radar Detection Duration (s)", "Radar Detection Duration NEXRAD (s)"]:
                display_comp_df[col] = display_comp_df[col].apply(
                    lambda val: f"{val:.1f}" if pd.notna(val) else "N/A"
                )
            
            # Reset index to avoid index out of range bugs
            st.dataframe(display_comp_df.reset_index(drop=True), use_container_width=True)

        # ----------------- B-Slope Section -----------------
        st.markdown("<h3 class='section-title'>Meteorite b-Slope Estimates (from falls_b_slopes.json)</h3>", unsafe_allow_html=True)
        
        # Filter for rows that have slope data
        slope_df = df[df["Has Slope Data"]].copy()
        
        if slope_df.empty:
            st.info("No b-slope reference data available for this selection.")
        else:
            st.markdown("This table incorporates the b-slope power law exponents and their corresponding R² linear regression qualities.")
            
            # Select and rename columns for display
            display_slope_df = slope_df[[
                "Meteorite Name", "State/Province", "Category",
                "b-Slope", "R-Squared"
            ]].copy()
            
            # Format columns
            display_slope_df["b-Slope"] = display_slope_df["b-Slope"].apply(
                lambda val: f"{val:.4f}" if pd.notna(val) else "N/A"
            )
            display_slope_df["R-Squared"] = display_slope_df["R-Squared"].apply(
                lambda val: f"{val:.4f}" if pd.notna(val) else "N/A"
            )
            
            # Reset index to avoid index out of range bugs
            st.dataframe(display_slope_df.reset_index(drop=True), use_container_width=True)
