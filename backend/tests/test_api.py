import copy

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.compiler import compile_plan
from backend.app.schemas import MissionPlan
from backend.app.store import Store, now_ms
from .fakes import connect, message, wait_for


@pytest.mark.parametrize('origin', ['http://127.0.0.1:5174', 'http://localhost:5174'])
def test_vite_fallback_port_http_and_websocket(setup, origin):
    client, _, _ = setup
    response = client.get('/api/health', headers={'Origin': origin})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == origin
    with client.websocket_connect('/ws/telemetry', headers={'Origin': origin}) as socket:
        assert socket.receive_json()['type'] == 'status'
        assert socket.receive_json()['type'] == 'telemetry'


def test_untrusted_origin_rejected(setup):
    client, _, _ = setup
    origin = 'http://example.com:5174'
    response = client.get('/api/health', headers={'Origin': origin})
    assert 'access-control-allow-origin' not in response.headers
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect('/ws/telemetry', headers={'Origin': origin}):
            pass
    assert error.value.code == 1008


def test_save_recompile_and_fetch_persistent_mission(setup, plan):
    client, peer, app = setup
    plan['items'] = [dict(command=400, param1=1)]
    response = client.post('/api/missions', json=plan)
    assert response.status_code == 201
    saved = response.json()
    assert [value['command'] for value in saved['items']] == [22, 16, 178, 16, 20]
    assert 'items' not in saved['plan']
    assert client.get('/api/missions/' + saved['missionId']).json() == saved
    assert Store(app.state.store.path).mission(saved['missionId']) == saved
    assert client.get('/api/missions').json()[0]['waypoints'] == 1
    assert peer.sent == []


@pytest.mark.parametrize('change', [
    lambda p: p['waypoints'][0].update(lat=91),
    lambda p: p['waypoints'].append(copy.deepcopy(p['waypoints'][0])),
    lambda p: p.update(version=4),
    lambda p: p['settings'].update(speed=0),
    lambda p: p['waypoints'][0].update(actions=[dict(id='x', command=400, params={})]),
    lambda p: p['waypoints'][0].update(actions=[dict(id='x', command=178, params={'speed': '12'})]),
    lambda p: p['waypoints'][0].update(actions=[dict(id='x', command=201, params={}, target={'lat': 91, 'lng': 0, 'alt': 0})]),
    lambda p: p['waypoints'][0].update(delay=0.5),
])
def test_validation(setup, plan, change):
    client, _, _ = setup
    change(plan)
    assert client.post('/api/missions', json=plan).status_code == 422


def save(client, plan):
    return client.post('/api/missions', json=plan).json()['missionId']


def test_disconnected_upload_and_arbitrary_commands_rejected(setup, plan):
    client, _, _ = setup
    mission_id = save(client, plan)
    assert client.post('/api/uploads', json={'missionId': mission_id}).status_code == 503
    assert client.post('/api/commands', json={'command': 400, 'params': {}}).status_code == 422
    assert client.post('/api/uploads', json={'missionId': '0' * 32}).status_code == 404


def test_upload_only_succeeds_after_all_requests_and_accepted_ack(setup, plan):
    client, peer, _ = setup
    connect(peer, client)
    response = client.post('/api/uploads', json={'missionId': save(client, plan)})
    assert response.status_code == 202
    operation_id = response.json()['operationId']
    wait_for(lambda: peer.counts)
    count = peer.counts[0]
    assert count == 6  # Home 0 + five compiled items.
    assert client.get('/api/operations/' + operation_id).json()['status'] == 'running'
    assert client.post('/api/commands', json={'command': 20}).status_code == 409
    # Unrelated sender, mission type and recipient must not advance the upload.
    for values in ({'system': 2}, {'mission_type': 1}, {'target_system': 99}):
        peer.incoming.put(message('MISSION_REQUEST_INT', seq=0, **values))
    for seq in range(count):
        peer.incoming.put(message('MISSION_REQUEST_INT', seq=seq))
        wait_for(lambda: any(value[0] == seq for value in peer.sent))
    assert peer.sent[0][1].frame == 0
    assert peer.sent[0][1].z == 150
    assert peer.sent[1][1].command == 22
    assert client.get('/api/operations/' + operation_id).json()['status'] == 'running'
    peer.incoming.put(message('MISSION_ACK', type=0))
    result = wait_for(lambda: (job if (job := client.get('/api/operations/' + operation_id).json())['status'] == 'succeeded' else None))
    assert result['result']['count'] == count


@pytest.mark.parametrize('ack', [0, 4])
def test_premature_or_rejected_ack_is_failure(setup, plan, ack):
    client, peer, _ = setup
    connect(peer, client)
    operation_id = client.post('/api/uploads', json={'missionId': save(client, plan)}).json()['operationId']
    wait_for(lambda: peer.counts)
    peer.incoming.put(message('MISSION_ACK', type=ack))
    job = wait_for(lambda: (value if (value := client.get('/api/operations/' + operation_id).json())['status'] == 'failed' else None))
    assert job['error']


def test_timeout_retries_and_no_false_success(setup, plan):
    client, peer, _ = setup
    connect(peer, client)
    operation_id = client.post('/api/uploads', json={'missionId': save(client, plan)}).json()['operationId']
    job = wait_for(lambda: (value if (value := client.get('/api/operations/' + operation_id).json())['status'] == 'failed' else None))
    assert 'timeout' in job['error']
    assert len(peer.counts) == 3
    assert not client.get('/api/status').json()['busy']


def test_duplicate_request_and_lost_item_response_are_retried(setup, plan):
    client, peer, _ = setup
    connect(peer, client)
    operation_id = client.post('/api/uploads', json={'missionId': save(client, plan)}).json()['operationId']
    wait_for(lambda: peer.counts)
    peer.incoming.put(message('MISSION_REQUEST', seq=0))
    wait_for(lambda: len(peer.sent) >= 1)
    peer.incoming.put(message('MISSION_REQUEST_INT', seq=0))
    wait_for(lambda: len(peer.sent) >= 3)
    job = wait_for(lambda: (value if (value := client.get('/api/operations/' + operation_id).json())['status'] == 'failed' else None))
    assert job['progress'] == 1
    assert all(seq == 0 for seq, _ in peer.sent)


def test_heartbeat_loss_clears_connection_and_home(setup):
    client, peer, _ = setup
    connect(peer, client)
    wait_for(lambda: not client.get('/api/status').json()['connected'], timeout=4)
    status = client.get('/api/status').json()
    assert status['home'] is None
    assert status['error'] == 'HEARTBEAT timeout'


def test_out_of_range_sequence_rejects_operation(setup, plan):
    client, peer, _ = setup
    connect(peer, client)
    operation_id = client.post('/api/uploads', json={'missionId': save(client, plan)}).json()['operationId']
    wait_for(lambda: peer.counts)
    peer.incoming.put(message('MISSION_REQUEST_INT', seq=9999))
    job = wait_for(lambda: (value if (value := client.get('/api/operations/' + operation_id).json())['status'] == 'failed' else None))
    assert 'недопустимый' in job['error']


def test_home_mismatch_and_armed_state_reject_upload(setup, plan):
    client, peer, _ = setup
    connect(peer, client)
    plan['settings']['home']['lat'] = 56
    assert client.post('/api/uploads', json={'missionId': save(client, plan)}).status_code == 409
    plan['settings']['home']['lat'] = 55.755
    peer.incoming.put(message('HEARTBEAT', autopilot=3, base_mode=128))
    wait_for(lambda: client.get('/api/status').json()['armed'])
    assert client.post('/api/uploads', json={'missionId': save(client, plan)}).status_code == 409
    assert peer.counts == []


def test_command_ack_is_matched_and_does_not_retry_photo(setup):
    client, peer, _ = setup
    connect(peer, client)
    operation_id = client.post('/api/commands', json={'command': 203, 'params': {}}).json()['operationId']
    wait_for(lambda: peer.commands)
    assert peer.commands[0][1][4] == 1
    peer.incoming.put(message('COMMAND_ACK', command=512, result=0))
    assert client.get('/api/operations/' + operation_id).json()['status'] == 'running'
    peer.incoming.put(message('COMMAND_ACK', command=203, result=0))
    wait_for(lambda: client.get('/api/operations/' + operation_id).json()['status'] == 'succeeded')
    assert len(peer.commands) == 1


def test_websocket_status_telemetry_units_and_unknown_values(setup):
    client, peer, _ = setup
    connect(peer, client)
    with client.websocket_connect('/ws/telemetry') as socket:
        assert socket.receive_json()['type'] == 'status'
        peer.incoming.put(message('GLOBAL_POSITION_INT', lat=557550000, lon=375900000, relative_alt=80000, vx=300, vy=400, hdg=12345))
        peer.incoming.put(message('SYS_STATUS', battery_remaining=-1))
        peer.incoming.put(message('GPS_RAW_INT', satellites_visible=255, fix_type=3))
        for _ in range(10):
            event = socket.receive_json()
            if event['type'] == 'telemetry' and event['payload'].get('altitude') == 80:
                payload = event['payload']
                break
        else:
            pytest.fail('No telemetry event')
        assert payload['lat'] == 55.755
        assert payload['speed'] == 5
        assert payload['heading'] == 123.45
        assert payload['battery'] is None
        assert payload['satellites'] is None


def test_worker_shutdown_and_restart_marks_ambiguous_jobs_failed(tmp_path):
    store = Store(tmp_path / 'restart.sqlite3')
    store.put_operation(dict(operationId='a', status='running', updatedAt=now_ms()))
    restored = Store(store.path).operation('a')
    assert restored['status'] == 'failed'
    assert 'неизвестен' in restored['error']


def test_all_action_groups_compile_with_roi_target_and_preserved_order(plan):
    plan['waypoints'][0]['actions'] = [
        dict(id='1', command=115, params=dict(yaw=90, yawRate=30, direction=1, relative=0)),
        dict(id='2', command=203, params={}),
        dict(id='3', command=19, params=dict(duration=5)),
        dict(id='4', command=201, params={}, target=dict(lat=55.8, lng=37.7, alt=30)),
        dict(id='5', command=206, params=dict(distance=20, immediate=1)),
    ]
    items = compile_plan(MissionPlan.model_validate(plan))
    assert [value.command for value in items] == [22, 16, 178, 16, 16, 115, 203, 19, 16, 201, 206, 20]
    assert items[4].param1 == 15
    assert items[9].x == 558000000
    assert items[9].y == 377000000
    assert items[9].z == 30
