
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

    def __init__(self, rider, workout, route):
        self._rider = rider
        self._route = route
        self._workout = workout

        self._laps = []
        self._route.attach_lap_reporter(lap_reporter=self._report_lap)
        self._workout_time = sum(i.duration for i in workout)

        # Init physics variables
        self._timer = 0
        self._distance = 0
        self._climbed = 0

    @property
    def distance(self):
        return self._distance / 1000

    def _iterate_workout(self):
        finished = 0
        for interval in self._workout:
            print(f'==>Grabbed next interval segment: {interval}')
            # Keep returning "this" interval until we have "traveled" the full duration
            while self._timer - finished <= interval.duration:
                yield interval
            finished += interval.duration

    def _iterate_route(self):
        traveled = 0
        for segment in self._route:
            print(f'==>Grabbed next route segment: {segment}')
            # Keep returning "this" segment until we have traveled the full length
            while traveled + segment.length > self._distance:
                yield segment
            traveled += segment.length
            self._climbed += segment.elevation_gain

    def _report_lap(self):
        is_lead_in = (not self._laps) and self._route.has_lead_in()
        rem = self._workout_time - self._timer
        self._laps.append((split_time(self._timer), rem, is_lead_in))

    def _report_progress(self, distance):
        lap = self._route.active_lap
        pct_complete = distance / lap.length
        print(f'Workout completed with current lap only {pct_complete:.2%} complete ({distance:.2f}km out of {lap.length:.2f}km)')

    def _report_completions(self):
        distance = 0
        lap_number = iter(range(len(self._laps)))
        for t, rem, is_lead_in in self._laps:
            name = 'Lead-In' if is_lead_in else f'Lap {next(lap_number)}'
            print(f'{name} completed in {t} (with {rem:.2f}s left in workout)')
            distance += self._route._leadin.length if is_lead_in else self._route._lap.length
        return distance

    def _report_totals(self):
        print(f'In total, workout would travel {self.distance:.2f}km and climb {self._climbed:.2f}m')

    def __iter__(self):
        segment_generator = self._iterate_route()
        for interval in self._iterate_workout():
            segment = next(segment_generator)

            # Technically inaccurate, but close enough for the simulation
            old_v = self._rider.velocity
            self._distance += old_v * self.DT

            watts = interval.target(self._rider.ftp)
            self._rider.apply_watts(watts, segment.gradient, self.DT, self._route.surfaces)

            yield (old_v, self.distance, self._climbed, self._timer)
            self._timer += self.DT

        completed_lap_distance = self._report_completions()
        self._report_progress(self.distance - completed_lap_distance)
        self._report_totals()


class ZwiftController(object):
    # general controller class for managing workout/route selection and loading
    def __init__(self, rider, strava_client):
        self._rider = rider
        self._client = strava_client

    def set_workout(self, workout):
        self._workout = workout

    def set_route(self, route_name):
        self._route = route.load_route(route_name, self._client)

    def start_ride(self):
        return ZwiftRide(self._rider, self._workout, self._route)

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

    for v, d, e, t in zwift.start_ride():
        ts = split_time(t)
        print(f't={ts} r={me} v={v*3.6:.2f}kph d={d:.2f}km e={e:.2f}m')
