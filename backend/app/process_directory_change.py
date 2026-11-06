"""Internal replay entry point; input must come from a verified, already-imported directory event."""

import argparse
import json
from pathlib import Path

from app.bootstrap import build_container
from app.modules.requisition.contracts import DirectoryChange
from app.platform.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Verified directory event JSON file")
    args = parser.parse_args()
    command = DirectoryChange.model_validate_json(Path(args.file).read_text(encoding="utf-8-sig"))
    container = build_container(Settings())
    try:
        with container.scope() as services:
            result = services.requisition.consume_directory_change(command)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        container.db.engine.dispose()


if __name__ == "__main__":
    main()
