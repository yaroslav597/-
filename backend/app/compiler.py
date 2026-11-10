"""Rebuild MAVLink items from the validated plan; never forward browser items."""
import math
from dataclasses import asdict, dataclass

from .schemas import MissionPlan


@dataclass(frozen=True)
class MissionItem:
    command: int
    frame: int = 3
    param1: float = 0
    param2: float = 0
    param3: float = 0
    param4: float = 0
    x: int = 0
    y: int = 0
    z: float = 0

    def as_dict(self):
        return asdict(self)


def item(command, location=None, **params):
    values = {}
    if command in (16, 19, 21, 22, 201):
        values = dict(x=math.floor(location.lat * 1e7 + 0.5), y=math.floor(location.lng * 1e7 + 0.5), z=location.alt)
    if command in (16, 19):
        values['param1'] = params.get('delay', 0) if command == 16 else params['duration']
    elif command == 178:
        values.update(param1=1, param2=params['speed'], param3=-1)
    elif command == 115:
        values.update(param1=params['yaw'], param2=params['yawRate'], param3=params['direction'], param4=params['relative'])
    elif command == 201:
        values['param1'] = 3
    elif command == 206:
        values.update(param1=params['distance'], param3=params['immediate'])
    elif command == 203:
        values['x'] = 1
    return MissionItem(command=command, **values)


def hold_seconds(actions):
    return min(65535, max(3, sum(math.ceil(360 / (action.params.yawRate or 10)) + 2 if action.command == 115 else 1 for action in actions)))


def compile_plan(plan: MissionPlan):
    from types import SimpleNamespace
    settings = plan.settings
    home = SimpleNamespace(lat=settings.home.lat, lng=settings.home.lng, alt=settings.takeoffAlt)
    result = []
    if settings.takeoff:
        result.append(item(22, home))
    result.extend([item(16, home, delay=3), item(178, speed=settings.speed)])
    for point in plan.waypoints:
        result.append(item(16, point, delay=0 if point.actions else point.delay))
        group = []

        def flush():
            if group:
                result.append(item(16, point, delay=hold_seconds(group)))
                for action in group:
                    result.append(item(action.command, getattr(action, 'target', point), **action.params.model_dump()))
                group.clear()

        for action in point.actions:
            if action.command == 19:
                flush()
                result.append(item(19, point, **action.params.model_dump()))
            else:
                group.append(action)
        flush()
        if point.actions and point.delay:
            result.append(item(19, point, duration=point.delay))
    if settings.ending == 'rtl':
        result.append(item(20))
    elif settings.ending == 'land':
        result.append(item(21, settings.landing))
    return result


def with_ardupilot_home(items, home):
    return [MissionItem(command=16, frame=0, x=round(home['lat'] * 1e7), y=round(home['lng'] * 1e7), z=home['alt']), *items]
