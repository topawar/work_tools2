# AGENTS.md - Development Guide for work_tools2

Coding guidelines and commands for agentic coding agents.

## Project Overview

- **Type**: Django web application (Python)
- **Django Version**: 6.0.2
- **Database**: SQLite (db.sqlite3)
- **Virtual Environment**: `.venv/`

## Build / Run Commands

### Development Server
```bash
python manage.py runserver           # Default port 8000
python manage.py runserver 8080     # Custom port
```

### Database Operations
```bash
python manage.py migrate            # Apply migrations
python manage.py makemigrations     # Create migrations
python manage.py showmigrations     # Show migration status
python manage.py createsuperuser    # Create admin user
```

### Testing

**No test framework configured.** To add testing:

```bash
pip install pytest pytest-django
pytest                              # Run all tests
pytest path/to/test_file.py         # Run single file
pytest path/to/test_file.py::test_function_name  # Run single test
```

**pytest.ini (create in root):**
```ini
[pytest]
DJANGO_SETTINGS_MODULE = work_tools2.settings
python_files = tests.py test_*.py *_tests.py
```

### Linting (Not Configured)

```bash
pip install flake8 black mypy isort
flake8 .    # PEP 8 style
black .     # Code formatting
isort .     # Import sorting
mypy .      # Type checking
```

## Code Style Guidelines

### General
- Follow PEP 8 style guide
- Use 4 spaces for indentation (not tabs)
- Max line length: 100 characters (soft limit: 120)
- Use trailing commas in multi-line structures

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Functions/variables | snake_case | `get_user()`, `total_count` |
| Classes | PascalCase | `UserProfile`, `OrderItem` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRIES` |
| Django models | PascalCase | `class User(models.Model):` |
| Model fields | snake_case | `first_name = models.CharField()` |
| Private methods | _prefix | `_internal_method()` |

### Imports (Order: stdlib → third-party → local)
```python
import os
import sys
from datetime import datetime
from typing import Optional, List

from django.db import models
from django.http import HttpResponse

from . import views
from .models import User
```

### Django Patterns

**Models:**
```python
from django.db import models

class MyModel(models.Model):
    """Model description."""
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'My Model'
        verbose_name_plural = 'My Models'

    def __str__(self):
        return self.name
```

**Views:**
```python
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views import View

def my_view(request):
    """Handle GET requests."""
    return HttpResponse("Hello!")

class MyFormView(View):
    def get(self, request):
        return render(request, 'template.html')
    def post(self, request):
        return HttpResponse("Posted!")
```

**URLs:**
```python
from django.urls import path
from . import views

app_name = 'my_app'
urlpatterns = [
    path('', views.my_view, name='index'),
    path('detail/<int:pk>/', views.detail, name='detail'),
]
```

### Error Handling
```python
# Prefer Django's built-in handling
from django.shortcuts import get_object_or_404
obj = get_object_or_404(MyModel, pk=pk)

# When catching exceptions:
try:
    result = risky_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    raise MyCustomError("Fallback") from e
```

### Type Annotations
```python
from typing import Optional

def greet(name: str) -> str:
    return f"Hello, {name}!"

def process_items(items: list[dict]) -> Optional[int]:
    if not items:
        return None
    return len(items)
```

### Database Queries
```python
# Prefer Django ORM
User.objects.filter(is_active=True).order_by('-date_joined')
Post.objects.select_related('author').all()
User.objects.values_list('username', flat=True)
```

## File Structure
```
work_tools2/
├── manage.py              # Django management
├── db.sqlite3             # SQLite database
├── work_tools2/          # Main project
│   ├── settings.py
│   ├── urls.py
│   ├── models.py
│   ├── views.py
│   └── migrations/
├── templates/             # HTML templates
└── static/               # CSS, JS, images
```

## Important Notes

- **No linting/testing** - Add flake8, black, pytest as needed
- **No pre-commit hooks**
- **DEBUG=True** - Change to False in production
- **ALLOWED_HOSTS=[]** - Configure for production
