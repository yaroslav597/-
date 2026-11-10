"""Fly a small mission on the dedicated loopback SITL instance (TCP 5770)."""
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import time

from fastapi.testclient import TestClient

from backend.app.config import Config
from backend.app.main import create_app
from backend.tools.check_sitl import operation, post, wait_until


def run():
    report = {'success': False, 'endpoint': 'tcp:127.0.0.1:5770', 'operations': []}
    with tempfile.TemporaryDirectory(prefix='aero-flight-') as temporary:
        config = replace(Config(), endpoint=report['endpoint'], database=Path(temporary) / 'flight.sqlite3')
        with TestClient(create_app(config)) as client:
            def status():
                return client.get('/api/status').json()

            wait_until(lambda: status()['connected'] and status()['home'] and status()['landedState'] == 1)
            if status()['armed']:
                raise RuntimeError('Dedicated test SITL must initially be disarmed')
            home = status()['home']
            plan = dict(version=3, settings=dict(speed=3, takeoff=True, takeoffAlt=10, ending='rtl',
                        home=dict(lat=home['lat'], lng=home['lng']),
                        landing=dict(lat=home['lat'], lng=home['lng'], alt=5)), waypoints=[
                dict(id='near-1', lat=home['lat']+0.00010, lng=home['lng'], alt=10, delay=1, actions=[]),
                dict(id='near-2', lat=home['lat']+0.00010, lng=home['lng']+0.00010, alt=10, delay=1, actions=[]),
            ])
            saved = post(client, '/api/missions', plan)

            def execute(path, data):
                result = operation(client, post(client, path, data))
                report['operations'].append(result)
                if result['status'] != 'succeeded':
                    raise RuntimeError(f'{result.get("error")}; autopilot: {status().get("lastText")}')
                return result

            execute('/api/uploads', {'missionId': saved['missionId']})
            verification = execute('/api/mission-checks', {'missionId': saved['missionId']})
            if not verification['result']['matches']:
                raise RuntimeError('Uploaded mission differs')
            # Let the estimator finish initializing; do not disable any arming checks.
            time.sleep(12)
            execute('/api/flight', {'action': 'arm'})
            execute('/api/flight', {'action': 'start', 'missionId': saved['missionId']})
            max_altitude = 0
            airborne = False
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                current = status()
                telemetry = client.app.state.bridge.telemetry_snapshot()
                max_altitude = max(max_altitude, telemetry.get('altitude') or 0)
                airborne |= current['landedState'] == 2
                if airborne and current['landedState'] == 1 and not current['armed']:
                    report.update(success=True, final=current, maxAltitude=max_altitude)
                    break
                time.sleep(0.25)
            if not report['success']:
                # Leave a simulated airborne vehicle descending if the test fails.
                if status()['armed']:
                    execute('/api/flight', {'action': 'land'})
                raise TimeoutError(f'Flight did not finish: {status()}')
            # A second short flight checks the operator's RTL and LAND buttons.
            execute('/api/uploads', {'missionId': saved['missionId']})
            execute('/api/mission-checks', {'missionId': saved['missionId']})
            execute('/api/flight', {'action': 'arm'})
            execute('/api/flight', {'action': 'start', 'missionId': saved['missionId']})
            wait_until(lambda: status()['landedState'] == 2, timeout=30)
            execute('/api/flight', {'action': 'rtl'})
            execute('/api/flight', {'action': 'land'})
            wait_until(lambda: status()['landedState'] == 1 and not status()['armed'], timeout=90)
            report['operatorControls'] = {'rtl': True, 'land': True, 'final': status()}
    return report


if __name__ == '__main__':
    result = run()
    Path('.runtime/flight-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('success', 'maxAltitude', 'final')}, ensure_ascii=False, indent=2))
