from chronochina.g7 import classify_access


def test_classify_access_does_not_treat_confirmed_existence_as_available():
    results = [
        {"dataset_existence_confirmed": True, "http_status": 200},
        {"dataset_existence_confirmed": False, "http_status": 404},
        {"dataset_existence_confirmed": False, "http_status": 500},
    ]

    assert classify_access(results) == "not_publicly_accessible"


def test_classify_access_requires_an_actual_file_or_documented_application():
    assert classify_access([{"retrieved_dataset_file": True}]) == "available"
    assert classify_access(
        [{"documented_application_workflow": True}]
    ) == "available_with_conditions"


def test_classify_access_remains_unknown_without_enough_evidence():
    assert classify_access([{"dataset_existence_confirmed": True, "http_status": 200}]) == "unknown"
