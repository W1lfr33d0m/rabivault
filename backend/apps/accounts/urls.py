from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("mfa/setup/", views.mfa_setup, name="mfa_setup"),
    path("mfa/verify/", views.mfa_verify, name="mfa_verify"),
]
