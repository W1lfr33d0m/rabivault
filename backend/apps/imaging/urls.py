from django.urls import path

from . import views

app_name = "imaging"

urlpatterns = [
    path("imaging/orthanc/", views.orthanc_redirect, name="orthanc_redirect"),
]
