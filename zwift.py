
from bs4 import BeautifulSoup
import jsonpickle
import re
import requests

import intervals
import physics
import route
import strava


class WorkoutManager(object):
    def __init__(self, rider):
        self._workout_namer = re.compile(r'workouts/(?P<plan>[^/]+)/(?P<workout>.*)')
        self._plan_namer = re.compile(r'workouts/(?P<plan>[^/]+)')
        self._watt_pct_re = re.compile(r'((?P<rwatts>\d+) to )?(?P<watts>\d+)W')
        self._rider = rider
        with open('workouts.json') as f:
            self._cache = jsonpickle.decode(f.read())

    def _get(self, url):
        return BeautifulSoup(requests.get(url).content, "html.parser")

    def _scrape_intervals(self, soup):
        return soup.find_all('div', class_='workoutlist')[0].find_all('div', class_='textbar')

    # Convert between watt and %FTP intervals, in case the url somehow directs to watt
    def _grab_interval_text(self, text, showing_watts):
        if not showing_watts:
            return text
        while True:
            m = self._watt_pct_re.search(text)
            if not m:
                return text
            pct_ftp = int(int(m['watts']) / self._rider.ftp * 100)
            t = f'{pct_ftp}% FTP'
            if m['rwatts'] is not None:
                pct_ftp = int(int(m['rwatts']) / self._rider.ftp * 100)
                t = f'{pct_ftp} to {t}'
            text = text.replace(text[m.start():m.end()], t)

    def _scrape_workout(self, soup, showing_watts):
        wi = []
        for elem in self._scrape_intervals(soup):
            interval_block = intervals.parse_interval(self._grab_interval_text(elem.text, showing_watts))
            wi.extend(interval_block.intervals())
        return wi

    def load_workout(self, url):
        self.name_workout(url)
        s = self._get(url)
        showing_watts = s.find(text=r'View %FTP') is not None
        return self._scrape_workout(s, showing_watts)

    def _scrape_plan(self, soup):
        return soup.find_all('article', class_='workout')

    def load_training_plan(self, url):
        self.name_training_plan(url)
        s = self._get(url)
        showing_watts = s.find(text=r'View %FTP') is not None
        workouts = {}
        for w in self._scrape_plan(s):
            workouts[w['id'].replace('-', '_')] = self._scrape_workout(w, showing_watts)
        return workouts

    def name_training_plan(self, url):
        m = self._plan_namer.search(url)
        if not m:
            raise Exception("Failed to match expected workout plan url format")
        return m.group('plan').replace('-', '_')

    def name_workout(self, url):
        m = self._workout_namer.search(url)
        if not m:
            raise Exception("Failed to match expected workout url format")
        plan = m.group('plan').replace('-', '_')
        workout = m.group('workout').replace('-', '_')
        return plan, workout

    # This could be split into a separate class, technically
    def add_to_cache(self, workout_dict, plan=None):
        if plan is None:
            plan = 'global'
        if plan not in self._cache:
            self._cache[plan] = {}
        for k, v in workout_dict.items():
            self._cache[plan][k] = v

    def select_workout(self, workout, plan=None):
        if plan is None:
            plan = 'global'
        return self._cache.get(plan, {}).get(workout, [])

    def save_cache(self):
        with open('workouts.json', 'w') as f:
            f.write(jsonpickle.encode(self._cache))

# Zwift simulation controllers
class ZwiftRide(object):
    # iterator class for simulating a specific ride
    DT = 0.1

    def __init__(self, zwift):
        self._controller = zwift
        self._workout_time = sum(i.duration for i in self._controller._workout)

        # Init workout and route iterators
        self._workout_iter = iter(self._controller._workout)
        self._interval = next(self._workout_iter)
        print(f'==>Grabbed initial workout interval: {self._interval}')

        self._route_iter = iter(self._controller._route)
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
        watts = interval.target(self._controller._rider.ftp)
        return self._controller._rider.next_velocity(watts, self._velocity, segment.gradient, self.DT, self._controller._route.surfaces)

    def __next__(self):
        rte_length = self._controller._route.length
        if self._timer >= self._workout_time:
            for i, lap in enumerate(self._laps):
                print(f'Workout would complete lap {i + 1} in {lap}')
            current_lap_progress = self._distance - (len(self._laps) * rte_length)
            pct_rte = current_lap_progress / rte_length
            print(f"Workout would only finish {pct_rte:%} of the current lap ({current_lap_progress/1000:.2f}km out of {rte_length/1000:.2f}km)")
            raise StopIteration("")

        if self._distance >= rte_length * (len(self._laps) + 1):
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
    def __init__(self, rider, strava_client, workout_manager):
        self._rider = rider
        self._client = strava_client
        self._w = workout_manager

    def load_workout(self, url=None, plan=None, name=None):
        if url is not None:
            plan, name = self._w.name_workout(url)
        self._workout = self._w.select_workout(name, plan=plan)
        if not self._workout:
            self._workout = self._w.load_workout(url)
            self._w.add_to_cache({name: self._workout}, plan=plan)

    def _grab_segment_points(self, segment_id):
        s = self._client.get_segment_streams(segment_id, types=['distance', 'altitude'])
        it = zip(s['distance'].data, s['altitude'].data)
        points = [route.Point(*next(it))]
        prev = None
        for d, e in it:
            p = route.Point(d, e)
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

    def load_route_profile(self, route_name):
        self._route_name = route_name

        world, route_ = route_name.split('.')
        self._route = route.Route(self._route_name, route.ROUTE_DIRECTORY[world][route_], self)

    def __iter__(self):
        return ZwiftRide(self)


## main

client = strava.init_client(STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN)
me = physics.Rider(90, 180, 256)
me.set_bike(0)
me.set_wheels(0)
w =  WorkoutManager(me)

zwift = ZwiftController(me, client, w)
zwift.load_workout(url=r'https://whatsonzwift.com/workouts/ftp-builder/week-4-day-4-tempo')
zwift.load_route_profile('watopia.road_to_sky')

for v, d, t in zwift:
    m, s = divmod(t, 60)
    print(f't={m:.0f}m{s:.0f}s r={me} v={v*3.6:.2f}kph d={d/1000:.2f}km')
