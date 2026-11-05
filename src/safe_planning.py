"""Frozen-time 2D A*: exact endpoints and continuous edge/circle checks.

Uses an explicitly approximate local metric projection, conservative bounding
circles for approximate building footprints, and spatially sampled snapshot wind.
This is not a time-continuous flight safety or regulatory compliance claim.
"""
import heapq
import math
from src.metric_projection import MetricProjection

def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0.0
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)

class SafePlanner:
    def __init__(self, config, inputs):
        self.config, self.inputs = config, inputs
        self.coordinates=MetricProjection(config)
        self.envelope_cache={}
        self.settings = config['planning']
        pr = config['projection']
        self.lat0, self.lon0 = pr['origin_lat'], pr['origin_lon']
        self.ky = self.coordinates.ky
        self.kx = self.coordinates.kx
        r = config['region']
        self.xmin, self.ymin = self.project([r['lat_min'], r['lon_min']])
        self.xmax, self.ymax = self.project([r['lat_max'], r['lon_max']])
        if self.coordinates.metric:
            corners=[self.project([lat,lon]) for lat in [r['lat_min'],r['lat_max']] for lon in [r['lon_min'],r['lon_max']]]
            self.xmin=min(p[0] for p in corners);self.xmax=max(p[0] for p in corners)
            self.ymin=min(p[1] for p in corners);self.ymax=max(p[1] for p in corners)
        self.step = self.settings['grid_step_m']
        self.rows = math.floor((self.ymax-self.ymin)/self.step)+1
        self.cols = math.floor((self.xmax-self.xmin)/self.step)+1
        self.buildings = []
        for b in inputs['buildings']['buildings']:
            if b['height_m'] is None or b['height_m'] > self.settings['building_height_threshold_m']:
                x,y,w,h=self.building_envelope(b)
                self.buildings.append(((x,y), math.hypot(w,h)+self.settings['building_buffer_m']))
        # Insert every obstacle's complete envelope, so querying an edge's bbox
        # cannot miss a circle intersecting that edge. This changes speed only.
        self.building_bins={}
        for i,((x,y),radius) in enumerate(self.buildings):
            radius+=self.settings['clearance_tolerance_m']
            for col in range(math.floor((x-radius)/self.step),math.floor((x+radius)/self.step)+1):
                for row in range(math.floor((y-radius)/self.step),math.floor((y+radius)/self.step)+1):
                    self.building_bins.setdefault((row,col),[]).append(i)
        self.stations = [(self.project([s['lat'], s['lon']]), s['speed']) for s in inputs['wind']['stations']]
        self.static_ships = [self.project([s['lat'],s['lon']]) for s in inputs['static_vessels']]
        self.static_edge_cache = {}

    def project(self, point):
        return self.coordinates.project(point)

    def unproject(self, point):
        return self.coordinates.unproject(point)

    def building_envelope(self,b):
        key=id(b)
        if key not in self.envelope_cache:
            if self.coordinates.metric and b.get('geometry'):
                from shapely.geometry import shape
                from shapely.ops import transform
                xmin,ymin,xmax,ymax=transform(self.coordinates.forward.transform,shape(b['geometry'])).bounds
                value=((xmin+xmax)/2,(ymin+ymax)/2,(xmax-xmin)/2,(ymax-ymin)/2)
            else:
                x,y=self.project([b['lat'],b['lon']]);value=(x,y,b.get('footprint_w_m',50)/2,b.get('footprint_l_m',50)/2)
            self.envelope_cache[key]=value
        return self.envelope_cache[key]

    def inside(self, point):
        if self.coordinates.metric:
            lat,lon=self.unproject(point);r=self.config['region']
            return r['lat_min']-1e-10<=lat<=r['lat_max']+1e-10 and r['lon_min']-1e-10<=lon<=r['lon_max']+1e-10
        return self.xmin <= point[0] <= self.xmax and self.ymin <= point[1] <= self.ymax

    def wind_at(self, point):
        pairs = [(1/(math.hypot(point[0]-p[0],point[1]-p[1])+1)**2, speed) for p,speed in self.stations]
        return sum(w*s for w,s in pairs)/sum(w for w,_ in pairs)

    def static_edge(self, a, b):
        key = tuple(sorted((a,b)))
        if key not in self.static_edge_cache:
            tolerance = self.settings['clearance_tolerance_m']
            candidates=set()
            for col in range(math.floor(min(a[0],b[0])/self.step),math.floor(max(a[0],b[0])/self.step)+1):
                for row in range(math.floor(min(a[1],b[1])/self.step),math.floor(max(a[1],b[1])/self.step)+1):
                    candidates.update(self.building_bins.get((row,col),[]))
            valid = self.inside(a) and self.inside(b) and all(point_segment_distance(self.buildings[i][0],a,b) >= self.buildings[i][1]+tolerance for i in candidates)
            wind = 0.0
            if valid:
                samples = max(1, math.ceil(math.dist(a,b)/self.settings['wind_sample_step_m']))
                wind = max(self.wind_at((a[0]+(b[0]-a[0])*i/samples,a[1]+(b[1]-a[1])*i/samples)) for i in range(samples+1))
                valid = wind <= self.settings['wind_threshold_mps']
            self.static_edge_cache[key] = (valid, wind)
        return self.static_edge_cache[key]

    def edge(self, a, b, ships, buffer_m):
        valid, wind = self.static_edge(a,b)
        if not valid:
            return None
        distance = min((point_segment_distance(s,a,b) for s in ships),default=math.inf)
        if distance < buffer_m+self.settings['clearance_tolerance_m']:
            return None
        soft = max(0, (1.5*buffer_m-distance)/buffer_m)
        return math.dist(a,b)*(1+self.settings['wind_cost_weight']*wind/self.settings['wind_threshold_mps']+self.settings['ship_soft_cost_weight']*soft)

    def node_point(self, node):
        return (self.xmin+node[1]*self.step,self.ymin+node[0]*self.step)

    def anchors(self, point):
        row = math.floor((point[1]-self.ymin)/self.step+0.5)
        col = math.floor((point[0]-self.xmin)/self.step+0.5)
        radius = self.settings['endpoint_connector_cells']
        return [(r,c) for r in range(row-radius,row+radius+1) for c in range(col-radius,col+radius+1) if 0 <= r < self.rows and 0 <= c < self.cols]

    def plan(self, start, end, minute, buffer_m):
        start, end = list(start), list(end)
        if not isinstance(minute,int) or not 0 <= minute < len(self.inputs['by_minute']):
            raise ValueError('Minute outside snapshot sequence')
        if not math.isfinite(buffer_m) or buffer_m <= 0:
            raise ValueError('Buffer must be positive and finite')
        a, b = self.project(start), self.project(end)
        ships = [self.project(p) for p in self.inputs['by_minute'][minute]]+self.static_ships
        def fail(reason):
            return {'found':False,'geometry_valid':None,'failure_reason':reason,'path':None,'distance_m':None,'minimum_ship_distance_m':None,'minimum_building_clearance_m':None}
        for label,point in [('start',a),('end',b)]:
            if not self.inside(point):
                return fail(label+'_outside_region')
            if any(math.dist(point,s) < buffer_m+self.settings['clearance_tolerance_m'] for s in ships):
                return fail(label+'_ship_buffer')
            if not self.static_edge(point,point)[0]:
                return fail(label+'_building_or_wind_constraint')
        if a == b:
            path = [start,end]
        else:
            goals = {n:self.edge(self.node_point(n),b,ships,buffer_m) for n in self.anchors(b)}
            goals = {n:c for n,c in goals.items() if c is not None}
            if not goals:
                return fail('end_grid_connector_blocked')
            heap, costs, parents = [], {}, {}
            for node in self.anchors(a):
                cost = self.edge(a,self.node_point(node),ships,buffer_m)
                if cost is not None:
                    costs[node] = cost
                    heapq.heappush(heap,(cost+math.dist(self.node_point(node),b),cost,node))
            if not heap:
                return fail('start_grid_connector_blocked')
            goal_node = (-1,-1)
            while heap:
                _,cost,node = heapq.heappop(heap)
                if cost > costs[node]+1e-9:
                    continue
                if node == goal_node:
                    chain = []
                    while node in parents:
                        node = parents[node]
                        chain.append(self.node_point(node))
                    path = [start]+[self.unproject(p) for p in reversed(chain)]+[end]
                    break
                if node in goals:
                    new_cost = cost+goals[node]
                    if new_cost < costs.get(goal_node,math.inf):
                        costs[goal_node],parents[goal_node] = new_cost,node
                        heapq.heappush(heap,(new_cost,new_cost,goal_node))
                row,col = node
                for dr,dc in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                    neighbor=(row+dr,col+dc)
                    if not (0 <= neighbor[0] < self.rows and 0 <= neighbor[1] < self.cols):
                        continue
                    extra=self.edge(self.node_point(node),self.node_point(neighbor),ships,buffer_m)
                    if extra is None:
                        continue
                    new_cost=cost+extra
                    if new_cost < costs.get(neighbor,math.inf)-1e-9:
                        costs[neighbor],parents[neighbor]=new_cost,node
                        heapq.heappush(heap,(new_cost+math.dist(self.node_point(neighbor),b),new_cost,neighbor))
            else:
                return fail('no_safe_grid_path')
        # Independent geometry implementation; planner never publishes an invalid route.
        result = validate_path(path,start,end,ships,buffer_m,self.config,self.inputs['buildings']['buildings'],self)
        if not result['geometry_valid']:
            return fail('independent_validation_failed')
        return {'found':True,'failure_reason':None,'path':path,**result}

def validate_path(path, start, end, ships_xy, buffer_m, config, buildings, projection):
    """Independent GEOS/Shapely continuous geometry check of the full polyline."""
    from shapely.geometry import LineString, Point, box
    points = [projection.project(p) for p in path]
    line = LineString(points)
    ship_distance = min((line.distance(Point(p)) for p in ships_xy),default=math.inf)
    # Cache an independent GEOS union of footprint envelopes, instead of
    # reconstructing tens of thousands of polygons for every returned path.
    if not hasattr(projection,'_validation_building_union'):
        from shapely.ops import unary_union
        rectangles=[]
        for b in buildings:
            if b['height_m'] is not None and b['height_m'] <= config['planning']['building_height_threshold_m']:continue
            x,y,w,h=projection.building_envelope(b)
            rectangles.append(box(x-w,y-h,x+w,y+h))
        projection._validation_building_union=unary_union(rectangles)
    geometry=projection._validation_building_union
    building_distance=line.distance(geometry) if not geometry.is_empty else math.inf
    valid = path[0] == list(start) and path[-1] == list(end) and all(projection.inside(p) for p in points)
    valid = valid and building_distance >= config['planning']['building_buffer_m']
    valid = valid and ship_distance >= buffer_m
    return {'geometry_valid':bool(valid),'distance_m':line.length,'minimum_ship_distance_m':ship_distance if math.isfinite(ship_distance) else None,'minimum_building_clearance_m':building_distance if math.isfinite(building_distance) else None}
