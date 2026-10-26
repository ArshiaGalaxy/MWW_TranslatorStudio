"""URL configuration for MWW Translator Studio backend."""

from django.urls import include, path

from studio.views import media_file

urlpatterns = [
    path("api/", include("studio.urls")),
    path("media/<path:file_path>", media_file),
]
