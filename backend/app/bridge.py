import logging
import math
import queue
import threading
import time
from uuid import uuid4

from .compiler import MissionItem, item, with_ardupilot_home
from .comparison import compare_mission, from_message
from .store import now_ms

log = logging.getLogger(__name__)


class BridgeError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def distance(a, b):
    lat1, lat2 = math.radians(a['lat']), math.radians(b['lat'])
    dlat, dlng = lat2 - lat1, math.radians(b['lng'] - a['lng'])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(value)))


class Bridge:
    def __init__(self, config, store, events, transport_factory):
        self.config, self.store, self.events, self.transport_factory = config, store, events, transport_factory
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.tasks = queue.Queue(maxsize=1)
        self.thread = threading.Thread(target=self.run, name='mavlink-owner', daemon=True)
        self.transport = None
        self.active = None
        self.busy = False
        self.last_heartbeat = 0
        self.last_home = 0
        self.last_position = 0
        self.telemetry = {}
        self.field_timestamps = {}
        self.state = dict(connected=False, armed=False, mode=None, home=None, busy=False, operationId=None, error=None,
                          targetSystem=config.system_id, targetComponent=config.component_id, firmware=None,
                          uploadedMissionId=None, verifiedMissionId=None, missionCount=0, currentSeq=None,
                          reached=[], landedState=None, missionState=None, lastText=None, startConsumed=False)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError('MAVLink worker did not stop')

    def snapshot(self):
        with self.lock:
            return {**self.state, 'timestamp': now_ms()}

    def telemetry_snapshot(self):
        with self.lock:
            return dict(self.telemetry) if self.telemetry else {'timestamp': now_ms(), 'stale': True}

    def set_state(self, **values):
        with self.lock:
            self.state.update(values)
            payload = self.snapshot()
        self.events.publish(dict(type='status', payload=payload))

    def update_telemetry(self, **values):
        now = time.monotonic()
        self.field_timestamps.update({field: now for field in values})
        self.telemetry.update(values, timestamp=now_ms())

    def job_update(self, **values):
        if not self.active:
            return
        job = self.active['job']
        job.update(values, updatedAt=now_ms())
        self.store.put_operation(job)
        self.events.publish(dict(type='operation', payload=dict(job)))

    def finish(self, error=None, result=None):
        if not self.active:
            return
        self.job_update(status='failed' if error else 'succeeded', error=error, result=result)
        with self.lock:
            self.active = None
            self.busy = False
            self.set_state(busy=False, operationId=None)

    def submit(self, kind, payload, mission_id=None):
        with self.lock:
            if not self.state['connected'] or time.monotonic() - self.last_heartbeat > self.config.heartbeat_timeout:
                raise BridgeError('Автопилот не подключён: ожидается HEARTBEAT', 503)
            if self.busy:
                raise BridgeError('Другая операция MAVLink ещё выполняется')
            if kind == 'upload' and self.state['armed']:
                raise BridgeError('Для загрузки новой миссии требуется снятый ARM')
            if kind == 'upload':
                self.check_home(payload['plan']['settings']['home'])
            if kind == 'flight':
                self.check_flight(payload)
            job = dict(operationId=uuid4().hex, kind=kind, missionId=mission_id, status='queued', progress=0,
                       total=0, error=None, updatedAt=now_ms())
            self.store.put_operation(job)
            self.busy = True
            self.state.update(busy=True, operationId=job['operationId'])
            self.tasks.put_nowait(dict(job=job, payload=payload))
        self.events.publish(dict(type='operation', payload=dict(job)))
        return job

    def check_flight(self, request):
        action = request['action']
        if action == 'arm':
            if self.state['armed']:
                raise BridgeError('ARM уже включён')
            if self.state['landedState'] != 1:
                raise BridgeError('Ожидается подтверждение: аппарат на земле')
            if time.monotonic() - self.last_position > self.config.heartbeat_timeout or self.telemetry.get('fixType', 0) < 3:
                raise BridgeError('Для подготовки к полёту нужны свежие координаты и GPS 3D fix')
            self.check_home(self.state['home'] or {})
        elif action == 'start':
            if not self.state['armed']:
                raise BridgeError('Сначала подготовьте аппарат к полёту (ARM)')
            if not request.get('missionId') or request['missionId'] != self.state['verifiedMissionId']:
                raise BridgeError('Перед запуском проверьте совпадение текущей миссии с бортом')
            if self.state['landedState'] != 1:
                raise BridgeError('Запуск миссии разрешён с земли; повторный запуск в полёте запрещён')
            if self.state['startConsumed'] or (self.state['missionState'] == 5 and not self.state['uploadedMissionId']) or self.state['currentSeq'] not in (None, 0, 1):
                raise BridgeError('Для нового полёта загрузите миссию заново, чтобы начать с первой команды')
            mission = self.store.mission(request['missionId'])
            if not mission or not mission['plan']['settings']['takeoff']:
                raise BridgeError('Для запуска с земли нужна команда взлёта в начале миссии')
            self.check_home(mission['plan']['settings']['home'])
            if time.monotonic() - self.last_position > self.config.heartbeat_timeout:
                raise BridgeError('Нет свежих координат аппарата')
        elif action == 'disarm':
            if self.state['landedState'] != 1:
                raise BridgeError('Выключение ARM разрешено только после подтверждения посадки')
        elif not self.state['armed']:
            raise BridgeError('Аппарат не вооружён: полёт не выполняется')

    def begin_flight(self, task):
        self.check_flight(task['payload'])
        action = task['payload']['action']
        # Copter mode numbers: GUIDED=4, AUTO=3. Never force arm/disarm.
        stages = {
            'arm': [(176, [1, 4, 0, 0, 0, 0, 0], 'mode', 'GUIDED'), (400, [1, 0, 0, 0, 0, 0, 0], 'armed', True)],
            'disarm': [(400, [0, 0, 0, 0, 0, 0, 0], 'armed', False)],
            'start': [(176, [1, 3, 0, 0, 0, 0, 0], 'mode', 'AUTO'), (300, [0]*7, 'mode', 'AUTO')],
            'rtl': [(20, [0]*7, 'mode', 'RTL')],
            'land': [(21, [0]*7, 'mode', 'LAND')],
        }
        task.update(stages=stages[action], stage=0)
        self.job_update(status='running', total=len(task['stages']))
        self.send_flight_stage()

    def send_flight_stage(self):
        task = self.active
        command, params, _, _ = task['stages'][task['stage']]
        if command == 300:
            self.set_state(startConsumed=True)
        task.update(command=command, accepted=False, sent_at=time.monotonic())
        self.transport.command(command, params)

    def advance_flight(self):
        task = self.active
        if not task or task['job']['kind'] != 'flight' or not task.get('accepted'):
            return
        _, _, key, expected = task['stages'][task['stage']]
        if self.state[key] != expected:
            return
        task['stage'] += 1
        self.job_update(progress=task['stage'])
        if task['stage'] == len(task['stages']):
            self.finish(result=dict(action=task['payload']['action'], ack=0, confirmed=True))
        else:
            self.send_flight_stage()

    def check_home(self, planned):
        home = self.state['home']
        if home is None or time.monotonic() - self.last_home > 30:
            raise BridgeError('Нет свежего HOME_POSITION от автопилота. Дождитесь Home перед загрузкой')
        if distance(home, planned) > self.config.home_tolerance:
            raise BridgeError(f'Плановый Home отличается от Home автопилота более чем на {self.config.home_tolerance:g} м')

    def source_matches(self, message):
        return message.get_srcSystem() == self.config.system_id and message.get_srcComponent() == self.config.component_id

    def addressed(self, message):
        return (getattr(message, 'target_system', 0) in (0, self.config.source_system)
                and getattr(message, 'target_component', 0) in (0, self.config.source_component)
                and getattr(message, 'mission_type', 0) == 0)

    def begin(self, task):
        self.active = task
        task.update(retries=0, requested=set(), last_seq=None, started=time.monotonic())
        if not self.state['connected']:
            self.finish('Соединение с автопилотом потеряно')
            return
        if task['job']['kind'] == 'upload':
            if self.state['armed']:
                self.finish('Автопилот вооружён; загрузка отменена')
                return
            self.check_home(task['payload']['plan']['settings']['home'])
            self.set_state(uploadedMissionId=None, verifiedMissionId=None, currentSeq=None, reached=[], missionState=None, missionCount=0, startConsumed=False)
            task['items'] = with_ardupilot_home([MissionItem(**value) for value in task['payload']['items']], dict(self.state['home']))
            self.job_update(status='running', total=len(task['items']))
            self.transport.mission_count(len(task['items']))
        elif task['job']['kind'] == 'flight':
            self.begin_flight(task)
            return
        elif task['job']['kind'] == 'verify':
            self.set_state(verifiedMissionId=None)
            task.update(downloaded=[], download_count=None, expected=[MissionItem(**value) for value in task['payload']['items']])
            self.job_update(status='running', total=0)
            self.transport.mission_request_list()
        else:
            request = task['payload']
            compiled = item(request['command'], **request['params'])
            task['command'] = compiled.command
            task['params'] = [compiled.param1, compiled.param2, compiled.param3, compiled.param4, compiled.x, compiled.y, compiled.z]
            self.job_update(status='running', total=1)
            self.transport.command(task['command'], task['params'])
        task['sent_at'] = time.monotonic()

    def handle_operation(self, message):
        task = self.active
        if not task or not self.addressed(message):
            return
        name = message.get_type()
        if task['job']['kind'] == 'flight':
            if name == 'COMMAND_ACK' and message.command == task['command']:
                if message.result == 0:
                    task['accepted'] = True
                    self.advance_flight()
                elif message.result == 5:
                    task['sent_at'] = time.monotonic()
                else:
                    self.finish(f'Команда отклонена: MAV_RESULT={message.result}. {self.state.get("lastText") or "Проверьте сообщения автопилота"}')
            return
        if task['job']['kind'] == 'verify':
            self.handle_download(message)
            return
        if task['job']['kind'] == 'upload':
            if name in ('MISSION_REQUEST_INT', 'MISSION_REQUEST'):
                seq = message.seq
                if not 0 <= seq < len(task['items']):
                    self.finish(f'Автопилот запросил недопустимый номер команды: {seq}')
                    return
                if seq > len(task['requested']):
                    self.finish('Нарушен порядок запросов команд миссии')
                    return
                self.transport.mission_item(seq, task['items'][seq])
                task['requested'].add(seq)
                task.update(last_seq=seq, sent_at=time.monotonic(), retries=0)
                self.job_update(progress=len(task['requested']))
            elif name == 'MISSION_ACK':
                if message.type != 0:
                    self.finish(f'Автопилот отклонил миссию: MAV_MISSION_RESULT={message.type}')
                elif len(task['requested']) != len(task['items']):
                    self.finish('Получен преждевременный MISSION_ACK: не все команды запрошены')
                else:
                    self.set_state(uploadedMissionId=task['job']['missionId'], missionCount=len(task['items'])-1)
                    self.finish(result=dict(ack=0, count=len(task['items'])))
        elif name == 'COMMAND_ACK' and message.command == task['command']:
            if message.result == 5:  # MAV_RESULT_IN_PROGRESS
                task['sent_at'] = time.monotonic()
                self.job_update(progress=getattr(message, 'progress', 0))
            elif message.result == 0:
                self.job_update(progress=1)
                self.finish(result=dict(ack=0, command=task['command']))
            else:
                self.finish(f'Команда отклонена: MAV_RESULT={message.result}')

    def complete_download(self):
        task = self.active
        self.transport.mission_ack()
        result = compare_mission(task['expected'], task['downloaded'])
        self.set_state(verifiedMissionId=task['job']['missionId'] if result['matches'] else None,
                       missionCount=max(0, len(task['downloaded'])-1))
        self.finish(result=result)

    def handle_download(self, message):
        task = self.active
        name = message.get_type()
        if name == 'MISSION_COUNT':
            count = message.count
            if not 0 <= count <= 4000:
                self.transport.mission_ack(4)
                self.finish('Недопустимое количество команд на борту')
                return
            if task['download_count'] is not None:
                if task['download_count'] != count:
                    self.finish('Количество команд изменилось во время чтения')
                return
            task.update(download_count=count, retries=0, sent_at=time.monotonic())
            self.job_update(total=count)
            if count == 0:
                self.complete_download()
            else:
                self.transport.mission_request(0)
        elif name in ('MISSION_ITEM_INT', 'MISSION_ITEM') and task['download_count'] is not None:
            expected_seq = len(task['downloaded'])
            if message.seq != expected_seq:
                self.transport.mission_request(expected_seq)
                return
            task['downloaded'].append(from_message(message))
            task.update(retries=0, sent_at=time.monotonic())
            self.job_update(progress=len(task['downloaded']))
            if len(task['downloaded']) == task['download_count']:
                self.complete_download()
            else:
                self.transport.mission_request(len(task['downloaded']))
        elif name == 'MISSION_ACK' and message.type != 0:
            self.finish(f'Автопилот отклонил чтение миссии: MAV_MISSION_RESULT={message.type}')

    def handle(self, message):
        if not self.source_matches(message):
            return
        name = message.get_type()
        if name == 'HEARTBEAT':
            if message.autopilot != 3:  # MAV_AUTOPILOT_ARDUPILOTMEGA
                return
            first = not self.state['connected']
            self.last_heartbeat = time.monotonic()
            self.set_state(connected=True, armed=bool(message.base_mode & 128), mode=self.transport.mode(message), error=None)
            self.advance_flight()
            if first:
                self.transport.request_streams()
        elif self.state['connected']:
            if name == 'HOME_POSITION':
                self.last_home = time.monotonic()
                self.set_state(home=dict(lat=message.latitude / 1e7, lng=message.longitude / 1e7, alt=message.altitude / 1000))
            elif name == 'AUTOPILOT_VERSION':
                version = message.flight_sw_version
                self.set_state(firmware=f'{version >> 24}.{(version >> 16) & 255}.{(version >> 8) & 255}', firmwareType=version & 255)
            elif name == 'GLOBAL_POSITION_INT':
                self.last_position = time.monotonic()
                self.update_telemetry(lat=message.lat / 1e7, lng=message.lon / 1e7, altitude=message.relative_alt / 1000,
                                      speed=math.hypot(message.vx, message.vy) / 100,
                                      heading=None if message.hdg == 65535 else message.hdg / 100)
            elif name == 'SYS_STATUS':
                self.update_telemetry(battery=None if message.battery_remaining < 0 else message.battery_remaining)
            elif name == 'GPS_RAW_INT':
                self.update_telemetry(satellites=None if message.satellites_visible == 255 else message.satellites_visible, fixType=message.fix_type)
            elif name == 'MISSION_CURRENT':
                self.set_state(currentSeq=message.seq, missionState=getattr(message, 'mission_state', None))
                self.events.publish(dict(type='mission_current', payload=dict(seq=message.seq, timestamp=now_ms())))
            elif name == 'MISSION_ITEM_REACHED':
                self.set_state(reached=sorted(set(self.state['reached']) | {message.seq}))
            elif name == 'EXTENDED_SYS_STATE':
                self.set_state(landedState=message.landed_state)
            elif name == 'STATUSTEXT':
                text = message.text.decode('utf-8', errors='replace') if isinstance(message.text, bytes) else message.text
                self.set_state(lastText=text.rstrip('\0'))
            self.handle_operation(message)

    def tick(self):
        now = time.monotonic()
        if self.state['connected'] and now - self.last_heartbeat > self.config.heartbeat_timeout:
            self.telemetry.clear()
            self.set_state(connected=False, home=None, armed=False, verifiedMissionId=None, landedState=None,
                           currentSeq=None, reached=[], missionState=None, error='HEARTBEAT timeout')
            self.finish('Потерян HEARTBEAT. Результат операции на борту неизвестен')
            if self.transport:
                self.transport.close()
                self.transport = None
        if self.active:
            task = self.active
            if now - task['started'] > 120:
                self.finish('Превышено общее время операции; результат на борту неизвестен')
            elif now - task['sent_at'] > (15 if task['job']['kind'] == 'flight' else self.config.response_timeout):
                if task['job']['kind'] not in ('upload', 'verify') or task['retries'] >= self.config.max_retries:
                    self.finish('Нет подтверждения MAVLink (timeout); результат на борту неизвестен')
                elif task['job']['kind'] == 'verify':
                    if task['download_count'] is None:
                        self.transport.mission_request_list()
                    else:
                        self.transport.mission_request(len(task['downloaded']))
                    task.update(sent_at=now, retries=task['retries'] + 1)
                else:
                    if task['last_seq'] is None:
                        self.transport.mission_count(len(task['items']))
                    else:
                        seq = task['last_seq']
                        self.transport.mission_item(seq, task['items'][seq])
                    task.update(sent_at=now, retries=task['retries'] + 1)

    def run(self):
        next_connect = next_heartbeat = next_publish = next_home = 0
        try:
            while not self.stop_event.is_set():
                try:
                    now = time.monotonic()
                    if self.transport is None:
                        if now < next_connect:
                            self.stop_event.wait(0.1)
                            continue
                        self.transport = self.transport_factory(self.config)
                    if now >= next_heartbeat:
                        self.transport.heartbeat()
                        next_heartbeat = now + 1
                    if self.state['connected'] and now >= next_home and not self.busy:
                        self.transport.request_streams()
                        next_home = now + 10
                    # Process incoming messages before beginning a queued transaction.
                    message = self.transport.receive(timeout=0.05)
                    if message is not None:
                        with self.lock:
                            self.handle(message)
                    if not self.active:
                        try:
                            task = self.tasks.get_nowait()
                        except queue.Empty:
                            task = None
                        if task:
                            try:
                                self.begin(task)
                            except BridgeError as error:
                                self.finish(str(error))
                    self.tick()
                    if now >= next_publish:
                        with self.lock:
                            for field, updated in self.field_timestamps.items():
                                if now - updated > self.config.heartbeat_timeout:
                                    self.telemetry.pop(field, None)
                            stale = not self.state['connected'] or now - self.last_position > self.config.heartbeat_timeout
                            if stale:
                                for field in ('lat', 'lng', 'altitude', 'speed', 'heading'):
                                    self.telemetry.pop(field, None)
                            self.telemetry.update(timestamp=now_ms(), mode=self.state['mode'], stale=stale)
                            payload = dict(self.telemetry)
                        self.events.publish(dict(type='telemetry', payload=payload))
                        next_publish = now + 0.5
                except Exception as error:
                    log.exception('MAVLink worker error')
                    self.finish(f'Ошибка связи: {error}')
                    self.telemetry.clear()
                    self.set_state(connected=False, home=None, verifiedMissionId=None, landedState=None,
                                   currentSeq=None, reached=[], missionState=None, error=str(error))
                    if self.transport:
                        self.transport.close()
                        self.transport = None
                    next_connect = time.monotonic() + 2
        finally:
            self.finish('Backend остановлен; результат на борту неизвестен')
            while not self.tasks.empty():
                self.active = self.tasks.get_nowait()
                self.finish('Backend остановлен до начала операции')
            if self.transport:
                self.transport.close()
