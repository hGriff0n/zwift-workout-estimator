
from bs4 import BeautifulSoup
import jsonpickle
import re
import requests

import intervals

class WorkoutLoader(object):
    """
    Loader object to manage extracting zwift workouts from "whatsonzwift"

    Also manages saving and loading the intervals from a local cache if one is provided
    """

    def __init__(self, rider):
        self._workout_namer = re.compile(r'workouts/(?P<plan>[^/]+)/(?P<workout>.*)')
        self._plan_namer = re.compile(r'workouts/(?P<plan>[^/]+)')
        self._watt_pct_re = re.compile(r'((?P<rwatts>\d+) to )?(?P<watts>\d+)W')
        self._rider = rider
        # TODO(me): Allow for this to fail with an empty cache
        with open('workouts.json') as f:
            self._cache = jsonpickle.decode(f.read())

    def _list_intervals(self, soup):
        return soup.find_all('div', class_='workoutlist')[0].find_all('div', class_='textbar')

    def _text_to_pct_ftp(self, text):
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

    def _scrape_whatsonzwift(self, url):
        s = BeautifulSoup(requests.get(url).content, "html.parser")
        displays_watts = s.find(text=r'View %FTP') is not None
        return self._scrape_workout(s, displays_watts)

    def _scrape_workout(self, s, displays_watts):
        blocks = []
        for elem in self._list_intervals(s):
            txt = elem.text if not displays_watts else self._text_to_pct_ftp(elem.text)
            block = intervals.parse_interval(txt)
            blocks.extend(block.intervals())
        return blocks

    def _generate_url(self, plan, workout):
        return f'https://whatsonzwift.com/workouts/{plan}/{workout}'

    def _extract_workout_name(self, url, name):
        if url is None:
            return name.split('.')
        m = self._workout_namer.search(url)
        if not m:
            raise Exception("Failed to match expected workout plan url format")
        return m.group('plan').replace('-', '_'), m.group('workout').replace('-', '_')

    def load_workout(self, url=None, name=None):
        plan, workout = self._extract_workout_name(url=url, name=name)
        intervals = self._cache.get(plan, {}).get(workout, [])
        if not intervals:
            intervals = self._scrape_whatsonzwift(url or self._generate_url(plan, workout))
            if plan not in self._cache:
                self._cache[plan] = {}
            self._cache[plan][workout] = intervals

        return intervals

    def _extract_plan_name(self, url):
        m = self._plan_namer.search(url)
        if not m:
            raise Exception("Failed to match expected workout plan url format")
        return m.group('plan').replace('-', '_')

    def _generate_plan_url(self, plan, workout):
        return f'https://whatsonzwift.com/workouts/{plan}'

    def _scrape_training_plan(self, url):
        s = BeautifulSoup(requests.get(url).content, "html.parser")
        displays_watts = s.find(text=r'View %FTP') is not None
        workouts = {}
        for workout in s.find_all('article', class_='workout'):
            workouts[workout['id'].replace('-', '_')] = self._scrape_workout(workout, displays_watts)
        return workouts

    def load_plan(self, url=None, plan=None):
        name = plan if plan is not None else self._extract_plan_name(url)
        workouts = self._cache.get(name, {})
        if not workouts:
            workouts = self._scrape_training_plan(url or self._generate_plan_url(name))
            self._cache[name] = workouts
        return workouts

    def save_cache(self):
        with open('workouts.json', 'w') as f:
            f.write(jsonpickle.encode(self._cache))
