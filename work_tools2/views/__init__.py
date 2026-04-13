from .page_views import home, form_merge, table_config, dashboard, dynamic, component_config,file_path_config
from .page_views import database_config as database_config_page
from .form_config_views import (
    get_form_configs,
    get_form_config_detail,
    save_form_config,
    delete_form_config,
    get_menu_list,
    create_or_get_menu,
    get_database_tables,
    get_table_fields,
    query_supplement_data,
    batch_query_supplement_data
)
from .form_merge_views import (
    download_merge_template,
)
from .form_merge_batch import (
    batch_import_merge,
)
from .dynamic_views import (
    dynamic_submit,
    download_template,
    batch_import,
    download_failed_file,
)
from .component_views import (
    get_components,
    get_component_detail,
    save_component,
    delete_component,
    get_component_usage,
    import_options_from_excel,
)
from .database_config import (
    get_table_list,
    create_table,
    get_table_structure,
    update_table_structure,
    delete_table,
    truncate_table,
    import_csv_data,
    get_database_statistics,
    execute_sql_query,
    get_import_task_status,
    get_import_tasks_list,
    save_query_sql,
    load_query_sql
)
from .database_ip_config import (
    get_database_ip_configs,
    save_database_ip_config,
    delete_database_ip_config,
    get_database_ip_config_detail,
)
# 1. 使用不同的别名导入模块，避免与函数名冲突
from . import file_path_config as file_path_config_api
# 2. 显式导出 API 中的函数
from .file_path_config import (
    get_file_path_configs,
    get_file_path_config,
    save_file_path_config,
    delete_file_path_config,
    get_default_file_path_config,
    select_directory_dialog
)
# 3. 导入页面渲染函数
from .page_views import file_path_config

__all__ = [
    'home', 'form_merge', 'table_config', 'dashboard', 'dynamic',
    'get_form_configs', 'get_form_config_detail', 'save_form_config', 'delete_form_config',
    'get_menu_list', 'create_or_get_menu', 'get_database_tables', 'get_table_fields',
    'dynamic_submit', 'download_template', 'batch_import', 'download_failed_file', 'component_config',
    'get_components', 'get_component_detail', 'save_component', 'delete_component', 'get_component_usage',
    'import_options_from_excel', 'query_supplement_data', 'batch_query_supplement_data',
    'database_config_page',
    'get_table_list', 'create_table', 'get_table_structure', 'update_table_structure',
    'delete_table', 'truncate_table', 'import_csv_data', 'get_database_statistics', 'execute_sql_query',
    'get_import_task_status','get_import_tasks_list',
    'save_query_sql', 'load_query_sql',
    'download_merge_template', 'batch_import_merge',
    'get_database_ip_configs', 'save_database_ip_config', 'delete_database_ip_config', 'get_database_ip_config_detail',
    # 4. 正确暴露页面函数和模块别名
    'file_path_config', 'file_path_config_api',
    # 5. 直接暴露 API 函数以便路由使用
    'get_file_path_configs', 'get_file_path_config', 'save_file_path_config',
    'delete_file_path_config', 'get_default_file_path_config', 'select_directory_dialog'
]