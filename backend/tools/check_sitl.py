"""Save/upload/read/compare through FastAPI against a running local SITL.

Does not send ARM, MISSION_START or change flight mode. Replaces the simulated
vehicle mission. Requires a running local ArduPilot SITL TCP endpoint.
"""
import argparse
import json
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Config
from backend.app.main import create_app


def wait_until(callback, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = callback()
        if value:
            return value
        time.sleep(0.15)
    raise TimeoutError('Timed out waiting for SITL/backend')


def post(client, path, data):
    response = client.post(path, json=data)
    response.raise_for_status()
    return response.json()


def operation(client, job):
    def completed():
        value = client.get('/api/operations/' + job['operationId']).json()
        return value if value['status'] in ('succeeded', 'failed') else None
    return wait_until(completed, timeout=125)


def sample_plan(home, ending):
    lat, lng = home['lat'], home['lng']
    return dict(version=3, settings=dict(speed=12, takeoff=True, takeoffAlt=80, ending=ending,
                home=dict(lat=lat, lng=lng), landing=dict(lat=lat+0.0003, lng=lng+0.0001, alt=60)), waypoints=[
        dict(id='one', lat=lat+0.0001, lng=lng, alt=80, delay=5, actions=[
            dict(id='yaw', command=115, params=dict(yaw=90, yawRate=30, direction=1, relative=0)),
            dict(id='photo', command=203, params={}),
        ]),
        dict(id='two', lat=lat+0.0002, lng=lng+0.0001, alt=70, delay=0, actions=[
            dict(id='speed', command=178, params=dict(speed=8)),
            dict(id='hover', command=19, params=dict(duration=3)),
            dict(id='roi', command=201, params={}, target=dict(lat=lat, lng=lng+0.0002, alt=10)),
            dict(id='camera', command=206, params=dict(distance=20, immediate=1)),
        ]),
        dict(id='three', lat=lat+0.0003, lng=lng+0.0001, alt=60, delay=2, actions=[]),
    ])


def run(endpoint):
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(), endpoint=endpoint, success=False, cases=[])
    with tempfile.TemporaryDirectory(prefix='aero-sitl-') as temporary:
        config = replace(Config(), endpoint=endpoint, database=Path(temporary) / 'test.sqlite3')
        with TestClient(create_app(config)) as client:
            status = wait_until(lambda: (value if (value := client.get('/api/status').json())['home'] and value['connected'] else None))
            if status['armed']:
                raise RuntimeError('Expected disarmed local SITL')
            wait_until(lambda: client.get('/api/status').json().get('firmware'), timeout=20)
            report['vehicle'] = client.get('/api/status').json()
            for ending in ('rtl', 'land'):
                saved = post(client, '/api/missions', sample_plan(status['home'], ending))
                upload = operation(client, post(client, '/api/uploads', {'missionId': saved['missionId']}))
                case = dict(ending=ending, expectedCount=len(saved['items'])+1, upload=upload)
                report['cases'].append(case)
                if upload['status'] != 'succeeded':
                    return report
                verification = operation(client, post(client, '/api/mission-checks', {'missionId': saved['missionId']}))
                case['verification'] = verification
                if verification['status'] != 'succeeded' or not verification['result']['matches']:
                    return report
            report['success'] = True
            report['armedAtEnd'] = client.get('/api/status').json()['armed']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default='tcp:127.0.0.1:5760', choices=['tcp:127.0.0.1:5760'])
    parser.add_argument('--output', type=Path, default=Path('.runtime/sitl-check.json'))
    args = parser.parse_args()
    report = run(args.endpoint)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(success=report['success'], firmware=report['vehicle'].get('firmware'),
                         cases=[dict(ending=case['ending'], upload=case['upload']['status'],
                                     matches=case.get('verification', {}).get('result', {}).get('matches'),
                                     count=case['expectedCount']) for case in report['cases']],
                         output=str(args.output)), ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['success'] else 1)


if __name__ == '__main__':
    main()
