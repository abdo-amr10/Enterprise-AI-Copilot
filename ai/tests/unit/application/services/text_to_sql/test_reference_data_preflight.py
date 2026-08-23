import json

from src.application.services.text_to_sql.reference_data_preflight import (
    ReferenceDataPreflight,
)


def test_reports_a_missing_branch_manager_from_reference_data(tmp_path) -> None:
    data_path = tmp_path / "sample_data.json"
    data_path.write_text(
        json.dumps({"branches": [{"manager_name": "Sara Mahmoud"}]}),
        encoding="utf-8",
    )

    result = ReferenceDataPreflight(data_path).check_branch_manager(
        "show accounts in the branch whose manager is Sergio Parker"
    )

    assert result == ("Sergio Parker", ("Sara Mahmoud",))


def test_allows_a_known_branch_manager_from_reference_data(tmp_path) -> None:
    data_path = tmp_path / "sample_data.json"
    data_path.write_text(
        json.dumps({"branches": [{"manager_name": "Sara Mahmoud"}]}),
        encoding="utf-8",
    )

    assert ReferenceDataPreflight(data_path).check_branch_manager(
        "show accounts whose manager is sara mahmoud"
    ) is None


def test_recognizes_possessive_branch_manager_wording(tmp_path) -> None:
    data_path = tmp_path / "sample_data.json"
    data_path.write_text(json.dumps({"branches": []}), encoding="utf-8")

    result = ReferenceDataPreflight(data_path).check_branch_manager(
        "show all accounts in Sergio Parker's branch"
    )

    assert result == ("Sergio Parker", ())
