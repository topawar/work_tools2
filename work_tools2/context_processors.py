from work_tools2.models import Menu


def _resolve_menu_icon(menu):
    """根据菜单 URL 或名称解析合适的图标，避免一级菜单图标全部相同。"""
    icon = (menu.icon or "").strip()
    url = (menu.url or "").rstrip("/")
    name = menu.name or ""

    # URL 映射（优先按 URL 识别系统菜单）
    # 统一去掉尾部斜杠，根路径保留为 /
    normalized_url = url if url != "" else "/"
    url_mapping = {
        "/": "bi-house-door",
        "/form_merge": "bi-layers",
        "/document-library": "bi-journal-bookmark",
        "/table_config": "bi-grid-3x3-gap",
        "/component_config": "bi-puzzle",
        "/database_config": "bi-database",
        "/database-ip-config": "bi-hdd-network",
        "/file_path_config": "bi-folder",
        "/usage_statistics": "bi-graph-up-arrow",
    }
    if normalized_url in url_mapping:
        return url_mapping[normalized_url]

    # 父级容器菜单（URL 为 #，用于承载动态表单模块）统一使用文件夹图标，
    # 保证新增模块时侧边栏风格一致。
    if url == "#":
        return "bi-folder"

    # 保留自定义图标；无图标时兜底为文件夹
    return icon or "bi-folder"


def menus_context(request):
    """Context processor to add menus to all templates"""
    # 获取当前URL路径
    current_path = request.path

    # 获取所有一级菜单
    parent_menus = Menu.objects.filter(parent__isnull=True, is_visible=True).order_by(
        "group_name", "sort_order"
    )

    # 需要展开的菜单ID列表
    expanded_menu_ids = []

    # 检查当前URL是否匹配某个子菜单
    child_menus = Menu.objects.filter(parent__isnull=False, is_visible=True)
    for child in child_menus:
        if child.url:
            # 精确匹配或前缀匹配
            child_url = child.url.rstrip("/")
            if current_path.rstrip("/") == child_url or current_path.startswith(
                child_url + "/"
            ):
                if child.parent_id:
                    expanded_menu_ids.append(child.parent_id)
                break

    menus_by_group = {}
    for menu in parent_menus:
        group = menu.group_name or "其他"
        if group not in menus_by_group:
            menus_by_group[group] = []

        # 获取子菜单
        children = Menu.objects.filter(parent=menu, is_visible=True).order_by(
            "sort_order"
        )

        # 判断当前路径是否与菜单 URL 匹配（兼容带/不带尾部斜杠）
        def _is_active(menu_url):
            if not menu_url:
                return False
            return current_path.rstrip("/") == menu_url.rstrip("/")

        is_menu_active = _is_active(menu.url)
        resolved_icon = _resolve_menu_icon(menu)

        menus_by_group[group].append(
            {
                "id": menu.id,
                "name": menu.name,
                "pinyin": menu.pinyin or "",
                "icon": menu.icon or "",
                "resolved_icon": resolved_icon,
                "url": menu.url,
                "has_children": children.exists(),
                "is_expanded": menu.id in expanded_menu_ids,
                "is_active": is_menu_active,
                "children": [
                    {
                        "id": child.id,
                        "name": child.name,
                        "pinyin": child.pinyin or "",
                        "icon": child.icon or "",
                        "resolved_icon": resolved_icon,
                        "url": child.url,
                        "is_active": _is_active(child.url),
                    }
                    for child in children
                ],
            }
        )

    return {"menus": menus_by_group}
