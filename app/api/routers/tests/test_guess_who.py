from app.core import security
#TODO: add unit test


def test_wrong_login(client, test_db, test_user, test_password):
    response = client.post(
        "/api/token", data={"username": "fakeuser", "password": test_password}
    )
    assert response.status_code == 401
