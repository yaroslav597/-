"""Real MAVLink 2 packets over loopback UDP; this peer is not ArduPilot SITL."""
import socket
from dataclasses import replace

from fastapi.testclient import TestClient
from pymavlink import mavutil

from backend.app.config import Config
from backend.app.main import create_app
from .fakes import wait_for


def test_real_udp_mission_upload_and_telemetry(tmp_path, plan):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    config = replace(Config(), endpoint=f'udpin:127.0.0.1:{port}', database=tmp_path / 'udp.sqlite3')
    app = create_app(config)
    with TestClient(app) as client:
        wait_for(lambda: app.state.bridge.transport is not None)
        # Windows pymavlink udpout binds the destination port locally. Use a
        # separately bound peer socket so replies cannot loop back to the bridge.
        peer = mavutil.mavlink_connection('udpin:127.0.0.1:0', source_system=1, source_component=1)
        if hasattr(socket, 'SIO_UDP_CONNRESET'):
            peer.port.ioctl(socket.SIO_UDP_CONNRESET, False)
        peer.clients.add(('127.0.0.1', port))
        try:
            # Repeated heartbeat also makes this robust to the UDP listener startup race.
            def ready():
                peer.mav.heartbeat_send(2, 3, 0, 0, 3)
                peer.mav.home_position_send(557550000, 375900000, 150000, 0, 0, 0, [1, 0, 0, 0], 0, 0, 0)
                return client.get('/api/status').json()['home']
            wait_for(ready)
            peer.mav.global_position_int_send(1000, 557550000, 375900000, 230000, 80000, 300, 400, 0, 9000)
            wait_for(lambda: app.state.bridge.telemetry_snapshot().get('speed') == 5)
            mission_id = client.post('/api/missions', json=plan).json()['missionId']
            operation_id = client.post('/api/uploads', json={'missionId': mission_id}).json()['operationId']
            count = peer.recv_match(type='MISSION_COUNT', blocking=True, timeout=3)
            assert count is not None, client.get('/api/operations/' + operation_id).json()
            assert count.target_system == 1
            assert count.count == 6
            for seq in range(count.count):
                peer.mav.mission_request_int_send(255, 190, seq, 0)
                packet = peer.recv_match(type='MISSION_ITEM_INT', blocking=True, timeout=2)
                assert packet is not None
                assert packet.seq == seq
                assert packet.target_system == 1
                assert packet.get_srcSystem() == 255
                if seq == 0:
                    assert packet.frame == 0
                    assert packet.z == 150
                if seq == 1:
                    assert packet.command == 22
                    assert packet.frame == 6
                    assert packet.x == 557550000
            peer.mav.mission_ack_send(255, 190, 0, 0)
            wait_for(lambda: client.get('/api/operations/' + operation_id).json()['status'] == 'succeeded')
        finally:
            peer.close()
