"""Synthetic/staging migration command; never changes key provisioning or purges.

Run only after backup/key inventory review. Restart with cursor 0 after faults;
repeat a complete clean pass with old writers stopped before retirement.
"""

import argparse
import asyncio
import json

from app.core.byok import get_byok_manager
from app.core.byok_storage import BYOKError, RedisStore


async def migrate(cursor: str, count: int) -> int:
    manager = get_byok_manager()
    failed = False
    try:
        while True:
            report = await manager.reencrypt_batch(cursor, count)
            print(json.dumps(report, sort_keys=True))
            failed = failed or bool(report["errors"]) or bool(report["conflicts"])
            cursor = report["cursor"]
            if cursor == "0":
                return 1 if failed else 0
    except BYOKError as exc:
        print(json.dumps({"error": exc.code, "restart_cursor": "0"}))
        return 1
    finally:
        if isinstance(manager.store, RedisStore):
            await manager.store.client.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cursor", default="0")
    parser.add_argument("--count", type=int, default=100)
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(migrate(arguments.cursor, arguments.count)))
