import os

os.environ.setdefault('MAVLINK20', '1')

from pymavlink import mavutil


class MavlinkTransport:
    def __init__(self, config):
        self.config = config
        self.link = mavutil.mavlink_connection(config.endpoint, baud=config.baud, source_system=config.source_system,
                                              source_component=config.source_component, dialect='ardupilotmega', retries=1)

    def receive(self, timeout=0.1):
        return self.link.recv_match(blocking=True, timeout=timeout)

    def heartbeat(self):
        self.link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)

    def request_streams(self):
        self.link.mav.request_data_stream_send(self.config.system_id, self.config.component_id, mavutil.mavlink.MAV_DATA_STREAM_ALL, 2, 1)
        self.link.mav.command_long_send(self.config.system_id, self.config.component_id, 512, 0, 242, 0, 0, 0, 0, 0, 0)
        self.link.mav.command_long_send(self.config.system_id, self.config.component_id, 512, 0, 148, 0, 0, 0, 0, 0, 0)
        self.link.mav.command_long_send(self.config.system_id, self.config.component_id, 512, 0, 245, 0, 0, 0, 0, 0, 0)

    def mission_count(self, count):
        self.link.mav.mission_count_send(self.config.system_id, self.config.component_id, count, 0)

    def mission_request_list(self):
        self.link.mav.mission_request_list_send(self.config.system_id, self.config.component_id, 0)

    def mission_request(self, seq):
        self.link.mav.mission_request_int_send(self.config.system_id, self.config.component_id, seq, 0)

    def mission_ack(self, result=0):
        self.link.mav.mission_ack_send(self.config.system_id, self.config.component_id, result, 0)

    def mission_item(self, seq, item):
        frame = 6 if item.command in (16, 19, 21, 22, 201) and item.frame == 3 else item.frame
        self.link.mav.mission_item_int_send(self.config.system_id, self.config.component_id, seq, frame, item.command,
                                            0, 1, item.param1, item.param2, item.param3, item.param4, item.x, item.y, item.z, 0)

    def command(self, command, params, confirmation=0):
        self.link.mav.command_long_send(self.config.system_id, self.config.component_id, command, confirmation, *params)

    def mode(self, message):
        return mavutil.mode_string_v10(message)

    def close(self):
        self.link.close()
