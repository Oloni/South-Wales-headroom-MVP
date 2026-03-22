# South Wales Grid Connection Screener — MVP

## What this is

A prototype screening tool that shows, for every major substation in the South Wales 33kV/66kV/132kV network: the transformer capacity, actual measured power flows, the connection queue (connected, accepted, offered, enquired generation), and the resulting headroom — how much room is left for new connections.


## What it shows

For each of 35 substations in South Wales:

| Metric | Source | What it means |
|--------|--------|---------------|
| Transformer rating (MVA) | LTDS Table 2a | How much power the substation can physically handle |
| Peak import (MW) | BSP transformer flow CSVs | Highest actual power flow measured over a year |
| Mean import (MW) | BSP transformer flow CSVs | Average flow — negative means net exporter |
| Utilisation (%) | Computed: peak import / rating | How close to capacity the substation already runs |
| Connected generation (MVA) | Generation Connection Register | Generation already built and operating |
| Accepted generation (MVA) | Generation Connection Register | Generation with a connection agreement but not yet built |
| Offered generation (MVA) | Generation Connection Register | Connection offers made but not yet accepted |
| Enquired generation (MVA) | Generation Connection Register | Enquiries not yet offered |
| Headroom (MVA) | Computed: rating − (connected + accepted) | Room for new connections — negative = overcommitted |
| Dominant technology | Generation Connection Register | What type of generation dominates at this substation |
| Net exporter flag | Computed: mean import < 0 | Whether the substation exports more power than it imports on average |


---

## Data sources

### 1. LTDS Table 2a — Two-winding Transformer Data

**What it is:** Official transformer ratings published by NGED as part of the Long Term Development Statement. Every two-winding transformer in the NGED network with nominal and emergency MVA ratings, impedance, tap range, and vector group.

**File in this repo:** `data/ltds-table-2a-two-winding-transformer.csv`

**How we use it:** Filter to Licence = 'SWALES', Operating Voltage 1 = 132, Operating Voltage 2 in [33, 66]. Extract the 4-letter CIM code from the Node 1 column (e.g. AMMA1_#110 → AMMA = Ammanford). Sum the Nominal Rating per CIM code to get total substation capacity. This gives us the real transformer rating that the CIM file doesn't have (the CIM uses 100 MVA placeholders for everything).

**Key fields used:**
- `Licence` — filter to SWALES
- `Node 1` — contains the 4-letter CIM substation code
- `Operating Voltage 1`, `Operating Voltage 2` — filter to 132kV primary, 33/66kV secondary
- `Nominal Rating` — the continuous MVA rating
- `Emergency Rating` — the short-term overload rating

**Ratings found:** range from 22.5 MVA (single small transformer, e.g. Rhos, Lampeter) to 180 MVA (three 60 MVA transformers at Swansea North).

**Last updated:** 03/12/2025 on the NGED portal.

### 2. BSP Transformer Flow CSVs

**What it is:** Half-hourly measurements from every Bulk Supply Point (BSP) transformer in South Wales. Real sensor data: MW (active power), MVAr (reactive power), and kV (voltage) recorded every 30 minutes.

**Files in this repo:** Referenced from external directory (too large for the repo). Located at: `/Users/leonie/Documents/grid-model-experiments/BSP_transformer_flows_south_wales/`

**35 files, one per substation:**
- abergavenny-66kv-transformer-flows.csv
- ammanford-33kv-transformer-flows.csv
- bridgend-33kv-transformer-flows.csv
- ... (see full list in the build script)
- ystradgynlais-33kv-transformer-flows.csv

**Date range:** 31 March 2022 to 1 April 2023 (one full year).

**How we use it:** For each substation, filter to Reading Type = 'Import' (net power flowing from 132kV into the 33kV/66kV network). Aggregate across all transformers per timestamp. Compute peak MW, mean MW, and whether the substation is a net exporter (mean import < 0).

**Key fields:**
- `Timestamp` — half-hourly
- `Substation Name` — human-readable name
- `Transformer` — GT1, GT2, GT3 etc.
- `Reading Type` — Import, Demand, Gen, Volts
- `MW`, `MVAr`, `MVA`, `kV` — the measurements

**Key insight:** Several substations are net exporters on average (Haverfordwest, Swansea North, Rhos, Sudbrook) — they have so much connected generation that power flows backwards up into the 132kV network.

**Last updated:** 08/04/2025 on the NGED portal. Data covers 2022-2023.

### 3. Generation Connection Register (GCR)

**What it is:** Aggregated summary of all generation connected or in the queue at each BSP, broken down by technology and pipeline stage. Published by NGED.

**Where to get it:** https://connecteddata.nationalgrid.co.uk → search "generation connection register" or look for the GCR dataset.

**File in this repo:** `data/gcr.csv`

**How we use it:** Filter to Licence_Area = 'South Wales'. Group by BSP. Sum the four capacity columns to get total connected, accepted, offered, and enquired generation per substation. Identify dominant technology per substation.

**Key fields:**
- `BSP` — substation name (NGED's naming convention, e.g. "Ammanford Grid", "Swansea North Bsp")
- `Licence_Area` — filter to South Wales
- `Generator_Technology` — solar, wind, battery, etc.
- `Voltage` — connection voltage
- `Latest_Connected_Export_Capacity_kVA` — generation already built
- `Latest_Accepted_not_yet_Connected_Export_Capacity_kVA` — has connection agreement, not yet built
- `Latest_Offered_not_yet_Accepted_Export_Capacity_kVA` — offered but not accepted
- `Latest_Enquired_not_yet_Offered_Export_Capacity_kVA` — enquiries only

**Why we use this instead of the ECR:** The GCR has four pipeline stages (connected, accepted, offered, enquired). The ECR (Embedded Capacity Register, also downloaded as `nged_ecr_jan_2026.csv`) only has two (connected, accepted). The GCR also aggregates by BSP already, saving us the need to match individual project addresses to substations.

**Coverage:** 60 BSPs in South Wales, of which 33 match to our 35 flow file substations. The unmatched GCR BSPs are either 132kV direct connections, substations without flow files, or naming mismatches.

### 4. CIM File (used for cross-referencing only)

**What it is:** NGED's Common Information Model file for South Wales — the complete engineering model of the network in XML format. Contains every line, transformer, busbar, breaker, and switch.

**File:** `data/LTDS_SWALES_2025-02_EQ_2025-09-19_v1_0.xml`

**How we use it in this MVP:** Only for cross-referencing substation names and verifying transformer counts. We do NOT use the CIM's transformer ratings (they are all 100 MVA placeholders). We do NOT run power flow in this MVP.

**Note:** Parsing the CIM for network topology is complex.

### 5. Embedded Capacity Register (ECR) — supplementary

**What it is:** Project-level detail for every distributed generator in the NGED network. Individual sites with addresses, lat/long, MW, technology, connection date.

**File:** `data/nged_ecr_jan_2026.csv`

**How we use it:** We used the ECR's lat/long coordinates (averaged per BSP) to get approximate substation locations for the map. We do not use the ECR's capacity data in the headroom calculation (the GCR is better for that because it has all four pipeline stages).


---

## Name matching

The biggest challenge in this project is that every data source uses different names for the same substations:

| BSP Flow File | GCR Name | LTDS/CIM Code | Display Name |
|---|---|---|---|
| ammanford-33kv | Ammanford Grid | AMMA | Ammanford |
| swansea-north-33kv | Swansea North Bsp | SWAN | Swansea North |
| cardiff-east-33kv | Cardiff East Grid Bsp | CARE | Cardiff East |

The full matching table is in `01_build_substation_table.py` as the `SUBSTATION_NAMES` DataFrame. This was built by hand and should be checked carefully if extending to other regions.

**Known mapping issues:**
- **Upper Boat** is mapped to CIM code YSTR (Ystradgynlais transformers), but in the LTDS it appears as its own GSP group containing DOWL and MOUA transformers. The headroom number for Upper Boat (-285 MVA) is probably wrong because of this.
- **Brynhill** is mapped to "Barry Grid" in the GCR — this is a guess based on geographic proximity.
- **Gowerton East** and **Milford Haven** don't match to any GCR BSP, so they show no queue data.
- **Grange** shows 251% utilisation (113 MW peak through 45 MVA transformers) which suggests the MAGA CIM code mapping may be incomplete — there may be additional transformers feeding Grange that aren't captured.


---

## How headroom is calculated

```
headroom = total_nominal_mva − (connected_mva + accepted_mva)
```

Where:
- `total_nominal_mva` = sum of Nominal Rating from LTDS Table 2a for all 132/33kV or 132/66kV transformers at this substation
- `connected_mva` = sum of Latest_Connected_Export_Capacity from GCR
- `accepted_mva` = sum of Latest_Accepted_not_yet_Connected_Export_Capacity from GCR

**Negative headroom** means the committed generation (connected + accepted) exceeds the transformer's continuous rating on paper.

**This is deliberately conservative / simplistic.** It does NOT account for:
- **Diversity** — not all generators run at full output simultaneously (solar generates nothing at night, wind is intermittent)
- **Demand** — substations also serve load, which offsets generation
- **Curtailment** — many connections have curtailment arrangements allowing the DNO to reduce output when the network is congested
- **Queue attrition** — An estimated 40-60% of accepted battery projects and 20-30% of solar projects will never actually connect
- **Planned reinforcements** — NGED may be upgrading transformers or building new circuits
- **ANM zones** — some substations have Active Network Management that dynamically manages generation output

The headroom number should be read as "how oversubscribed is this substation on paper" — a screening signal, not a definitive answer. Substations with large negative headroom have high connection risk. Substations with positive headroom are more likely to have capacity available.

---

## File structure

```
South_Wales_headroom_MVP/
├── README.md                              ← this file
├── requirements.txt                       ← Python dependencies
├── data/
│   ├── south_wales_substations.csv        ← OUTPUT: the joined table (35 rows)
│   ├── gcr.csv                            ← NGED Generation Connection Register
│   ├── nged_ecr_jan_2026.csv              ← NGED Embedded Capacity Register (supplementary)
│   ├── ltds-table-2a-two-winding-transformer.csv  ← NGED LTDS transformer ratings
│   └── LTDS_SWALES_2025-02_EQ_2025-09-19_v1_0.xml  ← CIM file (for reference)
├── notebooks/
│   └── 01_build_substation_table.py       ← Data pipeline: joins all sources
└── app/
    └── app.py                             ← Streamlit screening tool
```

BSP transformer flow files are stored externally at:
`/Users/leonie/Documents/grid-model-experiments/BSP_transformer_flows_south_wales/`
(35 CSV files, ~140k rows each, too large to include in repo)


---

## Data freshness

| Dataset | Date of data | Last updated on portal |
|---------|-------------|----------------------|
| BSP Transformer Flows | Mar 2022 – Apr 2023 | 08/04/2025 |
| LTDS Table 2a | Current network | 03/12/2025 |
| GCR | Current queue | Downloaded Jan 2026 |
| ECR | Current connections | 15/01/2026 |
| CIM file | Feb 2025 snapshot | 10/02/2026 |

The flow data is the oldest — it covers 2022-2023. If NGED publishes updated flows, refreshing this would improve the utilisation numbers.


---
