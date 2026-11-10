from dataclasses import replace

import pytest

from backend.app.compiler import MissionItem, compile_plan
from backend.app.comparison import compare_mission
from backend.app.schemas import MissionPlan
from .fakes import connect, message, wait_for


def mission_items(plan):
    return [MissionItem(16, frame=0, x=557550000, y=375900000, z=150), *compile_plan(MissionPlan.model_validate(plan))]


def begin_check(client, peer, plan):
    connect(peer, client)
    saved = client.post('/api/missions', json=plan).json()
    response = client.post('/api/mission-checks', json={'missionId': saved['missionId']})
    assert response.status_code == 202
    wait_for(lambda: peer.list_requests)
    return response.json()['operationId']


def finish_job(client, operation_id):
    return wait_for(lambda: (job if (job := client.get('/api/operations/' + operation_id).json())['status'] in ('succeeded', 'failed') else None))


def test_readback_matches_and_ends_with_ack(setup, plan):
    client, peer, _ = setup
    operation_id = begin_check(client, peer, plan)
    items = mission_items(plan)
    peer.incoming.put(message('MISSION_COUNT', count=len(items)))
    for seq, item in enumerate(items):
        wait_for(lambda: peer.item_requests and peer.item_requests[-1] == seq)
        if seq == 1:
            peer.incoming.put(message('MISSION_ITEM_INT', seq=0, **items[0].as_dict()))
        peer.incoming.put(message('MISSION_ITEM_INT', seq=seq, **item.as_dict()))
    result = finish_job(client, operation_id)
    assert result['status'] == 'succeeded'
    assert result['result']['matches']
    assert result['result']['count'] == len(items)
    assert peer.acks == [0]


def test_download_diff_is_successful_read_not_matching_mission(setup, plan):
    client, peer, _ = setup
    operation_id = begin_check(client, peer, plan)
    items = mission_items(plan)
    items[-1] = MissionItem(21, x=1, y=2, z=80)
    peer.incoming.put(message('MISSION_COUNT', count=len(items)))
    for seq, item in enumerate(items):
        wait_for(lambda: peer.item_requests and peer.item_requests[-1] == seq)
        peer.incoming.put(message('MISSION_ITEM_INT', seq=seq, **item.as_dict()))
    result = finish_job(client, operation_id)
    assert result['status'] == 'succeeded'
    assert not result['result']['matches']
    assert result['result']['differences'][0]['field'] == 'command'


@pytest.mark.parametrize('count', [0, 4001])
def test_empty_or_oversized_mission(setup, plan, count):
    client, peer, _ = setup
    operation_id = begin_check(client, peer, plan)
    peer.incoming.put(message('MISSION_COUNT', count=count))
    result = finish_job(client, operation_id)
    assert result['status'] == ('succeeded' if count == 0 else 'failed')
    if count == 0:
        assert not result['result']['matches']


def test_download_timeout_retries_list_and_releases_worker(setup, plan):
    client, peer, _ = setup
    operation_id = begin_check(client, peer, plan)
    result = finish_job(client, operation_id)
    assert result['status'] == 'failed'
    assert peer.list_requests == 3
    assert not client.get('/api/status').json()['busy']


def test_comparison_float32_aliases_unused_params_and_small_coordinate_change(plan):
    expected = compile_plan(MissionPlan.model_validate(plan))
    downloaded = mission_items(plan)
    downloaded[1] = replace(downloaded[1], frame=6, x=0, y=0, param4=float('nan'))
    downloaded[2] = replace(downloaded[2], frame=6, x=downloaded[2].x+1, z=80.00001)
    downloaded[3] = replace(downloaded[3], param1=0, param3=0)
    result = compare_mission(expected, downloaded)
    assert result['matches']
    assert result['items'][1]['param4'] is None
    downloaded[4] = replace(downloaded[4], x=downloaded[4].x+100)
    result = compare_mission(expected, downloaded)
    assert not result['matches']
    assert result['differences'][0]['field'] == 'x'
