# vessel_positions.csv 数据来源说明

最后更新：2026-04-27

## 数据真实性等级

| Vessel ID | 真实船名 | IMO | 船型 | 船旗 | 抵港时间 | 真实性等级 |
|---|---|---|---|---|---|---|
| StarFerry_0 | Star Ferry (one of fleet) | — | PASSENGER FERRY | 香港 | — | **GRADE A** |
| StarFerry_1 | Star Ferry (one of fleet) | — | PASSENGER FERRY | 香港 | — | **GRADE A** |
| StarFerry_2 | Star Ferry (one of fleet) | — | PASSENGER FERRY | 香港 | — | **GRADE A** |
| Cargo_0 | **HELIOS** | 9810733 | BULK / WOODCHIP / CEMENT / ORE CARRIER | PANAMA | 2026/04/27 18:04 | **GRADE B** |
| Cargo_1 | **JIN XIANG** | 9566588 | BULK / WOODCHIP / CEMENT / ORE CARRIER | HONG KONG, CHINA | 2026/04/27 15:32 | **GRADE B** |
| Yacht_0 | **OCEAN STAR** | TEMP00167 | PLEASURE VESSEL / YACHT | CHINA | 2024/02/03 16:56 | **GRADE B** |
| Yacht_1 | **SUNONE** | 9663829 | PLEASURE VESSEL / YACHT | PANAMA | 2023/11/10 06:27 | **GRADE B** |
| Yacht_2 | **CLB65-5224** | TEMP00088 | PLEASURE VESSEL / YACHT | CHINA | 2023/05/09 18:00 | **GRADE B** |

## 真实性等级定义

**GRADE A — 高真实性**
- 真实班次频率（来自 Star Ferry 官方 Open Data CSV，2018-02 更新）
- 真实码头坐标：Central Pier No.7 (22.2870, 114.1614)、Kowloon Point Ferry Pier (22.2945, 114.1685)
- 官方公布的航行时间 9 分钟
- 班次密度按时段调整（早高峰 6 分钟一班、平峰 8 分钟、夜间 11 分钟）

**GRADE B — 中等真实性（真实身份 + 合成航线）**
- 船名、IMO 编号、船型、船旗、抵港时间均为真实数据（来自 Hong Kong Marine Department RP06005i.XML，实时数据）
- 港内具体航线为合成（按主航道东西向往返 + 水带约束），因为公开数据不含连续 GPS 轨迹
- 想要 GRADE A 货船航线需要付费 AIS 服务（MarineTraffic / VesselFinder）

**GRADE C — 完全合成**
- 本数据集中已无 GRADE C 船只

## 数据源原始文件

`../realdata/`

| 文件 | 来源 | 内容 |
|---|---|---|
| `starferry_central_tst_timetable.csv` | https://www.starferry.com.hk/sites/default/files/ferry_sf_central_tsimshatsui_timetable_updatedon022018_eng.csv | 中环↔尖沙咀官方班次表 |
| `mardep_in_port.xml` | https://www.mardep.gov.hk/e_files/en/opendata/RP06005i.XML | 香港海事处实时维港在港船单（65 艘船） |

## 重新生成

`gen_v3_realdata.py` 是当前生成脚本。重跑：

```bash
cd /Users/rozz/Desktop/pre/uav-maritime-twin/output
python3 gen_v3_realdata.py
```

输出：
- `vessel_positions.csv` — 11520 行（1440 分钟 × 8 艘）每分钟位置
- `vessel_metadata.csv` — 8 行 vessel_id → 真实船舶信息映射

## 升级到 GRADE A 货船航线（如有预算）

如果项目需要货船也是真实 GPS 轨迹：

| 服务 | 费用 | 数据 |
|---|---|---|
| [MarineTraffic Historical AIS](https://www.marinetraffic.com/en/ais/details/ports/2429) | ~USD 20-50/月起 | 香港港口完整 AIS 历史轨迹 |
| [VesselFinder Historical AIS](https://www.vesselfinder.com/historical-ais-data) | 类似 | 同上 |
| [AISHub](https://www.aishub.net/) | 免费但需自架接收器 | 实时但需贡献数据 |

拿到 AIS 后只需要把 `gen_v3_realdata.py` 里 `cargo_position()` 替换成读取 AIS CSV 即可，其他不变。
