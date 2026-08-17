from django.urls import path

from . import views

app_name = "imaging"

urlpatterns = [
    path("imaging/orthanc/", views.orthanc_redirect, name="orthanc_redirect"),
    path("imaging/studies/", views.imaging_study_list, name="study_list"),
    path("imaging/studies/<int:pk>/open/", views.imaging_study_open, name="study_open"),

    path("imaging/orthanc-auth/user/get-profile", views.orthanc_auth_user_profile, name="orthanc_auth_user_profile"),
    path("imaging/orthanc-auth/tokens/validate", views.orthanc_auth_token_validate, name="orthanc_auth_token_validate"),
    path("imaging/orthanc-auth/tokens/decode", views.orthanc_auth_token_decode, name="orthanc_auth_token_decode"),
]
