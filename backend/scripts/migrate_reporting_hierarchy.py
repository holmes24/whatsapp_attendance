"""Preview or apply the one-time migration to direct PC assignments."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import migrate_legacy_reporting_hierarchy


async def main(apply: bool) -> None:
    try:
        count = await migrate_legacy_reporting_hierarchy(dry_run=not apply)
        mode = "updated" if apply else "would update"
        print(f"{count} participant(s) {mode} to report directly to a project coordinator.")
        if not apply:
            print("Review the result, back up the database, then rerun with --apply.")
    finally:
        from app.db.mssql import close

        await close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the updates (default is a read-only preview)",
    )
    asyncio.run(main(parser.parse_args().apply))
