import asyncio


class EventBus:
    """Only the asyncio loop owns subscribers; MAVLink publishes via call_soon_threadsafe."""
    def __init__(self, loop):
        self.loop = loop
        self.subscribers = set()

    def publish(self, event):
        def distribute():
            for queue in tuple(self.subscribers):
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(event)
        if not self.loop.is_closed():
            self.loop.call_soon_threadsafe(distribute)

    def subscribe(self):
        queue = asyncio.Queue(maxsize=100)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self.subscribers.discard(queue)
