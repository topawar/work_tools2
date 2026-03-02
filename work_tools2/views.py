from django.http import HttpResponse
from django.shortcuts import render
from work_tools2.models import Menu


def home(request):
    """Home page."""
    return render(request, "home.html", {"active_page": "home"})


def form_merge(request):
    """Runoob tutorial page."""
    return render(request, "form_merge.html", {"active_page": "form_merge"})


def dashboard(request):
    """Dashboard page with sidebar layout."""
    return render(request, "dashboard.html", {"active_page": "dashboard"})


def orders(request):
    """Orders list page."""
    return render(request, "orders.html", {"active_page": "orders_list"})


def get_menus():
    """获取菜单数据，用于侧边栏"""
    # 获取所有一级菜单（is_visible=True）
    parent_menus = Menu.objects.filter(parent__isnull=True, is_visible=True).order_by(
        "group_name", "sort_order"
    )

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
                "icon": menu.icon or "bi-circle",
                "url": menu.url,
                "has_children": children.exists(),
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

    return menus_by_group


def render_with_menus(request, template_name, context=None):
    """Render template with menu data"""
    if context is None:
        context = {}

    # 添加菜单数据
    context["menus"] = get_menus()

    return render(request, template_name, context)
