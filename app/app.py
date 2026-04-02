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
buildout_df = load_csv_or_none('south_wales_curtailment_buildout.csv')
colocation_df = load_csv_or_none('south_wales_curtailment_colocation.csv')
confidence_df = load_csv_or_none('south_wales_curtailment_confidence.csv')

# Load methodology text
methodology_text = ""
for prefix in ['../data/', 'data/', '../', '']:
    mpath = prefix + 'README_methodology.md'
    if os.path.exists(mpath):
        with open(mpath) as f:
            methodology_text = f.read()
        break

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
if 'test_run' not in st.session_state:
    st.session_state.test_run = False
if 'test_mw' not in st.session_state:
    st.session_state.test_mw = 20
if 'test_tech' not in st.session_state:
    st.session_state.test_tech = 'Solar'
if 'power_price' not in st.session_state:
    st.session_state.power_price = 50.0
if 'discount_rate' not in st.session_state:
    st.session_state.discount_rate = 8.0
if 'project_life' not in st.session_state:
    st.session_state.project_life = 25


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
hdr1, hdr2 = st.columns([5, 1])
with hdr1:
    st.markdown("# South Wales Grid Connection Screener")
with hdr2:
    st.markdown("<br/>", unsafe_allow_html=True)
    if st.button("📄 Methodology", use_container_width=True):
        st.session_state.show_methodology = not st.session_state.get('show_methodology', False)

if st.session_state.get('show_methodology', False):
    with st.expander("Methodology & Assumptions", expanded=True):
        if methodology_text:
            st.markdown(methodology_text)
        else:
            st.info("Methodology document not found. Please ensure README_methodology.md is in the data or app directory.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
with col1: st.metric("Substations", len(filtered))
with col2: st.metric("Overcommitted", (filtered['headroom_flag'] == 'Overcommitted').sum())
with col3: st.metric("Tight", (filtered['headroom_flag'] == 'Tight').sum())
with col4: st.metric("Available / Moderate", filtered['headroom_flag'].isin(['Moderate', 'Available']).sum())

st.caption("**Headroom data** covers 35 BSP substations at 33kV, 66kV and 132kV across all of South Wales. **Curtailment estimates** cover 162 connection points at 33kV across all 7 GSP zones. Substations connecting at 66kV or above may not have curtailment data.")


# ============================================================
# MAP
# ============================================================
map_df = filtered.dropna(subset=['lat', 'lon']).copy()

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

    st_folium(m, width=None, height=450, use_container_width=True, returned_objects=[])

except ImportError:
    st.warning("Install folium and streamlit-folium for the map.")

# Legend
leg1, leg2, leg3, leg4 = st.columns(4)
with leg1: st.markdown("🔴 **Overcommitted**")
with leg2: st.markdown("🟡 **Tight** (<20 MVA)")
with leg3: st.markdown("🔵 **Moderate** (20-50)")
with leg4: st.markdown("🟢 **Available** (>50)")


# ============================================================
# SUBSTATION SELECTOR (sole control for substation selection)
# ============================================================
st.markdown("---")

sub_options = ['(Overview table)'] + sorted(filtered['display_name'].tolist())

selected_sub = st.selectbox(
    "Select a substation",
    options=sub_options,
    key='sub_selector',
)

# Reset test when substation changes
if 'prev_sub' not in st.session_state:
    st.session_state.prev_sub = selected_sub
if selected_sub != st.session_state.prev_sub:
    st.session_state.test_run = False
    st.session_state.prev_sub = selected_sub


# ============================================================
# OVERVIEW TABLE
# ============================================================
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


# ============================================================
# SUBSTATION DETAIL
# ============================================================
else:
    sub_name = selected_sub
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

    # ANM zone flags
    has_tanm = row.get('has_tanm', False)
    has_danm = row.get('has_danm', False)
    if has_tanm and has_danm:
        st.info("⚡ **Transmission & Distribution ANM zone** — curtailment at this substation is managed in real-time by both NESO (transmission) and NGED DERMS (distribution).")
    elif has_tanm:
        st.info("⚡ **Transmission ANM zone** — curtailment at this substation is managed in real-time by NESO. Our estimates replicate what the ANM system enforces; SCADA data reflects post-ANM conditions.")
    elif has_danm:
        st.info("⚡ **Distribution ANM zone** — curtailment at this substation is managed in real-time by NGED's DERMS system.")

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

    # Revenue assumptions (collapsible)
    with st.expander("Revenue assumptions", expanded=False):
        rev1, rev2, rev3 = st.columns(3)
        with rev1:
            power_price = st.number_input("Power price (£/MWh)", min_value=0.0, max_value=500.0, value=50.0, step=5.0, key='power_price_input')
        with rev2:
            discount_rate = st.number_input("Discount rate (%)", min_value=0.0, max_value=30.0, value=8.0, step=0.5, key='discount_rate_input')
        with rev3:
            project_life = st.number_input("Project life (years)", min_value=1, max_value=40, value=25, step=1, key='project_life_input')

    if run_clicked:
        st.session_state.test_run = True
        st.session_state.test_mw = test_mw
        st.session_state.test_tech = test_tech
        st.session_state.power_price = power_price
        st.session_state.discount_rate = discount_rate
        st.session_state.project_life = project_life
        st.rerun()

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

                    # Get revenue assumptions
                    pp = st.session_state.get('power_price', 50.0)
                    dr = st.session_state.get('discount_rate', 8.0) / 100
                    life = st.session_state.get('project_life', 25)

                    # Revenue calculations
                    annual_revenue_uncurtailed = total * pp
                    annual_revenue_curtailed = delivered * pp
                    annual_revenue_lost = lost * pp

                    # NPV of revenue lost over project life
                    if dr > 0:
                        npv_factor = (1 - (1 + dr) ** -life) / dr
                    else:
                        npv_factor = life
                    npv_lost = annual_revenue_lost * npv_factor

                    r1, r2, r3 = st.columns(3)
                    with r1:
                        st.metric("Annual Curtailment", f"{pct:.1f}%")
                    with r2:
                        st.metric("Energy Curtailed", f"{lost:,.0f} MWh/yr")
                    with r3:
                        st.metric("Energy Exported", f"{delivered:,.0f} MWh/yr")

                    if pct > 0:
                        rv1, rv2, rv3 = st.columns(3)
                        with rv1:
                            st.metric("Annual Revenue Lost", f"£{annual_revenue_lost:,.0f}")
                        with rv2:
                            st.metric("Annual Revenue (after curtailment)", f"£{annual_revenue_curtailed:,.0f}")
                        with rv3:
                            st.metric(f"NPV of Lost Revenue ({life}yr)", f"£{npv_lost:,.0f}")
                        st.caption(f"At £{pp:.0f}/MWh, {dr*100:.0f}% discount rate, {life}-year project life. Change assumptions in 'Revenue assumptions' above.")

                    binding = e.get('binding_branch', '')
                    if binding and binding != 'None' and str(binding) != 'nan':
                        st.caption(f"Binding constraint: {binding}")

                    # Model confidence from SCADA validation
                    if confidence_df is not None:
                        conf_match = match_substation(confidence_df, sub_name)
                        if len(conf_match) > 0:
                            conf_row = conf_match[
                                (conf_match['technology'] == curt_tech_key) &
                                (conf_match['capacity_mw'] == closest_mw)
                            ]
                            if len(conf_row) > 0:
                                conf = conf_row.iloc[0]
                                conf_level = conf.get('confidence', 'Unknown')
                                conf_reason = conf.get('confidence_reason', '')
                                if conf_level == 'High':
                                    st.success(f"🟢 **Model confidence: High** — {conf_reason}")
                                elif conf_level == 'Moderate':
                                    st.info(f"🔵 **Model confidence: Moderate** — {conf_reason}")
                                elif conf_level == 'Low':
                                    st.warning(f"🟡 **Model confidence: Low** — {conf_reason}")
                                elif conf_level == 'Very Low':
                                    st.error(f"🔴 **Model confidence: Very Low** — {conf_reason}")

                                # ANM context on confidence
                                if has_tanm or has_danm:
                                    anm_type = "Transmission ANM (NESO)" if has_tanm and not has_danm else "Distribution ANM (NGED DERMS)" if has_danm and not has_tanm else "Transmission & Distribution ANM"
                                    st.caption(f"This substation is in a {anm_type} zone. Any divergence between the model and SCADA may partly reflect ANM actively curtailing generators to keep flows within limits — meaning the real network is better managed than the planning model alone would suggest.")

                    if closest_mw != active_mw:
                        st.caption(f"Estimate shown for {closest_mw} MW (closest available).")

                    # BESS profile warning
                    if curt_tech_key == 'BESS':
                        st.warning("⚠️ **BESS profile caveat:** This estimate uses NGED's generic battery export profile, which assumes a fixed daily pattern. Our SCADA validation at Newport South found that actual BESS dispatch diverges significantly from this profile — real batteries operate market-driven strategies that vary by site and by day. Treat BESS curtailment estimates with more caution than solar or wind.")

                    if pct == 0:
                        st.success("No branch exceeds its pre-event limit at this size, even with the full queue built out.")
                        if flag == 'Overcommitted':
                            st.caption("This substation appears overcommitted on a transformer-headroom basis (committed generation exceeds the nominal rating). However, the branch-level curtailment analysis shows no constraint is breached. This can happen because: (1) local demand absorbs generation before it reaches the transformer, (2) sensitivity factors route generation across multiple branches rather than all through the BSP transformer, or (3) the pre-event limit accounts for emergency ratings and demand offsets that the simple headroom metric ignores. The curtailment analysis is more accurate than the headline headroom number.")
                else:
                    st.info(f"No curtailment estimate available for {active_tech} at this substation.")
            else:
                st.info(f"No curtailment estimate available for {active_tech} at this substation.")

            # --- CURTAILMENT BY SIZE (single technology) ---
            st.markdown("---")
            st.markdown(f"#### Curtailment by size — {active_tech}")

            tech_curt = sub_curt[sub_curt['technology'] == curt_tech_key].sort_values('capacity_mw')
            if len(tech_curt) > 0:
                pp = st.session_state.get('power_price', 50.0)
                size_display = tech_curt[['capacity_mw', 'curtailment_pct', 'curtailed_mwh', 'total_mwh']].copy()
                size_display['revenue_lost'] = size_display['curtailed_mwh'] * pp
                size_display.columns = ['Capacity (MW)', 'Curtailment %', 'Curtailed (MWh)', 'Total (MWh)', 'Revenue Lost (£/yr)']
                size_display['Curtailment %'] = size_display['Curtailment %'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
                size_display['Curtailed (MWh)'] = size_display['Curtailed (MWh)'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
                size_display['Total (MWh)'] = size_display['Total (MWh)'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
                size_display['Revenue Lost (£/yr)'] = size_display['Revenue Lost (£/yr)'].apply(lambda x: f"£{x:,.0f}" if pd.notna(x) else "—")
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
                else:
                    st.markdown("---")
                    st.caption(f"ℹ️ No seasonal breakdown shown — {active_tech} curtailment is 0% in all months at 20MW.")
            else:
                st.markdown("---")
                st.caption(f"ℹ️ No seasonal data available for {sub_name}.")

            # --- LIFO POSITION (proper — who gets curtailed first) ---
            sub_lifo = match_substation(lifo_df, sub_name)
            if len(sub_lifo) > 0 and 'technology' in sub_lifo.columns:
                tech_lifo = sub_lifo[sub_lifo['technology'] == curt_tech_key]
                if len(tech_lifo) > 0 and tech_lifo['curtailment_pct'].notna().any() and tech_lifo['curtailment_pct'].max() > 0:
                    st.markdown("---")
                    st.markdown(f"#### LIFO queue position — {active_tech}")
                    st.caption("Under LIFO, generators behind you (newer) get curtailed before you. Lower position = less curtailment.")

                    lifo_display = pd.DataFrame()
                    if 'position_label' in tech_lifo.columns:
                        lifo_display['Your Position'] = tech_lifo['position_label'].values
                    else:
                        lifo_display['Your Position'] = tech_lifo['my_position'].apply(
                            lambda x: f"#{x}" if x < 9999 else "Last"
                        ).values
                    if 'n_projects_ahead' in tech_lifo.columns:
                        lifo_display['Projects Ahead'] = tech_lifo['n_projects_ahead'].values
                    lifo_display['Curtailment'] = tech_lifo['curtailment_pct'].apply(
                        lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
                    ).values
                    lifo_display['Energy Lost (MWh)'] = tech_lifo['curtailed_mwh'].apply(
                        lambda x: f"{x:,.0f}" if pd.notna(x) else "—"
                    ).values
                    st.dataframe(lifo_display, use_container_width=True, hide_index=True)
                else:
                    st.markdown("---")
                    st.caption(f"ℹ️ No LIFO sensitivity shown — {active_tech} curtailment is 0% at all queue positions at this substation.")
            else:
                st.markdown("---")
                st.caption(f"ℹ️ No LIFO data available for {sub_name}.")

            # --- QUEUE BUILD-OUT (what if projects don't build?) ---
            sub_buildout = match_substation(buildout_df, sub_name)
            if len(sub_buildout) > 0:
                bo_col = f'{curt_tech_key}_curtailment_pct'
                if bo_col in sub_buildout.columns and sub_buildout[bo_col].max() > 0:
                    st.markdown("---")
                    st.markdown(f"#### Queue build-out sensitivity — {active_tech}")
                    st.caption("What if not all accepted projects actually build? Shows curtailment under different build-out assumptions.")

                    bo_display = pd.DataFrame()
                    if 'n_projects' in sub_buildout.columns:
                        bo_display['Projects Built'] = sub_buildout['n_projects'].values
                    bo_display['Up to Position'] = sub_buildout['position_threshold'].apply(
                        lambda x: f"≤{x}" if x < 9999 else "All"
                    ).values
                    bo_display['Queue (MW)'] = sub_buildout['queue_mw'].values
                    bo_display[f'{active_tech} Curtailment'] = sub_buildout[bo_col].apply(
                        lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
                    ).values
                    st.dataframe(bo_display, use_container_width=True, hide_index=True)
                else:
                    st.markdown("---")
                    st.caption(f"ℹ️ No queue build-out sensitivity shown — {active_tech} curtailment is 0% regardless of how many projects build.")
            else:
                st.markdown("---")
                st.caption(f"ℹ️ No queue build-out data available for {sub_name}.")

            # --- CO-LOCATION (filtered to scenarios including this tech) ---
            sub_coloc = match_substation(colocation_df, sub_name)
            if len(sub_coloc) > 0:
                if sub_coloc['curtailment_pct'].sum() > 0:
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
                    st.markdown("---")
                    st.caption(f"ℹ️ No hybridisation analysis shown — all technology combinations show 0% curtailment at this substation.")
            else:
                st.markdown("---")
                st.caption(f"ℹ️ No hybridisation data available for {sub_name}.")

        elif len(sub_curt) == 0:
            st.info(f"No curtailment data available for {sub_name}. This substation may be at a voltage level (e.g. 66kV) not covered by the curtailment dataset.")
        else:
            st.info(f"Curtailment data for {sub_name} has no valid estimates. The substation may not have sensitivity factors in the NGED dataset.")

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
st.caption("Supported by NGED Open Data. Data: NGED LTDS, BSP transformer flows, Generation Connection Register, sensitivity factors, branch loading, pre-event limits (Mar 2026).")
st.caption("Model confidence ratings derived from validation against 17,568 half-hours of SCADA measurements.")
