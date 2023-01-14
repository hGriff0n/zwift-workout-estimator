
from datetime import timedelta
import math
import re


_TIMEDELTA = re.compile((r'((?P<days>-?\d+)d)?'
                   r'((?P<hours>-?\d+)h)?'
                   r'((?P<minutes>-?\d+)m)?'
                   r'((?P<seconds>-?\d+)s)?'), re.IGNORECASE)


def _parse_delta(delta):
    match = _TIMEDELTA.match(delta)
    if match:
        parts = {k: int(v) for k, v in match.groupdict().items() if v}
        return timedelta(**parts)


# TODO(me): Change these to a function which takes in a time interval
class Interval(object):

    def __init__(self, raw_str, matcher, **kwargs):
        if len(kwargs) > 0:
            self._interval = {**kwargs}
            return

        m = matcher.match(raw_str)
        if not m:
            raise Exception(f"Failed to parse interval - didn't match regex={raw_str}")
        self._interval = m.groupdict()
        self._end = m.end()

        # Early return in the case of set intervals
        if 'reps' in self._interval:
            self._interval['reps'] = int(self._interval['reps'])
            return

        m = self._interval.get('timem') or 0
        s = self._interval.get('times') or 0
        if not m and not s:
            raise Exception(f"Failed to parse interval - didn't specify time={raw_str}")
        self._interval['time'] = f'{m}m{s}s'

        self._interval['duration'] = int(_parse_delta(self.time).total_seconds())
        if 'pct_ftp' in self._interval:
            self._interval['pct_ftp'] = int(self._interval['pct_ftp']) / 100
        if 'cadence' in self._interval:
            if not self._interval['cadence']:
                del self._interval['cadence']
            else:
                self._interval['cadence'] = int(self._interval['cadence'])
        if 'end_pct' in self._interval:
            self._interval['end_pct'] = int(self._interval['end_pct']) / 100

    @property
    def pct_ftp(self):
        return self._interval['pct_ftp']
    @property
    def duration(self):
        return self._interval['duration']
    @property
    def cadence(self):
        return self._interval.get('cadence')

    @property
    def time(self):
        return self._interval.get('time')

    @property
    def match_end(self):
        return self._end

    def intervals(self):
        return [self]


class FreeRideInterval(Interval):
    MATCHER = re.compile(r'((?P<timem>\d+)min *)?((?P<times>\d+)sec *)?(@(?P<cadence>\d+)rpm)? free ride')

    def __init__(self, raw_str):
        super().__init__(raw_str, FreeRideInterval.MATCHER)

    def __repr__(self):
        return f'Free Ride for {self.time}'

    def target(self, _ftp):
        return 100


class SteadyInterval(Interval):
    MATCHER = re.compile(r'(((?P<timem>\d+)min *)?((?P<times>\d+)sec *)?@ )((?P<cadence>\d+)rpm, )?((?P<pct_ftp>\d+)% FTP)')

    def __init__(self, raw_str, round_to_5=None, **kwargs):
        super().__init__(raw_str, SteadyInterval.MATCHER, **kwargs)
        self._round_to_5 = round_to_5

    def __repr__(self):
        return f'Steady Interval: {self.duration}s at {self.pct_ftp:.0%} FTP'

    def target(self, ftp):
        w = self.pct_ftp * ftp
        if self._round_to_5:
            w = round(math.ceil(w) / 5) * 5
        return w


class RampInterval(Interval):
    MATCHER = re.compile(r'((?P<timem>\d+)min *)?((?P<times>\d+)sec *)?(@ (?P<cadence>\d+)rpm,? )?from (?P<pct_ftp>\d+) to ((?P<end_pct>\d+)%) FTP')

    def __init__(self, raw_str):
        super().__init__(raw_str, RampInterval.MATCHER)

    def __repr__(self):
        end = self._interval['end_pct']
        return f'Ramp Interval: {self.time} from {self.pct_ftp:.0%} FTP to {end:.0%} FTP'

    def _step(self, ftp_target, time):
        return SteadyInterval("", start_time=time, pct_ftp=ftp_target, cadence=self.cadence, duration=15, time='15sec')

    def intervals(self):
        m = (self._interval['end_pct'] - self.pct_ftp) / self.duration
        return [self._step(m*t+self.pct_ftp, t) for t in range(0, self.duration + 1, 15)]


class SetInterval(Interval):
    MATCHER = re.compile(r'(?P<reps>\d+)x (?P<set>.*)')

    def __init__(self, raw_str):
        super().__init__(raw_str, SetInterval.MATCHER)

        self._rep = []
        set_str = self._interval['set']
        while set_str:
            self._rep.append(parse_interval(set_str))
            set_str = set_str[self._rep[-1].match_end+1:]

    def intervals(self):
        return self._rep * self._interval['reps']


def parse_interval(raw_str):
    if 'free ride' in raw_str:
        return FreeRideInterval(raw_str)
    if 'from' in raw_str:
        return RampInterval(raw_str)
    if 'x' in raw_str:
        return SetInterval(raw_str)
    return SteadyInterval(raw_str)
