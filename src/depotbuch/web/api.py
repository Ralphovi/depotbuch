"""The JSON API, with its OpenAPI schema at /api/openapi.json."""

from django.contrib.admin.views.decorators import staff_member_required
from ninja import NinjaAPI, Schema

import depotbuch

# The schema (/api/openapi.json) and the Swagger UI (/api/docs) describe every endpoint,
# so they need the admin login like the data does. The front end's client is generated
# from the schema at build time, not fetched from a running server.
api = NinjaAPI(
    title="depotbuch",
    version=depotbuch.__version__,
    docs_decorator=staff_member_required,
)


class Health(Schema):
    status: str
    version: str


@api.get("/health", response=Health, auth=None)
def health(request: object) -> Health:
    """Liveness probe for the container. Needs no login and reveals no portfolio data."""
    return Health(status="ok", version=depotbuch.__version__)
