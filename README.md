# Digital Twin Air Corridor System for Victoria Harbour UAV Logistics

## Project Overview
A comprehensive thesis research project combining maritime traffic integration, multi-modal logistics optimization, and V&V frameworks for autonomous UAV operations in Victoria Harbour.

**Team**: Wardells & Rozz
**University**: Hong Kong University (HKU)
**Duration**: 12-14 weeks (6 phases)
**Start Date**: 2026-03-30

---

## Phase 1: Foundation & Data Integration (Week 1-2)

### Objectives
- Establish development infrastructure
- Validate external API connections (HKO, LandsD, Open3DHK)
- Load and verify geospatial datasets
- Create baseline maritime traffic simulator

### Key Deliverables
- ✓ GitHub repository with structure
- ✓ HKO Open Data API wrapper
- ✓ Geospatial data loaded (LandsD 3D-BIT00, Open3DHK)
- ✓ Cesium 3D visualization with maritime overlay
- ✓ Agent-based maritime simulator (baseline)
- ✓ 24-hour maritime traffic dataset

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

## Technology Stack

**Simulation & Development**
- Python 3.10+ (NumPy, SciPy, Pandas, Matplotlib)
- MATLAB/Simulink UAV Toolbox
- Jupyter Notebook for analysis

**Visualization**
- Cesium.js for 3D
- Folium for 2D mapping
- Matplotlib for plots

**Data & APIs**
- HKO Open Data API
- Geospatial: GeoPandas, Rasterio, Shapely
- Database: SQLite (lightweight, local)

**DevOps**
- Git/GitHub for version control
- pytest for unit testing
- Docker (optional, for reproducibility)

---

## Team Coordination

### Unified Project Structure
This is **ONE unified project**, not two separate tracks:
- **Shared foundation (both)**: Phase 1 infrastructure, API integration, 3D environment
- **Track 1 (Wardells focus)**: Maritime integration, fairway-corridor conflict
- **Track 2 (Rozz focus)**: V&V framework, cybersecurity, privacy routing
- **Integration points**: Constraint merging, validation, CAD package

### Communication
- Daily stand-ups: Progress + blockers
- GitHub issues for tracking work items
- Feature branches for each task (feature/[name])
- Code reviews before merging to main

---

## References & Documentation

- **Project Summary**: See Project_Summary_and_Execution_Plan.docx
- **Week 1-2 Action Plan**: See Week_1-2_Detailed_Action_Plan.docx
- **Opening Report**: See Thesis_Opening_Report_Enhanced.pptx
- **API Docs**: [HKO](https://www.hko.gov.hk/en/), [Open3DHK](https://3d.map.gov.hk/)

---

**Last Updated**: 2026-03-30
**Next Phase Review**: End of Week 2
