"""Compare fields used by Copter, tolerating float32 storage and frame aliases."""
import math

from .compiler import MissionItem

LOCATION_COMMANDS = {16, 19, 21, 22, 201}
FIELDS = {
    16: ('param1', 'x', 'y', 'z'),
    19: ('param1', 'x', 'y', 'z'),
    20: (),
    21: ('x', 'y', 'z'),
    22: ('z',),  # Copter takes off vertically; lat/lon and yaw are not used.
    178: ('param2',),
    115: ('param1', 'param2', 'param3', 'param4'),
    201: ('param1', 'x', 'y', 'z'),
    203: ('x',),
    206: ('param1', 'param3'),
}


def canonical_frame(frame):
    return {5: 0, 6: 3, 11: 10}.get(frame, frame)


def clean(value):
    return None if isinstance(value, float) and not math.isfinite(value) else value


def from_message(message):
    x, y = message.x, message.y
    if message.get_type() == 'MISSION_ITEM' and message.command in LOCATION_COMMANDS:
        x, y = math.floor(x * 1e7 + 0.5), math.floor(y * 1e7 + 0.5)
    return MissionItem(command=message.command, frame=message.frame, param1=message.param1, param2=message.param2,
                       param3=message.param3, param4=message.param4, x=x, y=y, z=message.z)


def compare_mission(expected, downloaded):
    differences = []

    def difference(seq, field, planned, actual):
        differences.append(dict(seq=seq, field=field, expected=clean(planned), actual=clean(actual)))

    if len(downloaded) != len(expected) + 1:
        difference(None, 'count', len(expected) + 1, len(downloaded))
    # ArduPilot owns seq 0 (actual Home). Compare flight commands beginning at 1.
    for seq, (planned, actual) in enumerate(zip(expected, downloaded[1:]), 1):
        if planned.command != actual.command:
            difference(seq, 'command', planned.command, actual.command)
            continue
        if planned.command in LOCATION_COMMANDS and canonical_frame(planned.frame) != canonical_frame(actual.frame):
            difference(seq, 'frame', planned.frame, actual.frame)
        for field in FIELDS.get(planned.command, ()):
            a, b = getattr(planned, field), getattr(actual, field)
            tolerance = 2 if field in ('x', 'y') and planned.command in LOCATION_COMMANDS else 0.001
            relative_tolerance = 0 if field in ('x', 'y') else 1e-6
            if clean(b) is None or not math.isclose(a, b, rel_tol=relative_tolerance, abs_tol=tolerance):
                difference(seq, field, a, b)
    return dict(matches=not differences, differences=differences, count=len(downloaded),
                items=[dict(seq=seq, **{key: clean(value) for key, value in item.as_dict().items()}) for seq, item in enumerate(downloaded)])
