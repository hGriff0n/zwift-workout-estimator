
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

    @property
    def frontal_area(self):
        return 0.1647


class WheelSet(CyclingObject):

    def __init__(self, mass, cd, _type):
        super().__init__(mass, cd)
        self._crr_map = CRR_MAP[_type]

    def crr(self, surfaces: dict):
        crr = 0
        rem = 1
        for surface, pct in surfaces.items():
            if pct != 0:
                crr += self._crr_map[surface] * pct
                rem -= pct
        return crr + self._crr_map['road'] * rem


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
        return math.sqrt(v)

    # TODO(me): Deprecated
    # https://physics.stackexchange.com/questions/226854/how-can-i-model-the-acceleration-velocity-of-a-bicycle-knowing-only-the-power-ou
    def next_velocity(self, pedal_power: float, velocity: float, gradient: float, dt: float, surfaces: dict):
        self._v = velocity
        return self.apply_watts(pedal_power, gradient, dt, surfaces)

    def start_ride(self):
        self._v = 0

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
        return f'{self._mass}kg ftp={self.ftp}w'

    @property
    def frontal_area(self):
        return 0.0276*math.pow(self._height / 100, 0.725)*math.pow(self.mass, 0.425) + self._bike.frontal_area

    @property
    def velocity(self):
        return self._velocity

    @property
    def ftp(self):
        return self._ftp
