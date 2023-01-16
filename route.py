
import copy
from functools import reduce
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
        self.gradient = 0 if self.delta == 0 else self.delta / math.sqrt(self.length*self.length - self.delta*self.delta)

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


# TODO(me): Add ability to customize laps as some routes just end.
# Will likely need to be able to reverse/offset/trim/insert segments to fuly work
class Route(object):
    """Combination of a lap with an optional lead in.

    Provides additional information about aggregate surface type and reports lap completions
    while also providing an iterator to repeatedly loop over the main lap (after a lead in).
    """

    def __init__(self, name, details, client):
        self._name = name
        self._surfaces = details.get('surfaces', {})
        self._lap = Lap(client, details['lap'])
        self._leadin = Lap(client, details.get('lead_in', []))
        self._leadin_active = False

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
        self._leadin_active = True
        for s in self._leadin:
            yield s
        self._report_lap()
        self._leadin_active = False

        while True:
            for s in self._lap:
                yield s
            self._report_lap()

    def attach_lap_reporter(self, lap_reporter=None):
        if lap_reporter is None:
            lap_reporter = lambda: None
        self._report_lap = lap_reporter


with open("routes.json") as fp:
    ROUTE_DIRECTORY = json.load(fp)

def load_route(name, strava_client):
    world, route_ = name.split('.')
    return Route(name, ROUTE_DIRECTORY[world][route_], strava_client)
