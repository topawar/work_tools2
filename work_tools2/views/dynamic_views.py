import json
import os
import sqlparse
from datetime import datetime
from io import BytesIO

from django.http import HttpResponse, JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill


# ==================== 工具函数 ====================

def format_sql(sql):
    """格式化 SQL 语句"""
    formatted = sqlparse.format(
        sql,
        reindent=True,
        keyword_case='upper',
        identifier_case='lower',
        use_space_around_operators=True,
    )

    lines = formatted.split('\n')
    result_lines = []
    indent = '  '

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.upper().startswith('UPDATE'):
            result_lines.append(line)
        elif 'SET' in line.upper() and line.strip().upper().startswith('SET'):
            result_lines.append(line)
        elif line.startswith(',') or line.startswith('AND') or line.startswith('OR'):
            result_lines.append(indent + line)
        elif '=' in line and (',' in line or 'AND' in line.upper()):
            result_lines.append(indent + line)
        else:
            result_lines.append(indent + line)

    return '\n'.join(result_lines)


def handle_field_value(field_name, value, valid_rule):
    """根据 ValidRule 处理字段值"""
    is_empty = (value is None or value == '' or value == 'null' or value == 'NULL')

    if valid_rule == 'required':
        if is_empty:
            return None
        else:
            return f"{field_name} = '{value}'"
    elif valid_rule == 'requiredReverse':
        if not is_empty:
            return f"{field_name} = '{value}'"
        else:
            return None
    elif valid_rule == 'defaultNull':
        if is_empty:
            return f"{field_name} = NULL"
        else:
            return f"{field_name} = '{value}'"
    elif valid_rule == 'defaultField':
        if is_empty:
            return f"{field_name} = {field_name}"
        else:
            return f"{field_name} = '{value}'"
    else:
        if is_empty:
            return None
        else:
            return f"{field_name} = '{value}'"


def generate_update_sql(config, form_values):
    """根据配置生成 SQL UPDATE 语句"""
    forward_sqls = []
    backward_sqls = []

    table_name_list = config.get('tableNameList', [])
    query_items = config.get('queryItems', [])
    update_items = config.get('updateItems', [])

    for table_name in table_name_list:
        where_conditions = []
        for item in query_items:
            connected_tables = item.get('connectedTable', [])
            valid_rule = item.get('ValidRule', '')

            if table_name in connected_tables:
                binding_key = item.get('bindingKey')
                value_data = form_values.get(binding_key, {})
                value = value_data.get('value', '')

                if valid_rule in ['required', 'requiredReverse']:
                    if value:
                        where_conditions.append(f"{binding_key} = '{value}'")
                else:
                    where_conditions.append(f"{binding_key} = '{value}'")

        forward_set_clauses = []
        backward_set_clauses = []

        for item in update_items:
            connected_tables = item.get('connectedTable', [])
            new_valid_rule = item.get('newValidRule', '')
            origin_valid_rule = item.get('originValidRule', '')

            if item.get('inputType') == 'supplement':
                parent_key = item.get('bindingKey')
                value_data = form_values.get(parent_key, {})
                new_value = value_data.get('newValue', '')
                origin_value = value_data.get('originValue', '')

                forward_set_value = handle_field_value(parent_key, new_value, new_valid_rule)
                if forward_set_value is not None and table_name in connected_tables:
                    forward_set_clauses.append(forward_set_value)

                backward_set_value = handle_field_value(parent_key, origin_value, origin_valid_rule)
                if backward_set_value is not None and table_name in connected_tables:
                    backward_set_clauses.append(backward_set_value)

                sub_fields = item.get('subFields', [])
                for sub_field in sub_fields:
                    sub_binding_key = sub_field.get('bindingKey')
                    sub_value_data = form_values.get(sub_binding_key, {})
                    sub_new_value = sub_value_data.get('newValue', '')
                    sub_origin_value = sub_value_data.get('originValue', '')

                    if table_name in connected_tables:
                        forward_sub_set_value = handle_field_value(sub_binding_key, sub_new_value, new_valid_rule)
                        if forward_sub_set_value is not None:
                            forward_set_clauses.append(forward_sub_set_value)

                        if sub_origin_value is None or sub_origin_value == '':
                            backward_sub_set_value = f"{sub_binding_key} = ''"
                        else:
                            backward_sub_set_value = f"{sub_binding_key} = '{sub_origin_value}'"

                        if backward_sub_set_value is not None:
                            backward_set_clauses.append(backward_sub_set_value)
            else:
                binding_key = item.get('bindingKey')
                value_data = form_values.get(binding_key, {})
                new_value = value_data.get('newValue', '')
                origin_value = value_data.get('originValue', '')

                if table_name in connected_tables:
                    forward_set_value = handle_field_value(binding_key, new_value, new_valid_rule)
                    if forward_set_value is not None:
                        forward_set_clauses.append(forward_set_value)

                    backward_set_value = handle_field_value(binding_key, origin_value, origin_valid_rule)
                    if backward_set_value is not None:
                        backward_set_clauses.append(backward_set_value)

        if (forward_set_clauses or backward_set_clauses) and where_conditions:
            where_clause_str = ' AND '.join(where_conditions)

            if forward_set_clauses:
                forward_set_clause_str = ', '.join(forward_set_clauses)
                forward_sql = f"UPDATE {table_name} SET {forward_set_clause_str} WHERE {where_clause_str}"
                forward_sqls.append(format_sql(forward_sql))

            if backward_set_clauses:
                backward_set_clause_str = ', '.join(backward_set_clauses)
                backward_sql = f"UPDATE {table_name} SET {backward_set_clause_str} WHERE {where_clause_str}"
                backward_sqls.append(format_sql(backward_sql))

    return {
        'forward_sqls': forward_sqls,
        'backward_sqls': backward_sqls
    }


def validate_form_data(config, form_values, query_values=None):
    """后端表单校验"""
    errors = []

    query_items = config.get('queryItems', [])
    update_items = config.get('updateItems', [])

    for item in update_items:
        if item.get('inputType') in ['select', 'input'] and item.get('type') in ['text', 'number', 'date', 'string']:
            binding_key = item.get('bindingKey')
            value_data = form_values.get(binding_key, {})

            new_value = value_data.get('newValue')
            new_valid_rule = item.get('newValidRule', '')
            if (new_value is None or new_value == '') and new_valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

            origin_value = value_data.get('originValue')
            origin_valid_rule = item.get('originValidRule', '')
            if (origin_value is None or origin_value == '') and origin_valid_rule == 'required':
                errors.append(f"原{item.get('label')}不能为空")

    for item in update_items:
        if item.get('inputType') == 'radio':
            binding_key = item.get('bindingKey')
            value_data = form_values.get(binding_key, {})
            new_value = value_data.get('newValue')
            valid_rule = item.get('newValidRule', '')

            if (new_value is None or new_value == '') and valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

    for item in query_items:
        binding_key = item.get('bindingKey')
        value_data = form_values.get(binding_key, {})
        value = value_data.get('value')
        valid_rule = item.get('ValidRule', '')

        if (value is None or value == '') and valid_rule == 'required':
            errors.append(f"{item.get('label')}不能为空")

    common_fields = ['filePrefix', 'onesLink', 'dynamicNo']
    for field_name in common_fields:
        value = None

        if query_values:
            value_data = query_values.get(field_name, {})
            value = value_data.get('value') if isinstance(value_data, dict) else value_data

        if not value:
            value_data = form_values.get(field_name, {})
            value = value_data.get('value')

        if value is None or str(value).strip() == '':
            errors.append(f"{field_name}不能为空")

    query_field_values = [
        form_values.get(item.get('bindingKey'), {}).get('value')
        for item in query_items
    ]
    has_non_empty_query = any(v is not None and v != '' for v in query_field_values)

    if query_items and not has_non_empty_query:
        errors.append("查询字段至少需要填写一个条件")

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


def build_form_values_from_excel(ws, row_idx, headers, query_items, update_items):
    """从 Excel 行构建表单值"""
    form_values = {}
    missing_columns = []

    for item in query_items:
        label = item.get('label', '')
        binding_key = item.get('bindingKey', '')

        if label in headers:
            col = headers[label]
            value = ws.cell(row=row_idx, column=col).value
            form_values[binding_key] = {
                'label': label,
                'value': str(value) if value is not None else '',
                'inputType': 'query',
                'fieldType': item.get('type', 'text'),
                'ValidRule': item.get('ValidRule', '')
            }
        else:
            missing_columns.append(label)
            form_values[binding_key] = {
                'label': label,
                'value': '',
                'inputType': 'query',
                'fieldType': item.get('type', 'text'),
                'ValidRule': item.get('ValidRule', '')
            }

    for item in update_items:
        label = item.get('label', '')
        binding_key = item.get('bindingKey', '')
        input_type = item.get('inputType', '')

        if input_type == 'supplement':
            sub_fields = item.get('subFields', [])
            new_label = f'新{label}'
            origin_label = f'原{label}'

            new_value = ''
            origin_value = ''

            if new_label in headers:
                col = headers[new_label]
                new_value = ws.cell(row=row_idx, column=col).value
            else:
                missing_columns.append(new_label)

            if origin_label in headers:
                col = headers[origin_label]
                origin_value = ws.cell(row=row_idx, column=col).value

            form_values[binding_key] = {
                'label': label,
                'newValue': str(new_value) if new_value is not None else '',
                'originValue': str(origin_value) if origin_value is not None else '',
                'inputType': 'supplement',
                'fieldType': 'supplement',
                'newValidRule': item.get('newValidRule', ''),
                'originValidRule': item.get('originValidRule', '')
            }

            for sub_field in sub_fields:
                sub_label = sub_field.get('label', '')
                sub_binding_key = sub_field.get('bindingKey', '')

                new_sub_label = f'新{sub_label}'
                origin_sub_label = f'原{sub_label}'

                new_sub_value = ''
                origin_sub_value = ''

                if new_sub_label in headers:
                    col = headers[new_sub_label]
                    new_sub_value = ws.cell(row=row_idx, column=col).value

                if origin_sub_label in headers:
                    col = headers[origin_sub_label]
                    origin_sub_value = ws.cell(row=row_idx, column=col).value

                form_values[sub_binding_key] = {
                    'newValue': str(new_sub_value) if new_sub_value is not None else '',
                    'originValue': str(origin_sub_value) if origin_sub_value is not None else '',
                    'inputType': 'supplement-sub',
                    'fieldType': 'supplement-sub',
                    'parentKey': binding_key,
                    'label': sub_label
                }
        else:
            new_label = f'新{label}'
            origin_label = f'原{label}'

            new_value = ''
            origin_value = ''

            if new_label in headers:
                col = headers[new_label]
                new_value = ws.cell(row=row_idx, column=col).value
            else:
                missing_columns.append(new_label)

            if origin_label in headers:
                col = headers[origin_label]
                origin_value = ws.cell(row=row_idx, column=col).value
            else:
                missing_columns.append(origin_label)

            form_values[binding_key] = {
                'label': label,
                'newValue': str(new_value) if new_value is not None else '',
                'originValue': str(origin_value) if origin_value is not None else '',
                'inputType': input_type,
                'fieldType': item.get('type', 'text'),
                'newValidRule': item.get('newValidRule', ''),
                'originValidRule': item.get('originValidRule', '')
            }

    return form_values, missing_columns


# ==================== 视图函数 ====================

@csrf_exempt
def dynamic_submit(request):
    """处理动态表单提交"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            config = data.get('config', {})
            form_values = data.get('formValues', {})

            validation_result = validate_form_data(config, form_values)

            if not validation_result['success']:
                return JsonResponse({
                    'success': False,
                    'message': validation_result['message'],
                    'errors': validation_result.get('errors', [])
                }, status=400)

            sql_result = generate_update_sql(config, form_values)

            dynamic_no = form_values.get('dynamicNo', {}).get('value', '')

            now = datetime.now()
            year_month = now.strftime('%Y%m')
            day = now.strftime('%d')
            save_dir = f"D:\\临时文件\\{year_month}\\{day}"

            os.makedirs(save_dir, exist_ok=True)

            sql_content = []
            sql_content.append(f"-- 表单：{config.get('formName', '未知')}")
            sql_content.append(f"-- 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
            sql_content.append(f"-- 文件名：{dynamic_no}")
            sql_content.append("")

            if sql_result['forward_sqls']:
                sql_content.append("-- ==================== 执行语句 ====================")
                sql_content.append("")
                for i, sql in enumerate(sql_result['forward_sqls'], 1):
                    sql_content.append(f"-- 执行语句 {i}")
                    sql_content.append(sql)
                    sql_content.append("")

            if sql_result['backward_sqls']:
                sql_content.append("-- ==================== 回退语句 ====================")
                sql_content.append("")
                for i, sql in enumerate(sql_result['backward_sqls'], 1):
                    sql_content.append(f"-- 回退语句 {i}")
                    sql_content.append(sql)
                    sql_content.append("")

            filename = f"{dynamic_no}.sql"
            filepath = os.path.join(save_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(sql_content))

            return JsonResponse({
                'success': True,
                'message': 'SQL 文件生成成功',
                'filePath': filepath,
                'sql_count': len(sql_result['forward_sqls']),
                'forward_sqls': sql_result['forward_sqls'],
                'backward_sqls': sql_result['backward_sqls']
            })

        except json.JSONDecodeError as e:
            return JsonResponse({'success': False, 'message': f'JSON 解析失败：{str(e)}'}, status=400)
        except Exception as e:
            print(f"处理异常：{e}")
            return JsonResponse({'success': False, 'message': f'服务器错误：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)


@csrf_exempt
def download_template(request):
    """根据配置动态生成 Excel 导入模板"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            config = data.get('config', {})

            form_name = config.get('formName', '模板')
            query_items = config.get('queryItems', [])
            update_items = config.get('updateItems', [])

            wb = Workbook()
            ws = wb.active
            ws.title = form_name[:31]

            header_font = Font(bold=True, size=12)
            header_alignment = Alignment(horizontal='center', vertical='center')
            header_fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")

            headers = []

            for item in query_items:
                headers.append({
                    'label': item.get('label', ''),
                    'bindingKey': item.get('bindingKey', ''),
                    'type': 'query'
                })

            for item in update_items:
                if item.get('inputType') == 'supplement':
                    parent_label = item.get('label', '')
                    parent_binding_key = item.get('bindingKey', '')
                    sub_fields = item.get('subFields', [])

                    headers.append({
                        'label': f'新{parent_label}',
                        'bindingKey': parent_binding_key,
                        'type': 'update_new'
                    })

                    headers.append({
                        'label': f'原{parent_label}',
                        'bindingKey': parent_binding_key,
                        'type': 'update_origin'
                    })

                    for sub_field in sub_fields:
                        sub_label = sub_field.get('label', '')
                        sub_binding_key = sub_field.get('bindingKey', '')

                        headers.append({
                            'label': f'原{sub_label}',
                            'bindingKey': sub_binding_key,
                            'type': 'update_origin_sub'
                        })
                else:
                    label = item.get('label', '')
                    binding_key = item.get('bindingKey', '')

                    headers.append({
                        'label': f'新{label}',
                        'bindingKey': binding_key,
                        'type': 'update_new'
                    })
                    headers.append({
                        'label': f'原{label}',
                        'bindingKey': binding_key,
                        'type': 'update_origin'
                    })

            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header['label'])
                cell.font = header_font
                cell.alignment = header_alignment
                cell.fill = header_fill

                col_letter = chr(64 + (col_num % 26)) if col_num <= 26 else chr(64 + (col_num // 26)) + chr(64 + (col_num % 26))
                ws.column_dimensions[col_letter].width = 15

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{form_name}_{timestamp}.xlsx".replace('/', '-').replace('\\', '-')

            buffer = BytesIO()
            wb.save(buffer)
            buffer.seek(0)

            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            from urllib.parse import quote
            encoded_filename = quote(filename)
            response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{encoded_filename}'

            return response

        except json.JSONDecodeError as e:
            return JsonResponse({'success': False, 'message': f'JSON 解析失败：{str(e)}'}, status=400)
        except Exception as e:
            print(f"处理异常：{e}")
            return JsonResponse({'success': False, 'message': f'服务器错误：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)


@csrf_exempt
def batch_import(request):
    """批量导入数据"""
    if request.method == 'POST':
        try:
            file = request.FILES.get('file')
            config_json = request.POST.get('config')
            query_values_json = request.POST.get('queryValues')

            if not file or not config_json:
                return JsonResponse({'success': False, 'message': '缺少文件或配置参数'}, status=400)

            config = json.loads(config_json)
            form_name = config.get('formName', '模板')
            query_items = config.get('queryItems', [])
            update_items = config.get('updateItems', [])

            query_values = {}
            if query_values_json:
                try:
                    query_values = json.loads(query_values_json)
                except json.JSONDecodeError:
                    query_values = {}

            common_fields = ['filePrefix', 'onesLink', 'dynamicNo']
            for field_name in common_fields:
                value_data = query_values.get(field_name, {})

                if isinstance(value_data, dict):
                    value = value_data.get('value', '')
                elif isinstance(value_data, str):
                    value = value_data
                else:
                    value = ''

                if not value or str(value).strip() == '':
                    return JsonResponse({'success': False, 'message': f'{field_name}不能为空'}, status=400)

            wb = load_workbook(file)
            ws = wb.active

            headers = {}
            for col in range(1, ws.max_column + 1):
                cell_value = ws.cell(row=1, column=col).value
                if cell_value is not None and str(cell_value).strip():
                    headers[str(cell_value).strip()] = col

            required_columns = []
            for item in query_items:
                required_columns.append(item.get('label', ''))

            for item in update_items:
                if item.get('inputType') == 'supplement':
                    required_columns.append(f'新{item.get("label", "")}')
                else:
                    required_columns.append(f'新{item.get("label", "")}')

            has_valid_data = any(col in headers for col in required_columns)

            if not has_valid_data or len(headers) == 0:
                return JsonResponse({'success': False, 'message': '数据表中无有效的数据，请检查 Excel 文件格式是否正确'}, status=400)

            if ws.max_row < 2:
                return JsonResponse({'success': False, 'message': 'Excel 文件没有数据行，请至少填写一行数据'}, status=400)

            valid_data_rows = 0
            for row_idx in range(2, ws.max_row + 1):
                has_required_value = False
                for col_name in required_columns:
                    col_num = headers.get(col_name)
                    if col_num:
                        cell_value = ws.cell(row=row_idx, column=col_num).value
                        if cell_value is not None and str(cell_value).strip():
                            has_required_value = True
                            break
                if has_required_value:
                    valid_data_rows += 1

            if valid_data_rows == 0:
                return JsonResponse({'success': False, 'message': f'Excel 中没有有效的必填数据（共{ws.max_row - 1}行，但都没有必填字段的值）'}, status=400)

            fail_column = ws.max_column + 1
            ws.cell(row=1, column=fail_column, value='失败原因')
            ws.cell(row=1, column=fail_column).font = Font(bold=True)
            ws.cell(row=1, column=fail_column).alignment = Alignment(horizontal='center')
            ws.cell(row=1, column=fail_column).fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")

            total_rows = ws.max_row - 1
            success_count = 0
            fail_count = 0
            all_sql_statements = []

            for row_idx in range(2, ws.max_row + 1):
                form_values, missing_columns = build_form_values_from_excel(ws, row_idx, headers, query_items, update_items)

                if missing_columns:
                    missing_cols_str = ', '.join(missing_columns)
                    fail_count += 1
                    ws.cell(row=row_idx, column=fail_column, value=f'缺少必需的列：{missing_cols_str}')
                    ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC", end_color="FFFFCC", fill_type="solid")
                    continue

                validation_result = validate_form_data(config, form_values, query_values)

                if not validation_result['success']:
                    fail_count += 1
                    fail_reason = '; '.join(validation_result.get('errors', []))
                    ws.cell(row=row_idx, column=fail_column, value=fail_reason)
                    ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC", end_color="FFFFCC", fill_type="solid")
                else:
                    sql_result = generate_update_sql(config, form_values)

                    if sql_result['forward_sqls'] and sql_result['backward_sqls']:
                        all_sql_statements.append({
                            'row': row_idx,
                            'forward_sqls': sql_result['forward_sqls'],
                            'backward_sqls': sql_result['backward_sqls']
                        })
                        success_count += 1
                    else:
                        fail_count += 1
                        ws.cell(row=row_idx, column=fail_column, value='未生成有效的 SQL 语句')
                        ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC", end_color="FFFFCC", fill_type="solid")

            stats_ws = wb.create_sheet(title='导入统计')
            stats_ws.cell(row=1, column=1, value='总行数').font = Font(bold=True)
            stats_ws.cell(row=1, column=2, value=total_rows).font = Font(bold=True)
            stats_ws.cell(row=2, column=1, value='成功数').font = Font(bold=True)
            stats_ws.cell(row=2, column=2, value=success_count).font = Font(bold=True)
            stats_ws.cell(row=3, column=1, value='失败数').font = Font(bold=True)
            stats_ws.cell(row=3, column=2, value=fail_count).font = Font(bold=True)
            stats_ws.cell(row=4, column=1, value='成功率').font = Font(bold=True)
            stats_ws.cell(row=4, column=2, value=f'{success_count / total_rows * 100:.2f}%' if total_rows > 0 else '0%').font = Font(bold=True)

            dynamic_no = ''
            if query_values:
                dynamic_no_data = query_values.get('dynamicNo', '')
                if isinstance(dynamic_no_data, dict):
                    dynamic_no = dynamic_no_data.get('value', '')
                elif isinstance(dynamic_no_data, str):
                    dynamic_no = dynamic_no_data

            now = datetime.now()
            year_month = now.strftime('%Y%m')
            day = now.strftime('%d')
            save_dir = f"D:\\临时文件\\{year_month}\\{day}"

            os.makedirs(save_dir, exist_ok=True)

            all_success = (fail_count == 0 and success_count > 0)

            sql_file_path = None
            if all_success and all_sql_statements:
                sql_filename = f"{dynamic_no}.sql"
                sql_filepath = os.path.join(save_dir, sql_filename)

                sql_content = []
                sql_content.append(f"-- 批量导入 SQL 文件")
                sql_content.append(f"-- 表单：{form_name}")
                sql_content.append(f"-- 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
                sql_content.append(f"-- 总行数：{total_rows}，成功：{success_count}，失败：{fail_count}")
                sql_content.append("")

                for idx, stmt in enumerate(all_sql_statements, 1):
                    sql_content.append(f"-- ==================== 第 {stmt['row']} 行数据 ====================")
                    sql_content.append("")
                    sql_content.append("-- 执行语句")
                    for sql in stmt['forward_sqls']:
                        sql_content.append(sql)
                        sql_content.append("")
                    sql_content.append("-- 回退语句")
                    for sql in stmt['backward_sqls']:
                        sql_content.append(sql)
                        sql_content.append("")

                with open(sql_filepath, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(sql_content))
                sql_file_path = sql_filepath

            excel_file_path = None
            if fail_count > 0:
                excel_filename = f"{dynamic_no}_导入结果_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
                excel_filepath = os.path.join(save_dir, excel_filename)

                wb.save(excel_filepath)
                excel_file_path = excel_filepath

            return JsonResponse({
                'success': True,
                'message': f'批量导入完成，成功{success_count}条，失败{fail_count}条',
                'sqlFilePath': sql_file_path,
                'excelFilePath': excel_file_path,
                'totalRows': total_rows,
                'successCount': success_count,
                'failCount': fail_count
            })

        except Exception as e:
            print(f"批量导入异常：{e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'success': False, 'message': f'服务器错误：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)


@csrf_exempt
def download_failed_file(request):
    """下载失败的 Excel 结果文件"""
    if request.method == 'GET':
        try:
            file_path = request.GET.get('path', '')

            if not file_path or not os.path.exists(file_path):
                return JsonResponse({'success': False, 'message': '文件不存在'}, status=404)

            response = FileResponse(open(file_path, 'rb'))
            response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

            filename = os.path.basename(file_path)
            from urllib.parse import quote
            encoded_filename = quote(filename)
            response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{encoded_filename}'

            return response

        except Exception as e:
            print(f"下载文件异常：{e}")
            return JsonResponse({'success': False, 'message': f'服务器错误：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)
