import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "resource-intake.yml"


def _workflow_input_block(source: str, name: str) -> str:
    match = re.search(
        rf"^      {re.escape(name)}:\n(?P<body>(?:        .*\n)+)",
        source,
        flags=re.MULTILINE,
    )
    assert match is not None, f"missing workflow input: {name}"
    return match.group("body")


def test_resource_intake_requires_an_explicit_snapshot_pair() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    trigger_block = source.split("permissions:", 1)[0]

    assert "\n  push:\n" not in trigger_block

    for input_name in ("territory_run_id", "territory_artifact_id"):
        input_block = _workflow_input_block(source, input_name)
        assert "required: true" in input_block
        assert "default:" not in input_block

    assert "artifact-ids: ${{ inputs.territory_artifact_id }}" in source
    assert "run-id: ${{ inputs.territory_run_id }}" in source
    assert "inputs.territory_artifact_id ||" not in source
    assert "inputs.territory_run_id ||" not in source
