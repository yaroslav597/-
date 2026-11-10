from .fakes import connect, message, wait_for


def ready(client, peer):
    connect(peer, client)
    peer.incoming.put(message('EXTENDED_SYS_STATE', landed_state=1))
    peer.incoming.put(message('GPS_RAW_INT', satellites_visible=10, fix_type=3))
    peer.incoming.put(message('GLOBAL_POSITION_INT', lat=557550000, lon=375900000, relative_alt=0, vx=0, vy=0, hdg=0))
    wait_for(lambda: client.get('/api/status').json()['landedState'] == 1)
    # Queue a final marker after the position, so readiness does not race the worker.
    peer.incoming.put(message('STATUSTEXT', text='Ready'))
    wait_for(lambda: client.get('/api/status').json()['lastText'] == 'Ready')


def job(client, operation_id):
    return client.get('/api/operations/' + operation_id).json()


def test_arm_requires_ack_and_observed_armed_state(setup):
    client, peer, _ = setup
    ready(client, peer)
    response = client.post('/api/flight', json={'action': 'arm'})
    assert response.status_code == 202
    operation_id = response.json()['operationId']
    wait_for(lambda: len(peer.commands) == 1)
    assert peer.commands[0] == (176, [1, 4, 0, 0, 0, 0, 0])
    peer.incoming.put(message('COMMAND_ACK', command=176, result=0))
    peer.incoming.put(message('HEARTBEAT', autopilot=3, base_mode=0, mode='GUIDED'))
    wait_for(lambda: len(peer.commands) == 2)
    assert peer.commands[1] == (400, [1, 0, 0, 0, 0, 0, 0])
    peer.incoming.put(message('COMMAND_ACK', command=400, result=0))
    assert job(client, operation_id)['status'] == 'running'
    peer.incoming.put(message('HEARTBEAT', autopilot=3, base_mode=128, mode='GUIDED'))
    wait_for(lambda: job(client, operation_id)['status'] == 'succeeded')
    assert job(client, operation_id)['result']['confirmed']


def test_mode_denied_never_sends_arm(setup):
    client, peer, _ = setup
    ready(client, peer)
    operation_id = client.post('/api/flight', json={'action': 'arm'}).json()['operationId']
    wait_for(lambda: peer.commands)
    peer.incoming.put(message('COMMAND_ACK', command=176, result=2))
    wait_for(lambda: job(client, operation_id)['status'] == 'failed')
    assert len(peer.commands) == 1


def test_start_rejects_unverified_mission_and_airborne_restart(setup, plan):
    client, peer, app = setup
    ready(client, peer)
    mission_id = client.post('/api/missions', json=plan).json()['missionId']
    request = {'action': 'start', 'missionId': mission_id}
    assert client.post('/api/flight', json=request).status_code == 409
    peer.incoming.put(message('HEARTBEAT', autopilot=3, base_mode=128, mode='GUIDED'))
    wait_for(lambda: client.get('/api/status').json()['armed'])
    assert client.post('/api/flight', json=request).status_code == 409
    app.state.bridge.set_state(verifiedMissionId=mission_id, landedState=2)
    assert client.post('/api/flight', json=request).status_code == 409
    assert client.post('/api/flight', json={'action': 'disarm'}).status_code == 409
    assert peer.commands == []


def test_start_changes_auto_then_sends_mission_start(setup, plan):
    client, peer, app = setup
    ready(client, peer)
    mission_id = client.post('/api/missions', json=plan).json()['missionId']
    app.state.bridge.set_state(verifiedMissionId=mission_id, armed=True)
    operation_id = client.post('/api/flight', json={'action': 'start', 'missionId': mission_id}).json()['operationId']
    wait_for(lambda: peer.commands)
    peer.incoming.put(message('COMMAND_ACK', command=176, result=0))
    peer.incoming.put(message('HEARTBEAT', autopilot=3, base_mode=128, mode='AUTO'))
    wait_for(lambda: len(peer.commands) == 2)
    assert peer.commands[-1] == (300, [0]*7)
    peer.incoming.put(message('COMMAND_ACK', command=300, result=0))
    wait_for(lambda: job(client, operation_id)['status'] == 'succeeded')


def test_timeout_never_retries_flight_command(setup):
    client, peer, app = setup
    ready(client, peer)
    operation_id = client.post('/api/flight', json={'action': 'arm'}).json()['operationId']
    wait_for(lambda: peer.commands)
    with app.state.bridge.lock:
        app.state.bridge.active['sent_at'] -= 16
    wait_for(lambda: job(client, operation_id)['status'] == 'failed')
    assert len(peer.commands) == 1


def test_progress_tracks_only_target_and_deduplicates_reached(setup):
    client, peer, _ = setup
    ready(client, peer)
    peer.incoming.put(message('MISSION_CURRENT', system=2, seq=999))
    peer.incoming.put(message('MISSION_CURRENT', seq=4, mission_state=3))
    peer.incoming.put(message('MISSION_ITEM_REACHED', seq=3))
    peer.incoming.put(message('MISSION_ITEM_REACHED', seq=3))
    wait_for(lambda: client.get('/api/status').json()['reached'] == [3])
    status = client.get('/api/status').json()
    assert status['currentSeq'] == 4
    assert status['missionState'] == 3


def test_no_arbitrary_action_or_forced_arming(setup):
    client, _, _ = setup
    assert client.post('/api/flight', json={'action': 'force_arm'}).status_code == 422
    assert client.post('/api/flight', json={'action': 'arm', 'force': True}).status_code == 422
    assert client.post('/api/flight', json={'action': 'arm'}).status_code == 503


def test_completed_mission_cannot_restart_without_upload(setup, plan):
    client, peer, app = setup
    ready(client, peer)
    mission_id = client.post('/api/missions', json=plan).json()['missionId']
    app.state.bridge.set_state(verifiedMissionId=mission_id, armed=True, missionState=5)
    assert client.post('/api/flight', json={'action': 'start', 'missionId': mission_id}).status_code == 409
    assert peer.commands == []


def test_new_upload_can_start_despite_previous_complete_status(setup, plan):
    client, peer, app = setup
    ready(client, peer)
    mission_id = client.post('/api/missions', json=plan).json()['missionId']
    app.state.bridge.set_state(verifiedMissionId=mission_id, uploadedMissionId=mission_id,
                               armed=True, missionState=5, currentSeq=0, startConsumed=False)
    assert client.post('/api/flight', json={'action': 'start', 'missionId': mission_id}).status_code == 202
    wait_for(lambda: peer.commands)
    peer.incoming.put(message('COMMAND_ACK', command=176, result=2))
    wait_for(lambda: not client.get('/api/status').json()['busy'])


def test_rtl_and_land_wait_for_observed_modes(setup):
    client, peer, app = setup
    ready(client, peer)
    app.state.bridge.set_state(armed=True, landedState=2)
    for action, command, mode in [('rtl', 20, 'RTL'), ('land', 21, 'LAND')]:
        operation_id = client.post('/api/flight', json={'action': action}).json()['operationId']
        wait_for(lambda: peer.commands and peer.commands[-1][0] == command)
        peer.incoming.put(message('COMMAND_ACK', command=command, result=0))
        assert job(client, operation_id)['status'] == 'running'
        peer.incoming.put(message('HEARTBEAT', autopilot=3, base_mode=128, mode=mode))
        wait_for(lambda: job(client, operation_id)['status'] == 'succeeded')
