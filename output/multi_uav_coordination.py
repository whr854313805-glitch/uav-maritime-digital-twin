"""
Phase 5.2: 多 UAV 协同避让
- 找出 5 条 UAV 走廊两两之间的交叉点 (3D: lat/lon + altitude)
- 算每架 UAV 通过每个交叉点的时间
- 检测时间差 < 30 秒 (TCAS 标准: 30s separation) 的冲突
- 调整起飞时间 (phase shift) 让 UAV 错峰
- 输出: cross_points.json + uav_schedule.csv + 冲突解决方案
"""
import json, math, csv, itertools

OUT = '/sessions/tender-dreamy-babbage/mnt/pre/uav-maritime-twin/output'

CORRIDORS = [
    {"id":"C1","name":"中环 → 启德邮轮码头","waypoints":[(22.288,114.161),(22.301,114.180),(22.305,114.215)],"altitude_m":80,"speed_mps":15},
    {"id":"C2","name":"尖沙咀 → 红磡医院","waypoints":[(22.294,114.170),(22.302,114.184)],"altitude_m":60,"speed_mps":18},
    {"id":"C3","name":"北角 → 鲤鱼门","waypoints":[(22.290,114.197),(22.293,114.220),(22.293,114.243)],"altitude_m":90,"speed_mps":12},
    {"id":"C4","name":"西九龙 → 中环","waypoints":[(22.302,114.150),(22.295,114.158),(22.288,114.165)],"altitude_m":70,"speed_mps":14},
    {"id":"C5","name":"尖沙咀 → 北角","waypoints":[(22.294,114.170),(22.296,114.183),(22.290,114.197)],"altitude_m":80,"speed_mps":16},
]

# TCAS 类标准: 水平 150m 或 垂直 30m 内才算"重叠"
HORIZONTAL_SEP_M = 150
VERTICAL_SEP_M = 30
TIME_SEP_S = 30  # 至少 30 秒间隔

def hav(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

# 2D segment intersection (经纬度近似)
def segments_intersect(a1, a2, b1, b2):
    """返回交点 lat/lon 或 None"""
    x1, y1 = a1[1], a1[0]
    x2, y2 = a2[1], a2[0]
    x3, y3 = b1[1], b1[0]
    x4, y4 = b2[1], b2[0]
    denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if abs(denom) < 1e-12: return None
    t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
    u = -((x1-x2)*(y1-y3) - (y1-y2)*(x1-x3)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        ix = x1 + t*(x2-x1)
        iy = y1 + t*(y2-y1)
        return (iy, ix), t, u  # (lat, lon), 段 a 上的比例, 段 b 上的比例
    return None

# 计算每条走廊总长 + 各段累计距离
for c in CORRIDORS:
    c['total_dist'] = 0
    c['cumul_dist'] = [0]
    for i in range(len(c['waypoints'])-1):
        d = hav(*c['waypoints'][i], *c['waypoints'][i+1])
        c['total_dist'] += d
        c['cumul_dist'].append(c['total_dist'])
    c['flight_time_s'] = c['total_dist'] / c['speed_mps']

print("===== UAV 走廊飞行时间 =====")
for c in CORRIDORS:
    print(f"  {c['id']}: 总长 {c['total_dist']:.0f}m, 速度 {c['speed_mps']} m/s, 单程 {c['flight_time_s']:.0f}s ({c['flight_time_s']/60:.1f}min)")

# ============== 1. 找所有走廊两两交叉点 ==============
print("\n===== 走廊交叉点检测 =====")
cross_points = []
for c1, c2 in itertools.combinations(CORRIDORS, 2):
    for i in range(len(c1['waypoints'])-1):
        for j in range(len(c2['waypoints'])-1):
            res = segments_intersect(c1['waypoints'][i], c1['waypoints'][i+1],
                                      c2['waypoints'][j], c2['waypoints'][j+1])
            if res:
                pt, t1, t2 = res
                # 算到达交点的距离 (沿走廊)
                dist1_to_pt = c1['cumul_dist'][i] + t1 * (c1['cumul_dist'][i+1] - c1['cumul_dist'][i])
                dist2_to_pt = c2['cumul_dist'][j] + t2 * (c2['cumul_dist'][j+1] - c2['cumul_dist'][j])
                # 高度差
                alt_diff = abs(c1['altitude_m'] - c2['altitude_m'])
                # UAV 到达时间 (假设两架同时起飞 t=0)
                t1_sec = dist1_to_pt / c1['speed_mps']
                t2_sec = dist2_to_pt / c2['speed_mps']
                cross_points.append({
                    'corridor_a': c1['id'], 'corridor_b': c2['id'],
                    'lat': round(pt[0], 6), 'lon': round(pt[1], 6),
                    'altitude_a': c1['altitude_m'], 'altitude_b': c2['altitude_m'],
                    'altitude_diff_m': alt_diff,
                    'dist_a_to_cross_m': round(dist1_to_pt, 0),
                    'dist_b_to_cross_m': round(dist2_to_pt, 0),
                    'time_a_to_cross_s': round(t1_sec, 1),
                    'time_b_to_cross_s': round(t2_sec, 1),
                    'time_diff_s': round(abs(t1_sec - t2_sec), 1),
                })

print(f"找到 {len(cross_points)} 个交叉点")
for cp in cross_points:
    sep_status = "垂直分离 ✓" if cp['altitude_diff_m'] >= VERTICAL_SEP_M else (
                  "时间错峰 ✓" if cp['time_diff_s'] >= TIME_SEP_S else "⚠️ 冲突!")
    print(f"  {cp['corridor_a']} × {cp['corridor_b']} @ ({cp['lat']:.4f}, {cp['lon']:.4f})")
    print(f"    高度差 {cp['altitude_diff_m']}m  时间差 {cp['time_diff_s']}s  →  {sep_status}")

# ============== 2. 调度优化: 错峰起飞时间 ==============
print("\n===== 起飞时间优化 (错峰) =====")
# 给每架 UAV 一个 takeoff_offset_s, 最小化冲突数
# 简化: 贪心算法, 按走廊序号顺次起飞, 每架间隔 STAGGER_S
STAGGER_S = 30

schedule = []
for i, c in enumerate(CORRIDORS):
    schedule.append({
        'corridor_id': c['id'],
        'name': c['name'],
        'altitude_m': c['altitude_m'],
        'speed_mps': c['speed_mps'],
        'flight_time_s': round(c['flight_time_s'], 1),
        'takeoff_offset_s': i * STAGGER_S,  # 错峰
        'arrival_s': round(i * STAGGER_S + c['flight_time_s'], 1),
    })

print(f"{'UAV':<5} {'起飞':>6} {'抵达':>8} {'高度':>6} {'冲突解决':>14}")
print('-' * 50)
for s in schedule:
    print(f"  {s['corridor_id']:<3} {s['takeoff_offset_s']:>6}s {s['arrival_s']:>8}s {s['altitude_m']:>5}m  错峰起飞")

# ============== 3. 错峰后冲突复检 ==============
print("\n===== 错峰后冲突复检 =====")
takeoffs = {s['corridor_id']: s['takeoff_offset_s'] for s in schedule}
remaining_conflicts = 0
for cp in cross_points:
    new_t_a = takeoffs[cp['corridor_a']] + cp['time_a_to_cross_s']
    new_t_b = takeoffs[cp['corridor_b']] + cp['time_b_to_cross_s']
    new_diff = abs(new_t_a - new_t_b)
    cp['post_schedule_time_diff_s'] = round(new_diff, 1)
    cp['post_schedule_status'] = (
        '垂直分离 ✓' if cp['altitude_diff_m'] >= VERTICAL_SEP_M
        else ('时间错峰 ✓' if new_diff >= TIME_SEP_S else '⚠️ 仍冲突')
    )
    if cp['post_schedule_status'] == '⚠️ 仍冲突':
        remaining_conflicts += 1
        print(f"  {cp['corridor_a']} × {cp['corridor_b']}: 时间差 {new_diff:.1f}s, 高度差 {cp['altitude_diff_m']}m → 仍冲突!")
    else:
        print(f"  {cp['corridor_a']} × {cp['corridor_b']}: {cp['post_schedule_status']} (Δt={new_diff:.1f}s, Δh={cp['altitude_diff_m']}m)")

print(f"\n剩余冲突: {remaining_conflicts}/{len(cross_points)}")

# ============== 4. 输出 ==============
output = {
    'separation_standard': {
        'horizontal_m': HORIZONTAL_SEP_M,
        'vertical_m': VERTICAL_SEP_M,
        'time_s': TIME_SEP_S,
    },
    'corridors_summary': [{
        'id': c['id'], 'altitude_m': c['altitude_m'], 'flight_time_s': round(c['flight_time_s'], 1),
        'total_dist_m': round(c['total_dist'], 0), 'speed_mps': c['speed_mps'],
    } for c in CORRIDORS],
    'cross_points': cross_points,
    'schedule': schedule,
    'remaining_conflicts': remaining_conflicts,
}
json.dump(output, open(f'{OUT}/multi_uav_coordination.json', 'w'), ensure_ascii=False, indent=2)
print(f"\n→ multi_uav_coordination.json")

# 写 CSV
with open(f'{OUT}/uav_schedule.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=schedule[0].keys())
    w.writeheader()
    [w.writerow(r) for r in schedule]
print(f"→ uav_schedule.csv")
