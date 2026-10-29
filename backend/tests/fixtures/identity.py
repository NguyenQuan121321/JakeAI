"""Explicit synthetic state for offline tests/ASGI overhead benchmarks only."""

from app.core.config import get_settings


class OfflineState:
    @property
    def settings(self):
        return get_settings()

    async def close(self):
        pass

    async def check(self, token, claims):
        assert token and claims["contract_ver"] == 1


def configure_asgi_benchmark_identity():
    """No socket server, no real Finn/capacity claim, no production runtime switch."""
    import base64
    import os
    import secrets

    from app.main import app

    if get_settings().ENVIRONMENT.lower() not in {"test", "development"}:
        raise RuntimeError("Offline benchmark identity is not a production authority")
    os.environ["JWT_SECRET_KEY"] = base64.b64encode(secrets.token_bytes(32)).decode()
    os.environ["JWT_KEY_ID"] = "benchmark-synthetic"
    get_settings.cache_clear()
    app.state.identity_client = OfflineState()
