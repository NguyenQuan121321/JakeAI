"""Explicit Bruno synthetic probe fixture; real HTTP identity/policy is retained.

This module is never part of the production image. Only the validation transport
is controlled; actual settings, encrypted storage, manager and routes execute.
The public sequence deletes the fixture credential before generation requests.
"""

import httpx

from app.core import byok
from app.core.byok_storage import MemoryStore
from app.main import app  # noqa: F401

byok._byok_manager = byok.BYOKManager(
    store=MemoryStore(),
    validation_transport=httpx.MockTransport(lambda _: httpx.Response(200)),
)
