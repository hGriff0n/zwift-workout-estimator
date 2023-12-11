
import json
import math


# Zwift Physics Constants
# https://www.gribble.org/cycling/power_v_speed.html
GRAVITY = 9.8067 # m/s*s
AIR_DENSITY = 1.225 # kg/m**3


# Taken from zwiftinsider tables
# Not sure how to handle this overall as it can vary within a route (maybe world averages?)
with open('road_values.json') as road_fp:
    CRR_MAP = json.load(road_fp)['crr']


# Values taken from https://johnedevans.wordpress.com/2018/05/31/the-physics-of-zwift-cycling/
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


class Bike(CyclingObject):

    def __init__(self, aero: int, weight: int):
        super().__init__(9 - weight, .0874 - .008*aero)

    @property
    def frontal_area(self):
        return 0.1647


class WheelSet(CyclingObject):

    def __init__(self, aero: int, weight: int, _type: str):
        super().__init__(2.2 - weight*.2, .1801 - .0186*aero)
        self._crr_map = CRR_MAP[_type]

    def crr(self, surfaces: dict):
        crr = 0
        rem = 1
        for surface, pct in surfaces.items():
            if pct != 0:
                crr += self._crr_map[surface] * pct
                rem -= pct
        return crr + self._crr_map['road'] * rem

class RoadWheels(WheelSet):
    def __init__(self, aero: int, weight: int):
        super().__init__(aero=aero, weight=weight, _type='road')


# Physics modelling class for zwift rider. Provides two
class Rider(CyclingObject):

    # mass in kg, height in cm, ftp in w
    def __init__(self, mass: int, height: int, ftp: int):
        super().__init__(mass, 0.5)  # Rider Cd taken from richmond dataset (https://johnedevans.wordpress.com/2018/05/31/the-physics-of-zwift-cycling/)
        self._bike, self._wheels = None, None
        self._height = height

        self._ftp = ftp
        self._v = 0

    def _rolling_friction(self, gradient: float, surfaces: dict):
        return GRAVITY * math.cos(math.atan(gradient)) * self.mass * self._wheels.crr(surfaces)

    def _gravity_friction(self, gradient):
        return GRAVITY * math.sin(math.atan(gradient)) * self.mass

    def _drag_friction(self):
        return self.cd * self.frontal_area * (self._v * self._v) * AIR_DENSITY / 2

    def sustaining_power(self, gradient: float, surfaces: dict):
        fr = self._rolling_friction(gradient, surfaces)
        fg = self._gravity_friction(gradient)
        fd = self._drag_friction()
        return (fr + fg + fd) * self._v

    # https://physics.stackexchange.com/questions/226854/how-can-i-model-the-acceleration-velocity-of-a-bicycle-knowing-only-the-power-ou
    def apply_watts(self, watts: int, gradient: float, dt: float, surfaces: dict):
        v = self._v
        power_needed = self.sustaining_power(gradient, surfaces)
        v = v*v + 2 * (watts - power_needed) * dt / self.mass
        self._v = math.sqrt(v)

    def reset(self):
        self._v = 0
        return self

    def _add_accessory(self, obj, remove=False):
        sign = -1 if remove else 1
        self._cd += (obj.cd * sign)
        self._mass += (obj.mass * sign)

    def set_bike(self, bike):
        if not isinstance(bike, Bike):
            raise Exception("Can only ride a bike")
        if self._bike:
            self._add_accessory(self._bike, remove=True)
        self._bike = bike
        self._add_accessory(self._bike)

    def set_wheels(self, wheels):
        if not isinstance(wheels, WheelSet):
            raise Exception("Bikes can only be fitted with wheels")
        if self._wheels:
            self._add_accessory(self._wheels, remove=True)
        self._wheels = wheels
        self._add_accessory(self._wheels)

    def __repr__(self):
        return f'{self._mass:.2f}kg ftp={self.ftp}w'

    @property
    def frontal_area(self):
        return 0.0276*math.pow(self._height / 100, 0.725)*math.pow(self.mass, 0.425) + self._bike.frontal_area

    @property
    def velocity(self):
        return self._v

    @property
    def ftp(self):
        return self._ftp


# Trawled from game data files
# https://docs.google.com/spreadsheets/d/1O2NN5RHH3Q2j4uNjKJTkxqse-Ax2DOf7EcywS5O5-VE/edit#gid=0
# emonda: cdA=0 weight=3.9kg
# canyon: cdA=0 weight=3.96kg
# nuclear: cdA=-.0047 weight=4.48kg
BIKES = {
    'emonda': Bike(weight=4, aero=2),
    'canyon': Bike(weight=4, aero=2),  # climbing route
    'nuclear': Bike(weight=3, aero=3), # flat route
}

# Trawled from game data files
# https://docs.google.com/spreadsheets/d/1O2NN5RHH3Q2j4uNjKJTkxqse-Ax2DOf7EcywS5O5-VE/edit#gid=0
# meilensteins: cdA=-.004 weight=1.83kg
# dt_swiss: cdA=-.0105 weight=2.13kg
# cadex: cdA=-.005 weight=2.11kg
# enve: cdA=-.008 weight=2.08kg
WHEELS = {
    'meilensteins': RoadWheels(weight=4, aero=3),   # climbing route
    'dt_swiss': RoadWheels(weight=3, aero=4),       # flat route (best overall)
    'cadex': RoadWheels(weight=3, aero=4),
    'enve': RoadWheels(weight=3, aero=4),
}
