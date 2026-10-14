import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh
import os

# Configure Streamlit page layout
st.set_page_config(page_title="Hydrology Executive Dashboard", layout="wide")

# Auto-refresh every 15 minutes
st_autorefresh(interval=15 * 60 * 1000, key="data_refresh")

# Initialize Session State
if 'cwc_sel' not in st.session_state:
    st.session_state.cwc_sel = "Select Station"
if 'nepal_sel' not in st.session_state:
    st.session_state.nepal_sel = "Select Station"

def go_home():
    st.session_state.cwc_sel = "Select Station"
    st.session_state.nepal_sel = "Select Station"

# Data Fetching
@st.cache_data(ttl=600)
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_path = r"C:\Nepal_Data_Web_Scrapping\credentials.json"
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1ghciZbDGR5Jxp8EzPKhX2VwjYH93L7yO-4abZzLzJ9w").sheet1
    return sheet.get_all_values()

try:
    raw_data = load_data()
except Exception as e:
    st.error(f"Could not connect to Google Sheets: {e}")
    st.stop()

# Parse Dynamic Title from Row 1
dynamic_title = "🌊 Hydrology Executive Dashboard"
for cell in raw_data[0]:
    if cell.strip():
        dynamic_title = cell.strip()
        break
st.title(dynamic_title)

# Header Rows
cwc_row = [str(c).strip() for c in raw_data[1][1:]]
station_names = [str(n).strip() for n in raw_data[2][1:]]
warning_levels = raw_data[4][1:]
danger_levels = raw_data[5][1:]
trends = raw_data[6][1:]

# Safe retrieval helper
def get_safe_val(source_list, index, default="N/A"):
    if index < len(source_list):
        val = str(source_list[index]).strip()
        return val if val else default
    return default

def get_safe_float(source_list, index):
    try:
        if index < len(source_list):
            return float(str(source_list[index]).strip())
    except (ValueError, TypeError):
        pass
    return None

# Build CWC -> Nepal Station Hierarchy
cwc_mapping = {}
nepal_to_index = {}
current_cwc = "Uncategorized"

for i, (cwc, nepal) in enumerate(zip(cwc_row, station_names)):
    if not nepal:
        continue
    if cwc != "":
        current_cwc = cwc
    if current_cwc not in cwc_mapping:
        cwc_mapping[current_cwc] = []
    cwc_mapping[current_cwc].append(nepal)
    nepal_to_index[nepal] = i

# Parse Historical Time Series
data_rows = raw_data[7:]
df = pd.DataFrame(data_rows, columns=["Date"] + station_names)
df["Date"] = pd.to_datetime(df["Date"], format="%d-%m-%Y %H:%M:%S", errors='coerce')
df = df.dropna(subset=["Date"]).sort_values("Date")

st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/e/ec/Cwclogo.jpg", use_container_width=True)

st.sidebar.button("🏠 Home Page", on_click=go_home, use_container_width=True)
st.sidebar.header("Site Selection")

cwc_options = ["Select Station"] + list(cwc_mapping.keys())
st.sidebar.selectbox("1. Select CWC Station", cwc_options, key='cwc_sel')

if st.session_state.cwc_sel != "Select Station":
    nepal_options = ["Select Station"] + cwc_mapping.get(st.session_state.cwc_sel, [])
else:
    nepal_options = ["Select Station"]
st.sidebar.selectbox("2. Select Nepal Station", nepal_options, key='nepal_sel')

# Helper function to render a strict Plotly table
def render_plotly_table(dataframe, first_col_left=True):
    col_count = len(dataframe.columns)
    if first_col_left:
        header_align = ['left'] + ['center'] * (col_count - 1)
        cell_align = ['left'] + ['center'] * (col_count - 1)
    else:
        header_align = ['center'] * col_count
        cell_align = ['center'] * col_count

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=list(dataframe.columns),
            fill_color='#f0f2f6',
            align=header_align,
            font=dict(size=14, color='black')
        ),
        cells=dict(
            values=[dataframe[col] for col in dataframe.columns],
            fill_color='white',
            align=cell_align,
            font=dict(size=13, color='black'),
            height=32
        )
    )])
    calc_height = 55 + (len(dataframe) * 32)
    fig.update_layout(margin=dict(l=0, r=0, t=5, b=5), height=calc_height)
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# --- VIEW ROUTING: Homepage Summary ---
if st.session_state.cwc_sel == "Select Station" or st.session_state.nepal_sel == "Select Station":
    st.markdown("### 📊 CWC Regional Summary")
    st.info("👈 Select a station from the sidebar to view detailed graphs, or click the **Home Page** button to return here.")
    
    for cwc_station, nepal_list in cwc_mapping.items():
        if not nepal_list or cwc_station == "Uncategorized":
            continue
            
        st.markdown(f"#### 📍 CWC Station: **{cwc_station}**")
        
        summary_rows = []
        for nepal in nepal_list:
            idx = nepal_to_index[nepal]
            stn_series = pd.to_numeric(df[nepal], errors='coerce').dropna()
            
            if not stn_series.empty:
                val = float(stn_series.iloc[-1])
                last_time_str = df.loc[stn_series.index[-1], "Date"].strftime("%d-%m-%Y %I:%M %p")
            else:
                val = None
                last_time_str = "No Data"
            
            w_lim = get_safe_float(warning_levels, idx)
            d_lim = get_safe_float(danger_levels, idx)
            
            if val is not None:
                if d_lim is not None and val >= d_lim:
                    status_text = "🔴 DANGER"
                elif w_lim is not None and val >= w_lim:
                    status_text = "🟠 Warning"
                else:
                    status_text = "🟢 Normal"
            else:
                status_text = "⚪ N/A"
            
            level_str = f"{val:.2f}" if val is not None else "N/A"
            trend_val = get_safe_val(trends, idx, default="N/A")
            
            summary_rows.append({
                "Associated Nepal Station": nepal,
                "Latest Water Level (m)": level_str,
                "Last Recorded Time": last_time_str,
                "Trend": trend_val,
                "Status": status_text
            })
            
        summary_df = pd.DataFrame(summary_rows)
        render_plotly_table(summary_df, first_col_left=True)

# --- VIEW ROUTING: Detailed Station View ---
else:
    selected_nepal = st.session_state.nepal_sel
    station_idx = nepal_to_index[selected_nepal]
    current_trend = get_safe_val(trends, station_idx, default="N/A")

    df[selected_nepal] = pd.to_numeric(df[selected_nepal], errors='coerce')
    station_df = df.dropna(subset=[selected_nepal])

    if station_df.empty:
        st.warning(f"No valid numerical data available for {selected_nepal}.")
        st.stop()

    latest_data = station_df.iloc[-1]
    current_level = latest_data[selected_nepal]
    last_update = latest_data["Date"].strftime("%d-%m-%Y %I:%M %p")

    warn_limit = get_safe_float(warning_levels, station_idx)
    danger_limit = get_safe_float(danger_levels, station_idx)

    status = "NORMAL"
    status_color = "green"
    if danger_limit is not None and current_level >= danger_limit:
        status = "DANGER LEVEL EXCEEDED"
        status_color = "red"
    elif warn_limit is not None and current_level >= warn_limit:
        status = "WARNING LEVEL EXCEEDED"
        status_color = "orange"

    st.subheader(f"Monitoring: {selected_nepal} (Under {st.session_state.cwc_sel})")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Water Level (m)", f"{current_level:.2f}")
    col2.metric("Trend", current_trend)
    col3.metric("Status", status)
    col4.metric("Last Updated", last_update)

    st.markdown(f"<h3 style='text-align: center; color: {status_color};'>{status}</h3>", unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=station_df["Date"], 
        y=station_df[selected_nepal],
        mode='lines+markers',
        name='Water Level',
        line=dict(color='blue', width=3)
    ))

    if warn_limit is not None:
        fig.add_hline(y=warn_limit, line_dash="dash", line_color="orange", 
                      annotation_text="Warning Level", annotation_position="top left")
    if danger_limit is not None:
        fig.add_hline(y=danger_limit, line_dash="dash", line_color="red", 
                      annotation_text="Danger Level", annotation_position="top left")

    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Water Level (m)",
        hovermode="x unified",
        template="plotly_white",
        height=500
    )

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("View Raw Data Log"):
        raw_df = station_df[["Date", selected_nepal]].sort_values("Date", ascending=False).copy()
        raw_df["Date"] = raw_df["Date"].dt.strftime("%d-%m-%Y %I:%M %p")
        raw_df.rename(columns={selected_nepal: f"{selected_nepal} Level (m)"}, inplace=True)
        render_plotly_table(raw_df, first_col_left=False)
