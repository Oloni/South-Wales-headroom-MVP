"""
South Wales Grid Connection Screener
=====================================
Streamlit app with headroom, curtailment, seasonal heatmaps,
queue position sensitivity, and hybridisation analysis.
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
    initial_sidebar_state="expanded",
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
# DATA PATHS
# ============================================================
def find_data_path(filename):
    for prefix in ['../data/', 'data/']:
        if os.path.exists(prefix + filename):
            return prefix + filename
    return None

# ============================================================
# LOAD DATA
# ============================================================
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

tech_map = {"Solar": "PV", "Onshore Wind": "Wind", "Battery": "BESS", "Other": "Other"}


# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.markdown("## ⚡ Loom Light")
st.sidebar.markdown("**Grid Connection Screener**")
st.sidebar.markdown("South Wales · 132/33kV & 132/66kV BSPs")
st.sidebar.divider()

headroom_options = ['All', 'Overcommitted', 'Tight', 'Moderate', 'Available']
selected_headroom = st.sidebar.selectbox("Filter by headroom", headroom_options)

st.sidebar.divider()
st.sidebar.markdown("### Test a connection")

# Use session state for test MW so we can clear it
if 'test_mw' not in st.session_state:
    st.session_state.test_mw = 0

test_mw = st.sidebar.number_input(
    "Proposed capacity (MW)", min_value=0, max_value=500,
    value=st.session_state.test_mw, step=5, key='test_mw_input'
)
st.session_state.test_mw = test_mw

test_tech = st.sidebar.selectbox("Technology", ["Solar", "Onshore Wind", "Battery", "Other"])

if test_mw > 0:
    if st.sidebar.button("Clear test"):
        st.session_state.test_mw = 0
        st.rerun()

# Apply filters
filtered = df.copy()
if selected_headroom != 'All':
    filtered = filtered[filtered['headroom_flag'] == selected_headroom]


# ============================================================
# HEADER
# ============================================================
st.markdown("# South Wales Grid Connection Screener")
st.markdown("Transformer ratings · measured flows · connection queue · headroom · curtailment estimates")
st.caption("📅 Flows: Mar 2022 – Apr 2023 · Ratings: Dec 2025 · Queue: Jan 2026 · Curtailment: Mar 2026")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Substations", len(filtered))
with col2:
    st.metric("Overcommitted", (filtered['headroom_flag'] == 'Overcommitted').sum())
with col3:
    st.metric("Tight", (filtered['headroom_flag'] == 'Tight').sum())
with col4:
    st.metric("Available / Moderate", filtered['headroom_flag'].isin(['Moderate', 'Available']).sum())


# ============================================================
# MAP
# ============================================================
st.markdown("---")

map_df = filtered.dropna(subset=['lat', 'lon']).copy()

# Add curtailment to map popups if testing
if test_mw > 0 and curtailment_df is not None:
    curt_tech = tech_map.get(test_tech, 'PV')
    available_mws = sorted(curtailment_df['capacity_mw'].unique())
    closest_mw = min(available_mws, key=lambda x: abs(x - test_mw))
    curt_slice = curtailment_df[
        (curtailment_df['technology'] == curt_tech) &
        (curtailment_df['capacity_mw'] == closest_mw)
    ][['substation', 'curtailment_pct', 'binding_branch']].copy()
    curt_slice = curt_slice.rename(columns={'substation': 'display_name'})
    map_df = map_df.merge(curt_slice, on='display_name', how='left')

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

        curt_html = ""
        if 'curtailment_pct' in row.index and pd.notna(row.get('curtailment_pct')):
            curt_pct = row['curtailment_pct']
            binding = row.get('binding_branch', '')
            curt_color = '#dc3545' if curt_pct > 5 else '#f0a028' if curt_pct > 1 else '#32b450'
            binding_html = f"<br/>Binding: {binding}" if binding and binding != 'None' and str(binding) != 'nan' else ""
            curt_html = f"""
            <hr style="margin: 4px 0;">
            <b style="color: {curt_color}">
            Curtailment ({test_mw}MW {test_tech}): {curt_pct:.1f}%</b>
            {binding_html}
            """

        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 13px; min-width: 220px;">
            <b>{row['display_name']}</b> ({row['voltage_kv']}kV)<br/>
            <hr style="margin: 4px 0;">
            Rating: {rating_str} MVA | Peak: {peak_str} MW<br/>
            <hr style="margin: 4px 0;">
            Connected: {connected_str} MVA<br/>
            Accepted: {accepted_str} MVA<br/>
            <b>Headroom: {headroom_str} MVA</b><br/>
            Status: <b>{row['headroom_flag']}</b>
            {curt_html}
        </div>
        """

        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=8,
            color=color, fill=True, fill_color=color, fill_opacity=0.7, weight=2,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row['display_name']}: {headroom_str} MVA headroom",
        ).add_to(m)

    st_folium(m, width=None, height=500, use_container_width=True)

except ImportError:
    st.warning("Install folium and streamlit-folium for the map.")

leg1, leg2, leg3, leg4 = st.columns(4)
with leg1: st.markdown("🔴 **Overcommitted** — committed > rating")
with leg2: st.markdown("🟡 **Tight** — <20 MVA headroom")
with leg3: st.markdown("🔵 **Moderate** — 20-50 MVA headroom")
with leg4: st.markdown("🟢 **Available** — >50 MVA headroom")

if test_mw > 0:
    st.info(f"Popups show curtailment estimate for **{test_mw} MW {test_tech}**. Select a substation below for seasonal breakdown, queue sensitivity, and hybridisation analysis.")


# ============================================================
# SUBSTATION DETAIL
# ============================================================
st.markdown("---")
st.markdown("## Substation Details")

selected_sub = st.selectbox(
    "Select a substation",
    options=['(Overview table)'] + sorted(filtered['display_name'].tolist()),
    key='substation_selector',
)

if selected_sub == '(Overview table)':
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

else:
    row = filtered[filtered['display_name'] == selected_sub].iloc[0]

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

    # ==================================================================
    # CURTAILMENT TABLE
    # ==================================================================
    if curtailment_df is not None:
        sub_curt = curtailment_df[curtailment_df['substation'] == selected_sub]

        if len(sub_curt) > 0 and sub_curt['curtailment_pct'].notna().any():
            st.markdown("---")
            st.markdown("#### Curtailment Estimates")
            st.caption("Estimated annual curtailment for a new generator, assuming all accepted projects are built.")

            # Build pivot table as plain dataframe (no .style — avoids Streamlit Cloud errors)
            pivot = sub_curt.pivot_table(
                index='technology', columns='capacity_mw',
                values='curtailment_pct', aggfunc='first'
            )
            pivot.index = pivot.index.map({'PV': 'Solar', 'Wind': 'Wind', 'BESS': 'Battery'})
            pivot.columns = [f"{int(c)} MW" for c in pivot.columns]
            # Format values as strings with %
            pivot_display = pivot.map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
            st.dataframe(pivot_display, use_container_width=True)

            # Binding constraint
            binding_info = sub_curt[sub_curt['capacity_mw'] == 20].groupby('technology')['binding_branch'].first()
            bindings = [f"{t}: {b}" for t, b in binding_info.items() if b != 'None' and str(b) != 'nan']
            if bindings:
                st.caption(f"Binding constraints (20MW): {' · '.join(bindings)}")

            # Test connection result
            if test_mw > 0:
                curt_tech = tech_map.get(test_tech, 'PV')
                available_mws = sorted(sub_curt['capacity_mw'].unique())
                closest_mw = min(available_mws, key=lambda x: abs(x - test_mw))
                estimate = sub_curt[
                    (sub_curt['technology'] == curt_tech) &
                    (sub_curt['capacity_mw'] == closest_mw)
                ]
                if len(estimate) > 0:
                    e = estimate.iloc[0]
                    if pd.notna(e['curtailment_pct']):
                        pct = e['curtailment_pct']
                        lost = e['curtailed_mwh']
                        if pct > 5:
                            st.error(f"**{test_mw} MW {test_tech}**: ~{pct:.1f}% curtailment ({lost:.0f} MWh/year lost)")
                        elif pct > 1:
                            st.warning(f"**{test_mw} MW {test_tech}**: ~{pct:.1f}% curtailment ({lost:.0f} MWh/year lost)")
                        elif pct > 0:
                            st.info(f"**{test_mw} MW {test_tech}**: ~{pct:.1f}% curtailment ({lost:.0f} MWh/year lost)")
                        else:
                            st.success(f"**{test_mw} MW {test_tech}**: no curtailment estimated")
                        binding = e.get('binding_branch', '')
                        if binding and binding != 'None' and str(binding) != 'nan':
                            st.caption(f"Binding constraint: {binding}")
                        if closest_mw != test_mw:
                            st.caption(f"Note: estimate shown for {closest_mw} MW (closest available).")

            # ==============================================================
            # SEASONAL HEATMAP
            # ==============================================================
            if seasonal_df is not None:
                sub_seasonal = seasonal_df[seasonal_df['substation'] == selected_sub]
                if len(sub_seasonal) > 0 and sub_seasonal['curtailed_mwh'].sum() > 0:
                    st.markdown("---")
                    st.markdown("#### When does curtailment happen?")

                    heatmap_tech = st.radio(
                        "Technology", ['Solar', 'Wind', 'Battery'],
                        horizontal=True, key='hm_tech'
                    )
                    tech_key = {'Solar': 'PV', 'Wind': 'Wind', 'Battery': 'BESS'}[heatmap_tech]
                    tech_seasonal = sub_seasonal[sub_seasonal['technology'] == tech_key]

                    if len(tech_seasonal) > 0 and tech_seasonal['curtailed_mwh'].sum() > 0:
                        heatmap = tech_seasonal.pivot_table(
                            index='hour', columns='month',
                            values='curtailment_pct', aggfunc='first'
                        ).fillna(0)

                        month_names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                                      7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
                        heatmap.columns = [month_names.get(c, c) for c in heatmap.columns]
                        heatmap.index = [f"{h:02d}:00" for h in heatmap.index]

                        # Display as plain dataframe with % formatting
                        heatmap_display = heatmap.map(lambda x: f"{x:.0f}%" if x > 0 else "")
                        st.dataframe(heatmap_display, use_container_width=True, height=400)
                        st.caption(f"Curtailment % by hour and month for 20MW {heatmap_tech}. Empty cells = no curtailment.")

                        # Monthly summary
                        monthly = tech_seasonal.groupby('month').agg(
                            total=('total_mwh', 'sum'), curtailed=('curtailed_mwh', 'sum'),
                        ).reset_index()
                        monthly['Curtailment %'] = (100 * monthly['curtailed'] / monthly['total']).fillna(0).round(1)
                        monthly['Month'] = monthly['month'].map(month_names)
                        monthly['Generation (MWh)'] = monthly['total'].round(0).astype(int)
                        monthly['Curtailed (MWh)'] = monthly['curtailed'].round(0).astype(int)

                        st.markdown(f"**Monthly summary — 20MW {heatmap_tech}:**")
                        st.dataframe(
                            monthly[['Month', 'Generation (MWh)', 'Curtailed (MWh)', 'Curtailment %']],
                            use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption(f"No curtailment for 20MW {heatmap_tech} at this substation.")

            # ==============================================================
            # LIFO POSITION SENSITIVITY
            # ==============================================================
            if lifo_df is not None:
                sub_lifo = lifo_df[lifo_df['substation'] == selected_sub]
                if len(sub_lifo) > 0:
                    has_lifo_data = False
                    for tech in ['PV', 'Wind', 'BESS']:
                        col = f'{tech}_curtailment_pct'
                        if col in sub_lifo.columns and sub_lifo[col].sum() > 0:
                            has_lifo_data = True

                    if has_lifo_data:
                        st.markdown("---")
                        st.markdown("#### Queue position sensitivity")
                        st.caption("How curtailment changes depending on how many queued projects actually build.")

                        lifo_display = pd.DataFrame()
                        lifo_display['Position'] = sub_lifo['position_threshold'].apply(
                            lambda x: f"≤{x}" if x < 9999 else "All"
                        )
                        lifo_display['Queue (MW)'] = sub_lifo['queue_mw'].values

                        for tech, label in [('PV','Solar'), ('Wind','Wind'), ('BESS','Battery')]:
                            col = f'{tech}_curtailment_pct'
                            if col in sub_lifo.columns:
                                lifo_display[label] = sub_lifo[col].apply(
                                    lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
                                ).values

                        st.dataframe(lifo_display, use_container_width=True, hide_index=True)

            # ==============================================================
            # CO-LOCATION / HYBRIDISATION
            # ==============================================================
            if colocation_df is not None:
                sub_coloc = colocation_df[colocation_df['substation'] == selected_sub]
                if len(sub_coloc) > 0 and sub_coloc['curtailment_pct'].sum() > 0:
                    st.markdown("---")
                    st.markdown("#### Hybridisation analysis")
                    st.caption("Curtailment for combined technologies on the same connection.")

                    coloc_display = sub_coloc[['scenario', 'total_mw', 'curtailment_pct', 'curtailed_mwh', 'binding_branch']].copy()
                    coloc_display.columns = ['Scenario', 'Total MW', 'Curtailment %', 'Lost MWh', 'Binding Constraint']
                    coloc_display['Binding Constraint'] = coloc_display['Binding Constraint'].replace('None', '—')
                    coloc_display['Curtailment %'] = coloc_display['Curtailment %'].apply(lambda x: f"{x:.1f}%")
                    coloc_display['Lost MWh'] = coloc_display['Lost MWh'].apply(lambda x: f"{x:,.0f}")

                    st.dataframe(coloc_display, use_container_width=True, hide_index=True)

        else:
            st.markdown("---")
            st.info("Curtailment data not available for this substation. It may be at a voltage level not covered by the curtailment dataset.")

    # Data notes
    st.markdown("---")
    st.caption(f"Flow data: {row.get('date_from', '?')} to {row.get('date_to', '?')} | {row.get('n_timestamps', '?')} timestamps")
    st.caption("Headroom = nominal transformer rating − (connected + accepted generation).")
    st.caption("Curtailment uses NGED's published sensitivity factors, 2024 branch loading, seasonal PELs, and generic generator profiles. Queue projected using all accepted projects.")


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption("**Loom Light** — Grid Connection Intelligence")
st.caption("Data: NGED LTDS Table 2a, BSP transformer flows, Generation Connection Register, Curtailment analysis data (Mar 2026)")
st.caption("⚠️ Prototype — not for investment decisions. Does not account for abnormal running, ANM interactions, or demand growth.")
