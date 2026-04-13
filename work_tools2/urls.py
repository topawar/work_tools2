from django.shortcuts import render

from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("form_merge/", views.form_merge, name="form_merge"),
    path("table_config/", views.table_config, name="table_config"),
    path("component_config/", views.component_config, name="component_config"),
    path("database_config/", views.database_config_page, name="database_config"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dynamic/<str:form_id>", views.dynamic, name="dynamic"),
    path("api/dynamic/submit/", views.dynamic_submit, name="dynamic_submit"),
    path("api/dynamic/download-template/", views.download_template, name="download_template"),
    path("api/dynamic/batch-import/", views.batch_import, name="batch_import"),
    path("api/dynamic/download-failed-file/", views.download_failed_file, name="download_failed_file"),
    path("api/form-configs/", views.get_form_configs, name="get_form_configs"),
    path("file_path_config/", views.file_path_config, name="file_path_config"),
    path("api/form-config/save/", views.save_form_config, name="save_form_config"),
    path("api/form-config/delete/<str:form_id>/", views.delete_form_config, name="delete_form_config"),
    path("api/form-config/<str:form_id>/", views.get_form_config_detail, name="get_form_config_detail"),
    path("api/menu-list/", views.get_menu_list, name="get_menu_list"),
    path("api/menu/create-or-get/", views.create_or_get_menu, name="create_or_get_menu"),
    # 数据库表和字段API
    path("api/database/tables/", views.get_database_tables, name="get_database_tables"),
    path("api/database/table-fields/", views.get_table_fields, name="get_table_fields"),
    path("api/supplement/query/", views.query_supplement_data, name="query_supplement_data"),
    path("api/supplement/batch-query/", views.batch_query_supplement_data, name="batch_query_supplement_data"),
    # 表单合并API
    path("api/form-merge/download-template/", views.download_merge_template, name="download_merge_template"),
    path("api/form-merge/batch-import/", views.batch_import_merge, name="batch_import_merge"),
    # 组件配置相关API
    path("api/components/", views.get_components, name="get_components"),
    path("api/components/<int:component_id>/", views.get_component_detail, name="get_component_detail"),
    path("api/components/save/", views.save_component, name="save_component"),
    path("api/components/delete/<int:component_id>/", views.delete_component, name="delete_component"),
    path("api/components/<int:component_id>/usage/", views.get_component_usage, name="get_component_usage"),
    path("api/components/import-options/", views.import_options_from_excel, name="import_options_from_excel"),
    # 数据库管理API
    path("api/db/table-list/", views.get_table_list, name="get_table_list"),
    path("api/db/create-table/", views.create_table, name="create_table"),
    path("api/db/table-structure/", views.get_table_structure, name="get_table_structure"),
    path("api/db/update-table/", views.update_table_structure, name="update_table_structure"),
    path("api/db/delete-table/", views.delete_table, name="delete_table"),
    path("api/db/truncate-table/", views.truncate_table, name="truncate_table"),
    path("api/db/import-csv/", views.import_csv_data, name="import_csv_data"),
    path("api/db/statistics/", views.get_database_statistics, name="get_database_statistics"),
    path("api/db/execute-sql/", views.execute_sql_query, name="execute_sql_query"),
    # 在 urls.py 中添加
    path('api/db/task-status/', views.get_import_task_status, name='get_import_task_status'),
    path('api/db/tasks-list/', views.get_import_tasks_list, name='get_import_tasks_list'),
    # 查询SQL保存/加载
    path('api/db/save-query-sql/', views.save_query_sql, name='save_query_sql'),
    path('api/db/load-query-sql/', views.load_query_sql, name='load_query_sql'),
    # 数据库IP配置API
    path("api/database-ip-configs/", views.get_database_ip_configs, name="get_database_ip_configs"),
    path("api/database-ip-config/save/", views.save_database_ip_config, name="save_database_ip_config"),
    path("api/database-ip-config/delete/<int:config_id>/", views.delete_database_ip_config,
         name="delete_database_ip_config"),
    path("api/database-ip-config/<int:config_id>/", views.get_database_ip_config_detail,
         name="get_database_ip_config_detail"),
    # 文件路径配置API
    path("api/file-path-configs/", views.get_file_path_configs, name="get_file_path_configs"),
    path("api/file-path-configs/<int:config_id>/", views.get_file_path_config, name="get_file_path_config"),
    path("api/file-path-configs/save/", views.save_file_path_config, name="save_file_path_config"),
    path("api/file-path-configs/save/<int:config_id>/", views.save_file_path_config, name="save_file_path_config"),
    path("api/file-path-configs/delete/<int:config_id>/", views.delete_file_path_config,
         name="delete_file_path_config"),
    path("api/file-path-configs/default/", views.get_default_file_path_config, name="get_default_file_path_config"),
    path("api/file-path-configs/select-directory/", views.select_directory_dialog, name="select_directory_dialog"),

]
