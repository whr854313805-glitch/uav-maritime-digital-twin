"""Coordinate adapter; UTM uses WGS84 ellipsoid, never a metres/degree guess."""
import math
from pyproj import Transformer

class MetricProjection:
    def __init__(self, config):
        p=config['projection'];self.lat0=p['origin_lat'];self.lon0=p['origin_lon']
        self.ky=p.get('metres_per_degree',111000);self.kx=self.ky*math.cos(math.radians(self.lat0))
        self.metric=p.get('kind')=='utm'
        if self.metric:
            if p.get('crs')!='EPSG:32650':raise ValueError('Unsupported approved metric CRS')
            self.forward=Transformer.from_crs(4326,32650,always_xy=True)
            self.inverse=Transformer.from_crs(32650,4326,always_xy=True)
    def project(self,p):
        if self.metric:return self.forward.transform(p[1],p[0])
        return ((p[1]-self.lon0)*self.kx,(p[0]-self.lat0)*self.ky)
    def unproject(self,p):
        if self.metric:
            lon,lat=self.inverse.transform(*p);return [lat,lon]
        return [p[1]/self.ky+self.lat0,p[0]/self.kx+self.lon0]
