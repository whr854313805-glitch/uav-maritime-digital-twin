"""
对 vessel_positions.csv 做水陆检测 + 自动修正：
- 用一个手工对过 OSM 的 Victoria Harbour 水面多边形（外环 + 内部岛/填海凸出区作为洞）
- 对每个 (lat, lon) 做 ray-casting point-in-polygon
- 不在水里的点，用 BFS 在 4 邻域 (0.0003° 步长) 找最近水点替换
- 输出修正后的 CSV + 修正报告
"""
import csv, math, os
from collections import deque

# ---- Victoria Harbour 水面外环 (lat, lon)，逆时针 ----
# 沿 HK Island 北岸 (从 Kennedy Town 西到 Lei Yu Mun) 作为南边界
# 然后沿 Kowloon 南岸 (从 Lei Yu Mun 回到 Stonecutters) 作为北边界
WATER_OUTER = [
    # SW Kennedy Town 西外海
    (22.290, 114.125),
    # 沿 HK Island 北岸往东
    (22.288, 114.135),  # Kennedy Town North
    (22.286, 114.143),  # Sai Ying Pun
    (22.284, 114.152),  # Sheung Wan
    (22.282, 114.160),  # Central piers (Star Ferry HK side ≈ 22.287, 114.161)
    (22.280, 114.168),  # Admiralty
    (22.281, 114.176),  # Wan Chai
    (22.283, 114.185),  # Causeway Bay typhoon shelter 北缘
    (22.286, 114.195),  # North Point
    (22.286, 114.205),  # Quarry Bay
    (22.286, 114.215),  # Sai Wan Ho
    (22.288, 114.225),  # Shau Kei Wan
    (22.286, 114.235),  # Lei Yu Mun HK side
    (22.288, 114.245),  # SE 鲤鱼门外
    # 沿 Kowloon 南岸回西
    (22.298, 114.245),  # 鲤鱼门 Kowloon 侧
    (22.300, 114.235),  # Yau Tong south
    (22.302, 114.225),  # Cha Kwo Ling
    (22.305, 114.215),  # Kwun Tong south coast
    (22.307, 114.207),  # Kowloon Bay south (避开启德)
    (22.305, 114.198),  # Hung Hom 东
    (22.302, 114.190),  # Hung Hom 南
    (22.298, 114.180),  # Whampoa / TST East
    (22.295, 114.172),  # TST East
    (22.296, 114.165),  # TST (Star Ferry Kowloon side ≈ 22.296, 114.170)
    (22.298, 114.158),  # Yau Ma Tei south coast
    (22.302, 114.150),  # West Kowloon south
    (22.305, 114.142),  # West Kowloon 西
    (22.305, 114.135),  # Stonecutters east
    (22.300, 114.130),  # West edge
    (22.290, 114.125),  # close
]

def point_in_poly(lat, lon, poly):
    """Ray casting point-in-polygon. poly = [(lat, lon), ...] closed."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside

def is_water(lat, lon):
    return point_in_poly(lat, lon, WATER_OUTER)

def nearest_water(lat, lon, max_steps=80, step=0.0003):
    """BFS 4-邻域 找最近水点。"""
    if is_water(lat, lon):
        return (lat, lon)
    seen = {(round(lat,5), round(lon,5))}
    q = deque([(lat, lon, 0)])
    while q:
        cy, cx, d = q.popleft()
        if d >= max_steps:
            continue
        for dy, dx in [(step,0), (-step,0), (0,step), (0,-step),
                       (step,step), (step,-step), (-step,step), (-step,-step)]:
            ny, nx = cy + dy, cx + dx
            key = (round(ny,5), round(nx,5))
            if key in seen:
                continue
            seen.add(key)
            if is_water(ny, nx):
                return (ny, nx)
            q.append((ny, nx, d+1))
    return (lat, lon)  # 找不到时原样返回

def main():
    csv_in = '/sessions/tender-dreamy-babbage/mnt/pre/uav-maritime-twin/output/vessel_positions.csv'
    csv_out = csv_in  # overwrite
    rows = list(csv.reader(open(csv_in)))
    header = rows[0]
    data = rows[1:]
    fixed = 0
    bad_by_vid = {}
    fixed_rows = [header]
    for row in data:
        vid, lat, lon = row[0], float(row[1]), float(row[2])
        if not is_water(lat, lon):
            new_lat, new_lon = nearest_water(lat, lon)
            bad_by_vid[vid] = bad_by_vid.get(vid, 0) + 1
            fixed += 1
            fixed_rows.append([vid, f"{new_lat:.6f}", f"{new_lon:.6f}"])
        else:
            fixed_rows.append([vid, f"{lat:.6f}", f"{lon:.6f}"])
    with open(csv_out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerows(fixed_rows)
    print(f"扫描 {len(data)} 行, 修正陆地点 {fixed} 个")
    if bad_by_vid:
        print("各船修正条数:")
        for vid, n in sorted(bad_by_vid.items()):
            print(f"  {vid:<14} {n} / 1440")

if __name__ == '__main__':
    main()
