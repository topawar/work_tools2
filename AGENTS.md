# Work Tools 2 - AI Agent 项目指南

## 项目概述

Work Tools 2 是一个基于 Django 开发的桌面端 Web 管理工具系统，主要面向 Windows 环境运行。该项目通过 PyInstaller 打包为独立的可执行文件夹，目标是在没有 Python 环境的 PC 上直接运行。

核心业务功能包括：
- **动态表单配置**：通过可视化配置生成数据库查询和更新 SQL，支持批量导入 Excel 生成 SQL 语句。
- **表单合并**：支持多表单合并导入，将多个 Sheet 的 Excel 数据批量处理为 SQL。
- **数据库管理**：内置 SQLite 数据库管理界面，支持表结构查看、创建、修改、删除、CSV 导入、SQL 执行、导入任务队列、SQL 查询保存等。
- **组件配置**：可复用的下拉框、单选框等表单组件配置管理。
- **数据库 IP 配置**：管理外部数据库 IP 和数据库名配置，用于动态表单的数据库连接。
- **文件路径配置**：管理文件输出路径，支持单一文件夹和按日期分层保存模式。
- **菜单管理**：动态侧边栏菜单，支持分组和拼音搜索。

项目文档、代码注释和模板文本主要使用中文。

## 技术栈

- **后端框架**：Django（`requirements.txt` 锁定为 `6.0.2`；`settings.py` 文件头部注释显示由 Django 5.2.8 生成，实际运行时以 `requirements.txt` 为准）
- **数据库**：SQLite3（本地文件 `db.sqlite3`）
- **前端**：Bootstrap 5 + Bootstrap Icons + 原生 JavaScript（无 Vue/React 等前端框架）
- **前端额外库**：axios、Sortable、jQuery、Layui，以及 luckysheet/sheetjs/x-spreadsheet 等表格处理库
- **Excel 处理**：openpyxl、xlrd
- **拼音转换**：pypinyin（用于菜单搜索）
- **SQL 格式化**：sqlparse
- **打包工具**：PyInstaller 6.19.0
- **开发环境**：Windows 10/11，Python 3.8+

## 项目结构

```
work_tools2/
├── manage.py                  # Django 命令行入口，默认端口 9123
├── launcher.py                # 启动器脚本，用于打包后启动 Django 服务器并自动打开浏览器
├── build.py                   # PyInstaller 打包脚本（主打包逻辑）
├── build_simple.bat           # 一键打包批处理（调用 build.py）
├── create_bat.py              # 生成 build_simple.bat 的辅助脚本（以 GBK 编码写入）
├── WorkTools.spec             # PyInstaller 配置文件（build.py 每次运行会删除旧 spec 并重新生成）
├── check_package.py           # 打包结果验证脚本
├── requirements.txt           # Python 依赖列表
├── db.sqlite3                 # SQLite 数据库文件
├── 使用说明.txt                # 中文使用说明（会被复制到打包输出目录）
│
├── work_tools2/               # Django 项目主应用（同时作为应用模块）
│   ├── settings.py            # Django 配置（DEBUG=True，SQLite，中文模板）
│   ├── urls.py                # 路由配置（页面路由 + API 路由）
│   ├── wsgi.py                # WSGI 入口
│   ├── models.py              # 数据模型：FormConfig、FormQueryItem、FormUpdateItem、ComponentConfig、Menu、DatabaseIPConfig、FilePathConfig
│   ├── views/                 # 视图模块（按功能拆分）
│   │   ├── __init__.py        # 统一导出所有视图函数
│   │   ├── page_views.py      # 页面渲染视图（home、form_merge、table_config、dynamic 等）
│   │   ├── dynamic_views.py   # 动态表单核心逻辑（SQL 生成、Excel 导入/导出、失败文件下载）
│   │   ├── form_config_views.py # 表单配置 CRUD、菜单管理、数据库表字段 API、补充数据查询、配置导入导出
│   │   ├── form_merge_views.py # 表单合并模板下载
│   │   ├── form_merge_batch.py # 表单合并批量导入
│   │   ├── form_merge.py      # 空文件（当前未使用）
│   │   ├── component_views.py # 组件配置 CRUD、Excel 导入选项
│   │   ├── database_config.py # 数据库管理（SQLite 表操作、CSV 导入、SQL 执行、导入任务、查询 SQL 保存）
│   │   ├── database_ip_config.py # 数据库 IP 配置管理
│   │   └── file_path_config.py # 文件路径配置管理
│   ├── path_utils.py          # 文件路径生成工具（日期分层、周格式等）
│   ├── context_processors.py  # 全局菜单上下文处理器
│   ├── task.py                # 异步 CSV 导入任务队列（后台线程）
│   └── migrations/            # Django 数据库迁移文件（当前到 0012）
│
├── templates/                 # HTML 模板
│   ├── base.html              # 基础布局（侧边栏 + 主内容区）
│   ├── home.html              # 首页
│   ├── dynamic.html           # 动态表单页面（最大最复杂的前端页面）
│   ├── table_config.html      # 表单配置管理页面
│   ├── form_merge.html        # 表单合并页面
│   ├── component_config.html  # 组件配置页面
│   ├── database_config.html   # 数据库管理页面
│   └── file_path_config.html  # 文件路径配置页面
│   └── (dashboard.html 缺失：urls.py 中注册了 dashboard/ 路由，但 templates/ 下无对应文件)
│
├── static/                    # 静态文件
│   ├── css/                   # Bootstrap 5 CSS
│   ├── js/                    # Bootstrap JS、axios、Sortable、index.js、jQuery、表格处理库等
│   ├── fonts/                 # 字体文件
│   ├── bootstrap-icons-1.13.1/ # Bootstrap 图标字体
│   ├── layui/                 # Layui 前端组件库（部分页面使用）
│   ├── sql/                   # SQL 示例文件
│   └── batch_results/         # 批量结果目录
│
├── batch_results/             # 批量导入生成的 SQL 文件存放目录
└── 临时文件/                   # 运行时临时文件
```

## 关键配置文件

本项目没有 `pyproject.toml`、`package.json`、`Cargo.toml` 等现代语言配置文件，主要配置如下：

### Django 设置（work_tools2/settings.py）

- `SECRET_KEY`：硬编码的开发密钥（生产环境需修改）。
- `DEBUG = True`：调试模式始终开启。
- `ALLOWED_HOSTS = []`：未配置允许主机。
- `DATABASES`：使用本地 `db.sqlite3`。
- `STATIC_URL = "/static/"`，`STATICFILES_DIRS` 指向项目根目录的 `static/` 文件夹。
- `TEMPLATES` 的 `DIRS` 指向项目根目录的 `templates/` 文件夹。
- `INSTALLED_APPS` 包含 Django 内置应用（admin、auth、contenttypes、sessions、messages、staticfiles）和 `work_tools2` 自身。
- 自定义上下文处理器 `work_tools2.context_processors.menus_context` 为所有模板注入侧边栏菜单。

### 运行端口

- 开发环境：`manage.py` 中设置 `Runserver.default_port = "9123"`。
- 打包后：`launcher.py` 启动 `runserver 127.0.0.1:9123 --noreload`，并在 3 秒后自动打开浏览器。

### 依赖管理

- `requirements.txt`：Python 依赖列表，包含 Django 6.0.2、PyInstaller 6.19.0、openpyxl、xlrd、pypinyin、sqlparse 等。
- `build.py` 在打包时若 `requirements.txt` 不存在会自动生成，但存在时不会更新。

## 构建、运行和测试命令

### 开发环境运行

```bash
# 确保在虚拟环境中并已安装依赖
pip install -r requirements.txt

# 数据库迁移
python manage.py makemigrations
python manage.py migrate

# 启动开发服务器（默认 9123 端口）
python manage.py runserver
# 或指定端口
python manage.py runserver 127.0.0.1:9123
```

### 一键打包（推荐）

```batch
# Windows 环境下双击或命令行执行
build_simple.bat
```

`build_simple.bat` 实际调用 `build.py`，`build.py` 会：
1. 检查 Python 环境
2. 安装 PyInstaller
3. 若不存在则生成 `requirements.txt`
4. 清理旧的 `dist/`、`build/` 目录和已有的 `*.spec` 文件
5. 使用 PyInstaller 以 `--onedir` 模式打包 `launcher.py` 为 `WorkTools.exe`
6. 复制 `db.sqlite3`、`使用说明.txt` 到输出目录，并生成英文 `README.txt`
7. 验证必要目录和文件

打包输出目录：`dist/WorkTools/`

### 打包验证

```bash
python check_package.py
```

检查 `dist/WorkTools/` 中必要的目录和文件是否齐全。

### 打包后运行

```batch
cd dist/WorkTools
WorkTools.exe
```

启动后会自动打开浏览器访问 `http://127.0.0.1:9123`。关闭命令行窗口即可停止服务。

### 测试

- 项目没有使用 Django 的单元测试框架（`tests.py` 不存在）。
- 提供了一个独立的 API 测试脚本：`test_component_api.py`，使用 `requests` 库对组件配置 API 进行端到端测试。
- **注意**：`test_component_api.py` 中 `BASE_URL = "http://127.0.0.1:8000"`，与项目默认端口 `9123` 不一致，运行前需根据实际端口修改。
- 测试前需要确保：
  1. 已执行数据库迁移
  2. Django 开发服务器正在运行

## 代码风格和组织约定

### 视图组织

- 所有视图函数按功能模块拆分到 `work_tools2/views/` 下的独立文件中。
- `work_tools2/views/__init__.py` 统一导入并暴露所有视图，供 `urls.py` 使用。
- 视图函数命名使用 `snake_case`。
- API 视图返回统一的 JSON 格式：`{"success": True/False, "data": ..., "message": ...}` 或 `{"success": False, "error": ...}`。
- 大量 API 视图使用 `@csrf_exempt` 装饰器以方便 AJAX 调用。

### 模型约定

- 所有自定义模型定义在 `work_tools2/models.py` 中。
- 表名使用 `work_tools2_` 前缀（由 Django 的 `db_table` Meta 选项显式指定）。
- 模型字段使用中文 `verbose_name`。
- 常用字段：`created_at`、`updated_at`、`is_active`、`is_default`。

### 前端约定

- 模板继承 `base.html`，通过 `{% block main_content %}` 填充内容。
- 前端与后端交互主要使用 `axios` 发送 AJAX 请求。
- 全局 Toast 提示函数 `showToast(message, type, title, duration)` 定义在 `base.html` 中。
- 侧边栏菜单支持中文、拼音模糊搜索。
- 部分页面（如数据库管理）混用了 Layui 组件库。
- 前端页面逻辑主要内联在 HTML 模板中的 `<script>` 标签里。

### URL 路由

- 页面路由和 API 路由统一配置在 `work_tools2/urls.py` 中。
- API 路径以 `/api/` 前缀开头。
- 动态表单页面路由：`dynamic/<str:form_id>`。

### 数据库操作约定

- 数据库管理功能直接通过 `sqlite3` 模块操作 `db.sqlite3`，而非完全通过 Django ORM。
- `work_tools2/task.py` 实现了基于后台线程的 CSV 导入任务队列，按 FIFO 顺序执行。

## 安全注意事项

- **SECRET_KEY 硬编码**：当前 `settings.py` 中的 `SECRET_KEY` 是明文硬编码的 Django 默认不安全密钥，仅供本地开发/桌面应用使用。请勿将其部署到公网服务器。
- **DEBUG = True**：调试模式始终开启，会暴露详细的错误堆栈信息。
- **ALLOWED_HOSTS 为空**：未限制可访问的主机名。
- **CSRF**：大量 API 视图使用了 `@csrf_exempt` 装饰器（如动态表单提交、组件配置保存、表单配置保存等），这在本地桌面应用场景下是可接受的，但不适用于公网部署。
- **SQL 注入风险**：`database_config.py` 中的部分功能（如 `execute_sql_query`）直接执行用户输入的 SQL，虽然仅限本地 SQLite，但仍需谨慎使用。
- **系统表保护**：`database_config.py` 中定义了 `SYSTEM_TABLES` 集合，禁止对 Django 系统表和业务核心表进行删除、清空或修改操作；同时通过 `is_system_table()` 额外排除 `sqlite_` 和 `django_` 前缀的表。
- **无身份验证**：项目没有启用用户登录/权限控制（虽然 `django.contrib.auth` 在 `INSTALLED_APPS` 中，但实际未使用）。
- **文件路径**：`path_utils.py` 中若未配置默认文件路径，会回退到 `D:\临时文件\{年月}\{日}`。

## 已知问题与需要注意的地方

- **dashboard.html 缺失**：`urls.py` 中注册了 `path("dashboard/", views.dashboard, ...)`，`page_views.py` 中也定义了 `dashboard()` 视图，但 `templates/` 目录下没有 `dashboard.html`，访问该路由会报模板不存在错误。
- **form_merge.py 为空文件**：`work_tools2/views/form_merge.py` 当前为空，实际表单合并逻辑在 `form_merge_views.py` 和 `form_merge_batch.py` 中。
- **文档中提到的文件不存在**：`PACKAGING.md` 和 `README_打包说明.md` 中提到 `build_package.bat`、`build_portable.py`、`dist_portable/` 等，但项目根目录中并不存在这些文件。
- **README.md 编码特殊**：根目录 `README.md` 为 UTF-16 LE 编码，内容仅有 `# work_tools2`，人类可读的说明主要在 `使用说明.txt` 和各打包说明文档中。
- **端口不一致**：测试脚本 `test_component_api.py` 默认指向 8000 端口，而项目运行端口为 9123。
- **WorkTools.spec 与 build.py 的关系**：根目录下存在 `WorkTools.spec`，但 `build.py` 在打包前会删除所有 `.spec` 文件并生成新的配置，因此该文件更多是上一次打包的残留或参考。

## 部署和分发

- **目标平台**：Windows 10/11。
- **无需目标环境安装 Python**：PyInstaller 打包后的 `dist/WorkTools/` 文件夹包含完整的 Python 运行时和依赖。
- **数据库文件**：`db.sqlite3` 会被复制到打包输出目录中。如果目标电脑需要保留数据，更新时只替换程序文件，保留 `db.sqlite3`。
- **防火墙**：首次运行可能需要允许 Windows 防火墙访问 9123 端口。
- **体积**：打包后约 200-500MB，包含完整的 Python 运行时、Django 框架和所有依赖。

## 开发和修改建议

- 修改代码后，在开发环境用 `python manage.py runserver` 测试。
- 如需修改端口，编辑 `manage.py` 中的 `Runserver.default_port` 并重新打包。
- 新增模型后，执行 `python manage.py makemigrations && python manage.py migrate`，然后重新打包。
- 新增静态文件或模板后，确保 `build.py` 的 `--add-data` 参数包含对应路径；若使用 `WorkTools.spec`，也需同步更新。
- 前端页面逻辑主要内联在 HTML 模板中的 `<script>` 标签里，修改前端直接编辑对应模板文件即可。
- 修改打包行为时，注意 `build.py` 会清理 `dist/`、`build/` 和 `*.spec`，并会生成新的 `WorkTools.spec`。
- 运行测试脚本前，记得将 `test_component_api.py` 中的 `BASE_URL` 改为实际服务端口（如 `http://127.0.0.1:9123`）。
