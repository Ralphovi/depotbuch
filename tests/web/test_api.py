import pytest
from django.contrib.auth.models import User
from django.test import Client

import depotbuch


def test_health_needs_no_login() -> None:
    response = Client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": depotbuch.__version__}


@pytest.mark.parametrize("url", ["/api/openapi.json", "/api/docs"])
def test_schema_and_docs_redirect_anonymous_users_to_login(url: str) -> None:
    response = Client().get(url)
    assert response.status_code == 302
    assert response["Location"].startswith("/admin/login/")


@pytest.mark.django_db
def test_schema_is_served_to_staff() -> None:
    client = Client()
    client.force_login(User.objects.create_user("owner", is_staff=True))
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "depotbuch"
