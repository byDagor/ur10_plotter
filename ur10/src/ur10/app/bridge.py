"""Event bridge: lets worker threads/processes talk to the DPG main thread.

The existing vectorizer and robot modules signal the GUI by calling
``window.write_event_value(key, value)`` (a FreeSimpleGUI idiom). An EventBridge
implements that same method but simply enqueues the event; the DPG render loop
calls ``pump()`` on every bridge each frame and dispatches queued events to the
handlers on the main thread, where touching widgets is safe.

This is what lets flow_vectorizer / hatched_vectorizer / dither_vectorizer and
UR10Controller.execute_path_realtime be reused unchanged - we just pass a bridge
where they expect a ``window``.
"""

import threading
from collections import deque

ALL_BRIDGES = []


class EventBridge:
    def __init__(self, handlers=None):
        # handlers: {event_key: callable(value)} run on the main thread
        self.handlers = handlers or {}
        self._q = deque()
        self._lock = threading.Lock()
        ALL_BRIDGES.append(self)

    # Called from any thread (mimics FreeSimpleGUI's window API).
    def write_event_value(self, key, value):
        with self._lock:
            self._q.append((key, value))

    # Called every frame on the main thread.
    def pump(self):
        with self._lock:
            items = list(self._q)
            self._q.clear()
        for key, value in items:
            handler = self.handlers.get(key)
            if handler:
                handler(value)


def pump_all():
    for bridge in ALL_BRIDGES:
        bridge.pump()
