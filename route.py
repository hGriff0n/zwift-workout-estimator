
import copy
import json
import math


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

    def __init__(self, start, end, traveled):
        self.start = start
        self.end = end
        self._traveled = traveled
        self.length = end.distance - start.distance
        self.delta = end.elevation - start.elevation
        self.gradient = 0 if self.delta == 0 else self.delta / math.sqrt(self.length*self.length - self.delta*self.delta)

    @property
    def traveled(self):
        return self._traveled + self.end.distance

    def __repr__(self):
        return f'{self.length:.2f}m at {self.gradient * 100:.2f}%'


class RouteIterator(object):
    """Steps along segments on a zwift route.

    Accommodates route lead_ins before repeating laps until iteration stops.
    Will iterate forever if no break is inserted into the loop.
    """
    def __init__(self, lead_in, lap):
        self._pos = lead_in
        self._lap = lap
        if self._pos is None:
            self._pos = copy.copy(self._lap)

        self._num_laps = 2
        self._base_distance = 0
        self._prev = next(self._pos)
        _ = next(self._lap)

    def __next__(self):
        nxt = next(self._pos, None)
        if nxt is None:
            self._base_distance += self._prev.distance
            self._prev.distance = 0
            self._pos = copy.copy(self._lap)
            nxt = next(self._pos)
        s = Segment(self._prev, nxt, self._base_distance)
        self._prev = nxt
        return s


# TODO(me): Add ability to customize laps as some routes just end.
# Will likely need to be able to reverse/offset/trim/insert segments to fuly work
class Route(object):
    """Provides an iterator to step along segments on a zwift route.

    Accommodates route lead_ins before repeating laps until iteration stops.
    """

    # TODO(me): Zwift loader doesn't have a "known" type at this point
    def _load_lap(self, segments):
        segment_id = segments['lap'][0]
        lap = self._grab_segment_points(segment_id)
        self._lap_distance = lap[-1].distance
        self._lap = iter(lap)
        self._leadin = None
        self._lead_in_distance = 0

    def _load_leadin(self, segments):
        leadin = []
        if segments.get('lead_in', []):
            leadin = self._grab_segment_points(segments['lead_in'][0])

        if leadin:
            self._lead_in_distance += leadin[-1].distance
            self._leadin = iter(leadin)

    def __init__(self, name, segments, strava_client):
        self._name = name
        self._client = strava_client
        self._surfaces = segments.get('surfaces', {})
        self._load_lap(segments)
        self._load_leadin(segments)

    def _grab_segment_points(self, segment_id):
        s = self._client.get_segment_streams(segment_id, types=['distance', 'altitude'])
        it = zip(s['distance'].data, s['altitude'].data)
        points = [Point(*next(it))]
        prev = None
        for d, e in it:
            p = Point(d, e)
            if p.elevation == points[-1].elevation:
                prev = p
            else:
                if prev is not None:
                    points.append(prev)
                    prev = None
                points.append(p)
        if prev is not None:
            points.append(prev)
        return points

    @property
    def length(self):
        return self._lap_distance + self._lead_in_distance

    @property
    def name(self):
        return self._name

    @property
    def surfaces(self):
        return self._surfaces

    def __iter__(self):
        return RouteIterator(copy.copy(self._leadin), copy.copy(self._lap))

with open("routes.json") as fp:
    ROUTE_DIRECTORY = json.load(fp)

def load_route(name, strava_client):
    world, route_ = name.split('.')
    return Route(name, ROUTE_DIRECTORY[world][route_], strava_client)
