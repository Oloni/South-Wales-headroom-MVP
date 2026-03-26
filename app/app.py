"""
South Wales Grid Connection Screener
=====================================
Map click → substation detail → test connection → curtailment results
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import requests

st.set_page_config(
    page_title="Loom Light — Grid Connection Screener",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# AUTHENTICATION
# ============================================================
SIGNIN_WEBHOOK = "https://script.google.com/macros/s/AKfycbzOew22u9fHbF727BeuuCi1cH1bgJzb3QvG92u15P-eGHy1pCfYxicuuZql3YeJB8gL/exec"
APP_PASSWORD = "LoomLight2026"

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("## ⚡ Loom Light")
    st.markdown("### South Wales Grid Connection Screener")
    st.markdown("---")
    with st.form("login_form"):
        name = st.text_input("Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if password == APP_PASSWORD and name.strip() and email.strip():
            try:
                requests.post(SIGNIN_WEBHOOK, json={"name": name.strip(), "email": email.strip()}, timeout=5)
            except Exception:
                pass
            st.session_state.authenticated = True
            st.rerun()
        elif password != APP_PASSWORD:
            st.error("Incorrect password.")
        else:
            st.warning("Please enter your name and email.")
    st.stop()


# ============================================================
# DATA
# ============================================================
def find_data_path(filename):
    for prefix in ['../data/', 'data/']:
        if os.path.exists(prefix + filename):
            return prefix + filename
    return None

@st.cache_data
def load_data():
    path = find_data_path('south_wales_substations.csv')
    if not path:
        return pd.DataFrame()
    df = pd.read_csv(path)
    coords = {
        'Abergavenny': (51.82, -3.02), 'Ammanford': (51.80, -3.92),
        'Bridgend': (51.51, -3.58), 'Briton Ferry': (51.63, -3.82),
        'Brynhill': (51.44, -3.33), 'Cardiff Central': (51.48, -3.18),
        'Cardiff East': (51.52, -3.13), 'Cardiff North': (51.52, -3.19),
        'Cardiff West': (51.48, -3.23), 'Carmarthen': (51.86, -4.30),
        'Crumlin': (51.68, -3.13), 'Dowlais': (51.75, -3.35),
        'East Aberthaw': (51.41, -3.39), 'Ebbw Vale': (51.78, -3.21),
        'Golden Hill': (51.70, -4.97), 'Gowerton East': (51.66, -4.00),
        'Grange': (51.55, -3.75), 'Haverfordwest': (51.80, -4.97),
        'Hirwaun': (51.73, -3.47), 'Lampeter': (52.12, -4.08),
        'Llanarth': (52.21, -4.35), 'Llantarnam': (51.65, -3.02),
        'Milford Haven': (51.72, -5.03), 'Mountain Ash': (51.68, -3.38),
        'Newport South': (51.58, -2.97), 'Panteg': (51.70, -3.01),
        'Pyle': (51.53, -3.70), 'Rhos': (52.03, -4.45),
        'Sudbrook': (51.58, -2.72), 'Swansea North': (51.67, -3.94),
        'Swansea West': (51.63, -3.96), 'Tir John': (51.63, -3.92),
        'Trostre': (51.69, -4.15), 'Upper Boat': (51.55, -3.35),
        'Ystradgynlais': (51.77, -3.79),
    }
    df['lat'] = df['display_name'].map(lambda x: coords.get(x, (None, None))[0])
    df['lon'] = df['display_name'].map(lambda x: coords.get(x, (None, None))[1])
    no_gcr = df['connected_mva'].isna() & df['accepted_mva'].isna()
    df.loc[no_gcr, 'headroom_flag'] = 'No data'
    df.loc[no_gcr, 'headroom_mva'] = np.nan
    return df

@st.cache_data
def load_csv_or_none(filename):
    path = find_data_path(filename)
    if path:
        return pd.read_csv(path)
    return None

df = load_data()
curtailment_df = load_csv_or_none('south_wales_curtailment.csv')
seasonal_df = load_csv_or_none('south_wales_curtailment_seasonal.csv')
lifo_df = load_csv_or_none('south_wales_curtailment_lifo.csv')
colocation_df = load_csv_or_none('south_wales_curtailment_colocation.csv')

tech_map = {"Solar": "PV", "Onshore Wind": "Wind", "Battery": "BESS", "Other (gas, biomass, CHP)": "Other"}

NAME_TO_CIM = {
    'Ammanford': 'AMMA', 'Briton Ferry': 'BRIF', 'Carmarthen': 'CARM',
    'Gowerton East': 'GOWE', 'Hirwaun': 'HIRW', 'Lampeter': 'LAMP',
    'Llanarth': 'LLAN', 'Rhos': 'RHOS', 'Swansea North': 'SWAN',
    'Swansea West': 'SWAW', 'Tir John': 'TIRJ', 'Trostre': 'TROS',
    'Ystradgynlais': 'TRAV', 'Abergavenny': 'ABGA', 'Bridgend': 'BREN',
    'Brynhill': 'BARR', 'Cardiff Central': 'CARC', 'Cardiff East': 'CARE',
    'Cardiff North': 'CARN', 'Cardiff West': 'CARW', 'Crumlin': 'CRUM',
    'Dowlais': 'DOWL', 'East Aberthaw': 'EAST', 'Ebbw Vale': 'EBBW',
    'Golden Hill': 'GOLD', 'Grange': 'MAGA', 'Haverfordwest': 'HAVE',
    'Llantarnam': 'LLTA', 'Milford Haven': 'MIFH', 'Mountain Ash': 'MOUA',
    'Newport South': 'NEWS', 'Panteg': 'PANT', 'Pyle': 'PYLE',
    'South Hook': 'SHHK', 'Sudbrook': 'SUDB', 'Upper Boat': 'UPPB',
}
CIM_TO_NAME_FULL = {v: k for k, v in NAME_TO_CIM.items()}

def match_substation(dataframe, display_name):
    if dataframe is None:
        return pd.DataFrame()
    result = dataframe[dataframe['substation'] == display_name]
    if len(result) > 0:
        return result
    cim = NAME_TO_CIM.get(display_name)
    if cim:
        result = dataframe[dataframe['substation'] == cim]
    return result


# ============================================================
# SESSION STATE
# ============================================================
if 'selected_sub' not in st.session_state:
    st.session_state.selected_sub = None
if 'test_run' not in st.session_state:
    st.session_state.test_run = False
if 'test_mw' not in st.session_state:
    st.session_state.test_mw = 20
if 'test_tech' not in st.session_state:
    st.session_state.test_tech = 'Solar'


# ============================================================
# SIDEBAR (minimal)
# ============================================================
st.sidebar.markdown("## ⚡ Loom Light")
st.sidebar.markdown("**Grid Connection Screener**")
st.sidebar.markdown("South Wales · 132/33kV & 132/66kV BSPs")
st.sidebar.divider()

headroom_options = ['All', 'Overcommitted', 'Tight', 'Moderate', 'Available']
selected_headroom = st.sidebar.selectbox("Filter by headroom", headroom_options)

filtered = df.copy()
if selected_headroom != 'All':
    filtered = filtered[filtered['headroom_flag'] == selected_headroom]

st.sidebar.divider()
st.sidebar.caption("Data: NGED LTDS, BSP flows, GCR, Curtailment data (Mar 2026)")
st.sidebar.caption("⚠️ Prototype — not for investment decisions.")


# ============================================================
# HEADER
# ============================================================
st.markdown("# South Wales Grid Connection Screener")

col1, col2, col3, col4 = st.columns(4)
with col1: st.metric("Substations", len(filtered))
with col2: st.metric("Overcommitted", (filtered['headroom_flag'] == 'Overcommitted').sum())
with col3: st.metric("Tight", (filtered['headroom_flag'] == 'Tight').sum())
with col4: st.metric("Available / Moderate", filtered['headroom_flag'].isin(['Moderate', 'Available']).sum())


# ============================================================
# MAP
# ============================================================
map_df = filtered.dropna(subset=['lat', 'lon']).copy()

# Overview button
mapcol1, mapcol2 = st.columns([6, 1])
with mapcol2:
    if st.button("⬜ Overview", use_container_width=True):
        st.session_state.selected_sub = None
        st.session_state.test_run = False
        st.rerun()

try:
    import folium
    from streamlit_folium import st_folium

    m = folium.Map(location=[51.65, -3.6], zoom_start=8, tiles='CartoDB positron')

    flag_colors = {
        'Overcommitted': '#dc3545', 'Tight': '#f0a028',
        'Moderate': '#50a0dc', 'Available': '#32b450', 'No data': '#999999',
    }

    for _, row in map_df.iterrows():
        color = flag_colors.get(row['headroom_flag'], '#999999')
        headroom_str = f"{row['headroom_mva']:.0f}" if pd.notna(row.get('headroom_mva')) else '?'
        rating_str = f"{row['total_nominal_mva']:.0f}" if pd.notna(row.get('total_nominal_mva')) else '?'
        connected_str = f"{row['connected_mva']:.1f}" if pd.notna(row.get('connected_mva')) else '?'
        accepted_str = f"{row['accepted_mva']:.1f}" if pd.notna(row.get('accepted_mva')) else '?'
        peak_str = f"{row['peak_import_mw']:.1f}" if pd.notna(row.get('peak_import_mw')) else '?'

        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 13px; min-width: 220px;">
            <b>{row['display_name']}</b> ({row['voltage_kv']}kV)<br/>
            <hr style="margin: 4px 0;">
            Rating: {rating_str} MVA | Peak: {peak_str} MW<br/>
            Connected: {connected_str} MVA | Accepted: {accepted_str} MVA<br/>
            <b>Headroom: {headroom_str} MVA</b> · {row['headroom_flag']}
        </div>
        """

        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=8,
            color=color, fill=True, fill_color=color, fill_opacity=0.7, weight=2,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=row['display_name'],
        ).add_to(m)

    map_result = st_folium(m, width=None, height=450, use_container_width=True)

    # Capture map click → select substation
    if map_result and map_result.get('last_object_clicked_tooltip'):
        clicked_name = map_result['last_object_clicked_tooltip']
        if clicked_name in filtered['display_name'].values:
            if st.session_state.selected_sub != clicked_name:
                st.session_state.selected_sub = clicked_name
                st.session_state.test_run = False
                st.rerun()

except ImportError:
    st.warning("Install folium and streamlit-folium for the map.")

# Legend
leg1, leg2, leg3, leg4 = st.columns(4)
with leg1: st.markdown("🔴 **Overcommitted**")
with leg2: st.markdown("🟡 **Tight** (<20 MVA)")
with leg3: st.markdown("🔵 **Moderate** (20-50)")
with leg4: st.markdown("🟢 **Available** (>50)")


# ============================================================
# SUBSTATION SELECTOR
# ============================================================
st.markdown("---")

sub_options = ['(Overview table)'] + sorted(filtered['display_name'].tolist())
current_idx = 0
if st.session_state.selected_sub and st.session_state.selected_sub in sub_options:
    current_idx = sub_options.index(st.session_state.selected_sub)

selected_sub = st.selectbox(
    "Select a substation",
    options=sub_options,
    index=current_idx,
    key='sub_selector',
)

# Sync selectbox with session state
if selected_sub == '(Overview table)':
    st.session_state.selected_sub = None
elif selected_sub != st.session_state.selected_sub:
    st.session_state.selected_sub = selected_sub
    st.session_state.test_run = False


# ============================================================
# OVERVIEW TABLE
# ============================================================
if st.session_state.selected_sub is None:
    display_cols = [
        'display_name', 'voltage_kv', 'total_nominal_mva', 'peak_import_mw',
        'utilisation_pct', 'connected_mva', 'accepted_mva',
        'headroom_mva', 'headroom_flag',
    ]
    rename = {
        'display_name': 'Substation', 'voltage_kv': 'kV',
        'total_nominal_mva': 'Rating (MVA)', 'peak_import_mw': 'Peak Import (MW)',
        'utilisation_pct': 'Utilisation %', 'connected_mva': 'Connected (MVA)',
        'accepted_mva': 'Accepted (MVA)',
        'headroom_mva': 'Headroom (MVA)', 'headroom_flag': 'Status',
    }
    table_df = filtered[[c for c in display_cols if c in filtered.columns]].rename(columns=rename).sort_values('Headroom (MVA)')
    st.dataframe(table_df, use_container_width=True, height=600, hide_index=True)


# ============================================================
# SUBSTATION DETAIL
# ============================================================
else:
    sub_name = st.session_state.selected_sub
    row = filtered[filtered['display_name'] == sub_name].iloc[0]

    st.markdown(f"### {row['display_name']} ({row['voltage_kv']}kV)")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### Transformer")
        rating = row.get('total_nominal_mva')
        emergency = row.get('total_emergency_mva')
        n_tx = row.get('n_transformers_ltds')
        ratings_detail = row.get('ratings_detail', '')
        st.metric("Nominal Rating", f"{rating:.0f} MVA" if pd.notna(rating) else "Unknown")
        if pd.notna(emergency):
            st.metric("Emergency Rating", f"{emergency:.0f} MVA")
        if pd.notna(n_tx):
            st.caption(f"{int(n_tx)} transformers: {ratings_detail} MVA")

    with c2:
        st.markdown("#### Measured Flows")
        peak = row.get('peak_import_mw')
        mean_imp = row.get('mean_import_mw')
        util = row.get('utilisation_pct')
        st.metric("Peak Import", f"{peak:.1f} MW" if pd.notna(peak) else "?")
        st.metric("Mean Import", f"{mean_imp:.1f} MW" if pd.notna(mean_imp) else "?")
        if pd.notna(util):
            st.caption(f"Utilisation: {util:.0f}% of nominal rating")
        if row.get('net_exporter'):
            st.warning("⚡ Net exporter — more generation than demand on average")

    with c3:
        st.markdown("#### Connection Queue")
        st.metric("Connected", f"{row.get('connected_mva', 0):.1f} MVA")
        st.metric("Accepted (not built)", f"{row.get('accepted_mva', 0):.1f} MVA")
        offered = row.get('offered_mva', 0)
        enquired = row.get('enquired_mva', 0)
        if pd.notna(offered) and offered > 0:
            st.caption(f"Offered: {offered:.1f} MVA")
        if pd.notna(enquired) and enquired > 0:
            st.caption(f"Enquired: {enquired:.1f} MVA")

    # Headroom
    st.markdown("---")
    headroom = row.get('headroom_mva')
    flag = row.get('headroom_flag', 'No data')
    if flag == 'Overcommitted':
        st.error(f"**{flag}**: Committed generation exceeds transformer rating by {abs(headroom):.0f} MVA")
    elif flag == 'Tight':
        st.warning(f"**{flag}**: Only {headroom:.0f} MVA of headroom remaining")
    elif flag in ['Moderate', 'Available']:
        st.success(f"**{flag}**: {headroom:.0f} MVA of headroom available")

    # ==============================================================
    # TEST A CONNECTION (below substation detail)
    # ==============================================================
    st.markdown("---")
    st.markdown("#### Test a connection")

    tc1, tc2, tc3, tc4 = st.columns([2, 2, 1, 1])
    with tc1:
        test_mw = st.number_input("Capacity (MW)", min_value=1, max_value=500, value=st.session_state.test_mw, step=5, key='test_mw_input')
    with tc2:
        test_tech = st.selectbox("Technology", ["Solar", "Onshore Wind", "Battery", "Other (gas, biomass, CHP)"], key='test_tech_input')
    with tc3:
        st.markdown("<br/>", unsafe_allow_html=True)
        run_clicked = st.button("🔍 Run test", use_container_width=True, type="primary")
    with tc4:
        st.markdown("<br/>", unsafe_allow_html=True)
        clear_clicked = st.button("✕ Clear", use_container_width=True)

    if run_clicked:
        st.session_state.test_run = True
        st.session_state.test_mw = test_mw
        st.session_state.test_tech = test_tech

    if clear_clicked:
        st.session_state.test_run = False
        st.rerun()

    # ==============================================================
    # CURTAILMENT RESULTS (only after Run)
    # ==============================================================
    if st.session_state.test_run:
        active_tech = st.session_state.test_tech
        active_mw = st.session_state.test_mw
        curt_tech_key = tech_map.get(active_tech, 'PV')
        tech_display = {'PV': 'Solar', 'Wind': 'Wind', 'BESS': 'Battery', 'Other': 'Other'}

        st.markdown("---")
        st.markdown(f"### Results: {active_mw} MW {active_tech} at {sub_name}")

        sub_curt = match_substation(curtailment_df, sub_name)

        if len(sub_curt) > 0 and sub_curt['curtailment_pct'].notna().any():

            # --- HEADLINE RESULT ---
            available_mws = sorted(sub_curt['capacity_mw'].unique())
            closest_mw = min(available_mws, key=lambda x: abs(x - active_mw))
            estimate = sub_curt[
                (sub_curt['technology'] == curt_tech_key) &
                (sub_curt['capacity_mw'] == closest_mw)
            ]

            if len(estimate) > 0:
                e = estimate.iloc[0]
                if pd.notna(e['curtailment_pct']):
                    pct = e['curtailment_pct']
                    lost = e['curtailed_mwh']
                    total = e['total_mwh']
                    delivered = total - lost

                    r1, r2, r3 = st.columns(3)
                    with r1:
                        st.metric("Annual Curtailment", f"{pct:.1f}%")
                    with r2:
                        st.metric("Energy Lost", f"{lost:,.0f} MWh/yr")
                    with r3:
                        st.metric("Energy Delivered", f"{delivered:,.0f} MWh/yr")

                    binding = e.get('binding_branch', '')
                    if binding and binding != 'None' and str(binding) != 'nan':
                        st.caption(f"Binding constraint: {binding}")
                    if closest_mw != active_mw:
                        st.caption(f"Estimate shown for {closest_mw} MW (closest available).")

                    if pct == 0:
                        st.success("No branch exceeds its pre-event limit at this size, even with the full queue built out.")

            # --- CURTAILMENT BY SIZE (single technology) ---
            st.markdown("---")
            st.markdown(f"#### Curtailment by size — {active_tech}")

            tech_curt = sub_curt[sub_curt['technology'] == curt_tech_key].sort_values('capacity_mw')
            if len(tech_curt) > 0:
                size_display = tech_curt[['capacity_mw', 'curtailment_pct', 'curtailed_mwh', 'total_mwh']].copy()
                size_display.columns = ['Capacity (MW)', 'Curtailment %', 'Curtailed (MWh)', 'Total (MWh)']
                size_display['Curtailment %'] = size_display['Curtailment %'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
                size_display['Curtailed (MWh)'] = size_display['Curtailed (MWh)'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
                size_display['Total (MWh)'] = size_display['Total (MWh)'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
                st.dataframe(size_display, use_container_width=True, hide_index=True)

            # --- SEASONAL HEATMAP (single technology) ---
            sub_seasonal = match_substation(seasonal_df, sub_name)
            if len(sub_seasonal) > 0:
                tech_seasonal = sub_seasonal[sub_seasonal['technology'] == curt_tech_key]
                if len(tech_seasonal) > 0 and tech_seasonal['curtailed_mwh'].sum() > 0:
                    st.markdown("---")
                    st.markdown(f"#### When does curtailment happen? — {active_tech}")

                    heatmap = tech_seasonal.pivot_table(
                        index='hour', columns='month',
                        values='curtailment_pct', aggfunc='first'
                    ).fillna(0)
                    month_names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                                  7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
                    heatmap.columns = [month_names.get(c, c) for c in heatmap.columns]
                    heatmap.index = [f"{h:02d}:00" for h in heatmap.index]
                    heatmap_display = heatmap.map(lambda x: f"{x:.0f}%" if x > 0 else "")
                    st.dataframe(heatmap_display, use_container_width=True, height=400)
                    st.caption("Curtailment % by hour and month. Empty = no curtailment.")

                    # Monthly summary
                    monthly = tech_seasonal.groupby('month').agg(
                        total=('total_mwh', 'sum'), curtailed=('curtailed_mwh', 'sum'),
                    ).reset_index()
                    monthly['Curtailment %'] = (100 * monthly['curtailed'] / monthly['total']).fillna(0).round(1)
                    monthly['Month'] = monthly['month'].map(month_names)
                    monthly['Generation (MWh)'] = monthly['total'].round(0).astype(int)
                    monthly['Curtailed (MWh)'] = monthly['curtailed'].round(0).astype(int)
                    st.dataframe(
                        monthly[['Month', 'Generation (MWh)', 'Curtailed (MWh)', 'Curtailment %']],
                        use_container_width=True, hide_index=True,
                    )

            # --- LIFO POSITION (single technology) ---
            sub_lifo = match_substation(lifo_df, sub_name)
            if len(sub_lifo) > 0:
                lifo_col = f'{curt_tech_key}_curtailment_pct'
                if lifo_col in sub_lifo.columns and sub_lifo[lifo_col].sum() > 0:
                    st.markdown("---")
                    st.markdown(f"#### Queue position sensitivity — {active_tech}")
                    st.caption("How curtailment changes depending on how many queued projects build.")

                    lifo_display = pd.DataFrame()
                    lifo_display['Position'] = sub_lifo['position_threshold'].apply(
                        lambda x: f"≤{x}" if x < 9999 else "All"
                    ).values
                    lifo_display['Queue (MW)'] = sub_lifo['queue_mw'].values
                    lifo_display[f'{active_tech} Curtailment'] = sub_lifo[lifo_col].apply(
                        lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
                    ).values
                    st.dataframe(lifo_display, use_container_width=True, hide_index=True)

            # --- CO-LOCATION (filtered to scenarios including this tech) ---
            sub_coloc = match_substation(colocation_df, sub_name)
            if len(sub_coloc) > 0 and sub_coloc['curtailment_pct'].sum() > 0:
                # Filter to scenarios relevant to the selected technology
                tech_to_col = {'PV': 'solar_mw', 'Wind': 'wind_mw', 'BESS': 'bess_mw'}
                filter_col = tech_to_col.get(curt_tech_key)
                if filter_col and filter_col in sub_coloc.columns:
                    relevant = sub_coloc[sub_coloc[filter_col] > 0]
                else:
                    relevant = sub_coloc

                if len(relevant) > 0:
                    st.markdown("---")
                    st.markdown(f"#### Hybridisation — scenarios including {active_tech}")
                    st.caption("Compare single-technology vs hybrid on the same connection.")

                    coloc_display = relevant[['scenario', 'total_mw', 'curtailment_pct', 'curtailed_mwh', 'binding_branch']].copy()
                    coloc_display.columns = ['Scenario', 'Total MW', 'Curtailment %', 'Lost MWh', 'Binding']
                    coloc_display['Binding'] = coloc_display['Binding'].replace('None', '—')
                    coloc_display['Curtailment %'] = coloc_display['Curtailment %'].apply(lambda x: f"{x:.1f}%")
                    coloc_display['Lost MWh'] = coloc_display['Lost MWh'].apply(lambda x: f"{x:,.0f}")
                    st.dataframe(coloc_display, use_container_width=True, hide_index=True)

        else:
            st.info("Curtailment data not available for this substation. It may be at a voltage level not covered by the curtailment dataset (e.g. 66kV).")

    # Data notes
    st.markdown("---")
    st.caption(f"Flow data: {row.get('date_from', '?')} to {row.get('date_to', '?')} | {row.get('n_timestamps', '?')} timestamps")
    st.caption("Headroom = nominal transformer rating − (connected + accepted generation).")
    st.caption("Curtailment uses NGED sensitivity factors, 2024 branch loading, seasonal PELs, and generic profiles. Full accepted queue projected.")


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption("**Loom Light** — Grid Connection Intelligence · ⚠️ Prototype — not for investment decisions.")
