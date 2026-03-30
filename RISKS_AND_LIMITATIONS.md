# Project Risks, Limitations & Assumptions

## 1. Technical Risks

### Risk 1.1: HKO API Availability & Data Quality
**Severity**: MEDIUM
**Probability**: LOW
**Impact**: If HKO API is unavailable, simulation cannot fetch real-time wind data. Phase 2 UAV avoidance logic depends on this data.

**Mitigation**:
- Cache wind data locally after each fetch
- Implement fallback to synthetic wind profile if API fails
- Test API reliability before Phase 2 integration (> 99% uptime requirement)
- Monitor API response time (should be < 500ms)

**Owner**: Rozz (Phase 2)
**Deadline**: End of Phase 2

---

### Risk 1.2: Geospatial Data Alignment (EPSG:2326 vs WGS84)
**Severity**: MEDIUM
**Probability**: MEDIUM
**Impact**: Coordinate system mismatch could cause 10-100m position errors. This affects fairway boundary checking and collision detection.

**Current Status**: We use EPSG:2326 (Hong Kong 1980 Grid) internally but output WGS84 lat/lon. Small risk of transformation errors.

**Mitigation**:
- Validate transform accuracy against known reference points (e.g., Star Ferry terminal)
- Unit test coordinate conversions with ±5m tolerance
- Cross-check output positions against Google Maps
- Document all CRS assumptions in Phase 2 documentation

**Owner**: Wardells (Phase 2 validation)
**Deadline**: Start of Phase 2

---

### Risk 1.3: Collision Detection Accuracy at Scale
**Severity**: LOW
**Probability**: HIGH
**Impact**: Haversine distance formula assumes spherical Earth. At harbor scale (< 10 km), this causes < 0.01% error. Acceptable for Phase 1.

**Known Limitation**: We use Haversine, not Vincenty. Phase 2 may need sub-meter accuracy for UAV-vessel collision avoidance.

**Mitigation**:
- Implement Vincenty formula for Phase 3+ if required by CAD
- Benchmark current accuracy against actual GPS traces
- Document formula choice and acceptance criteria

**Owner**: Wardells
**Deadline**: Phase 3 (if regulatory requirement)

---

## 2. Operational Risks

### Risk 2.1: Team Coordination Across Two Tracks
**Severity**: MEDIUM
**Probability**: MEDIUM
**Impact**: Track 1 (maritime) and Track 2 (V&V) may diverge. Conflicting architectural changes could delay integration.

**Mitigation**:
- Weekly sync meetings (Tuesday 10am)
- Shared branch naming convention (`feature/[Track-Issue]`)
- Code review required before merge (both reviewers)
- Integration tests verify both tracks work together

**Owner**: Both
**Frequency**: Weekly

---

### Risk 2.2: Python Environment Inconsistency
**Severity**: MEDIUM
**Probability**: LOW
**Impact**: Different Python versions / package versions could cause "works on my machine" bugs. Critical for reproducibility.

**Current Status**: Requirement: Python 3.10+. User had 3.9.6, now using 3.11. May affect other team members.

**Mitigation**:
- Lock dependencies in `requirements.txt` with exact versions
- Use Docker container for reproducible environment
- Document Python version tested on in README
- Automated environment check at startup

**Owner**: Rozz (Phase 2)
**Deadline**: Before Phase 2 code freeze

---

### Risk 2.3: Resource Constraints (Mac 16GB RAM)
**Severity**: LOW
**Probability**: MEDIUM
**Impact**: Monte Carlo simulation (Phase 2) generates 1000s of runs. Memory usage could spike.

**Phase 1 Status**: 1 run = 8 vessels, 1440 timesteps, ~11.5K records. CSV size = 1.6 MB. Safe.

**Phase 2 Risk**: 100 Monte Carlo runs = 160 MB CSV. 1000 runs = 1.6 GB. Still manageable on 16GB Mac.

**Mitigation**:
- Implement streaming output for large simulations
- Add memory profiling to CI/CD pipeline
- Split large runs across multiple processes
- Document minimum spec: 8GB RAM, 50GB disk

**Owner**: Both (Phase 2)
**Deadline**: Before Phase 2 production runs

---

## 3. Regulatory & Stakeholder Risks

### Risk 3.1: CAD Regulatory Changes
**Severity**: HIGH
**Probability**: MEDIUM
**Impact**: Hong Kong Civil Aviation Department may update UAV corridor rules during our 12-week project. Could invalidate Phase 3+ deliverables.

**Current Status**: Using eSUA Map as of 2026-03-30. No known updates pending.

**Mitigation**:
- Monthly check of CAD eSUA Map for rule changes
- Document all assumptions dated (see Section 4)
- Prepare flexibility into UAV pathfinding (don't hardcode rules)
- Plan stakeholder review meeting (Week 10) to validate approach

**Owner**: Wardells (regulatory liaison)
**Frequency**: Monthly

---

### Risk 3.2: Marine Department Data Access
**Severity**: MEDIUM
**Probability**: MEDIUM
**Impact**: Real vessel traffic data (VTMS/AIS) is restricted access. Phase 1 uses simulated data; Phase 2 needs real data for validation.

**Current Status**: Simulated 8 vessels. Real Hong Kong harbor has 200+ vessels/day.

**Mitigation**:
- Request VTMS data access from Marine Department (Week 3)
- Prepare letter from advisor explaining research purpose
- If denied, use published AIS data (MarineTraffic API as fallback)
- Validate simulator against real AIS traces as proxy for VTMS

**Owner**: Wardells (admin lead)
**Deadline**: End of Week 3

---

### Risk 3.3: PDPO Privacy Compliance Scope Creep
**Severity**: MEDIUM
**Probability**: LOW
**Impact**: Privacy requirements might extend beyond what we planned (Phase 2). Could require cryptographic protocols not in current scope.

**Current Status**: Phase 2 plans line-of-sight privacy routing. Sufficient for most scenarios.

**Mitigation**:
- Clarify privacy requirements with advisor early (Week 2)
- Document what PDPO specifically requires (see Assumptions, Section 4)
- Design privacy as plugin (can swap algorithms)
- Have fallback algorithm if scope changes

**Owner**: Rozz
**Deadline**: End of Week 2

---

## 4. Project Assumptions

### Assumption A1: Wind Data Availability
- **What we assume**: HKO Open Data provides 10-min resolution wind at ≥ 99% uptime
- **What we verified**: Tested 2 API calls successfully (2026-03-30)
- **Risk if false**: Simulation cannot run; would need offline wind synthesis
- **Validation plan**: Monitor uptime throughout project

---

### Assumption A2: Principal Fairway Boundaries Don't Change
- **What we assume**: 5 major fairways used in Phase 1 remain fixed throughout project
- **What we verified**: Downloaded from Marine Department GeoJSON (dated 2024-10)
- **Risk if false**: Vessel positions marked as "in_fairway=False" would become invalid
- **Validation plan**: Check Marine Department updates quarterly

---

### Assumption A3: Agent-Based Model Captures Real Behavior
- **What we assume**: 3 vessel agent types (Ferry/Cargo/Yacht) are sufficient for Phase 1 baseline
- **What we verified**: Researched ferry schedules, cargo wind sensitivity from literature
- **Risk if false**: Simulation outputs don't reflect actual harbor dynamics
- **Validation plan**: Compare simulated collision rates vs. historical incident reports (Phase 2)

---

### Assumption A4: 1-Minute Timestep is Sufficient
- **What we assume**: 60-second updates detect all collisions (min safe distance = 500m)
- **What we verified**: Max vessel speed = 12 m/s → 720 m traveled per minute. Detection works.
- **Risk if false**: Fast-moving vessels could pass through collision zone undetected
- **Validation plan**: Add sensitivity analysis in Phase 2 (test 30s, 60s, 120s timesteps)

---

### Assumption A5: Python 3.10+ is Available
- **What we assume**: All team members can install Python 3.10+ on their systems
- **What we verified**: Yes, user was able to install Python 3.11
- **Risk if false**: MATLAB-only teams cannot run simulator
- **Mitigation**: Provide Docker image for non-Python environments

---

### Assumption A6: Fairway Constraints are Hard (Vessels Must Stay In)
- **What we assume**: Vessels will not intentionally cross fairway boundaries
- **Reality**: Some vessels (yachts) may cross boundaries for short routes
- **Risk if false**: Simulation is too restrictive; doesn't capture real behavior
- **Mitigation**: Phase 2 add "emergency override" flag for fairway violations

---

## 5. Data Quality Issues

### Issue 5.1: All Vessels Start at Same Point (Resolved in Code, Not Simulation)
**Problem**: Phase 1 baseline shows 100% collision at t=0 because all 8 vessels spawn at (22.290°N, 114.175°E).

**Why**: Simplified initialization for Phase 1 proof-of-concept.

**Fix Applied**: Documented in README as "Known Limitation 1".

**Phase 2 Fix**: Randomize start positions from historical AIS data.

---

### Issue 5.2: Wind Perturbation is Linear (Not Physically Accurate)
**Problem**: Formula `δheading = 0.1 * wind_speed * sin(wind_dir - bearing)` is approximate.

**Why**: Simplified for Phase 1. Real wind dynamics require 3D field equations.

**Fix Applied**: Documented in README as "Known Limitation 2".

**Phase 2 Fix**: Implement spatial wind interpolation from HKO mesoscale data.

---

### Issue 5.3: No Vessel Avoidance Behavior
**Problem**: Agents move deterministically. Don't apply COLREGs.

**Why**: Simplified for Phase 1. Avoidance logic is complex (depends on vessel type, size, relative position).

**Fix Applied**: Documented in README as "Known Limitation 3".

**Phase 2 Fix**: Implement COLREGs Rules 8-19.

---

## 6. Quality Assurance Plan

### Test Coverage Target: 70% by End of Phase 2

**Currently (Phase 1)**:
- `tests/test_hko_api.py` → API wrapper tests
- Manual integration test (simulator runs without crashing)
- No unit tests for maritime agents yet

**Phase 2 Requirements**:
- Unit tests for VesselAgent position updates (test wind coupling)
- Unit tests for collision detection (Haversine accuracy)
- Integration tests for 24-hour simulation (determinism check)
- Performance tests (ensure < 60s runtime for 1 simulation)

**Owner**: Rozz
**Deadline**: End of Phase 2

---

### Code Review Checklist
- [ ] No hardcoded paths or API keys
- [ ] Docstrings for all public methods
- [ ] Type hints on function signatures
- [ ] No debug print statements in production code
- [ ] Unit tests for new logic
- [ ] Passes `pytest` without warnings

---

## 7. Success Criteria

### Phase 1 Success (✓ Achieved)
- [x] Simulator runs 24-hour baseline
- [x] Outputs 11,520 records with no NaN values
- [x] Fairway constraint checking works
- [x] Collision detection identifies proximity zones
- [x] Wind data integrates from HKO API
- [x] README documents limitations clearly

### Phase 2 Success (Target)
- [ ] 4 known limitations addressed (stagger starts, wind model, COLREGs, UAV integration)
- [ ] Collision rate realistic (< 5% for normal operation)
- [ ] Simulator passes all unit tests (> 70% coverage)
- [ ] Advisor sign-off on validation approach
- [ ] CAD stakeholder engagement confirmed

### Phase 3-6 Success (Target)
- [ ] UAV corridor pathfinding integrated
- [ ] CAD regulatory evidence package complete
- [ ] PDPO privacy routing validated
- [ ] Multi-modal logistics optimization delivered

---

**Document Updated**: 2026-03-30
**Next Review**: End of Week 2 (2026-04-13)
**Owner**: Rozz & Wardells
