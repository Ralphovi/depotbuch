from django.contrib import admin
from django.urls import URLPattern, URLResolver, path

from depotbuch.web.api import api

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
