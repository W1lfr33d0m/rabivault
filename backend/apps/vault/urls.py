from django.urls import path
from . import views

app_name = "vault"

urlpatterns = [
    path("", views.vault_dashboard, name="dashboard"),
    path("documents/", views.document_list, name="document_list"),
    path("documents/upload/", views.document_upload, name="document_upload"),
    path("folders/new/", views.folder_create, name="folder_create"),
    path("documents/<uuid:public_id>/", views.document_detail, name="document_detail"),
    path("documents/<uuid:public_id>/download/", views.document_download, name="document_download"),
    path("documents/<uuid:public_id>/delete/", views.document_delete, name="document_delete"),
]
