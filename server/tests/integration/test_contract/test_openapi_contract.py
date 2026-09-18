"""The checked-in `contracts/openapi.yaml` must match the running app exactly.

Constitution principle 11: the contract is the single source of truth, so a
schema hand-edited out of sync with the code -- or code changed without
regenerating the contract -- is a defect this test catches immediately,
rather than relying on someone remembering to keep the two in step.
"""

from pathlib import Path

import yaml

from warden_server.main import app

CONTRACT_PATH = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"


def test_checked_in_contract_matches_the_app_schema():
    checked_in = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert checked_in == app.openapi()
