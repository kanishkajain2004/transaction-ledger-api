import uuid

MISSING_ID = "00000000-0000-0000-0000-000000000000"


def test_create_account_starts_with_zero_balance(client):
    response = client.post("/accounts", json={"name": "  Alice  "})

    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["id"])
    assert body["name"] == "Alice"
    assert body["balance"] == "0.00"
    assert body["created_at"]


def test_account_ids_are_unique(create_account):
    assert create_account("A") != create_account("B")


def test_client_cannot_set_initial_balance(client):
    response = client.post("/accounts", json={"name": "Bob", "balance": 1000})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == "balance"


def test_client_cannot_set_id_or_created_at(client):
    response = client.post(
        "/accounts", json={"name": "Bob", "id": str(uuid.uuid4()), "created_at": "2020-01-01T00:00:00Z"}
    )
    assert response.status_code == 400


def test_name_is_required(client):
    for body in ({}, {"name": ""}, {"name": "   "}, {"name": None}):
        response = client.post("/accounts", json=body)
        assert response.status_code == 400, body
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_json_body(client):
    response = client.post("/accounts", content="{bad", headers={"content-type": "application/json"})

    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "body"


def test_get_account_and_balance(client, create_account):
    account_id = create_account()

    assert client.get(f"/accounts/{account_id}").json()["id"] == account_id
    assert client.get(f"/accounts/{account_id}/balance").json() == {
        "account_id": account_id,
        "balance": "0.00",
    }


def test_balance_of_unknown_account_is_404(client):
    response = client.get(f"/accounts/{MISSING_ID}/balance")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_malformed_account_id_is_400(client):
    response = client.get("/accounts/not-a-uuid/balance")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
