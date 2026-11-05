"""Offline first-admin provisioning for an already imported directory user."""

import argparse

from app.bootstrap import build_container
from app.platform.settings import Settings


def main():
    parser = argparse.ArgumentParser(
        description="Provision the first administrator; refuses if one exists"
    )
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--expected-version", required=True, type=int)
    args = parser.parse_args()
    container = build_container(Settings())
    try:
        with container.scope() as services:
            services.org.configuration.bootstrap_admin(args.user_id, args.expected_version)
        print("First administrator provisioned; permission change audited.")
    finally:
        container.db.engine.dispose()


if __name__ == "__main__":
    main()
