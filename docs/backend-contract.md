# План интеграции

Frontend → FastAPI (HTTP/WebSocket) → отдельный worker pymavlink → ArduPilot SITL.

Предлагаемый `POST /api/missions` принимает экспортируемый JSON: version=1, frame=GLOBAL_RELATIVE_ALT, closed, speed (м/с), waypoints=[{id,lat,lng,alt}]. Координаты WGS84; alt — метры относительно home. Backend валидирует ограничения, создаёт missionId. Сохранение задания и загрузка на автопилот — отдельные операции. Возвращать статус загрузки только после MAVLink MISSION_ACK; обрабатывать timeout и отрицательный ACK.

`WS /api/telemetry` передаёт `{type:"telemetry",payload:{timestamp,altitude,speed,battery,satellites,heading,mode}}`. timestamp — Unix миллисекунды, altitude — относительные метры, speed — м/с, battery — %, heading — градусы. Добавить проверку схемы, stale timeout, переподключение с backoff и индикатор потери связи перед активацией реального режима. Заменить subscribeDemo в App на subscribeWebSocket.

Worker владеет единственным MAVLink-соединением, принимает задания через очередь и транслирует HEARTBEAT, GLOBAL_POSITION_INT, SYS_STATUS, GPS_RAW_INT. При преобразовании учитывать масштаб целых координат и единиц MAVLink. Для SITL endpoint задаётся конфигурацией (например udpin:127.0.0.1:14550); порт сверять с запуском конкретного симулятора. У замкнутой миссии явно добавлять последнюю точку возврата или определять RTL отдельно. Взлёт/посадка, ARM и START — отдельный будущий функционал.

Backend и SITL в этой версии не реализованы. Предлагаемая структура: backend/app/api, schemas, services/mission, services/telemetry, adapters/mavlink. Перед интеграцией добавить серверную валидацию, обработку ACK и тесты на SITL.
