from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
import json
import sqlparse

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


def test(request):
    """Test page."""
    return HttpResponse("123")


def dynamic(request, form_id: str):
    """Orders list page."""
    return render(request, "dynamic.html", {"active_page": "dynamic"})


@csrf_exempt
def dynamic_submit(request):
    """处理动态表单提交"""
    if request.method == 'POST':
        try:
            # 解析 JSON 数据
            data = json.loads(request.body)

            # 获取配置信息
            config = data.get('config', {})
            form_values = data.get('formValues', {})

            # 执行后端校验
            validation_result = validate_form_data(config, form_values)

            if not validation_result['success']:
                return JsonResponse({
                    'success': False,
                    'message': validation_result['message'],
                    'errors': validation_result.get('errors', [])
                }, status=400)

            # 生成 SQL 更新语句（包括执行语句和回退语句）
            sql_result = generate_update_sql(config, form_values)

            print("=== 接收到表单数据 ===")
            print(f"表单名称：{config.get('formName')}")
            print(f"查询字段数量：{len(config.get('queryItems', []))}")
            print(f"更新字段数量：{len(config.get('updateItems', []))}")
            print(f"\n所有表单值:")
            for key, value in form_values.items():
                print(f"  {key}: {value}")
            print(f"\n生成的执行 SQL 语句:")
            for i, formatted_sql in enumerate(sql_result['forward_sqls'], 1):
                print(f"{i}. \n{formatted_sql}\n")
            print(f"\n生成的回退 SQL 语句:")
            for i, formatted_sql in enumerate(sql_result['backward_sqls'], 1):
                print(f"{i}. \n{formatted_sql}\n")

            # TODO: 在这里添加业务逻辑处理
            # 例如：保存到数据库、调用外部 API 等

            return JsonResponse({
                'success': True,
                'message': '数据接收成功',
                'sql_count': len(sql_result['forward_sqls']),
                'forward_sqls': sql_result['forward_sqls'],
                'backward_sqls': sql_result['backward_sqls']
            })

        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'message': f'JSON 解析失败：{str(e)}'
            }, status=400)
        except Exception as e:
            print(f"处理异常：{e}")
            return JsonResponse({
                'success': False,
                'message': f'服务器错误：{str(e)}'
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': '仅支持 POST 请求'
    }, status=405)


def generate_update_sql(config, form_values):
    """
    根据配置生成 SQL UPDATE 语句（包括执行语句和回退语句）
    ValidRule 规则说明：
    - required: 必填项，如果值为空则不拼接该字段
    - requiredReverse: 不必填（反向必填），如果值不为空才拼接
    - defaultNull: 不填时为空值，使用 NULL
    - defaultField: 不填时使用字段名本身

    返回：
    {
        'forward_sqls': [执行 SQL 语句列表],
        'backward_sqls': [回退 SQL 语句列表]
    }
    """
    forward_sqls = []
    backward_sqls = []

    table_name_list = config.get('tableNameList', [])
    query_items = config.get('queryItems', [])
    update_items = config.get('updateItems', [])

    # 对每个表生成 UPDATE 语句
    for table_name in table_name_list:
        # 1. 构建 WHERE 条件
        where_conditions = []
        for item in query_items:
            connected_tables = item.get('connectedTable', [])
            valid_rule = item.get('ValidRule', '')

            # 如果该字段关联到当前表
            if table_name in connected_tables:
                binding_key = item.get('bindingKey')
                value_data = form_values.get(binding_key, {})
                value = value_data.get('value', '')

                # 根据 ValidRule 判断是否添加到 WHERE 条件
                if valid_rule == 'required':
                    # 必填项：只有值不为空时才添加
                    if value:
                        where_conditions.append(f"{binding_key} = '{value}'")
                elif valid_rule == 'requiredReverse':
                    # 不必填：值不为空时才添加
                    if value:
                        where_conditions.append(f"{binding_key} = '{value}'")
                else:
                    # 其他情况默认添加
                    where_conditions.append(f"{binding_key} = '{value}'")

        # 2. 构建执行语句的 SET 子句（使用 newValue）
        forward_set_clauses = []
        # 3. 构建回退语句的 SET 子句（使用 originValue）
        backward_set_clauses = []

        for item in update_items:
            connected_tables = item.get('connectedTable', [])
            new_valid_rule = item.get('newValidRule', '')
            origin_valid_rule = item.get('originValidRule', '')

            # 如果是补充框，需要处理子字段
            if item.get('inputType') == 'supplement':
                parent_key = item.get('bindingKey')

                # 处理主字段 - 执行语句（newValue）
                value_data = form_values.get(parent_key, {})
                new_value = value_data.get('newValue', '')
                origin_value = value_data.get('originValue', '')

                # 执行语句：根据 newValidRule 处理 newValue
                forward_set_value = handle_field_value(parent_key, new_value, new_valid_rule)
                if forward_set_value is not None and table_name in connected_tables:
                    forward_set_clauses.append(forward_set_value)

                # 回退语句：根据 originValidRule 处理 originValue
                backward_set_value = handle_field_value(parent_key, origin_value, origin_valid_rule)
                if backward_set_value is not None and table_name in connected_tables:
                    backward_set_clauses.append(backward_set_value)

                # 处理子字段（继承主字段的 connectedTable）
                sub_fields = item.get('subFields', [])
                for sub_field in sub_fields:
                    sub_binding_key = sub_field.get('bindingKey')
                    sub_value_data = form_values.get(sub_binding_key, {})
                    sub_new_value = sub_value_data.get('newValue', '')
                    sub_origin_value = sub_value_data.get('originValue', '')

                    # 执行语句：子字段继承主字段的表关联和验证规则
                    if table_name in connected_tables:
                        forward_sub_set_value = handle_field_value(sub_binding_key, sub_new_value, new_valid_rule)
                        if forward_sub_set_value is not None:
                            forward_set_clauses.append(forward_sub_set_value)

                        # 回退语句：子字段继承主字段的表关联和验证规则
                        backward_sub_set_value = handle_field_value(sub_binding_key, sub_origin_value,
                                                                    origin_valid_rule)
                        if backward_sub_set_value is not None:
                            backward_set_clauses.append(backward_sub_set_value)
            else:
                # 普通字段直接处理
                binding_key = item.get('bindingKey')
                value_data = form_values.get(binding_key, {})
                new_value = value_data.get('newValue', '')
                origin_value = value_data.get('originValue', '')

                # 执行语句：使用 newValue
                if table_name in connected_tables:
                    forward_set_value = handle_field_value(binding_key, new_value, new_valid_rule)
                    if forward_set_value is not None:
                        forward_set_clauses.append(forward_set_value)

                    # 回退语句：使用 originValue
                    backward_set_value = handle_field_value(binding_key, origin_value, origin_valid_rule)
                    if backward_set_value is not None:
                        backward_set_clauses.append(backward_set_value)

        # 4. 只有当有 SET 子句和 WHERE 条件时才生成 SQL
        if (forward_set_clauses or backward_set_clauses) and where_conditions:
            where_clause_str = ' AND '.join(where_conditions)

            # 生成执行语句
            if forward_set_clauses:
                forward_set_clause_str = ', '.join(forward_set_clauses)
                forward_sql = f"UPDATE {table_name} SET {forward_set_clause_str} WHERE {where_clause_str}"
                forward_sqls.append(format_sql(forward_sql))

            # 生成回退语句
            if backward_set_clauses:
                backward_set_clause_str = ', '.join(backward_set_clauses)
                backward_sql = f"UPDATE {table_name} SET {backward_set_clause_str} WHERE {where_clause_str}"
                backward_sqls.append(format_sql(backward_sql))

    return {
        'forward_sqls': forward_sqls,
        'backward_sqls': backward_sqls
    }


def format_sql(sql):
    """
    格式化 SQL 语句（模仿 sql-formatter 风格）
    参考：https://github.com/sql-formatter-org/sql-formatter
    """
    # 使用 sqlparse 做基础格式化
    formatted = sqlparse.format(
        sql,
        reindent=True,
        keyword_case='upper',
        identifier_case='lower',
        use_space_around_operators=True,
    )

    # 进一步优化格式
    lines = formatted.split('\n')
    result_lines = []

    indent = '  '  # 2 空格缩进

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # UPDATE 语句特殊处理
        if line.upper().startswith('UPDATE'):
            result_lines.append(line)
        elif 'SET' in line.upper() and line.strip().upper().startswith('SET'):
            # SET 关键字单独一行
            result_lines.append(line)
        elif line.startswith(',') or line.startswith('AND') or line.startswith('OR'):
            # 操作符前置，带缩进
            result_lines.append(indent + line)
        elif '=' in line and (',' in line or 'AND' in line.upper()):
            # SET 子句的字段行
            if line.startswith('='):
                result_lines.append(indent + line)
            else:
                result_lines.append(indent + line)
        else:
            result_lines.append(indent + line)

    return '\n'.join(result_lines)


def handle_field_value(field_name, value, valid_rule):
    """
    根据 ValidRule 处理字段值
    返回：格式化后的 SQL 片段 或 None（表示不拼接该字段）

    规则说明：
    - required: 必填项，如果值为空返回 None（不拼接）
    - requiredReverse: 不必填，如果值不为空才拼接，否则返回 None
    - defaultNull: 不填时为空值，值为空时使用 NULL
    - defaultField: 不填时使用字段名本身，值为空时返回 field_name = field_name
    """
    # 检查值是否为空
    is_empty = (value is None or value == '' or value == 'null' or value == 'NULL')

    if valid_rule == 'required':
        # 必填项：如果值为空，不拼接该字段
        if is_empty:
            return None
        else:
            return f"{field_name} = '{value}'"

    elif valid_rule == 'requiredReverse':
        # 不必填：值不为空才拼接
        if not is_empty:
            return f"{field_name} = '{value}'"
        else:
            return None

    elif valid_rule == 'defaultNull':
        # 不填时为空值
        if is_empty:
            return f"{field_name} = NULL"
        else:
            return f"{field_name} = '{value}'"

    elif valid_rule == 'defaultField':
        # 不填时使用字段名本身
        if is_empty:
            return f"{field_name} = {field_name}"
        else:
            return f"{field_name} = '{value}'"

    else:
        # 默认情况：直接拼接
        if is_empty:
            return None
        else:
            return f"{field_name} = '{value}'"


def validate_form_data(config, form_values):
    """
    后端表单校验（与前端逻辑一致）
    返回：{'success': bool, 'message': str, 'errors': list}
    """
    errors = []

    query_items = config.get('queryItems', [])
    update_items = config.get('updateItems', [])

    # 1. 校验文本、数值、日期、下拉框的新值和原值
    for item in update_items:
        if item.get('inputType') in ['select', 'input'] and item.get('type') in ['text', 'number', 'date', 'string']:
            binding_key = item.get('bindingKey')
            value_data = form_values.get(binding_key, {})

            # 新值校验
            new_value = value_data.get('newValue')
            new_valid_rule = item.get('newValidRule', '')
            if (new_value is None or new_value == '') and new_valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

            # 原值校验
            origin_value = value_data.get('originValue')
            origin_valid_rule = item.get('originValidRule', '')
            if (origin_value is None or origin_value == '') and origin_valid_rule == 'required':
                errors.append(f"原{item.get('label')}不能为空")

    # 2. 校验单选框
    for item in update_items:
        if item.get('inputType') == 'radio':
            binding_key = item.get('bindingKey')
            value_data = form_values.get(binding_key, {})
            new_value = value_data.get('newValue')
            valid_rule = item.get('newValidRule', '')

            if (new_value is None or new_value == '') and valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

    # 3. 校验查询字段
    for item in query_items:
        binding_key = item.get('bindingKey')
        value_data = form_values.get(binding_key, {})
        value = value_data.get('value')
        valid_rule = item.get('ValidRule', '')

        if (value is None or value == '') and valid_rule == 'required':
            errors.append(f"{item.get('label')}不能为空")

    # 4. 校验补充框的主输入框和子输入框
    for item in update_items:
        if item.get('inputType') == 'supplement':
            binding_key = item.get('bindingKey')
            value_data = form_values.get(binding_key, {})

            # 主输入框校验
            new_value = value_data.get('newValue')
            if new_value is None or new_value == '':
                errors.append(f"新{item.get('label')}不能为空")

            # 子输入框校验
            sub_fields = item.get('subFields', [])
            for sub_field in sub_fields:
                sub_binding_key = sub_field.get('bindingKey')
                sub_value_data = form_values.get(sub_binding_key, {})
                sub_new_value = sub_value_data.get('newValue')

                if sub_new_value is None or sub_new_value == '':
                    errors.append(f"新{sub_field.get('label')}不能为空")

    # 5. 校验公共字段
    common_fields = ['filePrefix', 'onesLink', 'dynamicNo']
    for field_name in common_fields:
        value_data = form_values.get(field_name, {})
        value = value_data.get('value')

        if value is None or value == '':
            errors.append(f"{field_name}不能为空")

    # 6. 校验查询字段至少有一个不为空
    query_field_values = [
        form_values.get(item.get('bindingKey'), {}).get('value')
        for item in query_items
    ]
    has_non_empty_query = any(
        v is not None and v != ''
        for v in query_field_values
    )

    if query_items and not has_non_empty_query:
        errors.append("查询字段至少需要填写一个条件")

    # 返回校验结果
    if errors:
        return {
            'success': False,
            'message': f'共有{len(errors)}个校验错误',
            'errors': errors
        }

    return {
        'success': True,
        'message': '校验通过',
        'errors': []
    }


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
