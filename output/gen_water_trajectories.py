"""
重新生成 8 艘船的 24h 轨迹 (1 分钟粒度, 11520 行) —— 所有点都保证在维多利亚港水面上。

水域几何参考（手工从 OSM 对照得出）:
  维多利亚港主水道, 从 Kennedy Town 外海 (lon ≈ 114.125) 一路向东到 Lei Yu Mun (lon ≈ 114.245):
    - 西段 (lon 114.125~114.160): lat 水面约 22.290~22.300, 宽 ~0.010°
    - 中段 (lon 114.160~114.185): lat 水面约 22.290~22.305, 这是尖沙咀/中环最开阔段
    - 东段 (lon 114.185~114.220): lat 水面约 22.295~22.315
    - 再往东 (lon 114.220~114.245): lat 水面约 22.290~22.305, 鲤鱼门收窄

生成方案:
  StarFerry 0/1/2: 中环 (22.2870, 114.1607) <-> 尖沙咀 (22.2955, 114.1704) 之间来回, 周期 ~14 分钟
  Cargo 0/1:      沿主航道做东西向往返, 在中水线偏南
  Yacht 0/1/2:    在各自片段内慢速环绕, 保持在水面带内
"""
import math, csv, random

random.seed(42)

import os
OUT = "/sessions/tender-dreamy-babbage/mnt/pre/uav-maritime-twin/output/vessel_positions.csv"
if not os.path.isdir(os.path.dirname(OUT)):
    OUT = "/Users/rozz/Desktop/pre/uav-maritime-twin/output/vessel_positions.csv"
MINUTES = 1440

def clamp_to_water(lat, lon):
    """给 (lat, lon) 做一个粗略 '水陆安全带' 约束。返回 (lat', lon') 落在航道中轴附近的点。"""
    # 计算航道中轴 lat (随 lon 东西位置平移)
    if lon < 114.160:
        center_lat = 22.295
        half = 0.004
    elif lon < 114.185:
        center_lat = 22.297
        half = 0.006
    elif lon < 114.220:
        center_lat = 22.302
        half = 0.006
    else:
        center_lat = 22.298
        half = 0.004
    # 拉回带内
    if lat < center_lat - half: lat = center_lat - half
    if lat > center_lat + half: lat = center_lat + half
    # 经度也限制在主航道 114.125~114.245
    if lon < 114.130: lon = 114.130
    if lon > 114.238: lon = 114.238
    return lat, lon


def starferry(route_idx, m):
    """Star Ferry: 中环(22.2870, 114.1607) <-> 尖沙咀(22.2955, 114.1704).
    周期 14 分钟, 3 艘船相位错开 (0, 5, 9 分钟)."""
    central  = (22.2870, 114.1607)
    tst      = (22.2955, 114.1704)
    period = 14
    phase = [0, 5, 9][route_idx]
    t = (m + phase) % period
    # 前 6 分钟过海, 后 1 分钟靠岸, 后 6 分钟回程, 最后 1 分钟靠岸
    if t < 6:
        frac = t / 6.0
        lat = central[0] + (tst[0] - central[0]) * frac
        lon = central[1] + (tst[1] - central[1]) * frac
    elif t < 7:
        lat, lon = tst
    elif t < 13:
        frac = (t - 7) / 6.0
        lat = tst[0] + (central[0] - tst[0]) * frac
        lon = tst[1] + (central[1] - tst[1]) * frac
    else:
        lat, lon = central
    # 加小扰动避免 3 艘完全重合
    lat += (random.random() - 0.5) * 0.00015
    lon += (random.random() - 0.5) * 0.00015
    return clamp_to_water(lat, lon)


def cargo(route_idx, m):
    """大型货船: 沿主航道东西向往返, 速度慢, 周期 180 分钟.
    Cargo_0 走北水道, Cargo_1 走南水道 (错开避免碰撞)."""
    period = 180
    phase = [0, 90][route_idx]
    t = (m + phase) % period
    lon_west = 114.135
    lon_east = 114.235
    if t < 90:
        frac = t / 90.0
        lon = lon_west + (lon_east - lon_west) * frac
    else:
        frac = (t - 90) / 90.0
        lon = lon_east + (lon_west - lon_east) * frac
    # Cargo_0 走北偏一点, Cargo_1 走南偏一点
    if route_idx == 0:
        # 北水道
        if lon < 114.160:  lat = 22.298
        elif lon < 114.185: lat = 22.302
        elif lon < 114.220: lat = 22.306
        else:               lat = 22.301
    else:
        # 南水道
        if lon < 114.160:  lat = 22.292
        elif lon < 114.185: lat = 22.293
        elif lon < 114.220: lat = 22.298
        else:               lat = 22.295
    lat += (random.random() - 0.5) * 0.0006
    lon += (random.random() - 0.5) * 0.0006
    return clamp_to_water(lat, lon)


def yacht(route_idx, m):
    """游艇: 沿主航道做小段东西向往返巡航 (避免椭圆扫到岸边).
    各自占一个经度区间, lat 严格固定在已验证为水的中轴上."""
    period = 60
    phase = [0, 20, 40][route_idx]
    t = ((m + phase) % period) / period  # 0..1

    if route_idx == 0:
        # Yacht_0: 西段巡航 (Kennedy Town 外海 - Sheung Wan 外海)
        lon_a, lon_b = 114.138, 114.158
        lat_base = 22.293
    elif route_idx == 1:
        # Yacht_1: 东段巡航 (North Point 外海 - 鲤鱼门以西)
        lon_a, lon_b = 114.200, 114.222
        lat_base = 22.302
    else:
        # Yacht_2: 中段巡航 (尖沙咀外 - Hung Hom 外)
        lon_a, lon_b = 114.168, 114.188
        lat_base = 22.298

    # 半周期一个方向
    if t < 0.5:
        frac = t / 0.5
        lon = lon_a + (lon_b - lon_a) * frac
    else:
        frac = (t - 0.5) / 0.5
        lon = lon_b + (lon_a - lon_b) * frac

    # 小幅 lat 摆动让视觉上不死板, 但保证 ±0.0008 内
    lat = lat_base + 0.0008 * math.sin(2 * math.pi * t * 3)
    lat += (random.random() - 0.5) * 0.0003
    lon += (random.random() - 0.5) * 0.0003
    return clamp_to_water(lat, lon)


rows = []
for m in range(MINUTES):
    rows.append(("StarFerry_0",) + starferry(0, m))
    rows.append(("StarFerry_1",) + starferry(1, m))
    rows.append(("StarFerry_2",) + starferry(2, m))
    rows.append(("Cargo_0",)     + cargo(0, m))
    rows.append(("Cargo_1",)     + cargo(1, m))
    rows.append(("Yacht_0",)     + yacht(0, m))
    rows.append(("Yacht_1",)     + yacht(1, m))
    rows.append(("Yacht_2",)     + yacht(2, m))

with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["vessel_id", "latitude", "longitude"])
    for r in rows:
        w.writerow([r[0], f"{r[1]:.6f}", f"{r[2]:.6f}"])

print(f"Wrote {len(rows)} rows to {OUT}")

# 快速统计
from collections import defaultdict
stats = defaultdict(lambda: [90, -90, 180, -180])
for r in rows:
    s = stats[r[0]]
    s[0] = min(s[0], r[1]); s[1] = max(s[1], r[1])
    s[2] = min(s[2], r[2]); s[3] = max(s[3], r[2])
for vid, (mlat, Mlat, mlon, Mlon) in sorted(stats.items()):
    print(f"  {vid:<14} lat {mlat:.5f}..{Mlat:.5f}  lon {mlon:.5f}..{Mlon:.5f}")
