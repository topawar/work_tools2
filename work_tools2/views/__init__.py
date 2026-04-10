from .page_views import home, form_merge, table_config, dashboard, dynamic,component_config
from .form_config_views import (
    get_form_configs,
    get_form_config_detail,
    save_form_config,
    delete_form_config,
    get_menu_list,
    create_or_get_menu,
)
from .dynamic_views import (
    dynamic_submit,
    download_template,
    batch_import,
    download_failed_file,
)

__all__ = [
    'home', 'form_merge', 'table_config', 'dashboard', 'dynamic',
    'get_form_configs', 'get_form_config_detail', 'save_form_config', 'delete_form_config',
    'get_menu_list', 'create_or_get_menu',
    'dynamic_submit', 'download_template', 'batch_import', 'download_failed_file','component_config'
]
