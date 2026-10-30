"""Explicit Bruno synthetic probe fixture; real HTTP identity/policy is retained.

This module is never part of the production image. Validation and Finn state transports
are synthetic; actual signature verification, settings, encrypted storage, manager
and route permission/owner checks execute.
The public sequence deletes the fixture credential before generation requests.
"""

import httpx

from app.core import byok
from app.core.byok_storage import MemoryStore
from app.main import app
from tests.fixtures.identity import OfflineState

# This explicitly synthetic Bruno process is not actual Finn acceptance evidence.
app.state.identity_client = OfflineState()

byok._byok_manager = byok.BYOKManager(
    store=MemoryStore(),
    validation_transport=httpx.MockTransport(lambda _: httpx.Response(200)),
)
