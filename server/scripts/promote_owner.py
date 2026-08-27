"""Explicitly promote an existing user to owner of their workspace."""

import argparse
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from pymongo import AsyncMongoClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote an existing SupportFlow user to workspace owner."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--workspace-id", required=True, type=UUID)
    return parser.parse_args()


async def promote_owner(email: str, workspace_id: UUID) -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path)
    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        raise SystemExit("MONGODB_URI is required.")

    database_name = os.getenv("MONGODB_DATABASE", "supportflow")
    client = AsyncMongoClient(mongodb_uri)
    try:
        result = await client[database_name]["users"].update_one(
            {
                "email": email.strip().lower(),
                "workspace_id": str(workspace_id),
                "is_active": True,
            },
            {"$set": {"role": "owner", "updated_at": datetime.now(UTC)}},
        )
    finally:
        await client.close()

    if result.matched_count != 1:
        raise SystemExit(
            "No active user matched that email and workspace."
        )
    print("User promoted to workspace owner.")


def main() -> None:
    args = parse_args()
    asyncio.run(promote_owner(args.email, args.workspace_id))


if __name__ == "__main__":
    main()
