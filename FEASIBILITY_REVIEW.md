# 项目可行性审查报告

# Digital Twin Air Corridor System for Victoria Harbour UAV Logistics

**审查日期**: 2026-04-05
**审查人**: Rozz & Wardells
**项目周期**: 12-14 周（6个Phase）
**工具链调整**: AnyLogic 替代 MATLAB（经导师建议）

---

## 〇、核心问题：AnyLogic 能否替代 MATLAB？

### 结论：可以替代 90%，剩余 10% 不影响项目目标

| 能力 | AnyLogic | MATLAB | 项目是否需要 | 判定 |
|------|----------|--------|-------------|------|
| Agent-Based 仿真 | ✅ 原生支持 | ⚠️ 需手写 | ✅ 核心需求 | **AnyLogic 更优** |
| 3D 可视化 | ✅ 内置 | ⚠️ 需额外工具 | ✅ 核心需求 | **AnyLogic 更优** |
| GIS 地图集成 | ✅ 内置 OpenStreetMap | ❌ 无 | ✅ 核心需求 | **AnyLogic 更优** |
| 路径规划 (A*/RRT*) | ✅ 可实现 | ✅ Robotics Toolbox | ✅ Phase 3 | **两者均可** |
| COLREGs 避碰 | ✅ 状态图建模 | ⚠️ 需手写 | ✅ Phase 2 | **AnyLogic 更优** |
| Monte Carlo | ✅ 内置参数扫描 | ✅ 原生支持 | ✅ Phase 4 | **两者均可** |
| UAV 6-DOF 动力学 | ⚠️ 能做但不专业 | ✅ Simulink UAV Toolbox | ❌ 非核心 | **不影响** |
| PID 控制器设计 | ⚠️ 粗糙 | ✅ Control Toolbox | ❌ 非核心 | **不影响** |

**关键判断**：你们的项目目标是「走廊规划」和「冲突检测」，不是设计无人机飞控系统。UAV 6-DOF 动力学和 PID 控制是航空工程专业的课题，不在你们的 scope 内。AnyLogic 完全满足项目需求。

**建议**：不需要安装 MATLAB。节省的学习时间（2周）投入到 AnyLogic 和 3D 数据集成上。

---

## 一、Layer 1 可行性审查：数据输入与集成

### 1.1 审查对象

| 数据源 | 用途 | 格式 | 费用 |
|--------|------|------|------|
| HKO Open Data API | 风速、风向、温湿度 | REST JSON | 免费 |
| LandsD 3D-BIT00 | 地形高程 | GeoTIFF / NumPy | 免费 |
| Open3DHK | 3D建筑模型 | CityGML / 3D Tiles | 免费 |
| Marine Dept 海图 | Principal Fairways | GeoJSON | 免费 |
| AIS/VTMS | 历史船舶轨迹 | CSV / AIS NMEA | 需申请 |

### 1.2 逐项审查

**HKO Open Data API**
- 现状：✅ 已实现 (`hko_api_client.py`, 含 retry 逻辑)
- 实测：2026-03-30 成功获取风速=6.2m/s、风向=180°
- 风险：API 限流（未测试高频调用）
- 判定：**✅ 可行 — 已验证**

**LandsD 3D-BIT00 高程数据**
- 现状：✅ 已实现（`geospatial_loader.py`, 20m分辨率, 2.1MB）
- 问题：⚠️ 目前是**模拟数据**（`download_geospatial.py` 生成的随机网格），不是真实地形
- 修复：需要从 LandsD 官网下载真实高程数据（免费）
- 判定：**⚠️ 有条件可行 — 需替换为真实数据**

**Open3DHK 3D建筑**
- 现状：⚠️ 目前只加载了 **50个模拟建筑特征**，无建筑高度
- 问题：Phase 2/3 需要**真实3D建筑高度**用于 UAV 避障和 PDPO 视线分析
- 修复：从 https://3d.map.gov.hk 下载 Victoria Harbour 区域 CityGML 数据
- 格式兼容：AnyLogic 支持导入 GIS shapefile；CityGML 需转换
- 判定：**⚠️ 有条件可行 — 需下载真实数据 + 格式转换**

**Marine Department 航道数据**
- 现状：✅ 已实现（5条主要航道，lat/lon边界）
- 问题：⚠️ 实际上有10条 Principal Fairways，目前只建模了5条
- 修复：补充剩余5条航道定义
- 判定：**⚠️ 有条件可行 — 需补全数据**

**AIS/VTMS 历史船舶数据**
- 现状：❌ 未获取。Phase 1 使用模拟的8艘船
- 问题：真实数据需要向 Marine Department 申请，可能需要导师出面
- 替代方案：MarineTraffic.com 公开 AIS 数据（部分免费）
- 判定：**⚠️ 高风险 — 需尽快申请或找替代**

### 1.3 Layer 1 综合判定

```
┌─────────────────────────────────────┐
│  Layer 1 判定: ⚠️ 有条件可行        │
│                                     │
│  已完成: 2/5 (HKO API, 基础架构)    │
│  需改进: 3/5 (真实地形、3D建筑、AIS)│
│                                     │
│  阻断风险: AIS数据获取              │
│  预计修复时间: 1周                  │
└─────────────────────────────────────┘
```

---

## 二、Layer 2 可行性审查：环境仿真

### 2.1 审查对象

| 组件 | 当前状态 | 目标状态 | 工具 |
|------|---------|---------|------|
| Maritime Agent Model | ✅ Python 已实现 | 迁移到 AnyLogic | AnyLogic ABM |
| Wind Field Dynamics | ⚠️ 线性2D模型 | 3D风场插值 | AnyLogic + HKO |
| 3D Building & Terrain | ⚠️ 模拟数据 | 真实3D城市模型 | Open3DHK + AnyLogic GIS |
| Noise Propagation | ❌ 未开始 | 噪声传播模型 | AnyLogic + Python |

### 2.2 逐项审查

**Maritime Agent Model → AnyLogic 迁移**
- 现状：Python 实现了 3类船舶（Ferry/Cargo/Yacht），8艘船，24h仿真
- 迁移工作量：在 AnyLogic 中重建 3个 Agent 类型（约 2-3天）
- AnyLogic 优势：内置碰撞检测、空间查询、3D动画
- 风险：需要学习 AnyLogic 建模语言（Java-based）
- 判定：**✅ 可行 — 工作量可控**

**Wind Field Dynamics**
- 现状：`δheading = 0.1 × wind_speed × sin(wind_dir - bearing)` — 线性2D
- Phase 2 目标：3D风场（u,v,w三分量），空间插值
- AnyLogic能力：可以读取外部数据表，按位置插值
- 方案：Python 预处理 HKO 数据 → CSV → AnyLogic 读取 → 按Agent位置插值
- 判定：**✅ 可行 — 需要 Python-AnyLogic 数据桥接**

**3D Building & Terrain**
- 现状：模拟的 50个建筑 + 随机高程
- Phase 2 目标：真实 Victoria Harbour 3D 场景
- AnyLogic GIS 能力：支持导入 shapefile、OpenStreetMap
- Open3DHK：提供 CityGML 格式（需转为 shapefile 或 3D Tiles）
- 工具链：Open3DHK → QGIS 转换 → shapefile → AnyLogic 导入
- 风险：CityGML → shapefile 转换可能丢失高度信息
- 替代方案：直接在 AnyLogic 中使用 OpenStreetMap + 手动标注关键建筑高度
- 判定：**⚠️ 有条件可行 — 需验证3D数据导入流程**

**Noise Propagation Model**
- 现状：❌ 未开始
- 重要性：LOW（对UAV走廊规划是加分项，非必需）
- 方案：可推迟到 Phase 5，或简化为距离衰减公式
- 判定：**✅ 可行（可推迟）**

### 2.3 Layer 2 综合判定

```
┌─────────────────────────────────────┐
│  Layer 2 判定: ⚠️ 有条件可行        │
│                                     │
│  核心风险: AnyLogic 学习曲线        │
│  预计迁移时间: 1-2周               │
│  关键验证: 3D数据能否导入AnyLogic   │
│                                     │
│  建议: 先用AnyLogic搭建最简Demo    │
│  (1个Ferry + 1条Fairway + OSM地图) │
│  验证工具链可行后再全面迁移         │
└─────────────────────────────────────┘
```

---

## 三、Layer 3 可行性审查：决策优化

### 3.1 审查对象

| 组件 | 复杂度 | 工具 | 依赖 |
|------|--------|------|------|
| Path Planning (A*/RRT*) | HIGH | AnyLogic + Java | Layer 2 3D环境 |
| Fairway-Corridor Conflict | MEDIUM | AnyLogic 空间查询 | Maritime Agent + UAV Agent |
| Multi-modal Logistics | MEDIUM | AnyLogic 优化 | 全部Layer 1-2 |
| Vertiport Location | LOW | AnyLogic GIS分析 | 3D建筑 + 航道数据 |

### 3.2 逐项审查

**UAV Path Planning (A*/RRT*)**
- 目标：在3D空间中规划UAV走廊，避开建筑、航道、隐私区域
- AnyLogic 能力：有内置路径规划（适用于2D），3D路径需自定义
- 方案：
  - 2D路径规划：AnyLogic内置，可直接用 ✅
  - 3D路径规划：需自己实现 RRT* 或调用外部库
  - 替代：将3D问题分解为「2D平面路径 + 高度层选择」
- 风险：真正的3D RRT*实现复杂度高，可能需要2-3周
- 判定：**⚠️ 有条件可行 — 建议分解为2D+高度层**

**Fairway-Corridor Conflict Detection**
- 目标：检测UAV走廊是否与船舶航道在垂直投影上重叠
- 方案：在 AnyLogic 中，检测 UAV Agent 的(x,y)投影是否落在 Fairway 多边形内
- 复杂度：LOW — AnyLogic 有空间查询 API
- 判定：**✅ 可行**

**Multi-modal Logistics Comparison**
- 目标：对比 UAV 配送 vs 传统船舶/陆路运输的成本、时间、碳排放
- AnyLogic 能力：内置物流建模库
- 数据需求：运输成本数据（可查文献获取）
- 风险：需要合理的成本假设（运营成本、电池消耗等）
- 判定：**✅ 可行 — 依赖合理的参数假设**

**Vertiport Location Optimization**
- 目标：在Victoria Harbour选择最优无人机起降点
- 方案：基于约束的优化（远离航道、远离居民区、靠近需求点）
- AnyLogic 能力：可以用参数扫描 + GIS约束
- 判定：**✅ 可行**

### 3.3 Layer 3 综合判定

```
┌─────────────────────────────────────┐
│  Layer 3 判定: ⚠️ 有条件可行        │
│                                     │
│  核心风险: 3D路径规划复杂度         │
│  建议: 简化为 2D路径+高度层选择     │
│  预计时间: 2-3周                    │
│                                     │
│  前置条件: Layer 2 必须完成         │
│  (需要3D环境才能做路径规划)         │
└─────────────────────────────────────┘
```

---

## 四、Layer 4 可行性审查：验证与验证 (V&V)

### 4.1 审查对象

| 组件 | 复杂度 | Rozz负责 | 依赖 |
|------|--------|---------|------|
| Monte Carlo UQ | MEDIUM | ✅ | Layer 2 仿真引擎 |
| Component Validation | LOW | ✅ | 各组件单元测试 |
| Cybersecurity Threat | MEDIUM | ✅ | 系统架构文档 |
| PDPO Privacy (视线分析) | HIGH | ✅ | 3D建筑高度数据 |

### 4.2 逐项审查

**Monte Carlo Uncertainty Quantification**
- 目标：通过1000+次随机仿真，量化走廊安全性的置信区间
- AnyLogic 能力：内置 Parameter Variation Experiment（参数扫描）
- 方案：定义随机变量（风速±20%、船舶出发时间±30min、UAV速度±10%）→ 批量运行 → 统计碰撞概率
- 硬件要求：16GB Mac 可以跑 100-500 次（每次~30秒），1000次需要~8小时
- 判定：**✅ 可行 — AnyLogic 原生支持**

**Component-level Validation**
- 目标：验证每个模块的输出是否合理
- 方案：
  - HKO API：对比官方网站数据 ✅
  - Agent 行为：对比文献中的船舶速度/行为 ✅
  - 碰撞检测：手动计算已知距离验证 ✅
- 判定：**✅ 可行**

**Cybersecurity Threat Modeling**
- 目标：分析数字孪生系统的安全威胁（数据篡改、通信劫持等）
- 方案：使用 STRIDE 或 LINDDUN 框架进行威胁建模
- 工具：不需要编程，主要是文档分析 + 威胁矩阵
- 风险：需要网络安全领域知识（可查文献）
- 判定：**✅ 可行 — 文献驱动，不依赖工具**

**PDPO Privacy Compliance — 视线分析**
- 目标：计算UAV从空中到建筑窗户的视线（line-of-sight），确保不侵犯隐私
- 关键依赖：**3D建筑高度数据**
- 方案：
  - 从 Open3DHK 获取建筑高度
  - 实现 ray-casting 算法（从UAV位置到建筑立面）
  - 标记「隐私冲突区域」，UAV走廊必须避开
- AnyLogic 能力：3D场景中可以做射线检测
- 风险：Open3DHK 数据精度是否满足视线分析要求（需要窗户级精度 vs 建筑级精度）
- 替代方案：简化为「UAV距离建筑 > Xm → 无隐私风险」的缓冲区方法
- 判定：**⚠️ 有条件可行 — 建议先用缓冲区方法，再迭代改进**

### 4.3 Layer 4 综合判定

```
┌─────────────────────────────────────┐
│  Layer 4 判定: ✅ 基本可行           │
│                                     │
│  Rozz 负责的4个组件中:              │
│  ✅ 3个可行 (Monte Carlo, Validation,│
│     Cybersecurity)                  │
│  ⚠️ 1个需简化 (PDPO 视线分析)       │
│                                     │
│  建议: PDPO先用缓冲区方法           │
│  (距建筑>50m = safe)，Phase 5再迭代 │
└─────────────────────────────────────┘
```

---

## 五、Layer 5 可行性审查：输出与监管合规

### 5.1 审查对象

| 组件 | 复杂度 | 依赖 |
|------|--------|------|
| CAD Regulatory Evidence | HIGH | 全部 Layer 1-4 |
| Risk Assessment Report | MEDIUM | Monte Carlo 结果 |
| Multi-modal Recommendation | LOW | 物流对比分析 |

### 5.2 逐项审查

**CAD Regulatory Evidence Package**
- 目标：向民航处提交UAV走廊安全性证据
- 内容：仿真数据、碰撞概率、隐私合规证明、网络安全评估
- 问题：⚠️ 不确定 CAD 要求的具体格式和内容标准
- 方案：
  - 查阅 CAD eSUA Map 申请流程（公开文件）
  - 参考已发布的 UAV 运营申请案例
  - 如果找不到格式要求，按照学术论文格式组织证据
- 判定：**⚠️ 有条件可行 — 需要调研 CAD 具体要求**

**Risk Assessment Report**
- 目标：基于 Monte Carlo 结果，输出碰撞风险等级
- 方案：标准的风险矩阵（概率 × 后果 = 风险等级）
- 工具：AnyLogic 输出 → Python/Excel 分析 → 报告
- 判定：**✅ 可行**

**Multi-modal Logistics Recommendation**
- 目标：对比 UAV vs 船舶 vs 陆路的成本效益
- 方案：建立成本模型，用 AnyLogic 仿真验证
- 判定：**✅ 可行**

### 5.3 Layer 5 综合判定

```
┌─────────────────────────────────────┐
│  Layer 5 判定: ⚠️ 有条件可行        │
│                                     │
│  核心风险: CAD格式要求不明确        │
│  建议: 提前联系CAD了解要求          │
│  或以学术报告形式替代               │
└─────────────────────────────────────┘
```

---

## 六、工具链可行性审查

### 6.1 新工具链：AnyLogic + Python + Open3DHK

```
┌──────────────────────────────────────────────────┐
│  AnyLogic (核心仿真 + 3D可视化 + GIS)             │
│    ↑ 读取CSV/数据库                                │
│  Python (数据采集 + 预处理 + 分析)                  │
│    ↑ API调用                                       │
│  HKO API + Open3DHK + Marine Dept                  │
└──────────────────────────────────────────────────┘
```

| 工具 | 版本 | 费用 | Mac兼容 | 学习时间 |
|------|------|------|---------|---------|
| AnyLogic PLE | 8.x | 免费 | ✅ | 1-2周 |
| Python 3.11 | 已安装 | 免费 | ✅ | 已掌握 |
| Open3DHK | 在线 | 免费 | ✅ | 1-2天 |
| QGIS | 3.x | 免费 | ✅ | 1-2天 |

### 6.2 数据流验证

**需要验证的关键链路**：

| 链路 | 说明 | 验证方法 | 风险 |
|------|------|---------|------|
| Python → AnyLogic | HKO风场数据传入仿真 | CSV文件交换 | LOW |
| Open3DHK → AnyLogic | 3D建筑导入仿真环境 | CityGML → shapefile → AnyLogic | **HIGH** |
| AnyLogic → Python | 仿真结果导出分析 | CSV/数据库导出 | LOW |
| AnyLogic 3D → 演示 | 动画输出给老师/CAD | AnyLogic内置录制 | LOW |

**最高风险链路**：Open3DHK 3D数据 → AnyLogic

建议的验证步骤：
1. 从 Open3DHK 下载一个小区域的 CityGML
2. 用 QGIS 打开，检查建筑高度字段是否存在
3. 导出为 shapefile
4. 在 AnyLogic 中导入 shapefile
5. 验证建筑在3D场景中是否正确显示

**如果这条链路失败**：备选方案是使用 AnyLogic 内置的 OpenStreetMap 地图 + 手动定义关键建筑高度

### 6.3 工具链综合判定

```
┌─────────────────────────────────────┐
│  工具链判定: ⚠️ 有条件可行          │
│                                     │
│  必须先验证: Open3DHK → AnyLogic   │
│  预计验证时间: 1-2天               │
│  如果失败: 有备选方案（OSM + 手动） │
└─────────────────────────────────────┘
```

---

## 七、资源可行性审查

### 7.1 时间资源

| Phase | 计划时间 | 实际进度 | 剩余工作 | 风险 |
|-------|---------|---------|---------|------|
| Phase 1 | Week 1-2 | ✅ 基本完成 | 替换模拟数据为真实数据 | LOW |
| Phase 2 | Week 3-5 | 🔄 迁移到AnyLogic | AnyLogic学习+重建Agent | **MEDIUM** |
| Phase 3 | Week 6-8 | ❌ 未开始 | UAV路径规划+冲突检测 | **HIGH** |
| Phase 4 | Week 9-10 | ❌ 未开始 | Monte Carlo + PDPO | MEDIUM |
| Phase 5 | Week 11-12 | ❌ 未开始 | 报告+演示 | LOW |

**时间压力分析**：
- Phase 1 → Phase 2 转换增加了 1-2周（AnyLogic学习 + 迁移）
- 原计划 12周，现在可能需要 14周
- 建议：Phase 3 中的噪声传播模型推迟或取消，腾出2周

### 7.2 硬件资源

| 资源 | 需求 | 你的Mac | 判定 |
|------|------|---------|------|
| RAM | AnyLogic推荐8GB | 16GB | ✅ 足够 |
| 存储 | AnyLogic ~2GB + 数据 ~5GB | 75GB可用 | ✅ 足够 |
| CPU | Monte Carlo需要多核 | Apple M系列 | ✅ 足够 |
| GPU | 3D渲染 | Apple集成GPU | ⚠️ 够用但可能卡顿 |

### 7.3 团队技能

| 技能 | 当前水平 | 需要水平 | 差距 | 解决方案 |
|------|---------|---------|------|---------|
| Python | ✅ 中等 | 中等 | 无 | — |
| AnyLogic | ❌ 零基础 | 中等 | **大** | 官方教程 1-2周 |
| GIS/地理 | ⚠️ 基础 | 中等 | 中 | QGIS教程 2-3天 |
| Java (AnyLogic) | ⚠️ 基础 | 基础 | 小 | AnyLogic内可视化建模 |
| 网络安全 | ⚠️ 基础 | 基础 | 小 | STRIDE框架文献 |

### 7.4 资源综合判定

```
┌─────────────────────────────────────┐
│  资源判定: ⚠️ 有条件可行            │
│                                     │
│  最大瓶颈: AnyLogic学习曲线        │
│  建议: 本周开始学AnyLogic          │
│  硬件: 足够                        │
│  时间: 需要额外2周缓冲             │
└─────────────────────────────────────┘
```

---

## 八、综合可行性判定

### 8.1 总结矩阵

| 审查维度 | 判定 | 主要风险 | 缓解措施 |
|---------|------|---------|---------|
| Layer 1 数据层 | ⚠️ 有条件 | AIS数据获取 | 用MarineTraffic替代 |
| Layer 2 仿真层 | ⚠️ 有条件 | AnyLogic学习曲线 | 先做最简Demo |
| Layer 3 优化层 | ⚠️ 有条件 | 3D路径规划复杂 | 简化为2D+高度层 |
| Layer 4 验证层 | ✅ 基本可行 | PDPO视线分析 | 先用缓冲区方法 |
| Layer 5 输出层 | ⚠️ 有条件 | CAD格式不明确 | 学术报告替代 |
| 工具链 | ⚠️ 有条件 | 3D数据导入 | OSM备选方案 |
| 资源 | ⚠️ 有条件 | 时间+技能 | 砍掉噪声模型 |

### 8.2 最终判定

```
╔═══════════════════════════════════════════════╗
║                                               ║
║   项目整体可行性: ⚠️ 有条件可行               ║
║                                               ║
║   结论: 项目技术上可行，但需要:               ║
║   1. 砍掉或推迟非核心功能（噪声模型）         ║
║   2. 简化高复杂度功能（3D→2D+高度层）         ║
║   3. 本周验证 AnyLogic + Open3DHK 数据链路    ║
║   4. 增加 2周缓冲时间                         ║
║                                               ║
║   如果以上条件满足: ✅ 项目可执行              ║
║   如果 AnyLogic 3D导入失败: 仍可行            ║
║   （回退到 Python + Cesium.js 方案）           ║
║                                               ║
╚═══════════════════════════════════════════════╝
```

### 8.3 本周必须完成的3件事（Go/No-Go 检查点）

**检查点 1**: 下载并安装 AnyLogic PLE，完成官方 Hello World 教程
- 如果成功 → 继续
- 如果 Mac 不兼容 → 回退 Python 方案

**检查点 2**: 从 Open3DHK 下载 Victoria Harbour 小区域 → 尝试导入 AnyLogic
- 如果成功 → 继续
- 如果失败 → 用 OpenStreetMap + 手动建筑高度

**检查点 3**: 在 AnyLogic 中创建 1个Ferry Agent + 1条Fairway + 风场 的最简Demo
- 如果成功 → 确认迁移方案
- 如果失败 → 评估是否保留 Python 方案

---

## 九、建议的修订后时间表

| 周次 | 任务 | 交付物 |
|------|------|--------|
| **Week 1-2** ✅ | Phase 1 Python实现 | 已完成 |
| **Week 3** (本周) | AnyLogic学习 + Go/No-Go验证 | 3个检查点通过 |
| **Week 4-5** | Layer 2 AnyLogic重建 (Maritime ABM + 3D) | AnyLogic仿真Demo |
| **Week 6** | 真实数据替换 + Layer 1完善 | 真实Open3DHK + HKO集成 |
| **Week 7-8** | Layer 3 UAV路径规划 + 冲突检测 | UAV走廊Demo |
| **Week 9-10** | Layer 4 Monte Carlo + PDPO | 验证报告 |
| **Week 11-12** | Layer 5 输出 + 论文 | CAD证据包 + 最终报告 |
| **Week 13-14** (缓冲) | 修复 + 演示准备 | 最终演示 |

---

**文档版本**: 1.0
**审查日期**: 2026-04-05
**下次审查**: Week 3 结束时（Go/No-Go决策）
**审查人**: Rozz & Wardells
