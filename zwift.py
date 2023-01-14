
import argparse

import physics
import route
import strava
import workouts


# Zwift simulation controllers
class ZwiftRide(object):
    # iterator class for simulating a specific ride
    DT = 0.1

    def __init__(self, rider, workout, zroute):
        self._rider = rider
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
        self._velocity = 0
        self._distance = 0
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
            count += 1
            if count > 20:
                for i, lap in enumerate(self._laps):
                    print(f'Workout would complete lap {i + 1} in {lap}')
                raise Exception("Runaway due to known bug caused by completing 2 laps. Route distance calculation accidentally deletes one lap from distance causing infinite loop. TODO(me): Fix")
            self._segment = next(self._route_iter)
            print(f'==>Grabbed next route segment: {self._segment}')
        return self._segment

    def _apply_expected_power(self, interval, segment):
        watts = interval.target(self._rider.ftp)
        return self._rider.next_velocity(watts, self._velocity, segment.gradient, self.DT, self._surfaces)

    def __next__(self):
        if self._timer >= self._workout_time:
            for i, lap in enumerate(self._laps):
                print(f'Workout would complete lap {i + 1} in {lap}')
            current_lap_progress = self._distance - (len(self._laps) * self._route_length)
            pct_rte = current_lap_progress / self._route_length
            print(f"Workout would only finish {pct_rte:%} of the current lap ({current_lap_progress/1000:.2f}km out of {rte_length/1000:.2f}km)")
            raise StopIteration("")

        if self._distance >= self._route_length * (len(self._laps) + 1):
            rem = self._workout_time - self._timer
            m, s = divmod(self._timer, 60)
            self._laps.append(f'{m:.0f}m{s:.0f}s (with {rem:.2f}s to-go in the workout)')

        interval = self._get_current_interval()
        segment = self._get_current_segment()

        self._distance +=  self._velocity * self.DT
        v, self._velocity = self._velocity, self._apply_expected_power(interval, segment)

        self._timer += self.DT
        return (v, self._distance, self._timer)

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
# TODO(me): Incorporate elevation reporting
# TODO(me): Check time duration, workouts seem to be lasting much longer than workouts
# TODO(me): Make a "test" script that the workout file with specific args
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

    # Construct default bike and wheels
    # Values taken from https://johnedevans.wordpress.com/2018/05/31/the-physics-of-zwift-cycling/
    emonda = physics.Bike(4, 0.0714)
    meilensteins = physics.WheelSet(1.45, 0.1243, 'road')
    zipp_404 = physics.WheelSet(1.8, 0.1057, 'road')

    me = physics.Rider(args.weight, args.height, args.ftp)
    me.set_bike(emonda)
    me.set_wheels(meilensteins)

    zwift = ZwiftController(me, client)
    zwift.set_route(args.route)

    wl = workouts.WorkoutLoader(me, client)
    zwift.set_workout(wl.load_workout(name=args.workout))

    for v, d, t in zwift:
        m, s = divmod(t, 60)
        print(f't={m:.0f}m{s:.0f}s r={me} v={v*3.6:.2f}kph d={d/1000:.2f}km')
