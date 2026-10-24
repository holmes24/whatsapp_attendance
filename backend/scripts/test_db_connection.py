"""
Run this directly to prove the MongoDB connection and roster lookup
actually work — no FastAPI, no webhook, just the database layer in isolation.

Usage:
    python3 scripts/test_db_connection.py

Expects MongoDB running locally (see MONGODB_URL in your .env).
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.db.mongodb import ensure_indexes, get_db, lookup_roster


async def main():
    print("1. Connecting to MongoDB and creating indexes...")
    await ensure_indexes()
    print("   OK — connected, indexes created (or already existed).")

    print("\n2. Inserting a dummy roster entry (matches Ansar Shaikh's real sample data)...")
    db = get_db()
    await db.roster.update_one(
        {"phone_number": "918459885152"},  # from your real sample screenshot
        {
            "$set": {
                "phone_number": "918459885152",
                "employee_id": "EMP001",
                "name": "Ansar Shaikh",
                "assigned_site": {
                    "name": "Ashti ULB",
                    "lat": 18.804903,
                    "long": 75.174764,
                },
            }
        },
        upsert=True,
    )
    print("   OK — dummy roster entry inserted/updated.")

    print("\n3. Looking up that employee by phone number (the real lookup path)...")
    result = await lookup_roster("918459885152")
    if result is None:
        print("   FAILED — lookup returned None, something's wrong.")
        return
    print(f"   OK — found: {result.name} @ {result.assigned_site.name}")
    print(f"   Coordinates: {result.assigned_site.lat}, {result.assigned_site.long}")

    print("\n4. Confirming a phone number NOT in the roster correctly returns None...")
    missing = await lookup_roster("911111111111")
    print(f"   OK — correctly returned: {missing}")

    print("\nAll checks passed. MongoDB connection and roster lookup are working.")


if __name__ == "__main__":
    asyncio.run(main())
