"""
Phase 5.5: UAV 能耗续航分析
- 模型: DJI Matrice 300 RTK 标准 (典型 UAV 物流无人机)
  - 电池容量: 5935 mAh @ 52.8V = ~313 Wh
  - 巡航功耗: ~600W (15 m/s 巡航)
  - 风阻系数: 风速 m/s 每增加 1 → 功耗 +5% (经验估算)
  - 起降功耗: 比巡航 +30% (悬停爬升)
- 评估: 5 条走廊各自单程 + 往返 能否在 80% 电量内完成 (留 20% 备降)
- 输出: 续航分析表 + V&V 警告
"""
import json, math, csv

OUT = '/sessions/tender-dreamy-babbage/mnt/pre/uav-maritime-twin/output'
wind = json.load(open(f'{OUT}/wind_climatology.json'))

CORRIDORS = [
    {"id":"C1","name":"中环 → 启德邮轮码头","waypoints":[(22.288,114.161),(22.301,114.180),(22.305,114.215)],"altitude_m":80,"speed_mps":15},
    {"id":"C2","name":"尖沙咀 → 红磡医院","waypoints":[(22.294,114.170),(22.302,114.184)],"altitude_m":60,"speed_mps":18},
    {"id":"C3","name":"北角 → 鲤鱼门","waypoints":[(22.290,114.197),(22.293,114.220),(22.293,114.243)],"altitude_m":90,"speed_mps":12},
    {"id":"C4","name":"西九龙 → 中环","waypoints":[(22.302,114.150),(22.295,114.158),(22.288,114.165)],"altitude_m":70,"speed_mps":14},
    {"id":"C5","name":"尖沙咀 → 北角","waypoints":[(22.294,114.170),(22.296,114.183),(22.290,114.197)],"altitude_m":80,"speed_mps":16},
]

# UAV 物理参数 (DJI Matrice 300 RTK 类)
BATTERY_WH = 313       # 电池总容量
CRUISE_POWER_W = 600   # 巡航功耗
TAKEOFF_LANDING_POWER_W = 780  # 起降功耗 (+30%)
TAKEOFF_TIME_S = 60    # 起飞 1 min (爬升到目标高度)
LANDING_TIME_S = 60    # 降落 1 min
SAFETY_MARGIN = 0.20   # 留 20% 应急

def hav(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def interp_wind(lat, lon):
    num = den = 0
    for s in wind['stations']:
        d = hav(lat, lon, s['lat'], s['lon']) + 1
        w = 1/(d*d); num += s['speed']*w; den += w
    return num/den

results = []
for c in CORRIDORS:
    total_dist = 0
    for i in range(len(c['waypoints'])-1):
        total_dist += hav(*c['waypoints'][i], *c['waypoints'][i+1])
    flight_time_s = total_dist / c['speed_mps']
    # 平均风速 (沿走廊采样)
    samples = []
    for lat, lon in c['waypoints']:
        samples.append(interp_wind(lat, lon))
    avg_wind = sum(samples) / len(samples)
    # 风阻调整 (头风 / 顺风假设各半)
    wind_factor = 1 + (avg_wind / 5) * 0.05  # 每 1 m/s 风 +5%
    cruise_energy = (CRUISE_POWER_W * wind_factor) * flight_time_s / 3600  # Wh
    takeoff_energy = TAKEOFF_LANDING_POWER_W * TAKEOFF_TIME_S / 3600
    landing_energy = TAKEOFF_LANDING_POWER_W * LANDING_TIME_S / 3600
    one_way_energy = cruise_energy + takeoff_energy + landing_energy
    one_way_pct = one_way_energy / BATTERY_WH * 100
    round_trip_pct = (cruise_energy * 2 + takeoff_energy + landing_energy * 2 + takeoff_energy) / BATTERY_WH * 100
    feasible_one_way = one_way_pct < (1 - SAFETY_MARGIN) * 100
    feasible_round_trip = round_trip_pct < (1 - SAFETY_MARGIN) * 100
    
    results.append({
        'corridor_id': c['id'],
        'name': c['name'],
        'distance_m': round(total_dist, 0),
        'speed_mps': c['speed_mps'],
        'flight_time_s': round(flight_time_s, 1),
        'avg_wind_mps': round(avg_wind, 2),
        'wind_factor': round(wind_factor, 3),
        'one_way_energy_wh': round(one_way_energy, 1),
        'one_way_battery_pct': round(one_way_pct, 1),
        'round_trip_battery_pct': round(round_trip_pct, 1),
        'feasible_one_way': feasible_one_way,
        'feasible_round_trip': feasible_round_trip,
        'remaining_after_one_way_pct': round(100 - one_way_pct, 1),
        'remaining_after_round_trip_pct': round(100 - round_trip_pct, 1),
    })

print("===== UAV 能耗续航分析 (DJI Matrice 300 类, 313 Wh 电池) =====\n")
print(f"{'Cor':<4} {'Use':<10} {'Dist':>6} {'T':>5} {'Wind':>6} {'OneWay%':>8} {'RT%':>6} {'Feasible':>20}")
print('-' * 80)
for r in results:
    use = r['name'].split(' → ')[0][:10]
    feas = '单程 ✓ 往返 ✓' if r['feasible_round_trip'] else (
           '单程 ✓ 往返 ✗' if r['feasible_one_way'] else '⚠️ 单程不可行!')
    print(f"{r['corridor_id']:<4} {use:<10} {r['distance_m']:>6.0f}m {r['flight_time_s']:>4.0f}s "
          f"{r['avg_wind_mps']:>5.1f}m/s {r['one_way_battery_pct']:>7.1f}% {r['round_trip_battery_pct']:>5.1f}%  "
          f"{feas:>20}")

# 写 CSV
with open(f'{OUT}/uav_energy_analysis.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=results[0].keys())
    w.writeheader()
    [w.writerow(r) for r in results]
print(f"\n→ uav_energy_analysis.csv")

# 输出 JSON 给 dashboard 用
json.dump({
    'battery_wh': BATTERY_WH,
    'cruise_power_w': CRUISE_POWER_W,
    'safety_margin': SAFETY_MARGIN,
    'results': results
}, open(f'{OUT}/uav_energy.json', 'w'), ensure_ascii=False, indent=2)
print(f"→ uav_energy.json")
