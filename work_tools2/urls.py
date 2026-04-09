from django.shortcuts import render

from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("form_merge/", views.form_merge, name="form_merge"),
    path("table_config/", views.table_config, name="table_config"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dynamic/<str:form_id>", views.dynamic, name="dynamic"),
    path("api/dynamic/submit/", views.dynamic_submit, name="dynamic_submit"),
    path("api/dynamic/download-template/", views.download_template, name="download_template"),
    path("api/dynamic/batch-import/", views.batch_import, name="batch_import"),
    path("api/dynamic/download-failed-file/", views.download_failed_file, name="download_failed_file"),
    path("api/form-configs/", views.get_form_configs, name="get_form_configs"),
    path("api/form-config/<str:form_id>/", views.get_form_config_detail, name="get_form_config_detail"),
    path("api/form-config/save/", views.save_form_config, name="save_form_config"),
    path("api/form-config/delete/<str:form_id>/", views.delete_form_config, name="delete_form_config"),
]

