from django.shortcuts import render


def home(request):
    """Home page."""
    return render(request, "home.html", {"active_page": "home"})


def form_merge(request):
    """Runoob tutorial page."""
    return render(request, "form_merge.html", {"active_page": "form_merge"})


def table_config(request):
    """Runoob tutorial page."""
    return render(request, "table_config.html", {"active_page": "table_config"})


def dashboard(request):
    """Dashboard page with sidebar layout."""
    return render(request, "dashboard.html", {"active_page": "dashboard"})


def dynamic(request, form_id: str):
    """Orders list page."""
    return render(request, "dynamic.html", {"active_page": "dynamic"})


def component_config(request: str):
    """Orders list page."""
    return render(request, "component_config.html", {"active_page": "component_config"})