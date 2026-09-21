import asyncio
import argparse
from app.core.api_key import generate_api_key, hash_api_key
from app.db.models.device import Device
from app.db.session import get_session
async def create_device(name: str, device_type: str) -> None:
    async with get_session() as session:
        api_key = generate_api_key()
        api_key_hash = hash_api_key(api_key)
        device = Device(
            name=name,
            device_type=device_type,
            api_key_hash=api_key_hash,
            status="offline",
        )
        session.add(device)
        await session.commit()
        await session.refresh(device)
        print(f"Device created successfully:")
        print(f"  Name: {device.name}")
        print(f"  Type: {device.device_type}")
        print(f"  ID: {device.id}")
        print(f"  API Key: {api_key}")
        print(f"\nIMPORTANT: Save the API key - it won't be shown again!")
def main() -> None:
    parser = argparse.ArgumentParser(description="Create a device")
    parser.add_argument("--name", required=True, help="Device name")
    parser.add_argument(
        "--type",
        required=True,
        choices=["drone", "vehicle", "fixed"],
        help="Device type",
    )
    args = parser.parse_args()
    asyncio.run(create_device(args.name, args.type))
if __name__ == "__main__":
    main()
