"""Root URL configuration — all API endpoints live under /api/v1/."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1 = [
    path("auth/", include("authentication.urls")),
    path("", include("users.urls")),          # /doctors/, /parents/
    path("babies/", include("babies.urls")),
    path("bracelets/", include("bracelets.urls")),
    path("measurements/", include("measurements.urls")),
    path("alerts/", include("alerts.urls")),
    path("notifications/", include("notifications.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
