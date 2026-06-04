from pathlib import Path


def test_update_data_sets_sec_user_agent():
    workflow = Path("../.github/workflows/update-data.yml").read_text()
    assert "ATLAS_SEC_USER_AGENT" in workflow
    assert "secrets.ATLAS_SEC_USER_AGENT" in workflow


def test_update_data_uses_node24_actions():
    workflow = Path("../.github/workflows/update-data.yml").read_text()
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true" in workflow
    assert "actions/checkout@v4" not in workflow
    assert "astral-sh/setup-uv@v3" not in workflow
    assert "astral-sh/setup-uv@v8.2.0" in workflow
    assert "actions/setup-node@v4" not in workflow
    assert 'node-version: "24"' in workflow
