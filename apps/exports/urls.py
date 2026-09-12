from django.urls import path

from .views import (
    CommitteeExportView,
    EppExportView,
    InspectionsExportView,
    IpercExportView,
    ReportsExportView,
)

urlpatterns = [
    path("exports/reports.xlsx", ReportsExportView.as_view(), name="export-reports"),
    path("exports/iperc.xlsx", IpercExportView.as_view(), name="export-iperc"),
    path("exports/epp.xlsx", EppExportView.as_view(), name="export-epp"),
    path("exports/inspections.xlsx", InspectionsExportView.as_view(), name="export-inspections"),
    path("exports/committee.xlsx", CommitteeExportView.as_view(), name="export-committee"),
]
