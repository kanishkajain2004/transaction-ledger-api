MISSING_ID = "00000000-0000-0000-0000-000000000000"


def transfer(client, from_id, to_id, amount, reference_id="t1"):
    return client.post(
        "/transfers",
        json={"from_account_id": from_id, "to_account_id": to_id, "amount": amount, "reference_id": reference_id},
    )


def funded_pair(create_account, post_txn):
    a, b = create_account("A"), create_account("B")
    post_txn(a, "credit", 100, "seed")
    post_txn(b, "credit", 50, "seed")
    return a, b


def test_transfer_moves_money(client, create_account, post_txn, balance_of):
    a, b = funded_pair(create_account, post_txn)

    response = transfer(client, a, b, 30)

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == "30.00"
    assert body["from_account_balance"] == "70.00"
    assert body["to_account_balance"] == "80.00"
    assert body["debit_transaction"]["type"] == "debit"
    assert body["debit_transaction"]["account_id"] == a
    assert body["credit_transaction"]["type"] == "credit"
    assert body["credit_transaction"]["account_id"] == b
    assert balance_of(a) == "70.00"
    assert balance_of(b) == "80.00"


def test_transfer_with_insufficient_balance_changes_nothing(client, create_account, post_txn, balance_of):
    a, b = funded_pair(create_account, post_txn)

    response = transfer(client, a, b, 101)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert (balance_of(a), balance_of(b)) == ("100.00", "50.00")


def test_transfer_requires_both_accounts_to_exist(client, create_account, post_txn, balance_of):
    a, _ = funded_pair(create_account, post_txn)

    to_missing = transfer(client, a, MISSING_ID, 10)
    from_missing = transfer(client, MISSING_ID, a, 10)

    assert to_missing.status_code == 404
    assert from_missing.status_code == 404
    assert balance_of(a) == "100.00"


def test_transfer_to_same_account_is_rejected(client, create_account, post_txn):
    a, _ = funded_pair(create_account, post_txn)

    response = transfer(client, a, a, 10)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_retrying_a_transfer_does_not_move_money_twice(client, create_account, post_txn, balance_of):
    a, b = funded_pair(create_account, post_txn)
    transfer(client, a, b, 30, "t1")

    retry = transfer(client, a, b, 30, "t1")

    assert retry.status_code == 409
    assert (balance_of(a), balance_of(b)) == ("70.00", "80.00")


def test_failure_after_debit_rolls_back_the_whole_transfer(client, create_account, post_txn, balance_of):
    """The credit leg fails (reference already used on B) after the debit leg was staged on A."""
    a, b = funded_pair(create_account, post_txn)
    post_txn(b, "credit", 1, "clash")

    response = transfer(client, a, b, 10, "clash")

    assert response.status_code == 409
    assert (balance_of(a), balance_of(b)) == ("100.00", "51.00")
    a_refs = [t["reference_id"] for t in client.get(f"/accounts/{a}/transactions").json()["data"]]
    assert "clash" not in a_refs


def test_invalid_transfer_amount(client, create_account, post_txn):
    a, b = funded_pair(create_account, post_txn)

    assert transfer(client, a, b, 0).status_code == 400
    assert transfer(client, a, b, -1).status_code == 400
