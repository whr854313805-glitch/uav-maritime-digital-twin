"""
v2: 用严格保守的 Victoria Harbour 水带表，沿主航道生成 8 艘船的 24h 轨迹.
水带按 lon 分段，每段 lat 上下界都按真实 OSM 海岸线 -0.001 安全 margin 给.
所有船的主轴和 amplitude 都在水带内, 不依赖事后 clamp.
"""
import math, csv, random
random.seed(42)
OUT = '/sessions/tender-dreamy-babbage/mnt/pre/uav-maritime-twin/output/vessel_positions.csv'
MINUTES = 1440

# (lon_min, lon_max, lat_min, lat_max) — 维多利亚港主水道 安全水带
WATER_BANDS = [
    # (lon_lo, lon_hi, lat_lo, lat_hi)
    (114.130, 114.143, 22.292, 22.300),  # Kennedy Town N → West Kowloon S
    (114.143, 114.158, 22.290, 22.298),  # Sheung Wan N → Yau Ma Tei S
    (114.158, 114.172, 22.288, 22.293),  # Central pier ↔ TST pier   (最窄段)
    (114.172, 114.190, 22.288, 22.295),  # Wan Chai N → TST East S
    (114.190, 114.205, 22.290, 22.300),  # Causeway Bay N → Hung Hom S
    (114.205, 114.220, 22.293, 22.302),  # North Point N → Kwun Tong S
    (114.220, 114.235, 22.290, 22.298),  # Quarry Bay N → Cha Kwo Ling S
]

def water_band(lon):
    """返回该 lon 对应的 (lat_lo, lat_hi) 水带；超出范围返回 None"""
    for lo, hi, la, lb in WATER_BANDS:
        if lo <= lon < hi:
            return (la, lb)
    return None

def clamp(lat, lon):
    band = water_band(lon)
    if band is None:
        # 经度超出主水道, 拉回最近端
        if lon < 114.130: lon = 114.131
        elif lon > 114.235: lon = 114.234
        band = water_band(lon)
    la, lb = band
    if lat < la: lat = la + 0.0005
    if lat > lb: lat = lb - 0.0005
    return lat, lon

def axis_lat(lon):
    """主航道中轴 lat (随 lon 变化)"""
    band = water_band(lon)
    if band is None:
        return 22.293
    return (band[0] + band[1]) / 2.0

# ---------- StarFerry: 中环 ↔ 尖沙咀 真实航线 ----------
# Star Ferry 中环码头 ≈ (22.2870, 114.1607); 尖沙咀码头 ≈ (22.2945, 114.1685)
# 但在最窄段 lon 114.158~114.172 水面 lat 是 22.288~22.293
# 所以航线两端要在水带内: 中环端 (22.289, 114.161); 尖沙咀端 (22.293, 114.169)
def starferry(idx, m):
    central = (22.289, 114.161)
    tst     = (22.293, 114.169)
    period = 14
    phase = [0, 5, 9][idx]
    t = (m + phase) % period
    if t < 6:
        f = t / 6.0
        lat = central[0] + (tst[0] - central[0]) * f
        lon = central[1] + (tst[1] - central[1]) * f
    elif t < 7:
        lat, lon = tst
    elif t < 13:
        f = (t - 7) / 6.0
        lat = tst[0] + (central[0] - tst[0]) * f
        lon = tst[1] + (central[1] - tst[1]) * f
    else:
        lat, lon = central
    lat += (random.random() - 0.5) * 0.0001
    lon += (random.random() - 0.5) * 0.0001
    return clamp(lat, lon)

# ---------- Cargo: 沿主航道东西向往返, lat 走中轴 ----------
def cargo(idx, m):
    period = 180
    phase = [0, 90][idx]
    t = (m + phase) % period
    lon_w, lon_e = 114.135, 114.230
    if t < 90:
        f = t / 90.0
        lon = lon_w + (lon_e - lon_w) * f
    else:
        f = (t - 90) / 90.0
        lon = lon_e + (lon_w - lon_e) * f
    # 北/南水道 略偏中轴 ±0.001
    base = axis_lat(lon)
    offset = 0.001 if idx == 0 else -0.001
    lat = base + offset
    lat += (random.random() - 0.5) * 0.0003
    lon += (random.random() - 0.5) * 0.0003
    return clamp(lat, lon)

# ---------- Yacht: 各自占一个 lon 区间, 沿区间中轴东西往返 ----------
def yacht(idx, m):
    period = 60
    phase = [0, 20, 40][idx]
    t = ((m + phase) % period) / period
    if idx == 0:
        # 西段
        lon_a, lon_b = 114.137, 114.155
    elif idx == 1:
        # 东段
        lon_a, lon_b = 114.207, 114.225
    else:
        # 中段 (主航道窄段)
        lon_a, lon_b = 114.175, 114.188
    if t < 0.5:
        f = t / 0.5
        lon = lon_a + (lon_b - lon_a) * f
    else:
        f = (t - 0.5) / 0.5
        lon = lon_b + (lon_a - lon_b) * f
    base = axis_lat(lon)
    # yacht 在 ±0.0008 内小幅 lat 摆动
    lat = base + 0.0008 * math.sin(2 * math.pi * t * 3)
    lat += (random.random() - 0.5) * 0.0002
    lon += (random.random() - 0.5) * 0.0002
    return clamp(lat, lon)

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

with open(OUT, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(["vessel_id","latitude","longitude"])
    for vid, lat, lon in rows:
        w.writerow([vid, f"{lat:.6f}", f"{lon:.6f}"])

# stats
from collections import defaultdict
stats = defaultdict(lambda: [90, -90, 180, -180])
for vid, lat, lon in rows:
    s = stats[vid]
    s[0] = min(s[0], lat); s[1] = max(s[1], lat)
    s[2] = min(s[2], lon); s[3] = max(s[3], lon)
print(f"Wrote {len(rows)} rows")
for vid, (mlat, Mlat, mlon, Mlon) in sorted(stats.items()):
    print(f"  {vid:<14} lat {mlat:.5f}..{Mlat:.5f}  lon {mlon:.5f}..{Mlon:.5f}")
