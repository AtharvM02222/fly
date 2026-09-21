"""Script to create an admin user."""

import asyncio
import argparse
import sys

from app.core.security import hash_password
from app.db.models.user import User
from app.db.session import get_session


async def create_admin_user(email: str, password: str) -> None:
    """Create an admin user."""
    async with get_session() as session:
        # Check if user already exists
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"User with email {email} already exists")
            sys.exit(1)

        # Create admin user
        password_hash = hash_password(password)
        admin = User(
            email=email,
            role="admin",
            password_hash=password_hash,
        )

        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        print(f"Admin user created successfully:")
        print(f"  Email: {admin.email}")
        print(f"  Role: {admin.role}")
        print(f"  ID: {admin.id}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")

    args = parser.parse_args()

    asyncio.run(create_admin_user(args.email, args.password))


if __name__ == "__main__":
    main()
