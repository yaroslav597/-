import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .bridge import Bridge, BridgeError
from .compiler import compile_plan
from .config import Config
from .events import EventBus
from .schemas import CommandRequest, FlightRequest, MissionPlan, UploadRequest
from .store import Store
from .transport import MavlinkTransport


def create_app(config=None, transport_factory=MavlinkTransport):
    config = config or Config.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(config.database)
        app.state.events = EventBus(asyncio.get_running_loop())
        app.state.bridge = Bridge(config, app.state.store, app.state.events, transport_factory)
        app.state.bridge.start()
        try:
            yield
        finally:
            await asyncio.to_thread(app.state.bridge.stop)

    app = FastAPI(title='АЭРО · MAVLink bridge', version='0.1.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(config.origins), allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @app.exception_handler(BridgeError)
    async def bridge_error(request, error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=error.status, content={'detail': str(error)})

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'bridge': app.state.bridge.snapshot()}

    @app.get('/api/status')
    def status():
        return app.state.bridge.snapshot()

    @app.post('/api/missions', status_code=201)
    def save_mission(plan: MissionPlan):
        compiled = [item.as_dict() for item in compile_plan(plan)]
        return app.state.store.save(plan.model_dump(), compiled)

    @app.get('/api/missions')
    def list_missions():
        return app.state.store.missions()

    @app.get('/api/missions/{mission_id}')
    def get_mission(mission_id: UUID):
        result = app.state.store.mission(mission_id.hex)
        if result is None:
            raise HTTPException(404, 'Миссия не найдена')
        return result

    @app.post('/api/uploads', status_code=202)
    def upload_mission(request: UploadRequest):
        mission = app.state.store.mission(request.missionId)
        if mission is None:
            raise HTTPException(404, 'Миссия не найдена')
        return app.state.bridge.submit('upload', mission, request.missionId)

    @app.post('/api/commands', status_code=202)
    def send_command(request: CommandRequest):
        return app.state.bridge.submit('command', request.model_dump())

    @app.post('/api/flight', status_code=202)
    def flight_command(request: FlightRequest):
        return app.state.bridge.submit('flight', request.model_dump(), request.missionId)

    @app.post('/api/mission-checks', status_code=202)
    def check_mission(request: UploadRequest):
        mission = app.state.store.mission(request.missionId)
        if mission is None:
            raise HTTPException(404, 'Миссия не найдена')
        return app.state.bridge.submit('verify', mission, request.missionId)

    @app.get('/api/operations/{operation_id}')
    def get_operation(operation_id: UUID):
        result = app.state.store.operation(operation_id.hex)
        if result is None:
            raise HTTPException(404, 'Операция не найдена')
        return result

    @app.websocket('/ws/telemetry')
    async def telemetry(socket: WebSocket):
        if socket.headers.get('origin') not in (None, *config.origins):
            await socket.close(code=1008)
            return
        await socket.accept()
        queue = app.state.events.subscribe()

        async def sender():
            await socket.send_json({'type': 'status', 'payload': app.state.bridge.snapshot()})
            await socket.send_json({'type': 'telemetry', 'payload': app.state.bridge.telemetry_snapshot()})
            while True:
                await socket.send_json(await queue.get())

        async def receiver():
            while True:
                await socket.receive_text()

        tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            app.state.events.unsubscribe(queue)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return app


app = create_app()
