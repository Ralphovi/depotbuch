"""The JSON API. The OpenAPI spec is served at /api/openapi.json; the front end's client is
generated from it.
"""

from ninja import NinjaAPI, Schema

import depotbuch

api = NinjaAPI(title="depotbuch", version=depotbuch.__version__)


class Health(Schema):
    status: str
    version: str


@api.get("/health", response=Health, auth=None)
def health(request: object) -> Health:
    """Liveness probe for the container. Needs no login and reveals no portfolio data."""
    return Health(status="ok", version=depotbuch.__version__)
