from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.reports.urls")),
    path("api/v1/", include("apps.iperc.urls")),
    path("api/v1/", include("apps.epp.urls")),
    path("api/v1/", include("apps.inspections.urls")),
    path("api/v1/", include("apps.experiments.urls")),
    path("api/v1/", include("apps.committee.urls")),
    path("api/v1/", include("apps.exports.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
