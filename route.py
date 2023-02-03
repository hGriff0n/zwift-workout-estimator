
import copy
from functools import reduce
import gpxpy
from gpxpy import geo as gpxgeo
import json
import math
import operator


class Point(object):
    """A specific point on a zwift route, basically a tuple of (distance, altitude)
    """

    def __init__(self, dist, alt):
        self.distance = dist
        self.elevation = alt

    def __repr__(self):
        return f'dist={self.distance:.2f}m elev={self.elevation:.2f}m'


class Segment(object):
    """A piece of a zwift route with a constant gradient
    """

    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.length = end.distance - start.distance
        self.delta = end.elevation - start.elevation

        try:
            self.gradient = 0 if self.delta == 0 else self.delta / math.sqrt(self.length*self.length - self.delta*self.delta)
        except Exception:
            self.gradient = 0
            print(f'start: {start} end: {end} delta: {self.delta:.2f} len: {self.length: .2f}')

    @property
    def elevation_gain(self):
        return max(0, self.delta)

    def __repr__(self):
        return f'{self.length:.2f}m at {self.gradient * 100:.2f}%'


class Lap(object):
    """Collection of strava segments that are ridden in order.

    Provides easy access to total length and elevation gain.
    """

    def __init__(self, client, ids):
        self._segments = self._load_lap(client, ids)
        self._len = sum(s.length for s in self._segments)
        self._elev = sum(s.elevation_gain for s in self._segments)

    def _load_lap(self, client, segments):
        if not segments:
            return []
        return reduce(operator.concat, [self._grab_segment(client, sid) for sid in segments])

    def _grab_segment(self, client, segment_id):
        s = client.get_segment_streams(segment_id, types=['distance', 'altitude'])
        it = zip(s['distance'].data, s['altitude'].data)
        start = Point(*next(it))
        prev = None
        segments = []
        for d, e in it:
            p = Point(d, e)
            if e == start.elevation:
                prev = p
                continue
            if prev is not None:
                segments.append(Segment(copy.copy(start), copy.copy(prev)))
                start = prev
                prev = None
            segments.append(Segment(copy.copy(start), copy.copy(p)))
            start = p

        return segments

    @property
    def length(self):
        return self._len / 1000

    @property
    def elevation_gain(self):
        return self._elev

    def __iter__(self):
        return iter(self._segments)

class GpxLap(Lap):
    """Customization to enable building a "lap" from a gpx file, in case strava segments are unavailable.

    Mostly useful for integrating workout estimation with rouvy (though the physics are different)
    """

    def __init__(self, client, ids):
        super().__init__(client, ids)

    def _load_lap(self, _client, segments):
        with open(segments['gpx'], 'r') as f:
            self._gpx = gpxpy.parse(f)

        route = self._gpx.tracks[0].segments[0]
        points = [
            Point(gpxgeo.length_3d(route.points[:i]), point.elevation) for point, i in route.walk()
        ]
        start = points[0]
        prev = None
        segments = []
        for p in points[1:]:
            if p.elevation == start.elevation:
                prev = p
                continue
            if prev is not None:
                s = Segment(copy.copy(start), copy.copy(prev))
                if s.length > 0:
                    segments.append(s)
                start = prev
                prev = None
            s = Segment(copy.copy(start), copy.copy(p))
            if s.length > 0:
                segments.append(s)
            start = p
        return segments

# TODO(me): Add ability to customize laps as some routes just end.
# Will likely need to be able to reverse/offset/trim/insert segments to fuly work
class Route(object):
    """Combination of a lap with an optional lead in.

    Provides additional information about aggregate surface type and reports lap completions
    while also providing an iterator to repeatedly loop over the main lap (after a lead in).

    Surface information taken from https://zwiftmap.com/watopia
    """

    def __init__(self, name, details, client):
        self._name = name
        self._surfaces = details.get('surfaces', {})
        self._leadin = Lap(client, details.get('lead_in', []))
        self._leadin_active = ('lead_in' in details)

        if 'gpx' in details:
            self._lap = GpxLap(client, details)
        else:
            self._lap = Lap(client, details['lap'])

        self.attach_lap_reporter()

    @property
    def name(self):
        return self._name

    @property
    def surfaces(self):
        return self._surfaces

    @property
    def active_lap(self):
        return self._leadin if self._leadin_active else self._lap

    def has_lead_in(self):
        return self._leadin.length > 0

    # Define iterator which traverses the leadin before repeatedly traversing the lap
    def __iter__(self):
        while True:
            for s in self.active_lap:
                yield s
            self._leadin_active = False
            self._report_lap()

    def attach_lap_reporter(self, lap_reporter=None):
        if lap_reporter is None:
            lap_reporter = lambda: None
        self._report_lap = lap_reporter

class JungleLeadIn(Route):
    def __init__(self, name, details, client):
        super().__init__(name, details, client)
        self._alpe_surface = self._surfaces.copy()
        self._alpe_surface.pop('dirt', None)
        self._surfaces = { 'dirt': 1 }

    # Define iterator which traverses the leadin before repeatedly traversing the lap
    def __iter__(self):
        self._leadin_active = True
        it = iter(self._leadin)
        covered = 0
        while covered <= 5000:
            s = next(it)
            covered += s.length
            yield s

        self._surfaces = self._alpe_surface
        for s in it:
            yield s

        self._report_lap()
        self._leadin_active = False

        while True:
            for s in self._lap:
                yield s
            self._report_lap()


with open("routes.json") as fp:
    ROUTE_DIRECTORY = json.load(fp)

def load_route(name, strava_client):
    world, route_ = name.split('.')
    if route_ == 'road_to_sky':
        return JungleLeadIn(name, ROUTE_DIRECTORY[world][route_], strava_client)
    return Route(name, ROUTE_DIRECTORY[world][route_], strava_client)
