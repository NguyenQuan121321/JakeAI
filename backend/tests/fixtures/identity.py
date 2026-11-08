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
    from tests.offline_trust import provision_offline_trust

    if get_settings().ENVIRONMENT.lower() not in {"test", "development"}:
        raise RuntimeError("Offline benchmark identity is not a production authority")
    provision_offline_trust()
    get_settings.cache_clear()
    from app.main import app

    app.state.identity_client = OfflineState()
