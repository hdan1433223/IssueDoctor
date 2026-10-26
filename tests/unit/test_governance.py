from datetime import datetime

import pytest
import yaml

from issuedoctor.compat import UTC
from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.models import AIAnalysis, AnalysisRun, Repository
from issuedoctor.security.governance_paths import validate_governance_path
from issuedoctor.services.governance_service import GovernanceService


def _create_run():
    now = datetime.now(UTC)
    repository = Repository(
        owner="example",
        name="governance",
        full_name="example/governance",
        html_url="https://github.com/example/governance",
    )
    db.session.add(repository)
    db.session.flush()
    run = AnalysisRun(
        id="00000000-0000-0000-0000-000000000006",
        repository_id=repository.id,
        status="SUCCEEDED",
        mode="BASIC",
        progress_percent=100,
        current_stage="COMPLETED",
        created_at=now,
        window_start=now,
        window_end=now,
        issue_limit=500,
        pr_limit=500,
        scoring_config_json={},
        analysis_config_json={},
    )
    db.session.add(run)
    db.session.commit()
    return run


@pytest.mark.parametrize(
    "path",
    [
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/question.md",
        "CONTRIBUTING.md",
        ".github/ISSUE_TRIAGE.md",
        "docs/ISSUE_GUIDE.md",
    ],
)
def test_governance_path_whitelist_accepts_only_document_paths(path):
    assert validate_governance_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/execute.yml",
        "src/backdoor.py",
        "../CONTRIBUTING.md",
        "C:/project/file.md",
        ".github/ISSUE_TEMPLATE/../../workflows/evil.yml",
    ],
)
def test_governance_path_whitelist_blocks_executable_or_traversal_paths(path):
    with pytest.raises(IssueDoctorError) as error:
        validate_governance_path(path)
    assert error.value.code == "GOVERNANCE_PATH_FORBIDDEN"


def test_generated_issue_forms_are_parseable_and_diff_is_available(app):
    with app.app_context():
        db.create_all()
        run = _create_run()

        package = GovernanceService().generate(run)
        diff = GovernanceService.diff(package)

        assert ".github/ISSUE_TEMPLATE/bug_report.yml" in package.files_json
        for path, data in package.files_json.items():
            assert validate_governance_path(path) == path
            if path.endswith((".yml", ".yaml")):
                assert isinstance(yaml.safe_load(data["content"]), dict)
        assert all(content.startswith("---") for content in diff.values())


def test_governance_exposes_concrete_ai_action_items(app):
    with app.app_context():
        db.create_all()
        run = _create_run()
        db.session.add(
            AIAnalysis(
                analysis_run_id=run.id,
                issue_number=42,
                input_hash="1" * 64,
                prompt_version="v2",
                model_name="model-a",
                category="bug",
                category_confidence=0.9,
                completeness_json=["version"],
                quality_flags_json=[],
                semantic_quality_score=55,
                semantic_confidence=0.8,
                recommended_action="request_more_information",
                summary="缺少版本信息。",
                explanation="正文没有版本号。",
                status="SUCCEEDED",
                raw_response_hash="2" * 64,
            )
        )
        db.session.commit()

        package = GovernanceService().generate(run)

        item = package.workflow_plan_json["action_items"][0]
        assert item["issue_number"] == 42
        assert item["action"] == "request_more_information"
        assert package.workflow_plan_json["action_counts"] == {
            "request_more_information": 1
        }


def test_invalid_issue_form_yaml_is_rejected():
    with pytest.raises(IssueDoctorError) as error:
        GovernanceService.validate_file(
            ".github/ISSUE_TEMPLATE/bug.yml",
            "name: Bug\nbody: not-a-list\n",
        )
    assert error.value.code == "GOVERNANCE_YAML_INVALID"
