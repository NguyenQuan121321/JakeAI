"""Bounded, failure-only observation. Never enabled for gate measurements."""

import asyncio
import contextlib
import time
import tracemalloc
from contextvars import ContextVar

# Names only; never record Redis keys/values, HTTP paths, headers or bodies.
OPERATIONS = frozenset(
    {
        "GET",
        "SET",
        "SETEX",
        "DEL",
        "EXISTS",
        "EVAL",
        "EVALSHA",
        "HGET",
        "HSET",
        "HGETALL",
        "INCR",
        "INCRBY",
        "EXPIRE",
        "TTL",
        "MGET",
        "PING",
    }
)


class ChatDiagnostics:
    """Observe the existing one-shot diagnostic sample without changing its inputs."""

    def __init__(self, application_slot, redis_type):
        self.slot = application_slot
        self.redis_type = redis_type
        self.requests = []
        self.commands = []
        self.lags = []
        self.dropped = 0
        self.sequence = 0
        self.request_id = ContextVar("diagnostic_request_id", default=None)

    def append(self, target, value):
        if len(target) < 1024:
            target.append(value)
        else:
            self.dropped += 1

    async def __aenter__(self):
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.old_app = self.slot.app
        self.old_command = self.redis_type.execute_command

        async def command(client, *args, **kwargs):
            started, cpu = time.perf_counter(), time.process_time()
            failed = None
            try:
                return await self.old_command(client, *args, **kwargs)
            except BaseException as error:
                failed = type(error).__name__
                raise
            finally:
                operation = args[0] if args and isinstance(args[0], str) else "OTHER"
                self.append(
                    self.commands,
                    {
                        "request_id": self.request_id.get(),
                        "operation": operation if operation in OPERATIONS else "OTHER",
                        "wall_ms": (time.perf_counter() - started) * 1000,
                        "process_cpu_elapsed_ms": (time.process_time() - cpu) * 1000,
                        "error_class": failed,
                    },
                )

        self.slot.app = self.asgi
        self.redis_type.execute_command = command
        self.monitor = asyncio.create_task(self.observe_loop())
        return self

    async def __aexit__(self, *_):
        self.slot.app = self.old_app
        self.redis_type.execute_command = self.old_command
        self.monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.monitor
        self.wall_ms = (time.perf_counter() - self.started) * 1000
        self.cpu_ms = (time.process_time() - self.cpu_started) * 1000

    async def observe_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            due = loop.time() + 0.005
            await asyncio.sleep(0.005)
            self.append(self.lags, max(0.0, loop.time() - due) * 1000)

    async def asgi(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.old_app(scope, receive, send)
        self.sequence += 1
        identifier = self.sequence
        binding = self.request_id.set(identifier)
        started, cpu = time.perf_counter(), time.process_time()
        traced = tracemalloc.is_tracing()
        current, _ = tracemalloc.get_traced_memory()
        row = {
            "request_id": identifier,
            "start_offset_ms": (started - self.started) * 1000,
            "status": None,
            "response_start_ms": None,
            "tracemalloc_active": traced,
            "traced_current_start_bytes": current,
            "error_class": None,
        }

        async def observed_send(message):
            if message["type"] == "http.response.start":
                row["status"] = message["status"]
                row["response_start_ms"] = (time.perf_counter() - started) * 1000
            await send(message)

        try:
            await self.old_app(scope, receive, observed_send)
        except BaseException as error:
            row["error_class"] = type(error).__name__
            raise
        finally:
            row["wall_ms"] = (time.perf_counter() - started) * 1000
            row["process_cpu_elapsed_ms"] = (time.process_time() - cpu) * 1000
            current, peak = tracemalloc.get_traced_memory()
            row["traced_current_end_bytes"] = current
            row["traced_process_peak_end_bytes"] = peak
            self.append(self.requests, row)
            self.request_id.reset(binding)

    def evidence(self):
        return {
            "scope": "DIAGNOSTIC_ONLY_NOT_GATE_OR_CONFIRMATION",
            "limits": "1024 records per list; omissions counted, never silently dropped",
            "semantics": (
                "ASGI wall includes in-stack IO/queueing; excludes pre-ASGI client/semaphore wait. "
                "CPU deltas and traced bytes are process-wide overlapping intervals, not exclusive "
                "per-request costs. Redis wall includes scheduling/IO/CPU; it is not server-only RTT. "
                "Observer and cProfile overhead are present; no primary verdict is recomputed."
            ),
            "wall_ms": self.wall_ms,
            "process_cpu_ms": self.cpu_ms,
            "requests": self.requests,
            "redis_commands": self.commands,
            "event_loop_lag_ms": self.lags,
            "dropped_records": self.dropped,
        }
