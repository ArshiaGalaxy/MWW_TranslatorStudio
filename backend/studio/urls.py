"""URL configuration for the studio API.

All API routes intentionally have NO trailing slash: the Next.js dev proxy
normalizes URLs by stripping trailing slashes, so keeping routes slash-free
makes them work identically through the proxy and directly.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=False)
router.register(r"projects", views.ProjectViewSet, basename="project")
router.register(r"jobs", views.JobViewSet, basename="job")

blocks_router = DefaultRouter(trailing_slash=False)
blocks_router.register(r"blocks", views.TextBlockViewSet, basename="project-blocks")

pages_router = DefaultRouter(trailing_slash=False)
pages_router.register(r"pages", views.PageViewSet, basename="project-pages")

masks_router = DefaultRouter(trailing_slash=False)
masks_router.register(r"masks", views.MaskMarkViewSet, basename="project-masks")

urlpatterns = [
    # Global config & fonts
    path("config", views.ConfigView.as_view()),
    path("config/test-provider", views.ConfigTestProviderView.as_view()),
    path("fonts", views.FontsView.as_view()),
    path("fonts/<str:name>", views.font_file),
    # Chapter discovery (no project required)
    path("chapter-images", views.discover_chapter_images),
    # Nested project resources
    path("projects/<uuid:project_pk>/", include(blocks_router.urls)),
    path("projects/<uuid:project_pk>/", include(pages_router.urls)),
    path("projects/<uuid:project_pk>/", include(masks_router.urls)),
    # Projects + jobs
    path("", include(router.urls)),
]
