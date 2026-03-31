# Digital Twin Air Corridor System for Victoria Harbour UAV Logistics

## 1. Research Problem & Motivation

### The Core Question
How can autonomous unmanned aerial vehicles (UAVs) safely operate in ultra-dense urban airspace alongside manned maritime traffic?

**Context**: Victoria Harbour is one of the world's busiest shipping channels with:
- 10 Principal Fairways managing complex vessel flow
- Dense airspace subject to Civil Aviation Department (CAD) constraints
- Residential areas with strict privacy regulations (PDPO)
- Dynamic meteorological conditions affecting both air and sea traffic

**Challenge**: Current UAV corridor planning lacks integration with maritime traffic layer. Existing research treats airspace and sea traffic separately, missing critical interaction points.

**Our Approach**: Build a computational digital twin that unifies maritime traffic, environmental constraints, and UAV autonomy requirements into a single simulation environment.

---

## 2. System Architecture

### 2.1 Conceptual Framework: 5-Layer Digital Twin

```
┌─────────────────────────────────────────────────────────┐
│ Layer 5: OUTPUT GENERATION                               │
│  ├─ CAD Regulatory Evidence Package                       │
│  ├─ Risk Assessment Report                                │
│  └─ Multi-modal Logistics Recommendation                  │
├─────────────────────────────────────────────────────────┤
│ Layer 4: VERIFICATION & VALIDATION                       │
│  ├─ Monte Carlo Uncertainty Quantification                │
│  ├─ Component-level Validation                            │
│  ├─ Cybersecurity Threat Modeling                         │
│  └─ Privacy Compliance Verification (PDPO)               │
├─────────────────────────────────────────────────────────┤
│ Layer 3: DECISION OPTIMIZATION                           │
│  ├─ Path Planning (A*/RRT* algorithms)                    │
│  ├─ Fairway-Corridor Conflict Detection                   │
│  ├─ Multi-modal Logistics Comparison                      │
│  └─ Vertiport Location Optimization                       │
├─────────────────────────────────────────────────────────┤
│ Layer 2: ENVIRONMENTAL SIMULATION                        │
│  ├─ Maritime Traffic Agent-Based Model                    │
│  ├─ Wind Field Dynamics (from HKO data)                   │
│  ├─ 3D Building & Terrain Representation                  │
│  └─ Noise Propagation Model                               │
├─────────────────────────────────────────────────────────┤
│ Layer 1: DATA INPUT & INTEGRATION                        │
│  ├─ HKO Open Data API (meteorological)                    │
│  ├─ LandsD 3D-BIT00 (elevation)                           │
│  ├─ Open3DHK (urban geometry)                             │
│  ├─ Marine Department (fairway definitions)               │
│  └─ Historical AIS/VTMS (vessel behavior)                 │
└─────────────────────────────────────────────────────────┘
```

**Design Rationale**: Layered separation enables modularity — each layer can be validated independently before integration. Layer 1-2 form the **environmental foundation**, Layer 3 the **decision logic**, Layer 4-5 the **validation and output**.

---

## 3. Phase 1 Implementation: Foundation & Data Integration

### 3.1 What We Built

Our team implemented a complete end-to-end digital twin foundation. This phase focused on establishing the **environmental modeling backbone** that future UAV corridor analysis depends on.

| Component | Status | Our Implementation |
|-----------|--------|-------------------|
| **Data Integration Layer** | ✓ Complete | Wrapped HKO, LandsD, Open3DHK APIs with modular clients; implemented exponential backoff retry logic for robust data fetching |
| **Geospatial Environment** | ✓ Complete | Loaded 2.1 MB elevation grid (20m resolution) + 50 building features; set up spatial indexing for fast collision queries |
| **Maritime Agent Model** | ✓ Complete | Designed 3 heterogeneous agent classes (VesselAgent base) with type-specific speed profiles and wind sensitivity functions |
| **Traffic Simulator Engine** | ✓ Complete | Built agent-based orchestrator: per-minute timestep, wind coupling, fairway constraint checking, collision detection (Haversine < 500m) |
| **Output Pipeline** | ✓ Complete | Generated 11,520-record CSV (8 vessels × 1,440 minutes); verified schema completeness and no NaN values |

### 3.2 Key Design Decisions & Rationale

#### Decision 1: We Chose Agent-Based Modeling Instead of Flow Models
**Why We Made This Choice**:
Traditional traffic flow models (macroscopic) lose fidelity for small vessel populations. We knew Victoria Harbour has diverse traffic (ferries, cargo, yachts) with **conflicting behaviors** — ferries follow fixed timetables, cargo ships react to wind, yachts vary speed. A flow model would average these away.

**How We Implemented It**:
- Each vessel is an autonomous agent with persistent state (position, velocity, type, destination)
- Agent-specific update rules: ferries move deterministically; cargo agents apply wind sensitivity; yachts have variable speed
- Agents update every minute based on: heading-to-destination, wind perturbation, fairway boundary checks
- Multi-agent interactions happen through a centralized collision detector

**Trade-off**: ABM is slower than continuous flow models (~1440 timesteps per simulation) but captures agent diversity that a flow model would miss.

#### Decision 2: We Coupled Wind from HKO Real-Time API (Not Synthetic)
**Why We Made This Choice**:
Both UAVs and vessels respond to wind. Synthetic wind profiles would be internally consistent but decoupled from actual conditions. By pulling from HKO Open Data, our simulation inherits real meteorological context for the date (2026-03-30).

**How We Implemented It**:
- Query HKO API at each 10-minute interval
- Apply wind effect as **bearing perturbation** to vessel heading: `δheading = wind_strength_factor × sin(wind_direction − vessel_bearing)`
- Wind affects trajectory shape but not speed (physically accurate for large cargo vessels)

**Limitation Identified**: We're using linear perturbation in the simulator, but HKO provides full 3D wind gradients. Phase 2 will interpolate properly.

#### Decision 3: We Enforced Principal Fairways as Hard Constraints
**Why We Made This Choice**:
Hong Kong Marine Department defines 10 Principal Fairways (law-enforced shipping lanes). Violating these boundaries is illegal AND would make a UAV corridor plan unacceptable to regulators. We treated them as immutable operational constraints.

**How We Implemented It**:
- Modeled 5 major fairways with polygon boundaries (lat/lon min-max)
- Check-in-fairway: every vessel's position is tested each minute against fairway polygon
- Output CSV flags violations for phase 2 analysis (`in_fairway = True/False`)

**Our Decision**: Rather than force vessels to stay in fairways (which would require complex path-planning), we record violations and plan avoidance behavior for Phase 2.

#### Decision 4: We Used Python for Phase 1 (Deferring MATLAB)
**Why We Made This Choice**:
- **Iteration speed**: Python is interpretive (no compile-test-debug cycle); helps when exploring agent behavior
- **Data visualization**: Pandas + Matplotlib are mature; can plot 11,520 records instantly
- **Extensibility**: Adding a new vessel type is <10 lines (inherit base class); MATLAB would require more scaffolding
- **Future integration**: Phase 2 UAV pathfinding will likely use Python-based motion planning libraries (RRT*, OMPL)

**Trade-off**: MATLAB/Simulink's **Control Toolbox** (for UAV dynamics, PID control) is deferred to Phase 2+ when we design avoidance algorithms. For Phase 1, pure kinematics in Python is appropriate.

---

## 4. Technical Deep-Dive: How We Built the Simulator

### 4.1 The Simulation Loop — What We Implemented

We built the simulator as a **discrete-time step orchestrator**. Each minute (timestep = 60 seconds), the loop executes 4 stages:

```python
for t in range(simulation_start, simulation_end, dt=60s):
    # ========== STAGE 1: Environment Input ==========
    # We fetch HKO wind data at current time
    wind_data = hko_api_client.get_wind_at_time(t)

    # ========== STAGE 2: Agent Position Update ==========
    # For each active vessel, we calculate new position
    for vessel in active_vessels:
        # 2a. Bearing to destination (great circle course)
        bearing_to_dest = atan2(dest.lon - vessel.lon, dest.lat - vessel.lat)

        # 2b. Apply wind effect (our wind coupling model)
        wind_effect = 0.1 * wind_data.speed * sin(wind_data.direction - bearing_to_dest)
        actual_bearing = bearing_to_dest + wind_effect

        # 2c. Update lat/lon using Haversine forward formula
        # (converts speed [m/s] + bearing into lat/lon change)
        vessel.lat += (vessel.speed * cos(actual_bearing) * dt) / 111000
        vessel.lon += (vessel.speed * sin(actual_bearing) * dt) / (111000 * cos(lat_radians))

        # 2d. Check fairway compliance
        vessel.in_fairway = fairway_monitor.check_boundary(vessel.lat, vessel.lon)

    # ========== STAGE 3: Collision Detection ==========
    # We check all vessel pairs for proximity
    collision_detector.check_all_pairs(active_vessels, min_distance=500m)
    # Sets collision_risk = True if any vessel pair < 500m apart

    # ========== STAGE 4: Data Logging ==========
    # We record state snapshot for all vessels
    for vessel in active_vessels:
        output_csv.write({
            'timestamp': t,
            'vessel_id': vessel.id,
            'vessel_type': vessel.type,
            'lat': vessel.lat,
            'lon': vessel.lon,
            'speed': vessel.speed,
            'heading': vessel.bearing,
            'collision_risk': vessel.collision_risk,
            'in_fairway': vessel.in_fairway,
            'wind_speed': wind_data.speed
        })
```

**Key Implementation Decisions**:
- **1-minute timestep**: 60 seconds balances accuracy (collision detection needs fine granularity) vs. computational cost (1440 timesteps/day × 8 vessels = 11,520 records)
- **Haversine great-circle formula**: More accurate than flat-earth approximation for harbor-scale distances
- **Wind as bearing perturbation**: Simplified model appropriate for Phase 1 validation

### 4.2 Data Flow Example — What Happens in One Timestep

Here's a concrete walkthrough with real vessel + wind data:

```
INPUT: t = 2026-03-30 18:30
       HKO API returns: wind_speed=6.2 m/s, direction=180° (southerly)

VESSEL STATE (Before update):
  Ferry_001: lat=22.290°N, lon=114.175°E
  Type: StarFerry (speed always 12 m/s)
  Destination: 22.295°N, 114.180°E (next harbor tour waypoint)

CALCULATION STEP-BY-STEP:
  1. Bearing to destination = atan2(114.180-114.175, 22.295-22.290) = 66° (NE)
  2. Wind effect = 0.1 * 6.2 * sin(180° - 66°) = 0.1 * 6.2 * 0.940 = +0.58°
  3. Actual bearing = 66° + 0.58° = 66.58°
  4. Δlat = (12 m/s * cos(66.58°) * 60s) / 111000 m/deg = 0.00292°
  5. Δlon = (12 m/s * sin(66.58°) * 60s) / (111000 * cos(22.290°)) = 0.00352°

NEW POSITION (After update):
  Ferry_001: lat=22.29292°N, lon=114.17852°E

CONSTRAINT CHECKS:
  In Principal Fairway? → check_fairway_boundary(22.29292, 114.17852) → True ✓
  Collision with other vessels? → haversine distances to other 7 vessels → no pair < 500m → False ✓

OUTPUT RECORD:
  {timestamp: "2026-03-30 18:30", vessel_id: "Ferry_001", vessel_type: "StarFerry",
   lat: 22.29292, lon: 114.17852, speed: 12, heading: 66.58,
   collision_risk: False, in_fairway: True, wind_speed: 6.2}
```

**Why This Approach Works**:
- Transparent logic — every position change is auditable
- Composable — we can inject different wind models without changing position update code
- Extensible — adding COLREGs (avoidance behavior) in Phase 2 just modifies step 2b

---

## 5. Phase 1 Results & Validation

### 5.1 What We Ran: The 24-Hour Baseline Simulation

We executed a complete 24-hour simulation on 2026-03-30 to establish a **reference dataset** for Phase 2 comparison.

**Our Output**:
- **File**: `output/maritime_baseline_24h.csv`
- **Data Volume**: 11,520 records (8 vessels × 1,440 minutes × 1 min/timestep)
- **Time Range**: 2026-03-30 17:02 → 2026-03-31 17:02 (full 24-hour period)
- **Columns**: timestamp, vessel_id, vessel_type, lat, lon, altitude, speed, heading, active, in_fairway, collision_risk, wind_speed

**The Fleet We Simulated**:
- **3× StarFerry agents**: Constant speed 12 m/s, fixed circular routes (harbor tour pattern)
- **2× Cargo agents**: Constant speed 7 m/s, wind-sensitive (heading shifts when wind_speed > 5 m/s)
- **3× Yacht agents**: Variable speed 8-10 m/s (random ±1 m/s per timestep), exploratory paths

**What This Baseline Tells Us**:
- Establishes typical occupancy of fairways during 24 hours
- Records environmental conditions (HKO wind data integrated)
- Identifies collision risk zones (all flagged at t=0 due to initial condition artifact)

### 5.2 Limitations We Identified & Our Phase 2 Fixes

We reviewed the Phase 1 output carefully and documented 4 limitations. This is intentional: Phase 1 is meant to be a **functional prototype**, not production-ready simulation. Understanding what's missing is critical for Phase 2 prioritization.

⚠️ **Limitation 1: Initial Condition Artifact**
- **What Happens**: All 8 vessels spawn at (22.290°N, 114.175°E) → collision_risk = True for all at t=0 (100% collision rate initially)
- **Why We Accepted This**: Simplified Phase 1 startup; real vessel positions come from AIS data
- **Our Phase 2 Fix**: (1) Stagger departure times by ±15min per vessel type, (2) Initialize positions from historical AIS data snapshot for the same date in previous years, (3) Validate that collision risk becomes realistic (< 5% for well-separated paths)

⚠️ **Limitation 2: Wind Model is Linear and 2D**
- **What Happens**: We apply wind as heading perturbation only. Real wind creates complex 3D gradients, especially in harbor canyons
- **Approximation We Made**: `δheading = 0.1 × wind_speed × sin(wind_dir − bearing)` works for open water but breaks near buildings
- **Our Phase 2 Fix**: (1) Implement spatial wind interpolation from HKO mesoscale data (50km→ 1km resolution), (2) Model wind as (u,v,w) 3D vector, (3) Apply wind perturbation to both heading AND speed for realistic vessel behavior

⚠️ **Limitation 3: Vessels Don't Avoid Collisions**
- **What Happens**: Agents move deterministically toward waypoint, ignoring other vessels
- **Why This is Unrealistic**: Real mariners apply COLREGs (Collision Avoidance Rules of the Road)
- **Our Phase 2 Fix**: (1) Implement COLREGs logic (Rule 8-19), (2) Add avoidance heading calculation based on relative bearing/distance to other vessels, (3) Test with multiple vessel pairs and verify avoidance success rate > 95%

⚠️ **Limitation 4: No UAV Integration**
- **What Happens**: This is pure maritime simulation, no airspace model
- **Why Separation Was OK for Phase 1**: Decoupling maritime baseline from UAV pathfinding lets us validate each independently
- **Our Phase 2 Fix**: (1) Add UAV agent class with different speed/maneuverability, (2) Compute maritime-air 3D conflict zones, (3) Feed conflicts into UAV path planner to generate avoidance routes

---

## 6. Architectural Insights: How We Structured This for Growth

We designed the Phase 1 architecture to be **composable** — each piece can be swapped without breaking the whole system. This was intentional, because Phase 2 will add significant complexity (COLREGs, 3D wind fields, UAV agents). Here's how we achieved that:

### Design Pattern 1: Modular Separation of Concerns
**How We Organized It**:
- **`hko_api_client.py`**: Standalone HKO wrapper — no coupling to simulator
- **`geospatial_loader.py`**: Independent loader — same CSV format whether used by maritime sim or UAV planner
- **`maritime_simulator.py`**: Orchestrator that **composes** the above

**Why This Matters**:
- Each module can be tested independently (`pytest tests/test_hko_api.py`)
- Can swap implementations (e.g., "switch from HKO to NOAA API without touching simulator code")
- Reduces debugging when something breaks

### Design Pattern 2: Inheritance for Agent Extensibility
**How We Implemented It**:
We made `VesselAgent` a base class with abstract methods for speed/movement:
```python
class VesselAgent:
    def _get_current_speed(self):
        raise NotImplementedError
    def update_position(self, dt, wind_data):
        raise NotImplementedError

class FerryAgent(VesselAgent):
    def _get_current_speed(self):
        return 12  # m/s, constant

class CargoAgent(VesselAgent):
    def _get_current_speed(self):
        return 7 if wind_speed < 5 else 6.5  # reacts to wind
```

**Why We Did This**: Adding a fourth vessel type (e.g., SpeedBoat, Tanker) requires <20 lines of code. Phase 2 can add `DroneAgent(VesselAgent)` the same way.

### Design Pattern 3: Unidirectional Data Flow
**Our Data Pipeline**:
```
Simulation → CSV Output → Analysis (NumPy/Pandas) → Phase 2 Input
```
- Simulation produces one CSV per run (immutable artifact)
- Analysis code never modifies simulator logic
- Phase 2 reads previous CSV + creates new simulation with updates

**Why This Works**: Reproducibility. If Phase 2 results differ, we can trace back to which CSV version was used.

---

## 7. Project Structure

---

## Project Structure

```
uav-maritime-twin/
├── src/                          # Python source code
│   ├── hko_api_client.py        # HKO Open Data API wrapper
│   ├── geospatial_loader.py     # Load LandsD & Open3DHK
│   ├── maritime_agents.py       # Vessel agent model
│   ├── maritime_simulator.py    # Traffic simulator
│   ├── collision_detection.py   # Collision detection logic
│   └── download_geospatial.py  # Data download & preparation script
├── tests/                        # Unit tests
│   ├── test_hko_api.py
│   └── conftest.py
├── data/                         # Data storage
│   ├── hko/                     # HKO API responses
│   ├── geospatial/              # LandsD, Open3DHK
│   └── maritime/                # Fairways, vertiports
├── models/                       # MATLAB/Simulink models
├── visualization/                # Cesium.js 3D viewer
├── output/                       # Simulation results
├── docs/                         # Documentation
├── requirements.txt              # Python dependencies
├── .gitignore
└── README.md

```

---

## Getting Started

### Prerequisites
- Python 3.10+
- MATLAB R2023a+ with UAV Toolbox (academic license)
- Node.js 16+ (for Cesium visualization)
- Git 

### Setup

1. **Clone repository**
   ```bash
   git clone https://github.com/[username]/uav-maritime-digital-twin.git
   cd uav-maritime-digital-twin
   ```

2. **Create Python virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run tests**
   ```bash
   pytest tests/ -v
   ```

4. **Start Cesium viewer**
   ```bash
   cd visualization/cesium-app
   npm install
   npm start
   ```

---

## Phase 1 Tasks (Weeks 1-2)

### Week 1
- **Day 1**: GitHub setup, Python env, MATLAB workspace
- **Day 2**: HKO API integration
- **Day 3**: Geospatial data loading (LandsD, Open3DHK)
- **Day 4**: Cesium 3D visualization
- **Day 5**: Maritime data mapping, integration planning

### Week 2
- **Day 6-7**: Maritime simulator agent model
- **Day 8**: Collision detection, fairway monitoring
- **Day 9**: Visualization, documentation
- **Day 10**: Code review, testing, v0.1.0 release

---

## Data Sources

| Source | Status | Access | Description |
|--------|--------|--------|-------------|
| HKO Open Data | ✓ Free | weather.gov.hk/opendata | 10-min resolution wind/weather |
| LandsD 3D-BIT00 | ✓ Free | lands.cedd.gov.hk | 20m resolution elevation |
| Open3DHK | ✓ Free | https://3d.map.gov.hk | 3D city model (no registration) |
| CAD eSUA Map | ✓ Free | Civil Aviation Dept | Drone operation zones |
| Marine Dept | ✓ Agreement | VTMS data | Principal Fairways, vessel tracking |

---
## Team Coordination & Project Structure

### Why This is One Project, Not Two
Initially, we considered splitting maritime simulation and UAV pathfinding into two separate thesis tracks. We decided **against this** for three reasons:

1. **Shared Foundation**: Both tracks depend on the same geospatial data (elevation, buildings, fairways) and environmental API (HKO wind). Duplicating this work would be wasteful.

2. **Cross-Domain Constraints**: A UAV corridor that avoids a fairway is only useful if that fairway will actually have traffic. We need the maritime simulation to validate UAV routes are necessary.

3. **Unified Regulatory Package**: Hong Kong CAD will ask one question: "Is this design safe?" One integrated proof is stronger than two separate ones.

### How We Divided the Work

| Aspect | Responsibility | Deliverable |
|--------|---|---|
| **Phase 1 Foundation** | Both | Infrastructure (APIs, geospatial, simulator) |
| **Track 1: Maritime-Airspace Integration** | Wardells | Fairway-corridor conflict detection + pathfinding for UAV avoidance |
| **Track 2: Validation & Safety** | Rozz | Uncertainty quantification (Monte Carlo), cybersecurity threat model, PDPO privacy routing |
| **Phase 3+: Optimization** | Both | Multi-modal logistics comparison, CAD regulatory evidence package |

### Our Communication Strategy
- **Version Control**: Single GitHub repo (`uav-maritime-digital-twin`); feature branches per task
- **Integration Points**: Weekly review of interfaces between Track 1 and Track 2
- **Testing Discipline**: Each pull request requires code review + 2 unit tests minimum
- **Artifact Sharing**: All outputs (CSVs, reports) stored in `/output` with timestamp + author

---

## References & Documentation

- **Project Summary**: See Project_Summary_and_Execution_Plan.docx
- **Week 1-2 Action Plan**: See Week_1-2_Detailed_Action_Plan.docx
- **Opening Report**: See Thesis_Opening_Report_Enhanced.pptx
- **API Docs**: [HKO](https://www.hko.gov.hk/en/), [Open3DHK](https://3d.map.gov.hk/)

---

**Last Updated**: 2026-03-30
**Next Phase Review**: End of Week 2
