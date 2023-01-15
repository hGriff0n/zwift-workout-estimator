
import argparse

import physics
import route
import strava
import workouts


def split_time(t):
    m, s = divmod(t, 60)
    return f'{m:.0f}m{s:.0f}s'


# Zwift simulation controllers
class ZwiftRide(object):
    # iterator class for simulating a specific ride
    DT = 0.1

    def __init__(self, rider, workout, zroute):
        self._rider = rider.reset()
        self._route_length = zroute.length
        self._surfaces = zroute.surfaces

        # Init workout and route iterators
        self._workout_iter = iter(workout)
        self._interval = next(self._workout_iter)
        self._workout_time = sum(i.duration for i in workout)
        print(f'==>Grabbed initial workout interval: {self._interval}')

        self._route_iter = iter(zroute)
        self._segment = next(self._route_iter)
        print(f'==>Grabbed initial route segment: {self._segment}')

        # Init physics variables
        self._timer = 0
        self._interval_start = 0
        self._distance = 0
        self._elevation = 0
        self._laps = []

    # TODO(me): Could there be a possible problem here if a rider completely covers one interval in between ticks?
    # While this does get the correct interval/segment, it doesn't apply the intermediate physics
    # I am seeing this, especially at the end, might be resolvable with segment compaction though
    def _get_current_interval(self):
        while self._timer >= self._interval_start + self._interval.duration:
            self._interval_start += self._interval.duration
            self._interval = next(self._workout_iter)
            print(f'==>Grabbed next workout interval: {self._interval}')
        return self._interval

    def _get_current_segment(self):
        count = 0
        while self._distance >= self._segment.traveled:
            self._elevation += max(self._segment.delta, 0)
            count += 1
            if count > 20:
                self._report_laps()
                raise Exception("Runaway due to known bug caused by completing 2 laps. Route distance calculation accidentally deletes one lap from distance causing infinite loop. TODO(me): Fix")
            self._segment = next(self._route_iter)
            print(f'==>Grabbed next route segment: {self._segment}')
        return self._segment

    def _report_laps(self):
        for i, lap in enumerate(self._laps):
            print(f'Workout would complete lap {i + 1} in {lap}')

    def __next__(self):
        if self._timer >= self._workout_time:
            self._report_laps()
            current_lap_progress = self._distance - (len(self._laps) * self._route_length)
            pct_rte = current_lap_progress / self._route_length
            print(f"Workout would only finish {pct_rte:%} of the current lap ({current_lap_progress/1000:.2f}km out of {self._route_length/1000:.2f}km, {self._elevation}m gained)")
            raise StopIteration("")

        if self._distance >= self._route_length * (len(self._laps) + 1):
            rem = self._workout_time - self._timer
            t = split_time(self._timer)
            self._laps.append(f'{t} (with {rem:.2f}s to-go in the workout)')

        segment = self._get_current_segment()

        # TODO(me): Would this make more sense to apply before grabbing next segment?
        v = self._rider.velocity
        self._distance += v * self.DT

        interval = self._get_current_interval()
        watts = interval.target(self._rider.ftp)

        self._rider.apply_watts(watts, segment.gradient, self.DT, self._surfaces)

        self._timer += self.DT
        return (v, self._distance, self._elevation, self._timer)

class ZwiftController(object):
    # general controller class for managing workout/route selection and loading
    def __init__(self, rider, strava_client):
        self._rider = rider
        self._client = strava_client

    def set_workout(self, workout):
        self._workout = workout

    def set_route(self, route_name):
        self._route = route.load_route(route_name, self._client)

    def __iter__(self):
        return ZwiftRide(self._rider, self._workout, self._route)


# TODO(me): convert intervals to have a dt interface instead of producing list of dicts
# TODO(me): ZwiftRide can still be simplified with changes to route iterator
# TODO(me): Check time duration, workouts seem to be lasting much longer than workouts
# TODO(me): Starting at the 2nd lap, distance calculation seems to include a segment of -1Lap length
# causing an infinite loop
# TODO(me): Validate this matches the previous version
# TODO(me): Figure out domain error, start/end is really weird (legacy)
# TODO(me): Consider changing intervals into a "callable" state instead of translating ramps to a series of smaller intervals
## main
if __name__ == '__main__':
    p = argparse.ArgumentParser(prog='ZwiftEstimate')
    p.add_argument('route')
    p.add_argument('-w', '--workout', default='ftp-builder.week-5-day-2-threshold-development')
    p.add_argument('-m', '--weight', type=float, default=90)
    p.add_argument('-e', '--height', type=int, default=180)
    p.add_argument('-f', '--ftp', type=int, default=256)
    p.add_argument('-b', '--bike', default='emonda')
    p.add_argument('-c', '--wheels', default='meilensteins')
    args = p.parse_args()

    client = strava.load_from_config('strava_secrets.json')

    me = physics.Rider(args.weight, args.height, args.ftp)
    me.set_bike(physics.BIKES.get(args.bike))
    me.set_wheels(physics.WHEELS.get(args.wheels))

    zwift = ZwiftController(me, client)
    zwift.set_route(args.route)

    wl = workouts.WorkoutLoader(me)
    zwift.set_workout(wl.load_workout(name=args.workout))

    for v, d, e, t in zwift:
        ts = split_time(t)
        print(f't={ts} r={me} v={v*3.6:.2f}kph d={d/1000:.2f}km e={e}m')
