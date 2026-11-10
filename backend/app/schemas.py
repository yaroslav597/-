from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Altitude = Annotated[float, Field(ge=5, le=500)]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class Location(Model):
    lat: Latitude
    lng: Longitude


class Position(Location):
    alt: Altitude


class Roi(Location):
    alt: Annotated[float, Field(ge=0, le=500)]


class EmptyParams(Model):
    pass


class HoldParams(Model):
    duration: Annotated[int, Field(ge=0, le=65535)] = 10


class SpeedParams(Model):
    speed: Annotated[float, Field(ge=1, le=50)] = 12


class YawParams(Model):
    yaw: Annotated[float, Field(ge=0, le=360)] = 0
    yawRate: Annotated[float, Field(ge=0, le=360)] = 30
    direction: Literal[-1, 1] = 1
    relative: Literal[0, 1] = 0


class CameraParams(Model):
    distance: Annotated[float, Field(ge=0, le=10000)] = 25
    immediate: Literal[0, 1] = 0


class HoldAction(Model):
    id: Identifier
    command: Literal[19]
    params: HoldParams


class SpeedAction(Model):
    id: Identifier
    command: Literal[178]
    params: SpeedParams


class YawAction(Model):
    id: Identifier
    command: Literal[115]
    params: YawParams


class RoiAction(Model):
    id: Identifier
    command: Literal[201]
    params: EmptyParams
    target: Roi


class CameraAction(Model):
    id: Identifier
    command: Literal[206]
    params: CameraParams


class PhotoAction(Model):
    id: Identifier
    command: Literal[203]
    params: EmptyParams


Action = Annotated[HoldAction | SpeedAction | YawAction | RoiAction | CameraAction | PhotoAction, Field(discriminator='command')]


class Waypoint(Position):
    id: Identifier
    delay: Annotated[int, Field(ge=0, le=65535)] = 0
    actions: list[Action] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def unique_actions(self):
        if len({action.id for action in self.actions}) != len(self.actions):
            raise ValueError('Повторяющиеся идентификаторы действий')
        return self


class Settings(Model):
    speed: Annotated[float, Field(ge=1, le=50)] = 12
    takeoff: bool = True
    takeoffAlt: Altitude = 80
    ending: Literal['rtl', 'land', 'hold'] = 'rtl'
    home: Location
    landing: Position


class MissionPlan(Model):
    version: Literal[3] = 3
    frame: Literal['GLOBAL_RELATIVE_ALT'] = 'GLOBAL_RELATIVE_ALT'
    settings: Settings
    waypoints: list[Waypoint] = Field(min_length=1, max_length=100)
    # Compatibility with browser JSON exports. Never trusted or transmitted.
    items: list[dict[str, JsonValue]] | None = Field(default=None, max_length=4000, exclude=True)

    @model_validator(mode='after')
    def unique_points(self):
        if len({point.id for point in self.waypoints}) != len(self.waypoints):
            raise ValueError('Повторяющиеся идентификаторы точек')
        return self


class UploadRequest(Model):
    missionId: Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')]


class FlightRequest(Model):
    action: Literal['arm', 'disarm', 'start', 'rtl', 'land']
    missionId: Annotated[str, Field(pattern=r'^[a-f0-9]{32}$')] | None = None


class CommandRequest(Model):
    command: Literal[20, 178, 115, 203]
    params: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_parameters(self):
        schema = {20: EmptyParams, 178: SpeedParams, 115: YawParams, 203: EmptyParams}[self.command]
        self.params = schema.model_validate(self.params).model_dump()
        return self
