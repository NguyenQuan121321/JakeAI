"""Private long-lived subject worker; launched only by guarded paired capture.

Application modules come from the independently verified subject checkout.
Only app.performance is overlaid with the common candidate measurement harness.
Native JWT issuance formats remain source-specific; equivalent synthetic access
permissions/issuer/audience and ephemeral trust are reconciled outside timing.
"""

import asyncio
import contextlib
import cProfile
import importlib
import importlib.metadata
import json
import os
import pstats
import runpy
import sys
import types
from pathlib import Path


def allow_command(phase, names, initial_done, measured, profiled):
    if phase == "initial" and not initial_done:
        return
    if phase == "confirmation" and initial_done and not measured:
        return
    if (
        phase == "diagnostic_profile"
        and measured
        and not profiled
        and names
        and set(names) <= measured
    ):
        return
    raise RuntimeError("Repeated/out-of-order trial forbidden")


async def diagnostic_profile(runner, names):
    """Profile actual failed paths once, retaining all diagnostic samples.

    cProfile timing is instrumentation-affected and is NEVER gate evidence.
    No call arguments, local values, headers or credentials are captured.
    """
    data = {}
    for name in names:
        profile = cProfile.Profile()
        try:
            profile.enable()
            result = await runner.run_scenario(name)
        finally:
            profile.disable()
        stats = pstats.Stats(profile)
        functions = [
            {
                "file": key[0],
                "line": key[1],
                "function": key[2],
                "primitive_calls": value[0],
                "calls": value[1],
                "self_seconds": value[2],
                "cumulative_seconds": value[3],
            }
            for key, value in sorted(
                stats.stats.items(), key=lambda row: row[1][3], reverse=True
            )[:100]
        ]
        data[name] = {
            "instrumented_sample": result.model_dump(mode="json"),
            "functions": functions,
        }
    return {"scope": "DIAGNOSTIC_ONLY_NOT_CONFIRMATION_OR_GATE", "scenarios": data}


async def serve(source, harness):
    # A worker is not a public execution switch; verify hosted identity again.
    from j02_rehearsal import identity

    identity()
    if os.environ.get("J02_PAIRED_CONTRACT") != "review-v1":
        raise RuntimeError("Explicit reviewed contract selection required")
    protocol = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        sys.path.insert(0, str(source / "backend"))
        runpy.run_path(str(harness / "backend/tests/offline_trust.py"))[
            "provision_offline_trust"
        ]()
        import app

        common = types.ModuleType("app.performance")
        common.__path__ = [str(harness / "backend/app/performance")]
        sys.modules["app.performance"] = common
        app.performance = common
        fixture = importlib.import_module("tests.fixtures.auth")
        native_mint = fixture.create_test_jwt

        def mint(*args, **kwargs):
            kwargs.setdefault("expires_in", 900)
            kwargs.setdefault("permissions", ["chat:read", "chat:write", "rag:read"])
            kwargs.setdefault("iss", "finnapigo")
            kwargs.setdefault("aud", ["finnapigo-api", "jakeai-service"])
            return native_mint(*args, **kwargs)

        fixture.create_test_jwt = mint
        from app.core.config import get_settings
        from app.main import app as application

        # The control predates authoritative state checking; this adapter is
        # consumed only where the subject implements that boundary. No verifier,
        # permission dependency or application effect is patched.
        class OfflineState:
            @property
            def settings(self):
                return get_settings()

            async def check(self, token, claims):
                assert token and claims["contract_ver"] == 1

        application.state.identity_client = OfflineState()
        from app.performance.runner import PerformanceBenchmarkRunner

        runner = PerformanceBenchmarkRunner(mode="full")
        inventory = {
            d.metadata["Name"].lower().replace("_", "-").replace(".", "-"): d.version
            for d in importlib.metadata.distributions()
        }
        protocol.write(json.dumps({"ready": True, "dependencies": inventory}) + "\n")
        protocol.flush()
        measured = set()
        profiled = False
        initial_done = False
        while line := sys.stdin.readline():
            command = json.loads(line)
            if command["phase"] == "stop":
                return
            phase, names = command["phase"], command["names"]
            allow_command(phase, names, initial_done, measured, profiled)
            if phase == "diagnostic_profile":
                profiled = True
                payload = await diagnostic_profile(runner, names)
                protocol.write(json.dumps(payload, allow_nan=False) + "\n")
                protocol.flush()
                continue
            if phase == "initial" and not initial_done:
                results = await runner.run_all_scenarios(run_warmup=True)
                initial_done = True
            elif phase == "confirmation" and initial_done and not measured:
                results = {name: await runner.run_scenario(name) for name in names}
                measured.update(names)
            if set(results) != set(names):
                raise RuntimeError("Unexpected scenario capture")
            protocol.write(
                json.dumps(
                    {
                        key: value.model_dump(mode="json")
                        for key, value in results.items()
                    },
                    allow_nan=False,
                )
                + "\n"
            )
            protocol.flush()


if __name__ == "__main__":
    try:
        asyncio.run(serve(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
    except Exception as error:  # noqa: BLE001 -- process boundary: block and redact private diagnostics
        # Private logs can include application diagnostics; the parent publishes
        # only the exception class, not logs, headers or ephemeral keys.
        print("Paired worker stopped: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(2) from None
