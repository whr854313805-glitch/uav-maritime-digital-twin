# Development Workflow & Team Collaboration Guide

## 1. GitHub Workflow

### 1.1 Branch Naming Convention
Follow this pattern: `[type]/[track]-[issue]`

**Types**:
- `feature/` — new functionality
- `fix/` — bug fix or correction
- `docs/` — documentation update
- `refactor/` — code restructuring without behavior change
- `test/` — test addition or update

**Tracks**:
- `T1` = Track 1 (Maritime Integration, Wardells)
- `T2` = Track 2 (V&V & Safety, Rozz)
- `shared` = Both teams (foundation, utilities)

**Examples**:
```
feature/T1-fairway-conflict-detection
fix/shared-wind-api-retry
docs/T2-monte-carlo-design
refactor/T2-privacy-routing
test/T1-collision-detector-accuracy
```

---

### 1.2 Commit Message Format

**Structure**:
```
[scope]: brief description

Detailed explanation of why this change is needed.
- Reference issue if applicable (#123)
- Mention related files or modules
- Link to design doc if complex change

Co-Authored-By: [Teammate Name] <email@example.com>
```

**Examples**:

**Simple fix**:
```
fix(T1): correct Haversine distance calculation

Haversine formula had sign error in lat/lon delta calculation.
Affects collision detection accuracy (now within 0.1% tolerance).
```

**Feature with multiple commits**:
```
feature(T1): implement COLREGs avoidance logic

- Add Rule 8-19 collision avoidance decision tree
- Integrate with existing VesselAgent.update_position()
- Add unit tests for avoidance behavior

Closes #42

Co-Authored-By: Wardells <wardells@example.com>
```

---

### 1.3 Pull Request Workflow

**Step 1: Create Feature Branch**
```bash
git checkout -b feature/T1-new-feature
# Make changes
git add .
git commit -m "feature(T1): new feature description"
```

**Step 2: Push & Create PR**
```bash
git push origin feature/T1-new-feature
# Create PR via GitHub web interface
```

**PR Template** (fill in when creating):
```markdown
## Description
Brief summary of what this PR does.

## Changes Made
- Change 1
- Change 2
- Change 3

## Testing
- [ ] Unit tests written (pytest passes)
- [ ] Manual testing completed
- [ ] No regressions identified

## Related Issues
Closes #42

## Checklist
- [ ] Code follows project style (docstrings, type hints)
- [ ] No hardcoded paths or secrets
- [ ] Documentation updated (README, docstrings)
```

**Step 3: Code Review**
- Reviewer 1 (Wardells) reviews
- Reviewer 2 (Rozz) reviews
- Address feedback & push updates
- Both approve before merge

**Step 4: Merge & Delete Branch**
```bash
git merge feature/T1-new-feature --squash
git push origin --delete feature/T1-new-feature
```

---

## 2. Development Environment Setup

### 2.1 Prerequisites
- Python 3.10+ (verified: 3.11.15 on macOS)
- Git (for version control)
- MATLAB R2023a+ (for Phase 2+ UAV toolbox)
- Node.js 16+ (for Cesium visualization, Phase 2)

### 2.2 Local Setup Steps

**1. Clone repository**
```bash
git clone https://github.com/whr854313805-glitch/uav-maritime-digital-twin.git
cd uav-maritime-digital-twin
```

**2. Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# OR on Windows: venv\Scripts\activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
pip install pytest pytest-cov  # testing tools
```

**4. Verify setup**
```bash
python -c "import src.maritime_simulator; print('✓ Setup OK')"
pytest tests/ -v
```

**5. Configure git user (if not done)**
```bash
git config --local user.name "Your Name"
git config --local user.email "your.email@example.com"
```

---

### 2.3 Recommended IDE Setup

**VS Code** (recommended for Python + Git):
```
Extensions:
- Python (Microsoft)
- Pylance (for type checking)
- Git Graph (for branch visualization)
- Jupyter (for data analysis notebooks)
```

**PyCharm Community Edition** (alternative):
- Built-in Python interpreter management
- Integrated Git workflows
- Excellent refactoring tools

---

## 3. Development Cycle

### 3.1 Weekly Workflow

**Monday**: Plan & Assign
- Team meeting (10am)
- Review blockers from previous week
- Assign tasks for this week (GitHub issues)
- Update project board (Kanban view)

**Tuesday-Thursday**: Implementation
- Each team member works on assigned features
- Commit daily (keep changes small)
- Push to branch end-of-day

**Friday**: Integration & Review
- Create pull requests
- Code review (both reviewers)
- Merge approved PRs
- Verify simulator still runs
- Plan next week's tasks

---

### 3.2 Code Review Process

**Reviewer Checklist**:
1. Does it solve the stated problem? ✓
2. Is code readable & well-documented? ✓
3. Are there unit tests? ✓
4. Does it introduce new dependencies? ✓
5. Any performance concerns? ✓
6. Does it break existing functionality? ✓

**Review Comments**:
- 🟢 **Approve**: Ready to merge
- 🟡 **Request Changes**: Requires updates before merge
- 🔵 **Comment**: Suggestion (not blocking)

**Timeline**: 24-48 hours for review response

---

## 4. Testing Strategy

### 4.1 Unit Tests (Python)

**Run all tests**:
```bash
pytest tests/ -v
```

**Run specific test file**:
```bash
pytest tests/test_maritime_simulator.py -v
```

**Check coverage**:
```bash
pytest tests/ --cov=src --cov-report=html
# Opens coverage/index.html in browser
```

**Target Coverage by Phase**:
- Phase 1: 40% (basic validation)
- Phase 2: 70% (comprehensive testing)
- Phase 3+: 85% (production ready)

---

### 4.2 Test Structure

**Example Test File** (`tests/test_maritime_agents.py`):
```python
import pytest
from src.maritime_agents import VesselAgent, FerryAgent

class TestFerryAgent:
    """Tests for ferry-specific behavior."""

    def test_ferry_speed_constant(self):
        """Ferry should maintain constant 12 m/s speed."""
        ferry = FerryAgent(vessel_id="F001", start_pos=(22.290, 114.175))
        assert ferry.speed == 12

    def test_wind_coupling(self):
        """Wind should perturb heading, not speed."""
        ferry = FerryAgent(vessel_id="F001", start_pos=(22.290, 114.175))
        original_bearing = ferry.bearing

        wind_data = {'speed': 10, 'direction': 180}
        ferry.update_position(dt=60, wind_data=wind_data)

        # Speed unchanged
        assert ferry.speed == 12
        # Bearing perturbed
        assert abs(ferry.bearing - original_bearing) < 10  # deg
```

---

### 4.3 Integration Test: 24-Hour Simulation

**Run baseline simulation**:
```bash
python -m src.maritime_simulator \
  --duration 24h \
  --vessel-count 8 \
  --output output/maritime_baseline.csv
```

**Validate output**:
```python
import pandas as pd

df = pd.read_csv('output/maritime_baseline.csv')
assert len(df) == 8 * 1440, f"Expected 11,520 rows, got {len(df)}"
assert df.isnull().sum().sum() == 0, "CSV contains NaN values"
assert df['in_fairway'].any(), "No vessels in fairway (constraint issue)"
```

---

## 5. Documentation Standards

### 5.1 Code Comments & Docstrings

**Module docstring** (top of file):
```python
"""
Maritime traffic simulator engine.

This module orchestrates agent-based maritime traffic simulation:
- Fetches wind data from HKO API
- Updates vessel positions based on wind & constraints
- Detects collisions and fairway violations
- Outputs simulation results to CSV

Example:
    >>> sim = MaritimeSimulator(vessel_fleet=[...])
    >>> sim.run(duration_hours=24)
    >>> sim.save_results('output/baseline.csv')
"""
```

**Function docstring** (NumPy/SciPy style):
```python
def update_position(self, dt: float, wind_data: dict) -> None:
    """
    Update vessel position based on wind and constraints.

    Parameters
    ----------
    dt : float
        Timestep in seconds
    wind_data : dict
        Wind speed (m/s) and direction (degrees)
        {'speed': 6.2, 'direction': 180}

    Returns
    -------
    None
        Updates self.lat, self.lon, self.bearing in-place

    Notes
    -----
    Wind perturbation formula:
        δheading = wind_strength_factor × sin(wind_direction - vessel_bearing)

    This is a simplified model. Phase 2 will implement 3D wind fields.
    """
```

---

### 5.2 Markdown Documentation

**File headers**:
```markdown
# Document Title

**Purpose**: One-line summary of what this doc is for

**Owner**: [Name] (who maintains this?)

**Last Updated**: 2026-03-30

**Target Audience**: Developers / Advisors / CAD regulators

---
```

**Code blocks with context**:
```markdown
### How to Run Simulation

Execute the 24-hour baseline:
\`\`\`bash
python -m src.maritime_simulator --duration 24h
\`\`\`

Expected output: CSV with 11,520 records (8 vessels × 1,440 minutes)
```

---

## 6. Common Workflows

### 6.1 Adding a New Vessel Type

**Step 1**: Create class in `src/maritime_agents.py`
```python
class TankerAgent(VesselAgent):
    """Large tanker with slow response to wind."""

    def _get_current_speed(self):
        return 8  # m/s, slower than cargo
```

**Step 2**: Add test in `tests/test_maritime_agents.py`
```python
def test_tanker_initialization():
    tanker = TankerAgent(vessel_id="T001", start_pos=(22.290, 114.175))
    assert tanker.speed == 8
```

**Step 3**: Update simulator in `src/maritime_simulator.py`
```python
# In vessel fleet initialization
if vessel_type == 'tanker':
    fleet.append(TankerAgent(...))
```

**Step 4**: Commit & PR
```bash
git checkout -b feature/shared-tanker-agent
git add src/maritime_agents.py tests/test_maritime_agents.py src/maritime_simulator.py
git commit -m "feature(shared): add TankerAgent for large vessel modeling"
git push origin feature/shared-tanker-agent
# Create PR, wait for review, merge
```

---

### 6.2 Fixing a Bug

**Step 1**: Create issue (GitHub)
```
Title: Collision detection misses slow vessels
Description: Haversine formula returns inf for v < 0.1 m/s
```

**Step 2**: Create branch & fix
```bash
git checkout -b fix/shared-collision-min-velocity
# Edit src/collision_detection.py
git add src/collision_detection.py
git commit -m "fix(shared): handle zero velocity in collision detection"
```

**Step 3**: Add test
```bash
# Edit tests/test_collision_detection.py
def test_zero_velocity_collision():
    ...
git add tests/test_collision_detection.py
git commit -m "test(shared): validate collision detection at v=0"
```

**Step 4**: Push & PR
```bash
git push origin fix/shared-collision-min-velocity
```

---

### 6.3 Running Monte Carlo Simulation (Phase 2)

**Script** (`scripts/run_monte_carlo.py`):
```python
import src.maritime_simulator as sim
import numpy as np

# Run 100 simulations with random wind variance
results = []
for i in range(100):
    simulator = sim.MaritimeSimulator(
        wind_variance=np.random.uniform(0.8, 1.2)
    )
    simulator.run(duration_hours=24)
    simulator.save_results(f'output/mc_run_{i:03d}.csv')
    results.append(simulator.get_statistics())

# Analyze results
import pandas as pd
df = pd.DataFrame(results)
print(df.describe())
```

**Run**:
```bash
python scripts/run_monte_carlo.py
```

---

## 7. Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'src'"
**Solution**: Ensure virtual environment is activated and you're in project root
```bash
source venv/bin/activate
python -c "import src"
```

### Problem: HKO API returns 403 Forbidden
**Solution**: Check network connectivity and API rate limiting
```bash
python -c "from src.hko_api_client import HKOAPIClient; client = HKOAPIClient(); print(client.get_current_weather())"
```

### Problem: Git push fails with "unable to access"
**Solution**: Check proxy settings or SSH key configuration
```bash
git config --list | grep proxy
# If proxy configured, try: git config --global --unset https.proxy
```

### Problem: Pytest discovers no tests
**Solution**: Ensure tests follow naming convention (`test_*.py` or `*_test.py`)
```bash
pytest --collect-only  # Lists discovered tests
```

---

## 8. Deployment & Release

### 8.1 Version Numbering
Follow SemVer: `major.minor.patch` (e.g., 0.1.0)

**Phase 1 Release**: v0.1.0 (base maritime simulator)
**Phase 2 Release**: v0.2.0 (UAV integration, avoidance logic)
**Phase 3 Release**: v1.0.0 (full digital twin)

### 8.2 Release Checklist
- [ ] All tests pass (100% if Phase 1)
- [ ] README updated with new features
- [ ] CHANGELOG.md entry added
- [ ] Version bumped in setup.py
- [ ] Git tag created (`git tag v0.1.0`)
- [ ] Pushed to GitHub (`git push origin v0.1.0`)
- [ ] Advisor notified of release

---

**Document Version**: 1.0
**Last Updated**: 2026-03-30
**Owner**: Rozz & Wardells
