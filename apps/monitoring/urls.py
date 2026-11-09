from django.urls import path

from .views import ClientErrorView

urlpatterns = [path("client-errors/", ClientErrorView.as_view(), name="client-errors")]
