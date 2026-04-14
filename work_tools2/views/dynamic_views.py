import json
import os
import sqlparse
from datetime import datetime
from io import BytesIO
from collections import defaultdict

from django.http import HttpResponse, JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill

from work_tools2.models import DatabaseIPConfig
from work_tools2.path_utils import get_save_path_from_config


# ==================== 工具函数 ====================
def format_sql(sql):
    """格式化 SQL 语句 - 优化可读性"""
    try:
        import sqlparse
        import re
        
        # 先使用 sqlparse 进行基本格式化，但不重新缩进
        formatted = sqlparse.format(
            sql,
            reindent=False,  # 不自动重新缩进，我们自己控制
            keyword_case='upper',
            identifier_case='upper',
            strip_comments=True
        )
        
        # 处理 IN 子句：如果值很多，进行换行格式化
        def format_in_clause(match):
            """格式化 IN 子句，当值超过3个时换行显示"""
            field_name = match.group(1)
            values_str = match.group(2)
            
            # 提取所有值
            values = [v.strip() for v in values_str.split(',')]
            
            if len(values) <= 3:
                # 值不多，保持在一行
                return f"{field_name} IN ({values_str})"
            else:
                # 值很多，换行显示
                indent = " " * 4  # 基础缩进
                values_indent = " " * 6  # 值的缩进
                
                # 每行显示3个值
                formatted_values = []
                for i in range(0, len(values), 3):
                    chunk = values[i:i+3]
                    formatted_values.append(f"{values_indent}{', '.join(chunk)}")
                
                result = f"{field_name} IN (\n"
                result += ",\n".join(formatted_values)
                result += f"\n{indent})"
                return result
        
        # 匹配 IN 子句：FIELD IN (value1, value2, ...)
        in_pattern = r"([A-Z_][A-Z0-9_]*)\s+IN\s*\(([^)]+)\)"
        formatted = re.sub(in_pattern, format_in_clause, formatted, flags=re.IGNORECASE)
        
        # 手动格式化：按关键字分割并重新组织
        lines = []
        
        # 将SQL按关键字分割（注意：IN 子句可能已经包含换行）
        # 先按行分割，再处理每行
        raw_lines = formatted.split('\n')
        
        in_set_clause = False  # 标记是否在 SET 子句中
        
        for line in raw_lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            # 如果这一行已经是 IN 子句的一部分（以 ) 结尾且前面有 IN），直接保留
            if stripped.startswith(')') or (stripped.endswith(',') and '(' in line):
                lines.append(line)
                continue
            
            # 处理普通行
            parts = stripped.split()
            i = 0
            current_line = ""
            
            while i < len(parts):
                word = parts[i]
                word_upper = word.upper()
                
                # UPDATE 关键字：新起一行
                if word_upper == 'UPDATE':
                    if current_line:
                        lines.append(current_line)
                    current_line = word
                    in_set_clause = False
                    i += 1
                    continue
                
                # SET 关键字：新起一行，缩进
                if word_upper == 'SET':
                    if current_line:
                        lines.append(current_line)
                    current_line = f"  {word}"
                    in_set_clause = True
                    i += 1
                    continue
                
                # WHERE 关键字：新起一行
                if word_upper == 'WHERE':
                    if current_line:
                        lines.append(current_line)
                    current_line = f"  {word}"
                    in_set_clause = False
                    i += 1
                    continue
                
                # OR 关键字：新起一行，增加缩进
                if word_upper == 'OR':
                    if current_line:
                        lines.append(current_line)
                    current_line = f"    {word}"
                    i += 1
                    continue
                
                # 如果在 SET 子句中，遇到逗号说明是下一个字段，需要换行
                if in_set_clause and word.endswith(','):
                    # 添加当前字段（带逗号）
                    current_line += f" {word}"
                    lines.append(current_line)
                    current_line = "    "  # 下一行缩进
                    i += 1
                    continue
                
                # 其他内容：添加到当前行
                current_line += f" {word}"
                i += 1
            
            if current_line:
                lines.append(current_line)
        
        return '\n'.join(lines)
        
    except ImportError:
        # 如果 sqlparse 未安装，返回原始SQL
        return sql


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
        # 空值时设置为空字符串，而不是 NULL
        if is_empty:
            return f"{field_name} = ''"
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
    missing_field_labels = set()  # 收集所有缺失字段的label（去重）

    table_name_list = config.get('tableNameList', [])
    query_items = config.get('queryItems', [])
    update_items = config.get('updateItems', [])
    
    # 获取查询模式：strict(严格) 或 loose(宽松)
    query_mode = config.get('queryMode', 'strict')

    # 获取操作备注
    ops_remark = form_values.get('ops_remark', '')
    if isinstance(ops_remark, dict):
        ops_remark = ops_remark.get('value', '')
    elif not ops_remark:
        ops_remark = ''

    for table_name in table_name_list:
        # 第一步：找出该表关联的所有查询字段
        table_query_fields = []

        for item in query_items:
            connected_tables = item.get('connectedTable', [])
            if table_name in connected_tables:
                table_query_fields.append(item)

        # 第二步：先收集该表所有的SET子句，判断是否真的有更新操作
        forward_set_clauses = []
        backward_set_clauses = []

        for item in update_items:
            connected_tables = item.get('connectedTable', [])
            new_valid_rule = item.get('newValidRule', '')
            origin_valid_rule = item.get('originValidRule', '')
            input_type = item.get('inputType', '')
            binding_key = item.get('bindingKey')

            # 如果该表不在此更新字段的关联表中，跳过
            if table_name not in connected_tables:
                continue

            # 处理计算字段类型
            if input_type == 'calculated':
                # 获取当前表的表达式
                expressions = item.get('expressions', {})
                expression = expressions.get(table_name, '').strip()
                binding_key = item.get('bindingKey', '')

                if expression and binding_key:
                    import re

                    # 查找所有 ${variable} 模式的变量（允许内部有空格）
                    variables = re.findall(r'\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}', expression)

                    forward_expression = expression
                    backward_expression = expression
                    has_any_valid_value = False  # 是否至少有一个变量有有效值
                    all_variables_processed = True  # 是否所有变量都处理成功

                    for var_name in variables:
                        # 查找这个字段在update_items或query_items中的定义（不区分大小写）
                        field_item = None
                        var_name_upper = var_name.upper()

                        for ui in update_items:
                            if ui.get('bindingKey', '').upper() == var_name_upper:
                                field_item = ui
                                break

                        if not field_item:
                            for qi in query_items:
                                if qi.get('bindingKey', '').upper() == var_name_upper:
                                    field_item = qi
                                    break

                        if field_item:
                            field_key = field_item['bindingKey']
                            field_type = field_item.get('type', 'text')
                            
                            # 获取字段的验证规则
                            if 'value' in form_values.get(field_key, {}):
                                # 查询字段：没有验证规则概念，直接使用值
                                value_data = form_values.get(field_key, {})
                                new_value = value_data.get('value', '')
                                origin_value = value_data.get('value', '')
                                valid_rule = 'defaultField'  # 查询字段默认为defaultField
                            else:
                                # 更新字段：使用该字段自己配置的验证规则
                                value_data = form_values.get(field_key, {})
                                new_value = value_data.get('newValue', '')
                                origin_value = value_data.get('originValue', '')
                                # 关键修复：使用field_item（被引用字段）的验证规则，而不是item（计算字段）的
                                valid_rule = field_item.get('newValidRule', 'defaultField')

                            # 判断是否为数值类型
                            is_number_type = (field_type == 'number')

                            # 处理新值（forward表达式）
                            if new_value:
                                # 有值：正常替换
                                has_any_valid_value = True
                                if is_number_type:
                                    forward_expression = re.sub(
                                        r'\$\{\s*' + re.escape(var_name) + r'\s*\}',
                                        new_value,
                                        forward_expression
                                    )
                                else:
                                    forward_expression = re.sub(
                                        r'\$\{\s*' + re.escape(var_name) + r'\s*\}',
                                        f"'{new_value}'",
                                        forward_expression
                                    )
                            else:
                                # 没值：根据验证规则决定
                                if valid_rule == 'defaultField':
                                    # defaultField：替换为字段名本身（不加引号）
                                    forward_expression = re.sub(
                                        r'\$\{\s*' + re.escape(var_name) + r'\s*\}',
                                        var_name.upper(),
                                        forward_expression
                                    )
                                elif valid_rule == 'required':
                                    # required：标记为无效，整个计算字段不生成
                                    all_variables_processed = False
                                    has_any_valid_value = False
                                    break
                                else:
                                    # optional或其他：替换为空字符串或0
                                    replacement = '0' if is_number_type else "''"
                                    forward_expression = re.sub(
                                        r'\$\{\s*' + re.escape(var_name) + r'\s*\}',
                                        replacement,
                                        forward_expression
                                    )

                            # 处理原值（backward表达式）
                            if origin_value:
                                has_any_valid_value = True
                                if is_number_type:
                                    backward_expression = re.sub(
                                        r'\$\{\s*' + re.escape(var_name) + r'\s*\}',
                                        origin_value,
                                        backward_expression
                                    )
                                else:
                                    backward_expression = re.sub(
                                        r'\$\{\s*' + re.escape(var_name) + r'\s*\}',
                                        f"'{origin_value}'",
                                        backward_expression
                                    )
                            else:
                                # 没值：根据验证规则决定
                                if valid_rule == 'defaultField':
                                    backward_expression = re.sub(
                                        r'\$\{\s*' + re.escape(var_name) + r'\s*\}',
                                        var_name.upper(),
                                        backward_expression
                                    )
                                elif valid_rule == 'required':
                                    all_variables_processed = False
                                    has_any_valid_value = False
                                    break
                                else:
                                    replacement = '0' if is_number_type else "''"
                                    backward_expression = re.sub(
                                        r'\$\{\s*' + re.escape(var_name) + r'\s*\}',
                                        replacement,
                                        backward_expression
                                    )
                        else:
                            # 找不到字段定义，保留原样
                            print(f"[警告] 计算字段 {binding_key} 的表达式中引用了未定义的变量: {var_name}")

                    # 只有当所有变量都处理成功且至少有一个有效值时，才生成SET子句
                    if all_variables_processed and has_any_valid_value:
                        forward_set_clauses.append(f"{binding_key} = {forward_expression}")
                        backward_set_clauses.append(f"{binding_key} = {backward_expression}")

            # 处理补充框类型
            elif input_type == 'supplement':
                parent_key = item.get('bindingKey')

                # 如果 form_values 中没有这个补充框，说明前端没有传输（原值为空），跳过
                if parent_key not in form_values:
                    continue

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

            # 处理普通字段类型
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

        # 第三步：如果该表没有任何SET子句，直接跳过，不进行查询字段校验
        if not forward_set_clauses and not backward_set_clauses:
            print(f"[SQL生成-表:{table_name}] 跳过: 该表没有有效的更新字段")
            continue

        # 第四步：有SET子句时，才根据查询模式收集WHERE条件
        where_conditions = []
        
        if query_mode == 'loose':
            # 宽松模式：只收集有值的字段
            for item in table_query_fields:
                binding_key = item.get('bindingKey')
                value_data = form_values.get(binding_key, {})
                value = value_data.get('value', '')
                
                if value:
                    where_conditions.append(f"{binding_key} = '{value}'")
        else:
            # 严格模式（默认）：要求所有关联字段都有值
            all_fields_have_value = True
            
            for item in table_query_fields:
                binding_key = item.get('bindingKey')
                value_data = form_values.get(binding_key, {})
                value = value_data.get('value', '')
                
                if not value:
                    all_fields_have_value = False
                    break
                else:
                    where_conditions.append(f"{binding_key} = '{value}'")
            
            # 严格模式下，如果有字段为空则处理
            if not all_fields_have_value:
                # 关键逻辑：只有当表有多个查询字段时，才记录缺失字段
                # 如果只有一个查询字段，静默跳过（不生成SQL即可）
                if len(table_query_fields) > 1:
                    for item in table_query_fields:
                        binding_key = item.get('bindingKey')
                        label = item.get('label', binding_key)
                        value_data = form_values.get(binding_key, {})
                        value = value_data.get('value', '')
                        if not value:
                            missing_field_labels.add(label)
                    print(f"[SQL生成-表:{table_name}] 跳过(严格模式): 存在未填写的查询字段")
                else:
                    # 只有一个查询字段且为空，静默跳过
                    print(f"[SQL生成-表:{table_name}] 跳过(严格模式): 唯一查询字段为空，静默跳过")
                continue

        # 第五步：至少有一个查询字段有值时才生成SQL
        if not where_conditions:
            missing_fields = [item.get('bindingKey') for item in table_query_fields]
            print(f"[SQL生成-表:{table_name}] 跳过: 所有查询字段均为空: {missing_fields}")
            continue

        # 第六步：生成SQL语句
        where_clause_str = ' AND '.join(where_conditions)

        if forward_set_clauses:
            forward_set_clause_str = ', '.join(forward_set_clauses)
            # 添加操作备注
            if ops_remark:
                forward_set_clause_str += f", ops_remark = '{ops_remark}'"
            forward_sql = f"UPDATE {table_name} SET {forward_set_clause_str} WHERE {where_clause_str}"
            # 返回原始SQL和格式化后的SQL
            forward_sqls.append({
                'raw': forward_sql,
                'formatted': format_sql(forward_sql)
            })

        if backward_set_clauses:
            backward_set_clause_str = ', '.join(backward_set_clauses)
            # 回退语句的操作备注为空
            backward_set_clause_str += ", ops_remark = ''"
            backward_sql = f"UPDATE {table_name} SET {backward_set_clause_str} WHERE {where_clause_str}"
            # 返回原始SQL和格式化后的SQL
            backward_sqls.append({
                'raw': backward_sql,
                'formatted': format_sql(backward_sql)
            })

    # 将收集的缺失字段标签合并为错误信息
    # 关键逻辑：只有当没有任何SQL生成时，才返回错误信息
    missing_field_errors = []
    if missing_field_labels and not forward_sqls and not backward_sqls:
        for label in sorted(missing_field_labels):
            missing_field_errors.append(f"{label} 未填写")
    
    return {
        'forward_sqls': forward_sqls,
        'backward_sqls': backward_sqls,
        'missing_field_errors': missing_field_errors  # 返回缺失字段错误信息
    }


def merge_where_clauses(where_clauses):
    """
    智能合并WHERE子句
    - 单字段条件：使用 IN (value1, value2, value3)
    - 多字段组合条件：使用 (cond1 AND cond2) OR (cond3 AND cond4)
    """
    if not where_clauses:
        return ''

    if len(where_clauses) == 1:
        return where_clauses[0]

    # 检查是否所有条件都是单字段
    all_single_field = True
    field_values_map = {}  # {field: [values]}
    
    for where_clause in where_clauses:
        # 如果包含 AND，说明是多字段组合
        if ' AND ' in where_clause:
            all_single_field = False
            break
        
        # 解析单字段条件：field = 'value'
        if '=' in where_clause:
            parts = where_clause.split('=')
            if len(parts) == 2:
                field = parts[0].strip()
                value = parts[1].strip()
                
                if field not in field_values_map:
                    field_values_map[field] = []
                field_values_map[field].append(value)
    
    # 如果所有条件都是单字段，且只有一个字段，使用 IN
    if all_single_field and len(field_values_map) == 1:
        field = list(field_values_map.keys())[0]
        values = field_values_map[field]
        
        if len(values) == 1:
            # 只有一个值，直接用 =
            return f"{field} = {values[0]}"
        else:
            # 多个值，使用 IN
            values_str = ', '.join(values)
            return f"{field} IN ({values_str})"
    
    # 多字段组合条件：使用 (cond1 AND cond2) OR (cond3 AND cond4)
    merged_conditions = []
    for where_clause in where_clauses:
        # 如果条件中包含多个 AND，加上括号
        if ' AND ' in where_clause:
            merged_conditions.append(f"({where_clause})")
        else:
            merged_conditions.append(where_clause)

    # 用 OR 连接所有条件组
    return '\n  OR '.join(merged_conditions)


def merge_sql_statements(all_sql_statements):
    """
    合并相同修改但不同查询条件的SQL语句
    - 同一字段的不同值使用 IN
    - 不同字段的条件使用 OR
    - 完全相同的语句（包括WHERE）进行去重
    - 汇总表更新语句（多条明细共用一个汇总条件）放置在最后
    """
    if not all_sql_statements:
        return []

    # 按SET子句和表名分组
    forward_groups = defaultdict(list)
    backward_groups = defaultdict(list)

    for stmt in all_sql_statements:
        for forward_sql_item in stmt['forward_sqls']:
            # 使用原始SQL进行提取
            raw_sql = forward_sql_item['raw'] if isinstance(forward_sql_item, dict) else forward_sql_item

            # 提取表名和SET子句作为key
            table_name = extract_table_name(raw_sql)
            set_clause = extract_set_clause(raw_sql)
            where_clause = extract_where_clause(raw_sql)

            key = f"{table_name}|{set_clause}"
            forward_groups[key].append({
                'table_name': table_name,
                'set_clause': set_clause,
                'where_clause': where_clause
            })

        for backward_sql_item in stmt['backward_sqls']:
            # 使用原始SQL进行提取
            raw_sql = backward_sql_item['raw'] if isinstance(backward_sql_item, dict) else backward_sql_item

            table_name = extract_table_name(raw_sql)
            set_clause = extract_set_clause(raw_sql)
            where_clause = extract_where_clause(raw_sql)

            key = f"{table_name}|{set_clause}"
            backward_groups[key].append({
                'table_name': table_name,
                'set_clause': set_clause,
                'where_clause': where_clause
            })

    merged_forward_normal = []  # 普通SQL（明细表更新）
    merged_forward_summary = []  # 汇总SQL（主表汇总更新）
    merged_backward_normal = []
    merged_backward_summary = []

    # 合并执行语句
    for key, items in forward_groups.items():
        if len(items) == 1:
            # 只有一个条件，不需要合并
            item = items[0]
            sql = f"UPDATE {item['table_name']} SET {item['set_clause']} WHERE {item['where_clause']}"
            formatted_sql = format_sql(sql)
            
            # 判断是否为汇总SQL：如果包含SELECT SUM等聚合函数，则为汇总SQL
            if _is_summary_sql(item['set_clause']):
                merged_forward_summary.append(formatted_sql)
            else:
                merged_forward_normal.append(formatted_sql)
        else:
            # 多个条件，需要智能合并
            # 先对WHERE子句去重（完全相同的WHERE只保留一个）
            unique_where_clauses = list(dict.fromkeys([item['where_clause'] for item in items]))
            
            if len(unique_where_clauses) == 1:
                # 所有WHERE条件都相同，说明是重复的汇总SQL，只生成一条
                item = items[0]
                sql = f"UPDATE {item['table_name']} SET {item['set_clause']} WHERE {unique_where_clauses[0]}"
                formatted_sql = format_sql(sql)
                
                # 汇总SQL放到最后
                if _is_summary_sql(item['set_clause']):
                    merged_forward_summary.append(formatted_sql)
                else:
                    merged_forward_normal.append(formatted_sql)
            else:
                # 不同的WHERE条件，需要合并
                merged_where = merge_where_clauses(unique_where_clauses)
                sql = f"UPDATE {items[0]['table_name']} SET {items[0]['set_clause']} WHERE {merged_where}"
                formatted_sql = format_sql(sql)
                
                # 判断是否为汇总SQL
                if _is_summary_sql(items[0]['set_clause']):
                    merged_forward_summary.append(formatted_sql)
                else:
                    merged_forward_normal.append(formatted_sql)

    # 合并回退语句
    for key, items in backward_groups.items():
        if len(items) == 1:
            item = items[0]
            sql = f"UPDATE {item['table_name']} SET {item['set_clause']} WHERE {item['where_clause']}"
            formatted_sql = format_sql(sql)
            
            # 判断是否为汇总SQL
            if _is_summary_sql(item['set_clause']):
                merged_backward_summary.append(formatted_sql)
            else:
                merged_backward_normal.append(formatted_sql)
        else:
            # 先对WHERE子句去重
            unique_where_clauses = list(dict.fromkeys([item['where_clause'] for item in items]))
            
            if len(unique_where_clauses) == 1:
                # 所有WHERE条件都相同，只生成一条
                item = items[0]
                sql = f"UPDATE {item['table_name']} SET {item['set_clause']} WHERE {unique_where_clauses[0]}"
                formatted_sql = format_sql(sql)
                
                if _is_summary_sql(item['set_clause']):
                    merged_backward_summary.append(formatted_sql)
                else:
                    merged_backward_normal.append(formatted_sql)
            else:
                # 不同的WHERE条件，需要合并
                merged_where = merge_where_clauses(unique_where_clauses)
                sql = f"UPDATE {items[0]['table_name']} SET {items[0]['set_clause']} WHERE {merged_where}"
                formatted_sql = format_sql(sql)
                
                if _is_summary_sql(items[0]['set_clause']):
                    merged_backward_summary.append(formatted_sql)
                else:
                    merged_backward_normal.append(formatted_sql)

    # 合并结果：普通SQL在前，汇总SQL在后
    merged_forward = merged_forward_normal + merged_forward_summary
    merged_backward = merged_backward_normal + merged_backward_summary

    return {
        'forward_sqls': merged_forward,
        'backward_sqls': merged_backward
    }


def _is_summary_sql(set_clause):
    """
    判断SET子句是否包含汇总计算（聚合函数）
    如果包含 SELECT SUM、SELECT COUNT、SELECT AVG 等，则认为是汇总SQL
    """
    if not set_clause:
        return False
    
    set_upper = set_clause.upper()
    summary_keywords = ['SELECT SUM', 'SELECT COUNT', 'SELECT AVG', 'SELECT MAX', 'SELECT MIN']
    
    for keyword in summary_keywords:
        if keyword in set_upper:
            return True
    
    return False


def extract_set_clause(sql):
    """从SQL中提取SET子句"""
    sql_upper = sql.upper()
    set_start = sql_upper.find(' SET ')
    where_start = sql_upper.find(' WHERE ')

    if set_start != -1 and where_start != -1:
        return sql[set_start + 5:where_start].strip()
    elif set_start != -1:
        return sql[set_start + 5:].strip()
    return ''


def extract_where_clause(sql):
    """从SQL中提取WHERE子句"""
    sql_upper = sql.upper()
    where_start = sql_upper.find(' WHERE ')

    if where_start != -1:
        return sql[where_start + 7:].strip()
    return ''


def extract_table_name(sql):
    """从SQL中提取表名"""
    sql_upper = sql.upper()
    update_start = sql_upper.find('UPDATE ')
    set_start = sql_upper.find(' SET ')

    if update_start != -1 and set_start != -1:
        return sql[update_start + 7:set_start].strip()
    return ''


def validate_form_data(config, form_values, query_values=None):
    """后端表单校验"""
    errors = []

    query_items = config.get('queryItems', [])
    update_items = config.get('updateItems', [])

    # 校验更新字段
    for item in update_items:
        binding_key = item.get('bindingKey')
        value_data = form_values.get(binding_key, {})
        input_type = item.get('inputType', '')
        field_type = item.get('type', 'text')

        # 下拉框校验
        if input_type == 'select':
            new_value = value_data.get('newValue')
            origin_value = value_data.get('originValue')
            options = item.get('options', [])

            # 构建 label -> value 的映射
            label_to_value = {}
            valid_values = set()
            for opt in options:
                opt_value = str(opt.get('value', ''))
                opt_label = str(opt.get('label', ''))
                valid_values.add(opt_value)
                label_to_value[opt_label] = opt_value

            # 校验并转换新值（支持label或value）
            if new_value and new_value != '':
                new_value_str = str(new_value)
                # 如果是label，转换为value
                if new_value_str in label_to_value:
                    # 将label转换为value存储
                    form_values[binding_key]['newValue'] = label_to_value[new_value_str]
                elif new_value_str not in valid_values:
                    errors.append(f"新{item.get('label')}的值'{new_value}'不在可选范围内")

            # 校验并转换原值
            if origin_value and origin_value != '':
                origin_value_str = str(origin_value)
                if origin_value_str in label_to_value:
                    form_values[binding_key]['originValue'] = label_to_value[origin_value_str]
                elif origin_value_str not in valid_values:
                    errors.append(f"原{item.get('label')}的值'{origin_value}'不在可选范围内")

            # 重新获取转换后的值进行必填校验
            new_value = form_values[binding_key].get('newValue')
            origin_value = form_values[binding_key].get('originValue')

            # 校验必填
            new_valid_rule = item.get('newValidRule', '')
            origin_valid_rule = item.get('originValidRule', '')

            if (new_value is None or new_value == '') and new_valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

            if (origin_value is None or origin_value == '') and origin_valid_rule == 'required':
                errors.append(f"原{item.get('label')}不能为空")

        # 日期格式校验
        elif field_type == 'date' or input_type == 'date':
            new_value = value_data.get('newValue')
            origin_value = value_data.get('originValue')

            import re
            date_pattern = r'^\d{8}$'  # yyyyMMdd格式

            if new_value and new_value != '':
                if not re.match(date_pattern, str(new_value)):
                    errors.append(f"新{item.get('label')}的日期格式不正确，应为yyyyMMdd格式（如：20260125）")

            if origin_value and origin_value != '':
                if not re.match(date_pattern, str(origin_value)):
                    errors.append(f"原{item.get('label')}的日期格式不正确，应为yyyyMMdd格式（如：20260125）")

            # 校验必填
            new_valid_rule = item.get('newValidRule', '')
            origin_valid_rule = item.get('originValidRule', '')

            if (new_value is None or new_value == '') and new_valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

            if (origin_value is None or origin_value == '') and origin_valid_rule == 'required':
                errors.append(f"原{item.get('label')}不能为空")

        # 数值类型校验
        elif field_type == 'number' or input_type == 'number':
            new_value = value_data.get('newValue')
            origin_value = value_data.get('originValue')

            from decimal import Decimal, InvalidOperation

            # 校验新值是否为有效数值
            if new_value and new_value != '':
                try:
                    Decimal(str(new_value))
                except (InvalidOperation, ValueError, TypeError):
                    errors.append(f"新{item.get('label')}的值'{new_value}'不是有效的数值")

            # 校验原值是否为有效数值
            if origin_value and origin_value != '':
                try:
                    Decimal(str(origin_value))
                except (InvalidOperation, ValueError, TypeError):
                    errors.append(f"原{item.get('label')}的值'{origin_value}'不是有效的数值")

            # 校验必填
            new_valid_rule = item.get('newValidRule', '')
            origin_valid_rule = item.get('originValidRule', '')

            if (new_value is None or new_value == '') and new_valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

            if (origin_value is None or origin_value == '') and origin_valid_rule == 'required':
                errors.append(f"原{item.get('label')}不能为空")

        # 补充框校验
        elif input_type == 'supplement':
            # 如果 form_values 中没有这个补充框，说明前端没有传输（原值为空），跳过校验
            if binding_key not in form_values:
                continue

            main_table = item.get('mainTable', '')
            main_field = item.get('mainField', '')
            sub_fields = item.get('subFields', [])

            new_value = value_data.get('newValue')
            origin_value = value_data.get('originValue')

            # 只校验新值是否在数据库中存在
            if new_value and new_value != '' and main_table and main_field:
                from django.db import connection
                try:
                    with connection.cursor() as cursor:
                        sql = f"SELECT COUNT(*) FROM {main_table} WHERE {main_field} = %s"
                        cursor.execute(sql, [str(new_value)])
                        count = cursor.fetchone()[0]
                        if count == 0:
                            errors.append(f"新{item.get('label')}的值'{new_value}'在数据库中不存在")
                except Exception as e:
                    print(f"校验补充框新值失败: {e}")

            # 原值不校验，直接使用用户提供的值或数据库中的值

            # 校验必填
            new_valid_rule = item.get('newValidRule', '')
            origin_valid_rule = item.get('originValidRule', '')

            if (new_value is None or new_value == '') and new_valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

            if (origin_value is None or origin_value == '') and origin_valid_rule == 'required':
                errors.append(f"原{item.get('label')}不能为空")

        # 普通输入框校验
        elif input_type in ['input', 'text', 'string']:
            new_value = value_data.get('newValue')
            origin_value = value_data.get('originValue')
            new_valid_rule = item.get('newValidRule', '')
            origin_valid_rule = item.get('originValidRule', '')

            if (new_value is None or new_value == '') and new_valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

            if (origin_value is None or origin_value == '') and origin_valid_rule == 'required':
                errors.append(f"原{item.get('label')}不能为空")

    # 校验单选框
    for item in update_items:
        if item.get('inputType') == 'radio':
            binding_key = item.get('bindingKey')
            value_data = form_values.get(binding_key, {})
            new_value = value_data.get('newValue')
            valid_rule = item.get('newValidRule', '')

            if (new_value is None or new_value == '') and valid_rule == 'required':
                errors.append(f"新{item.get('label')}不能为空")

    # 校验查询字段
    for item in query_items:
        binding_key = item.get('bindingKey')
        value_data = form_values.get(binding_key, {})
        value = value_data.get('value')
        valid_rule = item.get('ValidRule', '')

        if (value is None or value == '') and valid_rule == 'required':
            errors.append(f"{item.get('label')}不能为空")

    # 校验公共字段
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

    # 校验查询字段至少填写一个
    query_field_values = [
        form_values.get(item.get('bindingKey'), {}).get('value')
        for item in query_items
    ]
    has_non_empty_query = any(v is not None and v != '' for v in query_field_values)

    if query_items and not has_non_empty_query:
        errors.append("查询字段至少需要填写一个条件")

    # 校验更新字段至少有一个有值（新值或原值）
    has_non_empty_update = False
    for item in update_items:
        binding_key = item.get('bindingKey')
        input_type = item.get('inputType', '')
        value_data = form_values.get(binding_key, {})

        if input_type == 'supplement':
            # 补充框：检查主字段的新值或原值
            new_value = value_data.get('newValue', '')
            origin_value = value_data.get('originValue', '')
            if new_value or origin_value:
                has_non_empty_update = True
                break
        else:
            # 普通字段：检查新值或原值
            new_value = value_data.get('newValue', '')
            origin_value = value_data.get('originValue', '')
            if new_value or origin_value:
                has_non_empty_update = True
                break

    if update_items and not has_non_empty_update:
        errors.append("更新字段至少需要填写一个新值或原值")

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

            # ==================== 自动填充补充框子字段 ====================
            # 如果新值或原值不为空，从数据库查询对应的子字段值
            main_table = item.get('mainTable', '')
            main_field = item.get('mainField', '')

            if main_table and main_field and sub_fields:
                from django.db import connection

                # 收集需要查询的主字段值
                query_values = []
                if new_value and str(new_value).strip():
                    query_values.append(str(new_value).strip())
                if origin_value and str(origin_value).strip():
                    query_values.append(str(origin_value).strip())

                if query_values:
                    # 去重
                    query_values = list(set(query_values))

                    # 构建要查询的字段列表
                    select_fields = [main_field]
                    for sub_field in sub_fields:
                        if isinstance(sub_field, dict):
                            field_name = sub_field.get('dbField') or sub_field.get('bindingKey')
                            if field_name:
                                select_fields.append(field_name)
                        elif isinstance(sub_field, str):
                            select_fields.append(sub_field)

                    # 使用 IN 查询
                    fields_str = ', '.join(select_fields)
                    values_str = ', '.join(["'" + str(v).replace("'", "''") + "'" for v in query_values])
                    sql = f"SELECT {fields_str} FROM {main_table} WHERE {main_field} IN ({values_str})"

                    print("=" * 50)
                    print(f"批量导入-自动查询补充框子字段: {binding_key}")
                    print("SQL:", sql)
                    print("=" * 50)

                    try:
                        with connection.cursor() as cursor:
                            cursor.execute(sql)
                            rows = cursor.fetchall()

                            # 将结果转换为字典，以主字段值为key
                            data_map = {}
                            for row in rows:
                                row_dict = {}
                                for idx, field in enumerate(select_fields):
                                    row_dict[field] = row[idx]

                                main_val = row_dict.get(main_field, '')
                                data_map[main_val] = row_dict

                        # 填充新值的子字段
                        if new_value and str(new_value).strip():
                            new_val_str = str(new_value).strip()
                            if new_val_str in data_map:
                                row_data = data_map[new_val_str]
                                for sub_field in sub_fields:
                                    if isinstance(sub_field, dict):
                                        sub_binding_key = sub_field.get('bindingKey', '')
                                        db_field = sub_field.get('dbField') or sub_binding_key
                                        sub_value = row_data.get(db_field, '')

                                        form_values[sub_binding_key] = {
                                            'newValue': str(sub_value) if sub_value is not None else '',
                                            'originValue': '',
                                            'inputType': 'supplement-sub',
                                            'fieldType': 'supplement-sub',
                                            'parentKey': binding_key,
                                            'label': sub_field.get('label', '')
                                        }

                        # 填充原值的子字段
                        if origin_value and str(origin_value).strip():
                            origin_val_str = str(origin_value).strip()
                            if origin_val_str in data_map:
                                row_data = data_map[origin_val_str]
                                for sub_field in sub_fields:
                                    if isinstance(sub_field, dict):
                                        sub_binding_key = sub_field.get('bindingKey', '')
                                        db_field = sub_field.get('dbField') or sub_binding_key
                                        sub_value = row_data.get(db_field, '')

                                        # 如果已经有新值的子字段数据，只更新originValue
                                        if sub_binding_key in form_values:
                                            form_values[sub_binding_key]['originValue'] = str(
                                                sub_value) if sub_value is not None else ''
                                        else:
                                            form_values[sub_binding_key] = {
                                                'newValue': '',
                                                'originValue': str(sub_value) if sub_value is not None else '',
                                                'inputType': 'supplement-sub',
                                                'fieldType': 'supplement-sub',
                                                'parentKey': binding_key,
                                                'label': sub_field.get('label', '')
                                            }

                    except Exception as e:
                        print(f"查询补充框子字段失败: {e}")
                        import traceback
                        traceback.print_exc()
            else:
                # 如果没有配置主表主字段，手动处理子字段
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
            # 处理普通字段和计算字段
            new_label = f'新{label}'
            origin_label = f'原{label}'

            new_value = ''
            origin_value = ''

            # 如果是计算字段，不需要从Excel读取，直接初始化为空
            if input_type == 'calculated':
                # 计算字段的值会在generate_update_sql中通过表达式计算
                form_values[binding_key] = {
                    'label': label,
                    'newValue': '',
                    'originValue': '',
                    'inputType': input_type,
                    'fieldType': item.get('type', 'text'),
                    'newValidRule': item.get('newValidRule', ''),
                    'originValidRule': item.get('originValidRule', ''),
                    'expressions': item.get('expressions', {})  # 保留表达式配置
                }
            else:
                # 普通字段需要从Excel读取
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

                # 如果值为空且有默认值，使用默认值
                new_value_str = str(new_value) if new_value is not None else ''
                origin_value_str = str(origin_value) if origin_value is not None else ''
                
                if not new_value_str and item.get('newDefaultValue'):
                    new_value_str = str(item.get('newDefaultValue', ''))
                
                if not origin_value_str and item.get('originDefaultValue'):
                    origin_value_str = str(item.get('originDefaultValue', ''))

                form_values[binding_key] = {
                    'label': label,
                    'newValue': new_value_str,
                    'originValue': origin_value_str,
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

            # 检查是否有缺失字段的错误（严格模式下）
            if sql_result.get('missing_field_errors'):
                error_messages = sql_result['missing_field_errors']
                return JsonResponse({
                    'success': False,
                    'message': f'共有{len(error_messages)}个字段校验错误',
                    'errors': error_messages
                }, status=400)

            dynamic_no = form_values.get('dynamicNo', {}).get('value', '')
            file_prefix = form_values.get('filePrefix', {}).get('value', '')

            # 使用路径配置获取保存路径
            save_dir = get_save_path_from_config()
            print(f"[DEBUG] SQL文件保存路径: {save_dir}")
            print(f"[DEBUG] 文件名: {dynamic_no}_{file_prefix}.sql")

            os.makedirs(save_dir, exist_ok=True)

            sql_content = []

            if sql_result['forward_sqls']:
                sql_content.append("1.执行语句")
                for i, sql_item in enumerate(sql_result['forward_sqls'], 1):
                    # sql_item可能是字典{'raw': ..., 'formatted': ...}或字符串
                    sql = sql_item['formatted'] if isinstance(sql_item, dict) else sql_item
                    # 确保SQL末尾有分号
                    if not sql.rstrip().endswith(';'):
                        sql = sql.rstrip() + ';'
                    sql_content.append(sql)
                    sql_content.append("")

            if sql_result['backward_sqls']:
                sql_content.append("2.回退语句")
                for i, sql_item in enumerate(sql_result['backward_sqls'], 1):
                    # sql_item可能是字典{'raw': ..., 'formatted': ...}或字符串
                    sql = sql_item['formatted'] if isinstance(sql_item, dict) else sql_item
                    # 确保SQL末尾有分号
                    if not sql.rstrip().endswith(';'):
                        sql = sql.rstrip() + ';'
                    sql_content.append(sql)
                    sql_content.append("")

            # 添加数据库信息
            database_ip_ids = config.get('databaseIpIds', [])
            if database_ip_ids:
                db_configs = DatabaseIPConfig.objects.filter(id__in=database_ip_ids).order_by('id')
                if db_configs:
                    sql_content.append("3.数据库")
                    for db_config in db_configs:
                        sql_content.append(f"ip：{db_config.ip_address}")
                        sql_content.append(f"库名：{db_config.database_name}")
                        sql_content.append("")

            # 文件名格式：编号_文件名.sql
            filename = f"{dynamic_no}_{file_prefix}.sql"
            filepath = os.path.join(save_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(sql_content))

            # 返回时也需要提取格式化后的SQL
            forward_formatted = [item['formatted'] if isinstance(item, dict) else item
                                 for item in sql_result['forward_sqls']]
            backward_formatted = [item['formatted'] if isinstance(item, dict) else item
                                  for item in sql_result['backward_sqls']]

            return JsonResponse({
                'success': True,
                'message': 'SQL 文件生成成功',
                'filePath': filepath,
                'sql_count': len(forward_formatted),
                'forward_sqls': forward_formatted,
                'backward_sqls': backward_formatted
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

            header_font = Font(bold=True, size=12, color='000000')  # 黑色字体
            header_alignment = Alignment(horizontal='center', vertical='center')
            header_fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
            # 黄色背景，用于标注有默认值的字段
            default_value_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

            headers = []

            for item in query_items:
                headers.append({
                    'label': item.get('label', ''),
                    'bindingKey': item.get('bindingKey', ''),
                    'type': 'query',
                    'hasDefaultValue': False
                })

            for item in update_items:
                # 跳过计算字段，计算字段由表达式自动生成
                if item.get('inputType') == 'calculated':
                    continue

                if item.get('inputType') == 'supplement':
                    parent_label = item.get('label', '')
                    parent_binding_key = item.get('bindingKey', '')
                    sub_fields = item.get('subFields', [])

                    # 主字段：新值和原值都需要用户填写
                    has_new_default = bool(item.get('newDefaultValue'))
                    has_origin_default = bool(item.get('originDefaultValue'))
                    
                    headers.append({
                        'label': f'新{parent_label}',
                        'bindingKey': parent_binding_key,
                        'type': 'update_new',
                        'hasDefaultValue': has_new_default,
                        'defaultValue': item.get('newDefaultValue', '')
                    })

                    headers.append({
                        'label': f'原{parent_label}',
                        'bindingKey': parent_binding_key,
                        'type': 'update_origin',
                        'hasDefaultValue': has_origin_default,
                        'defaultValue': item.get('originDefaultValue', '')
                    })

                    # 子字段：只有原值需要填写（新值自动查询）
                    for sub_field in sub_fields:
                        sub_label = sub_field.get('label', '')
                        sub_binding_key = sub_field.get('bindingKey', '')

                        headers.append({
                            'label': f'原{sub_label}',
                            'bindingKey': sub_binding_key,
                            'type': 'update_origin_sub',
                            'hasDefaultValue': False
                        })
                else:
                    label = item.get('label', '')
                    binding_key = item.get('bindingKey', '')
                    has_new_default = bool(item.get('newDefaultValue'))
                    has_origin_default = bool(item.get('originDefaultValue'))

                    headers.append({
                        'label': f'新{label}',
                        'bindingKey': binding_key,
                        'type': 'update_new',
                        'hasDefaultValue': has_new_default,
                        'defaultValue': item.get('newDefaultValue', '')
                    })
                    headers.append({
                        'label': f'原{label}',
                        'bindingKey': binding_key,
                        'type': 'update_origin',
                        'hasDefaultValue': has_origin_default,
                        'defaultValue': item.get('originDefaultValue', '')
                    })

            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header['label'])
                cell.font = header_font
                cell.alignment = header_alignment
                
                # 如果有默认值，使用黄色背景
                if header.get('hasDefaultValue'):
                    cell.fill = default_value_fill
                else:
                    cell.fill = header_fill

                col_letter = chr(64 + (col_num % 26)) if col_num <= 26 else chr(64 + (col_num // 26)) + chr(
                    64 + (col_num % 26))
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


def process_single_sheet_import(ws, query_items_data, update_items_data, query_values, form_name, table_name_list=None):
    """处理单个Sheet的导入（用于多Sheet批量导入）"""
    try:

        config = {
            'formName': form_name,
            'tableNameList': table_name_list or [],  # 添加表名列表
            'queryItems': query_items_data,
            'updateItems': update_items_data
        }

        # 读取表头
        headers = {}
        for col in range(1, ws.max_column + 1):
            cell_value = ws.cell(row=1, column=col).value
            if cell_value is not None and str(cell_value).strip():
                headers[str(cell_value).strip()] = col

        # 检查是否有有效数据
        required_columns = []
        for item in query_items_data:
            required_columns.append(item.get('label', ''))

        for item in update_items_data:
            if item.get('inputType') == 'supplement':
                required_columns.append(f'新{item.get("label", "")}')
            else:
                required_columns.append(f'新{item.get("label", "")}')

        has_valid_data = any(col in headers for col in required_columns)

        if not has_valid_data or len(headers) == 0:
            return {
                'success': False,
                'message': '数据表中无有效的数据，请检查 Excel 文件格式是否正确',
                'forward_sqls': [],
                'backward_sqls': []
            }

        if ws.max_row < 2:
            return {
                'success': False,
                'message': 'Excel 文件没有数据行，请至少填写一行数据',
                'forward_sqls': [],
                'backward_sqls': []
            }

        # 统计有效数据行数
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
            return {
                'success': False,
                'message': f'Excel 中没有有效的必填数据（共{ws.max_row - 1}行，但都没有必填字段的值）',
                'forward_sqls': [],
                'backward_sqls': []
            }

        # ==================== 第一步：收集所有补充框主字段值 ====================
        supplement_queries = {}  # {table_mainField: set of values}

        for row_idx in range(2, ws.max_row + 1):
            form_values, missing_columns = build_form_values_from_excel(ws, row_idx, headers, query_items_data,
                                                                        update_items_data)

            if missing_columns:
                continue

            # 收集补充框主字段值
            for item in update_items_data:
                if item.get('inputType') == 'supplement':
                    main_table = item.get('mainTable', '')
                    main_field = item.get('mainField', '')
                    parent_key = item.get('bindingKey', '')

                    if main_table and main_field:
                        query_key = f"{main_table}_{main_field}"
                        if query_key not in supplement_queries:
                            supplement_queries[query_key] = {
                                'tableName': main_table,
                                'mainField': main_field,
                                'subFields': item.get('subFields', []),
                                'values': set()
                            }

                        # 收集新值和原值
                        value_data = form_values.get(parent_key, {})
                        new_value = value_data.get('newValue', '')
                        origin_value = value_data.get('originValue', '')

                        if new_value:
                            supplement_queries[query_key]['values'].add(new_value)
                        if origin_value:
                            supplement_queries[query_key]['values'].add(origin_value)

        # ==================== 第二步：批量查询补充框数据 ====================
        supplement_data_cache = {}  # {table_mainField_value: {subField: value}}

        from django.db import connection

        for query_key, query_info in supplement_queries.items():
            if not query_info['values']:
                continue

            table_name = query_info['tableName']
            main_field = query_info['mainField']
            sub_fields = query_info['subFields']
            main_values = list(query_info['values'])

            # 构建查询字段
            select_fields = [main_field]
            for sub_field in sub_fields:
                if isinstance(sub_field, dict):
                    field_name = sub_field.get('dbField') or sub_field.get('bindingKey')
                    if field_name:
                        select_fields.append(field_name)
                elif isinstance(sub_field, str):
                    select_fields.append(sub_field)

            # 使用 IN 查询
            fields_str = ', '.join(select_fields)
            values_str = ', '.join(["'" + str(v).replace("'", "''") + "'" for v in main_values])
            sql = f"SELECT {fields_str} FROM {table_name} WHERE {main_field} IN ({values_str})"

            print("=" * 50)
            print(f"批量查询补充框数据: {query_key}")
            print("SQL:", sql)
            print("=" * 50)

            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()

                for row in rows:
                    row_dict = {}
                    for idx, field in enumerate(select_fields):
                        row_dict[field] = row[idx]

                    # 以主字段值为key存储
                    main_val = row_dict.get(main_field, '')
                    supplement_data_cache[f"{query_key}_{main_val}"] = row_dict

        print(f"补充框数据缓存: {len(supplement_data_cache)} 条")

        # ==================== 第三步：处理每一行数据 ====================
        all_sql_statements = []
        success_count = 0
        fail_count = 0

        # 在最后一列添加"失败原因"列
        from openpyxl.styles import Font, Alignment, PatternFill
        fail_column = ws.max_column + 1
        ws.cell(row=1, column=fail_column, value='失败原因').font = Font(bold=True)
        ws.cell(row=1, column=fail_column).alignment = Alignment(horizontal='center')
        ws.cell(row=1, column=fail_column).fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC",
                                                              fill_type="solid")

        for row_idx in range(2, ws.max_row + 1):

            form_values, missing_columns = build_form_values_from_excel(ws, row_idx, headers, query_items_data,
                                                                        update_items_data)

            if missing_columns:
                fail_count += 1
                missing_cols_str = ', '.join(missing_columns)
                ws.cell(row=row_idx, column=fail_column, value=f'缺少必需的列：{missing_cols_str}')
                ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC", end_color="FFFFCC",
                                                                            fill_type="solid")
                continue

            # ==================== 添加公共字段到form_values ====================
            # 将query_values中的公共字段添加到form_values中，以便校验通过
            if query_values:
                for field_name in ['filePrefix', 'onesLink', 'dynamicNo']:
                    if field_name in query_values:
                        value_data = query_values[field_name]
                        if isinstance(value_data, dict):
                            form_values[field_name] = value_data
                        else:
                            form_values[field_name] = {'value': str(value_data)}

                # 处理操作备注（如果存在）
                if 'ops_remark' in query_values:
                    ops_remark_data = query_values['ops_remark']
                    if isinstance(ops_remark_data, dict):
                        form_values['ops_remark'] = ops_remark_data
                    else:
                        form_values['ops_remark'] = {'value': str(ops_remark_data)}

            # ==================== 使用缓存的补充框数据填充子字段 ====================
            for item in update_items_data:
                if item.get('inputType') == 'supplement':
                    main_table = item.get('mainTable', '')
                    main_field = item.get('mainField', '')
                    parent_key = item.get('bindingKey', '')
                    sub_fields = item.get('subFields', [])

                    if main_table and main_field and sub_fields:
                        query_key = f"{main_table}_{main_field}"
                        value_data = form_values.get(parent_key, {})
                        new_value = value_data.get('newValue', '')
                        origin_value = value_data.get('originValue', '')

                        # 填充新值的子字段
                        if new_value and str(new_value).strip():
                            cache_key = f"{query_key}_{str(new_value).strip()}"
                            if cache_key in supplement_data_cache:
                                row_data = supplement_data_cache[cache_key]
                                for sub_field in sub_fields:
                                    if isinstance(sub_field, dict):
                                        sub_binding_key = sub_field.get('bindingKey', '')
                                        db_field = sub_field.get('dbField') or sub_binding_key
                                        sub_value = row_data.get(db_field, '')

                                        form_values[sub_binding_key] = {
                                            'newValue': str(sub_value) if sub_value is not None else '',
                                            'originValue': '',
                                            'inputType': 'supplement-sub',
                                            'fieldType': 'supplement-sub',
                                            'parentKey': parent_key,
                                            'label': sub_field.get('label', '')
                                        }

                        # 填充原值的子字段
                        if origin_value and str(origin_value).strip():
                            cache_key = f"{query_key}_{str(origin_value).strip()}"
                            if cache_key in supplement_data_cache:
                                row_data = supplement_data_cache[cache_key]
                                for sub_field in sub_fields:
                                    if isinstance(sub_field, dict):
                                        sub_binding_key = sub_field.get('bindingKey', '')
                                        db_field = sub_field.get('dbField') or sub_binding_key
                                        sub_value = row_data.get(db_field, '')

                                        # 如果已经有新值的子字段数据，只更新originValue
                                        if sub_binding_key in form_values:
                                            form_values[sub_binding_key]['originValue'] = str(
                                                sub_value) if sub_value is not None else ''
                                        else:
                                            form_values[sub_binding_key] = {
                                                'newValue': '',
                                                'originValue': str(sub_value) if sub_value is not None else '',
                                                'inputType': 'supplement-sub',
                                                'fieldType': 'supplement-sub',
                                                'parentKey': parent_key,
                                                'label': sub_field.get('label', '')
                                            }

            validation_result = validate_form_data(config, form_values, query_values)

            if not validation_result['success']:
                fail_count += 1
                # 标记具体的校验错误
                fail_reason = '; '.join(validation_result.get('errors', []))
                ws.cell(row=row_idx, column=fail_column, value=fail_reason)
                ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC", end_color="FFFFCC",
                                                                            fill_type="solid")
            else:
                sql_result = generate_update_sql(config, form_values)

                # 检查是否有缺失字段的错误（严格模式下）
                if sql_result.get('missing_field_errors'):
                    fail_count += 1
                    fail_reason = '; '.join(sql_result['missing_field_errors'])
                    ws.cell(row=row_idx, column=fail_column, value=fail_reason)
                    ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC",
                                                                                end_color="FFFFCC", fill_type="solid")
                elif sql_result['forward_sqls'] and sql_result['backward_sqls']:
                    all_sql_statements.append({
                        'row': row_idx,
                        'forward_sqls': sql_result['forward_sqls'],
                        'backward_sqls': sql_result['backward_sqls']
                    })
                    success_count += 1
                else:
                    fail_count += 1
                    ws.cell(row=row_idx, column=fail_column, value='未生成有效的 SQL 语句')
                    ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC",
                                                                                end_color="FFFFCC", fill_type="solid")

        if success_count == 0:
            return {
                'success': False,
                'message': f'没有成功处理任何数据（失败{fail_count}条）',
                'forward_sqls': [],
                'backward_sqls': []
            }

        # 合并相同修改条件的SQL
        merged_result = merge_sql_statements(all_sql_statements)

        return {
            'success': True,
            'message': f'成功处理{success_count}条数据',
            'forward_sqls': merged_result['forward_sqls'],
            'backward_sqls': merged_result['backward_sqls'],
            'success_count': success_count,
            'fail_count': fail_count
        }

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"处理Sheet失败: {error_detail}")
        return {
            'success': False,
            'message': f'处理失败：{str(e)}',
            'forward_sqls': [],
            'backward_sqls': []
        }


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
                return JsonResponse({'success': False, 'message': '数据表中无有效的数据，请检查 Excel 文件格式是否正确'},
                                    status=400)

            if ws.max_row < 2:
                return JsonResponse({'success': False, 'message': 'Excel 文件没有数据行，请至少填写一行数据'},
                                    status=400)

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
                return JsonResponse({'success': False,
                                     'message': f'Excel 中没有有效的必填数据（共{ws.max_row - 1}行，但都没有必填字段的值）'},
                                    status=400)

            fail_column = ws.max_column + 1
            ws.cell(row=1, column=fail_column, value='失败原因')
            ws.cell(row=1, column=fail_column).font = Font(bold=True)
            ws.cell(row=1, column=fail_column).alignment = Alignment(horizontal='center')
            ws.cell(row=1, column=fail_column).fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC",
                                                                  fill_type="solid")

            total_rows = ws.max_row - 1
            success_count = 0
            fail_count = 0
            all_sql_statements = []

            # ==================== 第一步：收集所有补充框主字段值 ====================
            supplement_queries = {}  # {table_mainField: set of values}

            for row_idx in range(2, ws.max_row + 1):
                form_values, missing_columns = build_form_values_from_excel(ws, row_idx, headers, query_items,
                                                                            update_items)

                if missing_columns:
                    continue

                # 收集补充框主字段值
                for item in update_items:
                    if item.get('inputType') == 'supplement':
                        main_table = item.get('mainTable', '')
                        main_field = item.get('mainField', '')
                        parent_key = item.get('bindingKey', '')

                        if main_table and main_field:
                            query_key = f"{main_table}_{main_field}"
                            if query_key not in supplement_queries:
                                supplement_queries[query_key] = {
                                    'tableName': main_table,
                                    'mainField': main_field,
                                    'subFields': item.get('subFields', []),
                                    'values': set()
                                }

                            # 收集新值和原值
                            value_data = form_values.get(parent_key, {})
                            new_value = value_data.get('newValue', '')
                            origin_value = value_data.get('originValue', '')

                            if new_value:
                                supplement_queries[query_key]['values'].add(new_value)
                            if origin_value:
                                supplement_queries[query_key]['values'].add(origin_value)

            # ==================== 第二步：批量查询补充框数据 ====================
            supplement_data_cache = {}  # {table_mainField_value: {subField: value}}

            from django.db import connection

            for query_key, query_info in supplement_queries.items():
                if not query_info['values']:
                    continue

                table_name = query_info['tableName']
                main_field = query_info['mainField']
                sub_fields = query_info['subFields']
                main_values = list(query_info['values'])

                # 构建查询字段
                select_fields = [main_field]
                for sub_field in sub_fields:
                    if isinstance(sub_field, dict):
                        field_name = sub_field.get('dbField') or sub_field.get('bindingKey')
                        if field_name:
                            select_fields.append(field_name)
                    elif isinstance(sub_field, str):
                        select_fields.append(sub_field)

                # 使用 IN 查询
                fields_str = ', '.join(select_fields)
                values_str = ', '.join(["'" + str(v).replace("'", "''") + "'" for v in main_values])
                sql = f"SELECT {fields_str} FROM {table_name} WHERE {main_field} IN ({values_str})"

                print("=" * 50)
                print(f"批量查询补充框数据: {query_key}")
                print("SQL:", sql)
                print("=" * 50)

                with connection.cursor() as cursor:
                    cursor.execute(sql)
                    rows = cursor.fetchall()

                    for row in rows:
                        row_dict = {}
                        for idx, field in enumerate(select_fields):
                            row_dict[field] = row[idx]

                        # 以主字段值为key存储
                        main_val = row_dict.get(main_field, '')
                        supplement_data_cache[f"{query_key}_{main_val}"] = row_dict

            print(f"补充框数据缓存: {len(supplement_data_cache)} 条")

            # ==================== 第三步：处理每一行数据 ====================
            for row_idx in range(2, ws.max_row + 1):
                form_values, missing_columns = build_form_values_from_excel(ws, row_idx, headers, query_items,
                                                                            update_items)

                if missing_columns:
                    missing_cols_str = ', '.join(missing_columns)
                    fail_count += 1
                    ws.cell(row=row_idx, column=fail_column, value=f'缺少必需的列：{missing_cols_str}')
                    ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC",
                                                                                end_color="FFFFCC", fill_type="solid")
                    continue

                # ==================== 使用缓存的补充框数据填充子字段 ====================
                for item in update_items:
                    if item.get('inputType') == 'supplement':
                        main_table = item.get('mainTable', '')
                        main_field = item.get('mainField', '')
                        parent_key = item.get('bindingKey', '')
                        sub_fields = item.get('subFields', [])

                        if main_table and main_field and sub_fields:
                            query_key = f"{main_table}_{main_field}"
                            value_data = form_values.get(parent_key, {})
                            new_value = value_data.get('newValue', '')
                            origin_value = value_data.get('originValue', '')

                            # 填充新值的子字段
                            if new_value and str(new_value).strip():
                                cache_key = f"{query_key}_{str(new_value).strip()}"
                                if cache_key in supplement_data_cache:
                                    row_data = supplement_data_cache[cache_key]
                                    for sub_field in sub_fields:
                                        if isinstance(sub_field, dict):
                                            sub_binding_key = sub_field.get('bindingKey', '')
                                            db_field = sub_field.get('dbField') or sub_binding_key
                                            sub_value = row_data.get(db_field, '')

                                            form_values[sub_binding_key] = {
                                                'newValue': str(sub_value) if sub_value is not None else '',
                                                'originValue': '',
                                                'inputType': 'supplement-sub',
                                                'fieldType': 'supplement-sub',
                                                'parentKey': parent_key,
                                                'label': sub_field.get('label', '')
                                            }

                            # 填充原值的子字段
                            if origin_value and str(origin_value).strip():
                                cache_key = f"{query_key}_{str(origin_value).strip()}"
                                if cache_key in supplement_data_cache:
                                    row_data = supplement_data_cache[cache_key]
                                    for sub_field in sub_fields:
                                        if isinstance(sub_field, dict):
                                            sub_binding_key = sub_field.get('bindingKey', '')
                                            db_field = sub_field.get('dbField') or sub_binding_key
                                            sub_value = row_data.get(db_field, '')

                                            # 如果已经有新值的子字段数据，只更新originValue
                                            if sub_binding_key in form_values:
                                                form_values[sub_binding_key]['originValue'] = str(
                                                    sub_value) if sub_value is not None else ''
                                            else:
                                                form_values[sub_binding_key] = {
                                                    'newValue': '',
                                                    'originValue': str(sub_value) if sub_value is not None else '',
                                                    'inputType': 'supplement-sub',
                                                    'fieldType': 'supplement-sub',
                                                    'parentKey': parent_key,
                                                    'label': sub_field.get('label', '')
                                                }

                validation_result = validate_form_data(config, form_values, query_values)

                if not validation_result['success']:
                    fail_count += 1
                    fail_reason = '; '.join(validation_result.get('errors', []))
                    ws.cell(row=row_idx, column=fail_column, value=fail_reason)
                    ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC",
                                                                                end_color="FFFFCC", fill_type="solid")
                else:
                    sql_result = generate_update_sql(config, form_values)

                    # 检查是否有缺失字段的错误（严格模式下）
                    if sql_result.get('missing_field_errors'):
                        fail_count += 1
                        fail_reason = '; '.join(sql_result['missing_field_errors'])
                        ws.cell(row=row_idx, column=fail_column, value=fail_reason)
                        ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC",
                                                                                    end_color="FFFFCC", fill_type="solid")
                    elif sql_result['forward_sqls'] and sql_result['backward_sqls']:
                        # 直接存储完整的sql_result，保留raw和formatted
                        all_sql_statements.append({
                            'row': row_idx,
                            'forward_sqls': sql_result['forward_sqls'],
                            'backward_sqls': sql_result['backward_sqls']
                        })
                        success_count += 1
                    else:
                        fail_count += 1
                        ws.cell(row=row_idx, column=fail_column, value='未生成有效的 SQL 语句')
                        ws.cell(row=row_idx, column=fail_column).fill = PatternFill(start_color="FFFFCC",
                                                                                    end_color="FFFFCC",
                                                                                    fill_type="solid")

            stats_ws = wb.create_sheet(title='导入统计')
            stats_ws.cell(row=1, column=1, value='总行数').font = Font(bold=True)
            stats_ws.cell(row=1, column=2, value=total_rows).font = Font(bold=True)
            stats_ws.cell(row=2, column=1, value='成功数').font = Font(bold=True)
            stats_ws.cell(row=2, column=2, value=success_count).font = Font(bold=True)
            stats_ws.cell(row=3, column=1, value='失败数').font = Font(bold=True)
            stats_ws.cell(row=3, column=2, value=fail_count).font = Font(bold=True)
            stats_ws.cell(row=4, column=1, value='成功率').font = Font(bold=True)
            stats_ws.cell(row=4, column=2,
                          value=f'{success_count / total_rows * 100:.2f}%' if total_rows > 0 else '0%').font = Font(
                bold=True)

            dynamic_no = ''
            if query_values:
                dynamic_no_data = query_values.get('dynamicNo', '')
                if isinstance(dynamic_no_data, dict):
                    dynamic_no = dynamic_no_data.get('value', '')
                elif isinstance(dynamic_no_data, str):
                    dynamic_no = dynamic_no_data

            # 使用路径配置获取保存路径
            save_dir = get_save_path_from_config()
            print(f"[DEBUG BATCH] 批量导入SQL文件保存路径: {save_dir}")

            os.makedirs(save_dir, exist_ok=True)

            all_success = (fail_count == 0 and success_count > 0)

            sql_file_path = None
            if all_success and all_sql_statements:
                # 文件名格式：编号_文件名.sql
                sql_filename = f"{dynamic_no}_{form_name}.sql"
                sql_filepath = os.path.join(save_dir, sql_filename)

                # ==================== 第四步：合并相同修改条件的SQL ====================
                merged_result = merge_sql_statements(all_sql_statements)

                sql_content = []

                sql_content.append("1.执行语句")
                for idx, sql in enumerate(merged_result['forward_sqls'], 1):
                    # 确保SQL末尾有分号
                    if not sql.rstrip().endswith(';'):
                        sql = sql.rstrip() + ';'
                    sql_content.append(sql)
                    sql_content.append("")
                sql_content.append("2.回退语句")
                for idx, sql in enumerate(merged_result['backward_sqls'], 1):
                    # 确保SQL末尾有分号
                    if not sql.rstrip().endswith(';'):
                        sql = sql.rstrip() + ';'
                    sql_content.append(sql)
                    sql_content.append("")

                # 添加数据库信息
                database_ip_ids = config.get('databaseIpIds', [])
                if database_ip_ids:
                    db_configs = DatabaseIPConfig.objects.filter(id__in=database_ip_ids).order_by('id')
                    if db_configs:
                        sql_content.append("3.数据库")
                        for db_config in db_configs:
                            sql_content.append(f"ip：{db_config.ip_address}")
                            sql_content.append(f"库名：{db_config.database_name}")
                            sql_content.append("")

                with open(sql_filepath, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(sql_content))
                sql_file_path = sql_filepath

            excel_file_path = None
            if fail_count > 0:
                now = datetime.now()
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
