import queue
import time
from types import SimpleNamespace


class Message(SimpleNamespace):
    def get_type(self):
        return self.name

    def get_srcSystem(self):
        return getattr(self, 'system', 1)

    def get_srcComponent(self):
        return getattr(self, 'component', 1)


def message(name, **values):
    return Message(name=name, **values)


class FakeTransport:
    """Protocol test peer; not a flight simulator or production fallback."""
    def __init__(self):
        self.incoming = queue.Queue()
        self.counts = []
        self.sent = []
        self.commands = []
        self.list_requests = 0
        self.item_requests = []
        self.acks = []
        self.closed = False

    def receive(self, timeout=0.1):
        try:
            return self.incoming.get(timeout=timeout)
        except queue.Empty:
            return None

    def heartbeat(self):
        pass

    def request_streams(self):
        pass

    def mission_count(self, count):
        self.counts.append(count)

    def mission_request_list(self):
        self.list_requests += 1

    def mission_request(self, seq):
        self.item_requests.append(seq)

    def mission_ack(self, result=0):
        self.acks.append(result)

    def mission_item(self, seq, item):
        self.sent.append((seq, item))

    def command(self, command, params):
        self.commands.append((command, params))

    def mode(self, msg):
        return getattr(msg, 'mode', 'STABILIZE')

    def close(self):
        self.closed = True


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError('Condition not reached before timeout')


def connect(peer, client):
    peer.incoming.put(message('HEARTBEAT', autopilot=3, base_mode=0))
    peer.incoming.put(message('HOME_POSITION', latitude=557550000, longitude=375900000, altitude=150000))
    wait_for(lambda: client.get('/api/status').json()['home'])
