from pathlib import Path


def test_update_data_sets_sec_user_agent():
    workflow = Path("../.github/workflows/update-data.yml").read_text()
    assert "ATLAS_SEC_USER_AGENT" in workflow
    assert "kc5587@users.noreply.github.com" in workflow
