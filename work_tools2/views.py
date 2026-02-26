from django.http import HttpResponse
from django.shortcuts import render


def hello(request):
    """Home page."""
    return render(request, "home.html", {"active_page": "home"})


def form_merge(request):
    """Runoob tutorial page."""
    return render(request, "form_merge.html", {"active_page": "form_merge"})


def dashboard(request):
    """Dashboard page with sidebar layout."""



def orders(request):
    """Orders list page."""
    return render(request, "orders.html", {"active_page": "orders_list"})
