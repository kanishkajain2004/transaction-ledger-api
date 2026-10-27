import pytest

MISSING_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def account_with_history(create_account, post_txn):
    """3 credits and 2 debits, created in order r1..r5."""
    account_id = create_account()
    for ref, type_, amount in [
        ("r1", "credit", 100),
        ("r2", "debit", 10),
        ("r3", "credit", 20),
        ("r4", "debit", 5),
        ("r5", "credit", 1),
    ]:
        assert post_txn(account_id, type_, amount, ref).status_code == 201
    return account_id


def refs(response) -> list[str]:
    return [t["reference_id"] for t in response.json()["data"]]


def test_history_returns_all_types_latest_first(client, account_with_history):
    response = client.get(f"/accounts/{account_with_history}/transactions")

    assert response.status_code == 200
    assert refs(response) == ["r5", "r4", "r3", "r2", "r1"]
    created = [t["created_at"] for t in response.json()["data"]]
    assert created == sorted(created, reverse=True)
    assert response.json()["pagination"] == {"page": 1, "limit": 10, "total_records": 5, "total_pages": 1}


def test_filter_by_type(client, account_with_history):
    credits = client.get(f"/accounts/{account_with_history}/transactions", params={"type": "credit"})
    debits = client.get(f"/accounts/{account_with_history}/transactions", params={"type": "debit"})

    assert refs(credits) == ["r5", "r3", "r1"]
    assert credits.json()["pagination"]["total_records"] == 3
    assert refs(debits) == ["r4", "r2"]
    assert debits.json()["pagination"]["total_records"] == 2


def test_pagination(client, account_with_history):
    url = f"/accounts/{account_with_history}/transactions"

    page1 = client.get(url, params={"page": 1, "limit": 2})
    page3 = client.get(url, params={"page": 3, "limit": 2})
    beyond = client.get(url, params={"page": 4, "limit": 2})

    assert refs(page1) == ["r5", "r4"]
    assert page1.json()["pagination"] == {"page": 1, "limit": 2, "total_records": 5, "total_pages": 3}
    assert refs(page3) == ["r1"]
    assert refs(beyond) == []
    assert beyond.json()["pagination"]["total_pages"] == 3


def test_pagination_combined_with_filter(client, account_with_history):
    response = client.get(
        f"/accounts/{account_with_history}/transactions", params={"type": "credit", "page": 2, "limit": 2}
    )

    assert refs(response) == ["r1"]
    assert response.json()["pagination"] == {"page": 2, "limit": 2, "total_records": 3, "total_pages": 2}


def test_empty_history(client, create_account):
    response = client.get(f"/accounts/{create_account()}/transactions")

    assert response.json() == {
        "data": [],
        "pagination": {"page": 1, "limit": 10, "total_records": 0, "total_pages": 0},
    }


@pytest.mark.parametrize(
    "params, field",
    [
        ({"page": 0}, "page"),
        ({"page": -1}, "page"),
        ({"page": "abc"}, "page"),
        ({"limit": 0}, "limit"),
        ({"limit": 101}, "limit"),
        ({"type": "refund"}, "type"),
    ],
)
def test_invalid_history_params(client, create_account, params, field):
    response = client.get(f"/accounts/{create_account()}/transactions", params=params)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == field


def test_history_of_unknown_account_is_404(client):
    response = client.get(f"/accounts/{MISSING_ID}/transactions")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"
