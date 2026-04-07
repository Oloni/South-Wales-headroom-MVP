# South Wales Grid Connection Screener — Methodology & User Guide

## What this tool does

For every major substation in the South Wales 33kV/66kV/132kV network, this tool shows:

1. **Headroom** — transformer rating minus committed generation
2. **Curtailment estimate** — for a proposed new generator of any size and technology
3. **Model confidence** — SCADA-validated rating of how reliable the estimate is
4. **Revenue impact** — annual revenue lost and NPV of curtailment over the project life
5. **ANM zone status** — whether the substation is in a Transmission or Distribution Active Network Management zone
6. **DNOA constraint status** — whether NGED has identified a constraint at this substation and what decision has been taken (reinforce, flexibility, or signpost)
7. **Seasonal breakdown** — when during the year curtailment occurs (by hour and month)
8. **LIFO queue position** — how curtailment changes depending on your position in the connection queue
9. **Queue build-out scenarios** — how curtailment changes if projects in the queue don't build
10. **Hybridisation analysis** — curtailment for combined technologies on the same connection
11. **Regulatory scenario comparison** — how curtailment changes under different regulatory futures (queue attrition post-Gate 2, reinforcement, NESO technical limit changes, dynamic sensitivity factors, Schedule 2D exceedance)

---

## How to use it

1. Open the app and sign in with the password provided
2. The **map** shows substations coloured by headroom status (red = overcommitted, yellow = tight, blue = moderate, green = available). Click any dot for a popup summary.
3. Use the **dropdown** below the map to select a substation for detail view
4. In the detail view, enter a proposed **capacity (MW)** and **technology**, then click **Run test**
5. Adjust **revenue assumptions** (power price, discount rate, project life) — these are always visible below the test inputs
6. Results appear below: headline curtailment under regulatory baseline with model confidence and revenue impact
7. The **Regulatory scenario comparison** section lets you select and run an alternative regulatory future to see how curtailment changes under different policy assumptions
8. Below the scenario comparison, the **Baseline scenario deep dive** shows curtailment by size, seasonal heatmap, LIFO position, queue build-out, and hybridisation analysis under current rules
9. Click **Clear** to reset the test

---

## Coverage

**Headroom data** covers 35 BSP substations at 33kV, 66kV and 132kV across all of South Wales.

**Curtailment estimates** cover 162 connection points at 33kV across all 7 GSP zones:
Aberthaw & Cardiff East, Pembroke, Pyle, Rassau, Swansea North, Upper Boat, Uskmouth.

**Model confidence** is validated against SCADA data for branches in zones with connected generators (Swansea North, Upper Boat, Uskmouth — 108 branches validated). Branches in other zones receive confidence based on SCADA flow activity.

**ANM zone status** is derived from NGED's connection queue data, which flags each project as subject to Transmission ANM (TANM), Distribution ANM (DANM), or neither.

Substations connecting at 66kV or above (e.g. Abergavenny at 66kV) may not have curtailment data because they are not represented as 33kV connection points in NGED's sensitivity factor dataset.

---

## What each section shows

### Headroom

```
Headroom (MVA) = Transformer nominal rating − (Connected generation + Accepted generation)
```

- **Transformer nominal rating** — from NGED's LTDS Table 2a. For substations with multiple transformers, ratings are summed.
- **Connected generation** — generators currently connected, from NGED's Generation Connection Register (GCR).
- **Accepted generation** — generators with accepted connection offers but not yet built, from the GCR.

Categories: Overcommitted (headroom < 0), Tight (0–20 MVA), Moderate (20–50 MVA), Available (>50 MVA).

**Limitation:** Headroom does not account for demand, diversity, curtailment arrangements, or planned reinforcements. A substation can be overcommitted on paper but operationally fine — our analysis found substations with 95 MVA of overcommitment but 0% curtailment, because local demand absorbs generation and sensitivity factors route power across multiple branches rather than all through the BSP transformer.

### Curtailment estimate

The curtailment percentage answers: **"If I connect a new generator here, what fraction of my annual energy would I lose due to network constraints?"**

The headline curtailment assumes the new generator is last in the LIFO queue — the worst case. See the LIFO section below for position-dependent estimates.

For each half-hour of the year (17,568 data points):

```
Generator output = Proposed MW × Generic profile for that technology and half-hour
```

For each branch (circuit or transformer) with sensitivity factor ≥ 5%:

```
New branch flow = Existing branch flow (from derived branch loading, 2024)
                + Queue projection (all accepted projects × profiles × (−sensitivity factors))
                + Generator output × (−Sensitivity factor from connection bus to this branch)
```

The negative sign on the sensitivity factor accounts for the fact that NGED's SFs are defined in the demand convention (ΔBranch flow / ΔDemand). A generator is negative demand, so its effect on branch flow is −SF × output.

If the new flow exceeds the seasonal pre-event limit (PEL):

```
Required curtailment = min(Excess / |Sensitivity factor|, Generator output)
```

The generator must satisfy the most constrained branch at each half-hour. Annual curtailment is the sum of all curtailed energy divided by total potential energy.

### Model confidence

Every curtailment estimate depends on a planning model — sensitivity factors and pre-event limits derived from NGED's network model. We validate this model against 17,568 half-hours of operational data to assess how reliable each estimate is.

**How the validation works:**

The branch loading data reflects what happened on every branch in 2024. This data is derived from substation-level measurements using the same sensitivity factors that underpin the curtailment calculation — it is not independently measured on each branch. For branches where connected generators have meaningful sensitivity factors, we can compare the model's prediction of generation contribution against the observed branch flows:

- During nighttime (solar output = 0), branch flow is demand-only
- During daytime, the planning model predicts: `branch flow = nighttime demand + generation × (−sensitivity factor)`
- The residual between prediction and actual loading reveals where the model breaks down

This comparison is strongest for detecting profile mismatches (e.g. the BESS generic profile not matching real battery behaviour) and disconnected branches (zero flow despite the model predicting activity). It is weaker for detecting impedance errors because the branch loading itself was derived using the sensitivity factors being tested.

**Confidence ratings:**

🟢 **High** — The mean model residual on the binding branch is less than 1 MW (operationally negligible), or less than 5% of the branch's thermal limit (PEL) with max residual below 25%. The curtailment estimate is well-supported by operational data.

🔵 **Moderate** — The binding branch carries real power (confirming it's active and monitored) but no generation-specific residual is available for direct validation. The estimate is directionally correct but has some uncertainty.

🟡 **Low** — The model residual exceeds 15% of PEL, or the branch shows intermittent readings. The estimate should be treated as indicative.

🔴 **Very Low** — The binding branch reads zero in SCADA for 95%+ of the year. The planning model assumes this branch is active, but operational data suggests it is disconnected, unmonitored, or normally open. **Any curtailment estimate relying on this branch may be unreliable.**

**Findings from our validation:**

We validated 108 branches across three zones (Swansea North, Upper Boat, Uskmouth) against 7 connected generators totalling 87 MW. Key findings:

- **224 curtailment estimates rated High confidence** with non-zero curtailment — the planning model matches operational reality within 1 MW on the binding constraint
- **Four branches identified as potentially disconnected:**
  - Hirwaun → Rhigos (HIRW3_7L5→RGOS3_#1L5): zero flow 100% of the time. Dead-end spur — the only circuit connecting Rhigos substation. SF = 1.000 but no power ever flows.
  - Ebbw Vale → Waunllwyd (EBBW3_6L5→WNYP3_#1L5): zero flow 96% of the time. Dead-end spur with SF = 0.986.
  - Brynhill → Smor (BRHI3_#6L5→SMOR3_#5L5): zero flow 96% of the time. Not even present in the sensitivity factor data.
  - Barry (51L7662P1→BARY3_#3L5): zero flow 98% of the time.
- **BESS profile mismatch at Uskmouth:** The 24 MW BESS at Newport South shows the model predicting 18 MW of evening peak flow on the NEWS–Trostre circuit, but actual loading shows -3.7 MW. The generic BESS export profile assumes evening export, but this battery operates completely differently. This finding is valid because the branch loading reflects real substation conditions while the model prediction uses the generic profile.

### ANM zone status

Each substation is flagged as being in a Transmission ANM zone (TANM, managed by NESO), a Distribution ANM zone (DANM, managed by NGED's DERMS system), both, or neither. This information is derived from the TANM and DANM flags in NGED's connection queue data.

In ANM zones, curtailment is managed in real-time by an automated system. Our curtailment estimates replicate the logic that the ANM system uses — same sensitivity factors, same thermal limits, same LIFO priority. The SCADA data we validate against reflects post-ANM conditions, meaning our estimates are calibrated to real operational outcomes including any active curtailment management.

Any divergence between the planning model and SCADA in an ANM zone may partly reflect the ANM system actively curtailing generators to keep flows within limits — meaning the real network is better managed than the planning model alone would suggest.

In ANM zones, curtailment is managed autonomously at no cost to the DNO. The Access SCR introduces curtailment limits and compensation requirements, but implementation is ongoing.

### DNOA constraint status

NGED's Distribution Network Options Assessment (DNOA) identifies network constraints and decides how to address them. For each constraint, NGED publishes a decision:

- **Reinforce** — the DNO plans to upgrade the network (new transformer, uprated circuit, etc.) with a target completion date
- **Reinforce with Flexibility** — reinforcement planned, but flexibility services will be used in the interim
- **Flexibility** — no reinforcement; the constraint will be managed through flexibility procurement (Constraint Management Zones)
- **Signposting** — the constraint is flagged but no action is taken yet
- **Remove** — a previously identified constraint has been resolved

The tool maps DNOA scheme names to substations and shows the decision, earliest reinforcement date, constraint season (winter/summer), and Constraint Management Zone code where applicable.

**Why it matters for curtailment:** If reinforcement is scheduled, curtailment at that substation may decrease once the upgrade is complete — but may be higher than expected in the interim period. If the decision is "Flexibility", the constraint is likely to persist and curtailment is the mechanism used to manage it. The DNOA data is from August 2023; more recent reinforcement decisions may already be reflected in the 2024 branch loading data.

Source: NGED DNOA August 2023 publication.

### Revenue impact

Curtailment percentages are useful for engineering screening, but investment decisions need revenue numbers. The tool translates curtailment into financial impact using three user-adjustable assumptions:

- **Power price (£/MWh)** — the average price received per MWh of exported energy. Default: £50/MWh.
- **Discount rate (%)** — for NPV calculation. Default: 8%.
- **Project life (years)** — the period over which revenue is discounted. Default: 25 years.

**Formulas:**

```
Annual revenue (uncurtailed) = Total potential MWh × Power price
Annual revenue (after curtailment) = Delivered MWh × Power price
Annual revenue lost          = Curtailed MWh × Power price
```

```
NPV of lost revenue = Annual revenue lost × [(1 − (1 + r)^−n) / r]
```

where r = discount rate and n = project life in years.

**Example:** A 20MW wind farm at Cardiff Central faces 48.2% curtailment, losing approximately 24,375 MWh/year. At £50/MWh, that's roughly £1.2M/year of lost revenue. Over 25 years at 8% discount rate, the NPV of lost revenue is approximately £13M. That number tells an investment committee that curtailment risk is a deal-breaker at this location for wind — but solar at the same substation faces 39.6%, suggesting both technologies are heavily constrained.

By contrast, a 20MW wind farm at NANG faces 17.1% curtailment — roughly £432k/year lost, £4.6M NPV. Material but potentially acceptable depending on the project economics.

The revenue calculation is intentionally simple. It does not model wholesale price shape (curtailment during high-price hours costs more than during low-price hours), capacity payments, balancing mechanism revenues, or ancillary service income. The calculation gives a first-order estimate suitable for screening — not for final investment decisions.

**Important caveat for battery storage (BESS):** The curtailment model treats BESS the same as wind or solar — applying a fixed half-hourly export profile and checking whether that export exceeds thermal limits. But batteries do not operate like this. A wind farm that is curtailed loses energy permanently (the wind blows and it cannot be captured). A battery that is told not to export at 6pm simply shifts that energy to 10pm when the constraint is not binding. There is no lost energy, only shifted revenue timing.

The BESS "curtailment" number should therefore be interpreted as **hours of export restriction**, not energy loss. A 13% BESS curtailment means "13% of your planned export windows are constrained by the network" — it is a measure of network congestion at that site, not a measure of lost revenue. The revenue loss figures shown for BESS are overstated because they assume the curtailed energy is lost rather than time-shifted. Our SCADA validation at Newport South confirmed that the 24MW BESS there operates completely differently from the generic export profile.

### Seasonal breakdown (hour × month heatmap)

The same half-hourly curtailment, disaggregated by hour-of-day and month. This shows **when** curtailment concentrates:

- Solar curtailment typically peaks at midday in summer (when solar output is highest and the network is most loaded by other solar generation)
- Wind curtailment patterns vary by constraint — some substations show evening peaks, others show winter peaks driven by demand-side constraints
- Battery curtailment follows NGED's generic BESS export profile, which assumes evening export — but our SCADA validation found this profile may not reflect actual BESS dispatch

### LIFO queue position

Under the Last-In-First-Off (LIFO) principle of access used by NGED, each flexible generator is assigned a position in a priority stack based on its application date. When a network constraint is breached, generators at the **bottom** of the stack (most recent applicants) are curtailed **first**. Generators at the top of the stack (earliest applicants) are curtailed **last**.

This means your curtailment depends not just on the network state, but on **where you sit in the queue relative to other generators that affect the same constraint.**

The LIFO analysis shows your estimated curtailment at different queue positions, using the actual positions from the zone's connection queue. The table shows:

- **Your Position** — the queue position number you would hold
- **Projects Ahead** — how many accepted projects are ahead of you in the LIFO stack
- **Curtailment** — your estimated annual curtailment at that position
- **Energy Lost** — the corresponding MWh of curtailed energy

For each position P, all generators with position > P (connected after you) are curtailed before you. You are only curtailed if the constraint is still binding after all generators behind you have been fully curtailed.

**Reference:** This follows the methodology described in:
- NGED, "Curtailment Estimator Guidance", November 2025
- UKPN, "Curtailment Assessment Methodology and Assumptions", May 2024
- ENA Open Networks, "Common Methodology for Providing Curtailment Estimates" (WS1A P8), August 2022
- ENA, "Flexibility Connections: Explainer and Q&A", August 2021

### Queue build-out scenarios

Separate from LIFO ordering, this analysis asks: **"What if not all projects in the queue actually build?"**

Many accepted projects never reach construction. Queue attrition is significant — particularly for battery projects post-Gate 2. This analysis shows curtailment under different build-out assumptions based on the actual queue:

- **Projects Built** — how many of the accepted projects actually construct
- **Up to Position** — the highest queue position included
- **Queue (MW)** — the total MW of generation in the queue at that level
- **Curtailment** — the resulting curtailment percentage

This is not the same as LIFO position. LIFO determines who gets curtailed first when the network is constrained. Queue build-out determines how constrained the network is in the first place.

### Hybridisation analysis

Curtailment for combined technology scenarios on the same connection:

- 30MW Wind + 20MW Solar
- 30MW Wind + 10MW BESS
- 20MW Solar + 10MW BESS
- 30MW Wind + 20MW Solar + 10MW BESS
- 50MW of each technology alone (for comparison)

This answers the question: **"I have a 50MW connection but my wind farm only uses it 30% of the time — can I fill the remaining 70% with solar or battery?"**

The combined output at each half-hour is the sum of individual technology profiles. Because wind and solar generate at different times, hybrid projects typically face lower curtailment than single-technology projects of the same total capacity.

### Regulatory scenario comparison

The baseline curtailment estimate assumes the current regulatory framework: full accepted queue, static sensitivity factors, current pre-event limits, and current NESO technical limits. But several of these assumptions are subject to change. The regulatory scenario comparison quantifies how curtailment would change under different plausible regulatory futures.

**The three policy levers tested:**

1. **Queue attrition post-Gate 2** — Not all accepted projects will build. Connections reform (Gate 2, G2TWQ) is removing projects from the queue, and technology-specific dropout rates are high (particularly for BESS post-Gate 2). Three attrition levels are modelled: full queue (current), moderate (BESS 50%, solar 80%, wind 90%), and high (BESS 30%, solar 60%, wind 80%).

2. **Reinforcement (+30% PEL)** — If the DNO upgrades a constrained asset, the pre-event limit increases and curtailment drops. Modelled as a 30% PEL uplift. **Caveat:** This scaling is currently applied uniformly to all branches. A real reinforcement would increase PELs only on the specific upgraded asset (e.g. a particular SGT or circuit). The benefit is overstated for sites constrained by distribution-level branches that would not be affected by the reinforcement. A future version will implement per-branch PEL scaling using DNOA reinforcement scheme data.

3. **Static to dynamic sensitivity factors** — NGED currently uses static SFs computed at a single operating point. UKPN has moved to dynamic SFs recomputed at each operating point (CIRED 2021). Under dynamic SFs, curtailment on meshed circuits decreases because the effective SF reduces at high generation levels. **Caveat:** The 9.4% median reduction used in this model is an empirical finding from Loom Light's analysis of the Swansea North 132kV network (script 16). The magnitude may differ in other zones depending on network topology and R/X ratios. A future version will run the SF stability analysis on each zone individually.

**Not yet modelled:** NESO GSP technical limit changes (TANM). NESO periodically updates the technical limits that govern Transmission ANM at each GSP. Modelling this correctly requires implementing the TD boundary limits as a separate constraint from the distribution-level PELs, which is planned for a future version.

**Schedule 2D curtailment limit check:** For every scenario, we check whether the modelled curtailment would exceed the contractual curtailment limit under DCUSA Schedule 2D. This is not a scenario — it is a contractual obligation that has been in force since April 2023. When DNOs provide a curtailable connection, they must compensate the connected customer if curtailment exceeds the prescribed limit (measured in hours per year). The scenario output flags whether curtailment exceeds 2,000 or 1,000 hours, indicating potential financial exposure for the DNO under each regulatory future.

**Pre-defined scenario bundles:**

| Scenario | Queue | PEL | SFs |
|----------|-------|-----|-----|
| Baseline (current rules) | Full | Current | Static |
| Post-Gate 2 (moderate attrition) | Moderate | Current | Static |
| Post-Gate 2 (high attrition) | High | Current | Static |
| Reinforcement (+30% PEL) | Full | +30%* | Static |
| Dynamic SFs (UKPN-style) | Full | Current | Dynamic* |
| Best case (attrition + reinforcement + dynamic) | High | +30%* | Dynamic* |

\* See caveats above: PEL scaling is uniform (not branch-specific), dynamic SF magnitude extrapolated from Swansea North.

**How to use:** In the substation detail view, after running a baseline test, the "Regulatory scenario comparison" section lets you select a scenario and click "Run scenario" to see the headline curtailment, revenue impact, and Schedule 2D status under that regulatory future. Click "Show all scenarios" for the full comparison table.

**Interpretation:** The range across scenarios tells you how much policy uncertainty affects your investment. A site with 2% curtailment under all scenarios is a robust investment. A site with 1% under best case and 40% under worst case is a bet on a specific reform happening.

**Coverage:** Regulatory scenarios are pre-computed for all 162 connection points across all 7 GSP zones, at 5 capacity levels (5, 10, 20, 30, 50 MW) and 3 technologies (solar, wind, battery). The computation runs the same curtailment engine as the baseline, with policy parameters applied to the inputs before the curtailment calculation.

**Key finding across South Wales (20MW Solar):**

| Scenario | Aggregate curtailment |
|----------|----------------------|
| Baseline | 8.8% |
| Moderate attrition | 7.3% |
| High attrition | 6.5% |
| Reinforcement (+30% PEL) | 3.2%* |
| Dynamic SFs | 8.3%* |
| Best case | — (recompute after rerun) |

\* See caveats above.

The biggest swing is reinforcement (8.8% → 3.2%), though this is overstated due to uniform PEL scaling. Queue attrition has a meaningful but smaller effect (8.8% → 6.5%). Dynamic SFs make a modest difference at aggregate level (8.8% → 8.3%) but can be significant at specific meshed substations.

---

## Curtailment calculation details

The curtailment calculation follows the methodology published by NGED in their [Curtailment Analysis Data Usage Guidance](https://dso.nationalgrid.co.uk/planning-our-future-network/curtailment-analysis) (November 2025). The key steps are summarised below.

### Step 1: Load baseline branch flows

Derived branch loading for every circuit and transformer in the zone, at half-hourly resolution, for the whole of 2024 (17,568 data points per branch). This data is published by NGED and is calculated from substation-level measurements using sensitivity factors. It is not independently measured on each branch.

### Step 2: Project the connection queue

For each accepted-but-not-built project in the zone:

```
Branch load addition = −(Project MW × Profile(technology, half-hour) × SF(project bus → branch))
```

The negative sign accounts for the demand convention of sensitivity factors. A generator decreases net demand, so its effect on branch flow is −SF × output.

Summed across all queued projects and added to the derived branch loads. After this step, the branch loads represent the estimated future network state.

### Step 3: Apply seasonal pre-event limits

For each branch, NGED publishes Forward PEL (MW) and Reverse PEL (MW) for four seasons:
- Winter (Dec–Feb)
- Intermediate Cool (Mar, Apr, Nov)
- Intermediate Warm (May, Sep, Oct)
- Summer (Jun–Aug)

Summer PELs are generally lower (warmer weather reduces conductor/transformer thermal ratings). The PEL is lower than the full thermal rating because NGED must maintain N-1 security margins (per the Sum Constraint methodology described in NGED's curtailment estimator guidance).

### Step 4: Compute curtailment

For each half-hour, for each sensitive branch:

The generator's effect on branch flow is −SF × output. Since SFs are in demand convention:
- **If SF < 0:** the generator pushes **positive** (forward) flow on this branch. Check against Forward PEL.
- **If SF > 0:** the generator pushes **negative** (reverse) flow on this branch. Check against Reverse PEL.

```
New flow = Existing flow − Generator output × SF

If SF < 0 (generator pushes forward flow):
    Excess = max(New flow − Forward PEL, 0)
    Curtailment = min(Excess / |SF|, Generator output)

If SF > 0 (generator pushes reverse flow):
    Excess = max(Reverse PEL − New flow, 0)
    Curtailment = min(Excess / SF, Generator output)
```

The binding constraint is the branch demanding the most curtailment at each half-hour.

For proper LIFO ordering, the excess is first absorbed by generators behind the study generator in the priority stack before any curtailment is applied to the study generator (see LIFO section above).

### Step 5: Validate against SCADA

For branches in zones with connected generators, we compare the planning model's prediction of branch flow against the derived branch loading. The method:

1. Identify nighttime half-hours (solar output = 0) as a demand-only baseline
2. During daytime, the model predicts: `branch flow = nighttime demand − sum(connected gen × profile × SF)`
3. The residual (actual − predicted) quantifies model error at each half-hour
4. Mean residual relative to the branch PEL determines the confidence rating

This validation is limited by three factors: (a) only 7 connected generators across 3 zones provide enough signal for comparison, (b) using nighttime demand as a proxy for daytime demand introduces a known bias (daytime demand is typically higher), and (c) the branch loading is derived from substation measurements using the same SFs being tested, making the comparison partly circular. The validation is strongest for detecting profile mismatches and disconnected branches.

### Step 6: Aggregate

```
Curtailment % = Total curtailed energy / Total potential energy × 100
```

---

## Data sources

| Dataset | What it provides | Vintage |
|---------|-----------------|---------|
| LTDS Table 2a | Transformer ratings (MVA) | Dec 2025 |
| BSP Transformer Flows | Half-hourly power flows at BSP level | Mar 2022 – Apr 2023 |
| Generation Connection Register | Connection queue by substation | Jan 2026 |
| Sensitivity Factors | Impact of 1 MW demand at each bus on each branch | Mar 2026 |
| Branch Loading | Half-hourly MW on every branch (derived from substation measurements) | 2024 |
| Pre-event Limits | Seasonal thermal limits per branch | Mar 2026 |
| Generic Generator Profiles | Normalised half-hourly output for solar, wind, battery | Mar 2026 |
| Connection Queue (per zone) | Accepted projects with bus numbers, LIFO position, ANM flags | Mar 2026 |
| DNOA (Distribution Network Options Assessment) | Constraint decisions, reinforcement timelines, CMZ codes | Aug 2023 |
| TD Boundary Limits | NESO technical limits and SGT forward/reverse power flow limits per GSP | Mar 2026 |

All data is publicly available from NGED's Connected Data portal under the NGED Open Data Licence (based on OGL v3.0). No proprietary data or models are used.

---

## Key assumptions and limitations

1. **Thermal constraints only**: Voltage constraints, fault level limits, and reactive power effects are not modelled. These would require a full power flow model.

2. **No abnormal running**: We assume normal network configuration throughout the year. Planned or unplanned outages that change topology are not modelled. Our SCADA validation identified four branches where the planning model's topology assumption appears to be wrong (see Model Confidence section).

3. **ANM zones identified but not separately modelled**: Substations in TANM or DANM zones are flagged in the app. The SCADA data we validate against reflects post-ANM conditions, but we do not separately model the ANM system's real-time behaviour.

4. **Generic profiles**: All generators of the same technology follow the same output profile. Individual wind farms vary by location and hub height. Our SCADA validation found that the generic BESS profile significantly mismatches actual BESS operation at Uskmouth — real batteries operate market-driven strategies, not the DNO's generic export profile.

5. **Single weather year**: Branch loading is from 2024. A different weather year could give different results.

6. **5% sensitivity threshold**: Branches with sensitivity factor below 5% are ignored, consistent with NGED's published methodology.

7. **Queue attrition modelled but not probabilistic**: The regulatory scenario engine models three attrition levels (none, moderate, high) with technology-specific dropout rates. These rates are based on industry observations of Gate 2 outcomes and connections reform, but are not derived from a formal probability model. Users should treat the range of scenarios as plausible bounds rather than point predictions.

8. **LIFO per-constraint stacks**: Our LIFO implementation builds a per-constraint stack and curtails in reverse position order per branch, consistent with the UKPN methodology. We do not currently enforce the voltage-level ordering (resolve lower voltage constraints first, then higher voltage) described in the NGED methodology document.

9. **90% operational margin**: NGED's DERMS typically starts curtailing at 90% of the constraint limit to allow for ramp-up time. Our calculation uses the published PEL values directly, which may or may not embed this margin.

10. **TD boundary limits not applied as separate constraints**: NGED publishes Transmission-Distribution boundary limits per GSP. In the zones we've checked (Swansea North), the PELs on individual SGTs are tighter than the TD limits, so this has no impact. Other zones may differ.

11. **Model confidence limitations**: The SCADA validation covers 108 branches across 3 zones (Swansea North, Upper Boat, Uskmouth). Branches in other zones (Aberthaw, Pembroke, Pyle, Rassau) have no connected generation to validate against and receive "Moderate" confidence by default. The branch loading is derived from substation measurements using sensitivity factors, making the validation partly circular — it is strongest for detecting profile mismatches and disconnected branches, weaker for detecting impedance errors.

12. **Sensitivity factor sign convention**: SFs are published in NGED's demand convention (ΔBranch flow / ΔDemand). A generator's effect on branch flow is −SF × output. This has been verified by physical direction checks on BSP transformers (Rhos, Swansea West) where the direction of power flow is known.

13. **Not a substitute for a formal connection study**: These estimates are for screening purposes. A G99 application and DNO study is required before any connection decision.

14. **Regulatory scenario engine limitations**: (a) The PEL scaling for the reinforcement scenario is applied uniformly across all branches — a real reinforcement would only increase PELs on the specific upgraded asset. This overstates the benefit for sites constrained by distribution branches. (b) The dynamic SF model applies a 9.4% reduction factor derived empirically from the Swansea North 132kV network; the magnitude may differ on other networks. (c) NESO GSP technical limits (TANM) are not yet modelled as a separate constraint — this requires implementing the TD boundary limits file, which is planned for a future version. (d) The scenario bundles are illustrative combinations, not exhaustive.

15. **DNOA data vintage**: The DNOA constraint mapping uses the August 2023 publication. Reinforcement decisions may have been updated, completed, or revised since then. Reinforcements completed before the 2024 branch loading data period are already reflected in the baseline curtailment estimate.

---

## Feedback we would value

- Do the curtailment numbers make sense for areas you know well?
- Is the model confidence rating useful? Does it change how you'd use the curtailment number?
- Are there specific sites where you have an NGED curtailment report we could cross-check against?
- What queue attrition assumptions would you apply by technology?
- Which regulatory scenarios are most relevant to your investment decisions? Are there scenarios we should add?
- Does the scenario range (best case to worst case) change how you assess a site?
- Would you pay more for a higher-confidence estimate? What would "higher confidence" need to look like?
- Does the ANM zone flag change how you think about curtailment risk at a substation?
- Is the Schedule 2D exceedance warning useful for identifying DNO compensation risk?
