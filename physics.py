
import json
import math


# Zwift Physics Constants
# https://www.gribble.org/cycling/power_v_speed.html
GRAVITY = 9.8067 # m/s*s
AIR_DENSITY = 1.225 # kg/m**3

# Taken from tables in https://johnedevans.wordpress.com/2018/05/31/the-physics-of-zwift-cycling/
EMONDA_MASS = 4
WHEEL_CD = 0.1057
EMONDA_CD = 0.0714
RIDER_CD = 0.5 # Computed from richmond tables
TOTAL_CD = WHEEL_CD + EMONDA_CD + RIDER_CD


# Taken from zwiftinsider tables
# Not sure how to handle this overall as it can vary within a route (maybe world averages?)
with open('road_values.json') as road_fp:
    CRR_MAP = json.load(road_fp)['crr']


class CyclingObject(object):

    def __init__(self, mass, cd):
        self._mass = mass
        self._cd = cd

    @property
    def mass(self):
        return self._mass

    @property
    def cd(self):
        return self._cd


class Wheels(CyclingObject):

    def __init__(self, mass, cd, _type):
        super().__init__(mass, cd)
        self._crr_map = CRR_MAP[_type]

    def crr(self, road_surface):
        return self._crr_map[road_surface]


# Physics modelling class for zwift rider. Provides two
class Rider(object):

    # mass in kg, height in cm, ftp in w
    def __init__(self, mass: int, height: int, ftp: int):
        self._bike, self._wheels = None, None

        self._mass = mass
        self._height = height

        self._ftp = ftp
        self._v = 0

    def _rolling_friction(self, gradient: float, surface: str):
        return GRAVITY * math.cos(math.atan(gradient)) * self.mass * self._wheels.crr(surface)

    def _gravity_friction(self, gradient):
        return GRAVITY * math.sin(math.atan(gradient)) * self.mass

    def _drag_friction(self):
        return self.cd * self.frontal_area * (self._v * self._v) * AIR_DENSITY / 2

    def sustaining_power(self, gradient: float, surface: str):
        fr = self._rolling_friction(gradient, surface)
        fg = self._gravity_friction(gradient)
        fd = self._drag_friction()
        return (fr + fg + fd) * self._v

    # https://physics.stackexchange.com/questions/226854/how-can-i-model-the-acceleration-velocity-of-a-bicycle-knowing-only-the-power-ou
    def apply_watts(self, watts: int, gradient: float, dt: float, surface: str):
        v = self._v
        power_needed = self.sustaining_power(gradient, surface)
        v = v*v + 2 * (watts - power_needed) * dt / self.mass
        return math.sqrt(v)

    # TODO(me): Deprecated
    # https://physics.stackexchange.com/questions/226854/how-can-i-model-the-acceleration-velocity-of-a-bicycle-knowing-only-the-power-ou
    def next_velocity(self, pedal_power: float, velocity: float, gradient: float, dt: float, surface: str):
        self._v = velocity
        return self.apply_watts(pedal_power, gradient, dt, surface)

    def start_ride(self):
        self._v = 0

    def set_bike(self, bike):
        print(f'Functionality currently unimplemented. Ignoring bike {bike}, using EMONDA')
        self._bike = CyclingObject(EMONDA_MASS, EMONDA_CD)

    # TODO(me): Figure out the wheel mass
    def set_wheels(self, wheels):
        print(f'Functionality currently unimplemented. Ignoring wheels {wheels}, using EMONDA')
        self._wheels = Wheels(0, WHEEL_CD, 'road')

    def __repr__(self):
        return f'{self._mass}kg ftp={self.ftp}w'

    @property
    def mass(self):
        return self._mass + self._bike.mass + self._wheels.mass

    @property
    def frontal_area(self):
        BIKE_AREA = 0.1647
        return 0.0276*math.pow(self._height / 100, 0.725)*math.pow(self.mass, 0.425) + BIKE_AREA

    @property
    def cd(self):
        RIDER_CD = 0.5 # Computed from richmond tables
        return RIDER_CD + self._wheels.cd + self._bike.cd

    @property
    def velocity(self):
        return self._velocity

    @property
    def ftp(self):
        return self._ftp
