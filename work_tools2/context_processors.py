from work_tools2.models import Menu


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

        menus_by_group[group].append(
            {
                "id": menu.id,
                "name": menu.name,
                "pinyin": menu.pinyin or "",
                "url": menu.url,
                "has_children": children.exists(),
                "is_expanded": menu.id in expanded_menu_ids,
                "children": [
                    {
                        "id": child.id,
                        "name": child.name,
                        "pinyin": child.pinyin or "",
                        "url": child.url,
                    }
                    for child in children
                ],
            }
        )

    return {"menus": menus_by_group}
