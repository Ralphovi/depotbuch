from django.test import Client

import depotbuch


def test_health_needs_no_login() -> None:
    response = Client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": depotbuch.__version__}


def test_openapi_schema_is_served() -> None:
    response = Client().get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "depotbuch"
