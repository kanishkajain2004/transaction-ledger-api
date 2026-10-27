import pytest

MISSING_ID = "00000000-0000-0000-0000-000000000000"


def test_credit_increases_balance(create_account, post_txn, balance_of):
    account_id = create_account()
    post_txn(account_id, "credit", 100, "r1")

    response = post_txn(account_id, "credit", 50, "r2", "bonus")

    assert response.status_code == 201
    body = response.json()
    assert body["balance"] == "150.00"
    txn = body["transaction"]
    assert txn["type"] == "credit"
    assert txn["amount"] == "50.00"
    assert txn["description"] == "bonus"
    assert txn["reference_id"] == "r2"
    assert txn["account_id"] == account_id
    assert txn["id"] and txn["created_at"]
    assert balance_of(account_id) == "150.00"


def test_debit_decreases_balance(create_account, post_txn, balance_of):
    account_id = create_account()
    post_txn(account_id, "credit", 100, "r1")

    response = post_txn(account_id, "debit", 30, "r2")

    assert response.status_code == 201
    assert balance_of(account_id) == "70.00"


def test_debit_with_insufficient_balance_is_rejected(create_account, post_txn, balance_of, client):
    account_id = create_account()
    post_txn(account_id, "credit", 100, "r1")

    response = post_txn(account_id, "debit", 150, "r2")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert balance_of(account_id) == "100.00"
    # The rejected debit was not recorded.
    assert client.get(f"/accounts/{account_id}/transactions").json()["pagination"]["total_records"] == 1


def test_debit_of_exact_balance_is_allowed(create_account, post_txn, balance_of):
    account_id = create_account()
    post_txn(account_id, "credit", "10.50", "r1")

    assert post_txn(account_id, "debit", "10.50", "r2").status_code == 201
    assert balance_of(account_id) == "0.00"


def test_balance_matches_all_valid_transactions(create_account, post_txn, balance_of):
    """The example from the assignment: 0 +100 +50 -30 -20 = 100 (with a rejected debit mixed in)."""
    account_id = create_account()
    post_txn(account_id, "credit", 100, "c1")
    post_txn(account_id, "credit", 50, "c2")
    post_txn(account_id, "debit", 30, "d1")
    assert post_txn(account_id, "debit", 1000, "rejected").status_code == 422
    post_txn(account_id, "debit", 20, "d2")

    assert balance_of(account_id) == "100.00"


def test_duplicate_reference_id_does_not_create_transaction(create_account, post_txn, balance_of, client):
    account_id = create_account()
    first = post_txn(account_id, "credit", 100, "ref-1")

    duplicate = post_txn(account_id, "credit", 100, "ref-1")

    assert duplicate.status_code == 409
    error = duplicate.json()["error"]
    assert error["code"] == "DUPLICATE_TRANSACTION"
    assert error["details"]["transaction"]["id"] == first.json()["transaction"]["id"]
    assert balance_of(account_id) == "100.00"
    assert client.get(f"/accounts/{account_id}/transactions").json()["pagination"]["total_records"] == 1


def test_duplicate_reference_id_with_different_payload_is_still_rejected(create_account, post_txn, balance_of):
    account_id = create_account()
    post_txn(account_id, "credit", 100, "ref-1")

    assert post_txn(account_id, "debit", 40, "ref-1").status_code == 409
    assert balance_of(account_id) == "100.00"


def test_same_reference_id_allowed_on_different_accounts(create_account, post_txn, balance_of):
    a, b = create_account("A"), create_account("B")

    assert post_txn(a, "credit", 10, "shared-ref").status_code == 201
    assert post_txn(b, "credit", 20, "shared-ref").status_code == 201
    assert balance_of(a) == "10.00"
    assert balance_of(b) == "20.00"


def test_transaction_on_unknown_account_is_404(post_txn):
    response = post_txn(MISSING_ID, "credit", 10, "r1")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


@pytest.mark.parametrize(
    "body, field",
    [
        ({"type": "refund", "amount": 10, "reference_id": "r"}, "type"),
        ({"amount": 10, "reference_id": "r"}, "type"),
        ({"type": "credit", "amount": 0, "reference_id": "r"}, "amount"),
        ({"type": "credit", "amount": -5, "reference_id": "r"}, "amount"),
        ({"type": "credit", "amount": "abc", "reference_id": "r"}, "amount"),
        ({"type": "credit", "amount": 1.005, "reference_id": "r"}, "amount"),
        ({"type": "credit", "reference_id": "r"}, "amount"),
        ({"type": "credit", "amount": 10}, "reference_id"),
        ({"type": "credit", "amount": 10, "reference_id": "  "}, "reference_id"),
        ({"type": "credit", "amount": 10, "reference_id": "r", "account_id": "x"}, "account_id"),
    ],
)
def test_invalid_transaction_payload(client, create_account, balance_of, body, field):
    account_id = create_account()

    response = client.post(f"/accounts/{account_id}/transactions", json=body)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in [d["field"] for d in error["details"]]
    assert balance_of(account_id) == "0.00"


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_transactions_cannot_be_edited_or_deleted_via_api(client, create_account, post_txn, method):
    account_id = create_account()
    txn_id = post_txn(account_id, "credit", 10, "r1").json()["transaction"]["id"]

    for path in (f"/accounts/{account_id}/transactions", f"/accounts/{account_id}/transactions/{txn_id}"):
        response = getattr(client, method)(path)
        assert response.status_code in (404, 405)

    history = client.get(f"/accounts/{account_id}/transactions").json()["data"]
    assert history[0]["amount"] == "10.00"
