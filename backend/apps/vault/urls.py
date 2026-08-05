from django.urls import path
from . import api, views

app_name = "vault"

urlpatterns = [
    path("", views.vault_dashboard, name="dashboard"),
    path("documents/", views.document_list, name="document_list"),
    path("documents/upload/", views.document_upload, name="document_upload"),
    path("folders/new/", views.folder_create, name="folder_create"),
    path("documents/<uuid:public_id>/", views.document_detail, name="document_detail"),
    path("documents/<uuid:public_id>/download/", views.document_download, name="document_download"),
    path("documents/<uuid:public_id>/delete/", views.document_delete, name="document_delete"),

    path("documents/api/tree/", api.folder_tree, name="api_folder_tree"),
    path("documents/api/contents/", api.folder_contents, name="api_folder_contents"),
    path("documents/api/move/", api.document_move, name="api_document_move"),
    path("documents/api/rename/", api.document_rename, name="api_document_rename"),
    path("folders/api/move/", api.folder_move, name="api_folder_move"),
    path("folders/api/rename/", api.folder_rename, name="api_folder_rename"),
    path("folders/api/delete/", api.folder_delete, name="api_folder_delete"),
]
