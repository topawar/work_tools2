from django.shortcuts import render
from django.middleware.csrf import get_token


def home(request):
    """Home page."""
    return render(request, "home.html", {"active_page": "home"})


def form_merge(request):
    """Runoob tutorial page."""
    return render(request, "form_merge.html", {"active_page": "form_merge"})


def table_config(request):
    """Runoob tutorial page."""
    # 确保设置 CSRF cookie
    response = render(request, "table_config.html", {"active_page": "table_config"})
    get_token(request)  # 这会强制设置 CSRF cookie
    return response


def dashboard(request):
    """Dashboard page with sidebar layout."""
    return render(request, "dashboard.html", {"active_page": "dashboard"})


def dynamic(request, form_id: str):
    """Orders list page."""
    return render(request, "dynamic.html", {"active_page": "dynamic", "form_id": form_id})



def component_config(request: str):
    """Orders list page."""
    return render(request, "component_config.html", {"active_page": "component_config"})

def database_config(request: str):
    """Orders list page."""
    return render(request, "database_config.html", {"active_page": "database_config"})


def file_path_config(request: str):
    """Orders list page."""
    return render(request, "file_path_config.html", {"active_page": "file_path_config"})
