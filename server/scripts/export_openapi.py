"""Regenerate `contracts/openapi.yaml` from the FastAPI app's own schema.

Run this after any change to a router, schema, or endpoint -- the checked-in
contract is meant to be generated, not hand-edited, so it cannot drift from
what the server actually serves (constitution principle 11).

    python scripts/export_openapi.py
"""

from pathlib import Path

import yaml

from warden_server.main import app

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi.yaml"


def main() -> None:
    schema = app.openapi()
    CONTRACT_PATH.write_text(
        yaml.safe_dump(schema, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(f"wrote {CONTRACT_PATH}")


if __name__ == "__main__":
    main()
