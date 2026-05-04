# 维港 UAV 数字孪生 V&V 项目 — 更新日志

## [v1.6.0] 2026-05-04 — 全面优化与统一

### 新增
- 项目导航首页 `output/index.html` — 一站式访问所有功能
- **加载 spinner** — 所有 dashboard 启动时显示
- **数据真实性 banner** — 顶部提示，点击查看 12 个数据源的真实性等级表
- **截图功能** — 右下角按钮，按引擎自动适配 (Cesium / Mapbox / MapLibre)
- **键盘快捷键**：
  - `Space` 暂停/播放
  - `← →` ±1 分钟（`Shift+← →` ±10 分钟）
  - `R` 重置视图
  - `F` 全屏
  - `M` 切换面板
  - `I` 数据真实性说明
  - `S` 截图
  - `P` FPS 监视
  - `Esc` 关闭弹窗
- **错误 toast** — 友好的错误提示（取代 alert）
- **FPS 监视器** — `P` 键开关，监控渲染性能
- **全局 console 横幅** — 控制台显示快捷键说明

### 修复 (Bug)
- **3D Free 版**: 初始 zoom 12.5 太远导致建筑物不可见，调整为 13.2
- **3D Free 版**: building 高度用 zoom interpolate 在初始视图为 0，改为直接 render_height
- **3D Mapbox 版**: 同上 zoom 修复
- **MapLibre/Mapbox**: 加 `preserveDrawingBuffer: true` 让截图能工作
- **所有版本**: 暴露 `window.maplibreMap` / `window.cesiumViewer` / 等到全局，方便快捷键和截图

### 优化
- 启动脚本菜单新增 "✨ 3D Free" 推荐项
- 所有 HTML 引擎 instance 暴露到 window 方便外部调用

---

## [v1.5.0] 2026-05-01 — Phase 5 + 6 完成

### 新增
- **Phase 5.1 实时 JS A***: 浏览器内 A* 算法每分钟随船位置自动重算 reroute
- **Phase 5.2 多 UAV 协同避让**: 4 交叉点检测 + TCAS 30s 错峰起飞
- **Phase 5.3 CesiumJS 3D 版**: vessel_replay_3d.html
- **Phase 5.5 UAV 能耗续航**: DJI Matrice 300 模型 + 5 走廊电量分析
- **Phase 6 V&V 集成报告**: VV_INTEGRATED_REPORT.html (单页面汇总)

### 数据
- `multi_uav_coordination.json` (4 交叉点 + 起飞调度)
- `uav_schedule.csv` (5 UAV 错峰起飞表)
- `uav_energy_analysis.csv` (能耗分析)
- `uav_energy.json` (UAV 物理参数)

### V&V 量化结果
- 平均合规率: 35.6% → **100%** (+64.4 pts via A* 动态规划)
- UAV 协同冲突: 1 (严重) → **0** (错峰后)
- 能耗: 5/5 走廊单程往返均可行 (≤61.6%)

---

## [v1.4.0] 2026-04-28 — Phase 4 A* 路径规划

### 新增
- **A* 算法实现** (`astar_routing.py`): 维港 1950 cells 栅格 + 静态/动态成本
- **24h 全量 reroute 基准**: 120 次 A* 全部成功，平均绕路成本 +5.6%
- 2D 大屏加 "A* 静态绕行" toggle 显示 reroute 路径
- Phase 4 完成报告

### 关键发现
- **C5 永久阻塞 (A-2 单船)** → A* 仅需 +56m (×1.02) 即可绕开
- 5 走廊 24h 任何时刻 A* 100% 找到路径

---

## [v1.3.0] 2026-04-28 — Phase 3 UAV Agent + V&V

### 新增
- **5 条候选 UAV 走廊**: 中环↔启德 / 尖沙咀↔红磡医院 / 北角↔鲤鱼门 / 西九龙↔中环 / 尖沙咀↔北角
- **5 架 UAV agent** 沿走廊 24h 飞行
- **5 数据源接入**:
  - HKO 气候态风场 (10 站) → IDW 插值
  - Open3DHK 公开数据 → 28 栋香港主要高层
  - LandsD 暂未接入
  - MarDep RP06005i.XML → 65 真实在港船
  - Star Ferry 官方时刻表 .csv
- **V&V 算法**: Haversine + IDW + PDPO 50m 缓冲 + 三维状态合成
- **24h × 5 走廊 全量分析** → vv_24h_analysis.csv (7200 行)
- Phase 3 完成报告

### V&V 业务洞察
- C2 紧急医疗走廊 24h 100% 合规 (唯一畅通)
- C1/C5 0% 合规 (与船舶轨迹冲突)
- 24h 内 100% 时段都至少 1 条走廊 BLOCKED → 必须做实时路径规划

---

## [v1.2.0] 2026-04-27 — 真实数据接入

### 新增
- 一键下载脚本 `realdata/download_realdata.command`
- 解析 MarDep XML → 65 艘真实在港船舶 (`all_real_vessels.json`)
- 解析 Star Ferry CSV → 真实班次表
- 8 仿真船全部映射到真实船身份 (vessel_metadata.csv):
  - StarFerry × 3: 真实班次 + 真实码头坐标
  - Cargo: HELIOS (IMO 9810733), JIN XIANG (IMO 9566588)
  - Yacht: OCEAN STAR, SUNONE, CLB65-5224
- 两层数据并存：8 仿真动画 + 65 真实静态

---

## [v1.1.0] 2026-04-22 — 水域几何修复

### 修复
- 原始合成 CSV 把船舶撒到 HK Island 山地 (lat 22.268)
- 重写 `gen_water_trajectories.py` 严格水带表
- 8 艘船 1440 分钟全部在 Victoria Harbour 真实水面

---

## [v1.0.0] 2026-04-13 — Phase 2A/2B 完成

### 新增
- AnyLogic GIS 项目验证
- 11520 条仿真数据 (8 船 × 1440 分钟)
- Java Timer 后台轮询替代 OnStepCode (Mac PLE bug 绕开)
- 浏览器 Leaflet 大屏 vessel_replay.html

---

## [v0.x] 2026-03-30 — Phase 1 数据基础

- Python 海上交通仿真 (11520 条记录, maritime_baseline_24h.csv)
- 5 数据源可行性评估 (FEASIBILITY_REVIEW.md)
- 项目架构设计 (README.md)
