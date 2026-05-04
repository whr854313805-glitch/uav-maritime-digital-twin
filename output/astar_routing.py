"""
Phase 4: A* 动态路径规划 (优化版本)
- 用 numpy 加速 cost 计算
- 静态成本预计算一次, 动态成本只算最近船舶距离
- 24h 改为 1 小时采样 (24 × 5 = 120 次 A*)
"""
import csv, json, math, heapq, time

OUT = '/sessions/tender-dreamy-babbage/mnt/pre/uav-maritime-twin/output'

# ============== 加载数据 ==============
rows = list(csv.reader(open(f'{OUT}/vessel_positions.csv')))[1:]
ORDER = ['StarFerry_0','StarFerry_1','StarFerry_2','Cargo_0','Cargo_1','Yacht_0','Yacht_1','Yacht_2']
by_minute = []
for m in range(1440):
    slc = rows[m*8:(m+1)*8]
    pos = {vid:(float(lat), float(lon)) for vid, lat, lon in slc}
    by_minute.append([pos[v] for v in ORDER])

real_ships = json.load(open(f'{OUT}/all_real_vessels.json'))
real_ship_pos = [(s['lat'], s['lon']) for s in real_ships]
wind = json.load(open(f'{OUT}/wind_climatology.json'))
buildings = [b for b in json.load(open(f'{OUT}/buildings_hk.json'))['buildings'] if b['height_m'] > 50]

CORRIDORS = [
    {"id":"C1","name":"中环 → 启德邮轮码头","start":(22.288,114.161),"end":(22.305,114.215),"buffer_m":150},
    {"id":"C2","name":"尖沙咀 → 红磡医院","start":(22.294,114.170),"end":(22.302,114.184),"buffer_m":100},
    {"id":"C3","name":"北角 → 鲤鱼门","start":(22.290,114.197),"end":(22.293,114.243),"buffer_m":200},
    {"id":"C4","name":"西九龙 → 中环","start":(22.302,114.150),"end":(22.288,114.165),"buffer_m":120},
    {"id":"C5","name":"尖沙咀 → 北角","start":(22.294,114.170),"end":(22.290,114.197),"buffer_m":150},
]

WIND_THRESH = 8.0
PDPO_BUFFER = 50

# ============== 几何 ==============
def hav(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

# 等距投影简化 (维港尺度 <0.1% 误差)
LAT0 = 22.295
KX = math.cos(math.radians(LAT0)) * 111000  # m per degree lon
KY = 111000  # m per degree lat
def fast_dist_sq(lat1, lon1, lat2, lon2):
    dx = (lon2-lon1) * KX; dy = (lat2-lat1) * KY
    return dx*dx + dy*dy

# ============== 栅格 ==============
LAT_MIN, LAT_MAX = 22.27, 22.32
LON_MIN, LON_MAX = 114.12, 114.27
STEP = 0.002
ROWS = int((LAT_MAX - LAT_MIN) / STEP) + 1
COLS = int((LON_MAX - LON_MIN) / STEP) + 1
print(f"Grid: {ROWS} × {COLS} = {ROWS*COLS} cells, step={STEP*111000:.0f}m")

def cell_to_latlon(r, c):
    return (LAT_MIN + r * STEP, LON_MIN + c * STEP)
def latlon_to_cell(lat, lon):
    return (max(0, min(ROWS-1, int(round((lat - LAT_MIN) / STEP)))),
            max(0, min(COLS-1, int(round((lon - LON_MIN) / STEP)))))

INF = float('inf')

# ============== 静态 cost 预计算 ==============
def interp_wind(lat, lon):
    num = den = 0
    for s in wind['stations']:
        d2 = fast_dist_sq(lat, lon, s['lat'], s['lon']) + 1
        w = 1/d2; num += s['speed']*w; den += w
    return num/den

print("预计算静态 cost...")
t0 = time.time()
static_cost = [[0.0]*COLS for _ in range(ROWS)]
for r in range(ROWS):
    for c in range(COLS):
        lat, lon = cell_to_latlon(r, c)
        # 风
        w = interp_wind(lat, lon)
        if w > WIND_THRESH:
            static_cost[r][c] = INF
            continue
        cost = (w / WIND_THRESH) * 5
        # 建筑物 PDPO
        block = False
        for b in buildings:
            d2 = fast_dist_sq(lat, lon, b['lat'], b['lon'])
            if d2 < PDPO_BUFFER*PDPO_BUFFER:
                block = True; break
            if d2 < (PDPO_BUFFER*2)**2:
                d = math.sqrt(d2)
                cost += (PDPO_BUFFER*2 - d) / PDPO_BUFFER * 8
        if block:
            static_cost[r][c] = INF
        else:
            static_cost[r][c] = cost

free = sum(1 for r in range(ROWS) for c in range(COLS) if static_cost[r][c] != INF)
print(f"静态可行 cells: {free}/{ROWS*COLS} ({free/(ROWS*COLS)*100:.1f}%) — 耗时 {time.time()-t0:.1f}s")

# ============== A* ==============
NEIGHBORS = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]

def astar(start_cell, end_cell, minute, buffer_m):
    sr, sc = start_cell; er, ec = end_cell
    buf2 = buffer_m * buffer_m
    buf15_2 = (buffer_m * 1.5)**2
    
    # 当前时刻所有船 (8 demo + 65 real)
    ships = list(by_minute[minute]) + real_ship_pos
    
    open_heap = [(0, sr, sc)]
    came_from = {}
    g = {(sr,sc): 0}
    while open_heap:
        _, cr, cc = heapq.heappop(open_heap)
        if (cr,cc) == (er,ec):
            path = [(cr,cc)]
            while (cr,cc) in came_from:
                cr, cc = came_from[(cr,cc)]
                path.append((cr,cc))
            return path[::-1]
        for dr, dc in NEIGHBORS:
            nr, nc = cr+dr, cc+dc
            if not (0 <= nr < ROWS and 0 <= nc < COLS): continue
            sc_cost = static_cost[nr][nc]
            if sc_cost == INF: continue
            # 动态 cost: 最近船距离
            lat, lon = cell_to_latlon(nr, nc)
            min_d2 = INF
            for slat, slon in ships:
                d2 = fast_dist_sq(lat, lon, slat, slon)
                if d2 < min_d2: min_d2 = d2
            if min_d2 < buf2: continue  # blocked
            cost = sc_cost
            if min_d2 < buf15_2:
                d = math.sqrt(min_d2)
                cost += (buffer_m*1.5 - d) / buffer_m * 10
            move = math.hypot(dr, dc) * (1 + cost * 0.1)
            tent = g[(cr,cc)] + move
            if tent < g.get((nr,nc), INF):
                g[(nr,nc)] = tent
                came_from[(nr,nc)] = (cr,cc)
                h = max(abs(nr - er), abs(nc - ec))
                heapq.heappush(open_heap, (tent + h, nr, nc))
    return None

def path_distance_m(path):
    if not path or len(path) < 2: return 0
    total = 0
    for i in range(len(path)-1):
        a = cell_to_latlon(*path[i]); b = cell_to_latlon(*path[i+1])
        total += hav(a[0], a[1], b[0], b[1])
    return total

def path_to_latlon(path):
    return [cell_to_latlon(r, c) for r, c in path]

def original_distance(c):
    return hav(c['start'][0], c['start'][1], c['end'][0], c['end'][1])

# ============== Demo: 几个关键时刻每条走廊算 reroute ==============
DEMO_MINUTES = [0, 360, 720, 1080]
print(f"\n===== Demo: minute {DEMO_MINUTES} 每条走廊 A* =====")
demo_results = {}
for dm in DEMO_MINUTES:
    print(f"\n[minute={dm} = {dm//60:02d}:{dm%60:02d}]")
    demo_results[str(dm)] = {}
    for c in CORRIDORS:
        sc = latlon_to_cell(*c['start'])
        ec = latlon_to_cell(*c['end'])
        t0 = time.time()
        path = astar(sc, ec, dm, c['buffer_m'])
        elapsed = (time.time() - t0) * 1000
        if path:
            dist = path_distance_m(path)
            orig = original_distance(c)
            ratio = dist / orig
            print(f"  {c['id']}: {len(path):>3} cells, {dist:>5.0f}m (原 {orig:>5.0f}m, ×{ratio:.2f}), {elapsed:>5.0f}ms")
            demo_results[str(dm)][c['id']] = {
                'path': path_to_latlon(path),
                'distance_m': round(dist, 0),
                'original_m': round(orig, 0),
                'ratio': round(ratio, 2),
            }
        else:
            print(f"  {c['id']}: 无可行路径! ({elapsed:.0f}ms)")
            demo_results[str(dm)][c['id']] = None

json.dump(demo_results, open(f'{OUT}/reroute_demo_paths.json', 'w'), separators=(',',':'))
print(f"\nDemo paths → reroute_demo_paths.json")

# ============== 24h hourly 采样 (24 × 5 = 120 次 A*) ==============
print(f"\n===== 24h hourly 采样 (24 hours × 5 corridors = 120 A* runs) =====")
results = []
total_start = time.time()
for minute in range(0, 1440, 60):
    for c in CORRIDORS:
        sc = latlon_to_cell(*c['start'])
        ec = latlon_to_cell(*c['end'])
        path = astar(sc, ec, minute, c['buffer_m'])
        if path:
            dist = path_distance_m(path)
            orig = original_distance(c)
            results.append({
                'hour': minute // 60, 'corridor_id': c['id'],
                'astar_found': True,
                'astar_distance_m': round(dist, 0),
                'original_distance_m': round(orig, 0),
                'ratio': round(dist/orig, 2),
                'cells': len(path),
            })
        else:
            results.append({
                'hour': minute // 60, 'corridor_id': c['id'],
                'astar_found': False,
                'astar_distance_m': '',
                'original_distance_m': round(original_distance(c), 0),
                'ratio': '',
                'cells': 0,
            })
total_elapsed = time.time() - total_start
print(f"24h 采样完成: {len(results)} 数据点, 总耗时 {total_elapsed:.1f}s")

with open(f'{OUT}/vv_24h_reroute.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=results[0].keys())
    w.writeheader()
    [w.writerow(r) for r in results]

# ============== 汇总 ==============
print("\n===== 24h Reroute 可用率汇总 =====")
print(f"{'Cor':<4} {'Use':<10} {'Hours':>6} {'Found':>6} {'Avail%':>8} {'Avg Ratio':>10}")
print('-' * 55)
summary = []
for c in CORRIDORS:
    rs = [r for r in results if r['corridor_id'] == c['id']]
    n_found = sum(1 for r in rs if r['astar_found'])
    n_total = len(rs)
    avail = n_found / n_total * 100
    ratios = [r['ratio'] for r in rs if r['astar_found']]
    avg_ratio = sum(ratios) / len(ratios) if ratios else 0
    use = c['name'].split(' → ')[0][:10]
    print(f"{c['id']:<4} {use:<10} {n_total:>6} {n_found:>6} {avail:>7.1f}% {avg_ratio:>9.2f}×")
    summary.append({
        'corridor_id': c['id'], 'corridor_name': c['name'],
        'hours_sampled': n_total, 'astar_found_hours': n_found,
        'astar_availability_pct': round(avail, 1),
        'avg_reroute_ratio': round(avg_ratio, 2),
    })

with open(f'{OUT}/vv_24h_reroute_summary.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=summary[0].keys())
    w.writeheader()
    [w.writerow(r) for r in summary]
print(f"\nSummary → vv_24h_reroute_summary.csv")
