import json
import os
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from openpyxl import load_workbook
from work_tools2.models import FormConfig, FormQueryItem, FormUpdateItem, DatabaseIPConfig
from work_tools2.path_utils import get_save_path_from_config


@csrf_exempt
def batch_import_merge(request):
    """批量导入并合并多个表单的SQL"""
    if request.method == 'POST':
        try:
            file = request.FILES.get('file')
            form_ids_json = request.POST.get('formIds')
            query_values_json = request.POST.get('queryValues')  # 公共字段值
            
            if not file or not form_ids_json:
                return JsonResponse({'success': False, 'message': '缺少文件或表单ID参数'}, status=400)
            
            form_ids = json.loads(form_ids_json)
            if not form_ids or len(form_ids) == 0:
                return JsonResponse({'success': False, 'message': '请至少选择一个表单'}, status=400)
            
            # 解析公共字段
            query_values = {}
            if query_values_json:
                try:
                    query_values = json.loads(query_values_json)
                except json.JSONDecodeError:
                    query_values = {}
            
            # 验证公共字段
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
            
            # 加载Excel文件
            wb = load_workbook(file)
            
            # 存储所有SQL语句
            all_forward_sqls = []
            all_backward_sqls = []
            failed_sheets = []  # 存储失败的Sheet信息（包含worksheet对象）
            success_count = 0
            total_processed = 0
            
            # 遍历每个Sheet
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                total_processed += 1
                
                # 根据Sheet名称查找对应的表单配置
                config = FormConfig.objects.filter(form_name=sheet_name).first()
                if not config:
                    failed_sheets.append({
                        'sheet': sheet_name,
                        'error': f'未找到表单配置：{sheet_name}',
                        'ws': ws
                    })
                    continue
                
                try:
                    # 获取表单配置
                    query_items_data = []
                    for item in FormQueryItem.objects.filter(form_config=config).order_by('sort_order'):
                        query_items_data.append({
                            'label': item.label,
                            'bindingKey': item.binding_key,
                            'type': item.field_type,
                            'defaultValue': item.default_value,
                            'ValidRule': item.valid_rule,
                            'connectedTable': item.connected_table or [],  # 添加关联表
                        })
                    
                    update_items_data = []
                    for item in FormUpdateItem.objects.filter(form_config=config).order_by('sort_order'):
                        update_item = {
                            'label': item.label,
                            'bindingKey': item.binding_key,
                            'inputType': item.input_type,
                            'type': item.field_type,
                            'newDefaultValue': item.new_default_value,
                            'originDefaultValue': item.origin_default_value,
                            'newValidRule': item.new_valid_rule,
                            'originValidRule': item.origin_valid_rule,
                            'mainTable': item.main_table,
                            'mainField': item.main_field,
                            'subFields': item.sub_fields or [],
                            'connectedTable': item.connected_table or [],  # 添加关联表
                        }
                        
                        # 如果是计算字段，添加表达式配置
                        if item.input_type == 'calculated':
                            # 从数据库获取表达式配置（假设存储在某个字段中）
                            # 这里需要根据实际的数据库结构来调整
                            update_item['expressions'] = item.expressions or {}  # 假设有expressions字段
                        
                        # 如果有componentName，从ComponentConfig表获取最新的options
                        if item.component_name:
                            from work_tools2.models import ComponentConfig
                            component = ComponentConfig.objects.filter(name=item.component_name).first()
                            if component:
                                update_item['options'] = component.options
                            else:
                                update_item['options'] = item.options or []
                        else:
                            update_item['options'] = item.options or []
                        
                        update_items_data.append(update_item)
                    
                    # 调用现有的batch_import逻辑处理这个Sheet
                    from work_tools2.views.dynamic_views import process_single_sheet_import
                    
                    result = process_single_sheet_import(
                        ws, 
                        query_items_data, 
                        update_items_data, 
                        query_values,
                        config.form_name,
                        config.table_name_list  # 添加表名列表
                    )
                    
                    if result['success']:
                        all_forward_sqls.extend(result['forward_sqls'])
                        all_backward_sqls.extend(result['backward_sqls'])
                        success_count += 1
                    else:
                        failed_sheets.append({
                            'sheet': sheet_name,
                            'error': result.get('message', '处理失败'),
                            'ws': ws  # 保留worksheet对象，已标记失败原因
                        })
                
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    print(f"处理Sheet '{sheet_name}' 失败: {error_detail}")
                    failed_sheets.append({
                        'sheet': sheet_name,
                        'error': f'处理失败：{str(e)}',
                        'ws': ws
                    })
            
            # 合并所有SQL语句
            now = datetime.now()
            year_month = now.strftime('%Y%m')
            day = now.strftime('%d')
            save_dir = f"D:\\临时文件\\{year_month}\\{day}"
            os.makedirs(save_dir, exist_ok=True)
            
            # 获取公共字段值
            dynamic_no = ''
            file_prefix = 'merge'
            if query_values:
                dynamic_no_data = query_values.get('dynamicNo', '')
                if isinstance(dynamic_no_data, dict):
                    dynamic_no = dynamic_no_data.get('value', '')
                elif isinstance(dynamic_no_data, str):
                    dynamic_no = dynamic_no_data
                
                file_prefix_data = query_values.get('filePrefix', '')
                if isinstance(file_prefix_data, dict):
                    file_prefix = file_prefix_data.get('value', 'merge')
                elif isinstance(file_prefix_data, str):
                    file_prefix = file_prefix_data
            
            fail_count = len(failed_sheets)
            
            # 判断是否全部成功
            all_success = (fail_count == 0 and success_count > 0)
            
            # 如果有失败的Sheet，生成带有错误信息的Excel文件（包含所有Sheet）
            excel_file_path = None
            if not all_success:
                from openpyxl import Workbook
                from openpyxl.styles import Font, Alignment, PatternFill
                
                # 创建结果Workbook
                wb_result = Workbook()
                
                # 删除默认的sheet
                if 'Sheet' in wb_result.sheetnames:
                    del wb_result['Sheet']

                # 复制所有Sheet（包括成功和失败的）- process_single_sheet_import已经在每行标记了具体的错误信息
                for sheet_name in wb.sheetnames:
                    original_ws = wb[sheet_name]

                    # 复制Sheet（Sheet名称最多31字符）
                    result_ws = wb_result.create_sheet(title=sheet_name[:31])

                    # 复制所有数据和样式（保留process_single_sheet_import写入的行级错误信息）
                    for row in original_ws.iter_rows():
                        for cell in row:
                            new_cell = result_ws.cell(row=cell.row, column=cell.column, value=cell.value)
                            if cell.font:
                                new_cell.font = Font(
                                    name=cell.font.name,
                                    size=cell.font.size,
                                    bold=cell.font.bold,
                                    italic=cell.font.italic
                                )
                            if cell.fill and cell.fill.start_color:
                                new_cell.fill = PatternFill(
                                    start_color=cell.fill.start_color.rgb if cell.fill.start_color else None,
                                    end_color=cell.fill.end_color.rgb if cell.fill.end_color else None,
                                    fill_type=cell.fill.fill_type or 'solid'
                                )
                            if cell.alignment:
                                new_cell.alignment = Alignment(
                                    horizontal=cell.alignment.horizontal,
                                    vertical=cell.alignment.vertical,
                                    wrap_text=cell.alignment.wrapText
                                )

                # 保存Excel文件
                excel_filename = f"{dynamic_no}_导入失败_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
                excel_filepath = os.path.join(save_dir, excel_filename)
                wb_result.save(excel_filepath)
                excel_file_path = excel_filepath
            
            # 如果全部成功，生成SQL文件
            sql_file_path = None
            if all_success and (all_forward_sqls or all_backward_sqls):
                # 文件名格式：编号_文件名.sql
                sql_filename = f"{dynamic_no}_{file_prefix}.sql"
                sql_filepath = os.path.join(save_dir, sql_filename)
                
                # 生成合并的SQL文件内容
                timestamp = now.strftime('%Y%m%d_%H%M%S')
                forward_sql_content = generate_merged_sql_file(all_forward_sqls, file_prefix, timestamp, is_forward=True)
                backward_sql_content = generate_merged_sql_file(all_backward_sqls, file_prefix, timestamp, is_forward=False)
                
                # 收集所有表单的databaseIpIds（去重）
                all_database_ip_ids = set()
                for form_id in form_ids:
                    form_config = FormConfig.objects.filter(id=form_id).first()
                    if form_config and form_config.database_ip_ids:
                        all_database_ip_ids.update(form_config.database_ip_ids)
                
                # 写入SQL文件
                sql_content = []
                
                sql_content.append("1.执行语句")
                sql_content.append(forward_sql_content)
                sql_content.append("")
                sql_content.append("2.回退语句")
                sql_content.append(backward_sql_content)
                
                # 添加数据库信息
                if all_database_ip_ids:
                    db_configs = DatabaseIPConfig.objects.filter(id__in=all_database_ip_ids).order_by('id')
                    if db_configs:
                        sql_content.append("3.数据库")
                        for db_config in db_configs:
                            sql_content.append(f"ip：{db_config.ip_address}")
                            sql_content.append(f"库名：{db_config.database_name}")
                            sql_content.append("")
                
                with open(sql_filepath, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(sql_content))
                
                sql_file_path = sql_filepath
            
            # 返回结果
            if all_success:
                return JsonResponse({
                    'success': True,
                    'message': f'批量导入成功！共处理{total_processed}个Sheet，全部成功',
                    'sqlFilePath': sql_file_path,
                    'excelFilePath': None,
                    'totalSheets': total_processed,
                    'successCount': success_count,
                    'failCount': 0,
                    'failed_sheets': []
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'批量导入失败！共处理{total_processed}个Sheet，成功{success_count}个，失败{fail_count}个',
                    'sqlFilePath': None,
                    'excelFilePath': excel_file_path,
                    'totalSheets': total_processed,
                    'successCount': success_count,
                    'failCount': fail_count,
                    'failed_sheets': [{'sheet': f['sheet'], 'error': f['error']} for f in failed_sheets]
                })

        except json.JSONDecodeError as e:
            return JsonResponse({'success': False, 'message': f'JSON 解析失败：{str(e)}'}, status=400)
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"批量导入合并异常: {error_detail}")
            return JsonResponse({'success': False, 'message': f'服务器错误：{str(e)}'}, status=500)
    
    return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)


def generate_merged_sql_file(sql_statements, file_prefix, timestamp, is_forward=True):
    """生成合并的SQL文件内容"""
    lines = []
    for idx, sql_item in enumerate(sql_statements, 1):
        # 如果sql_item是字典，使用formatted字段，否则直接使用
        if isinstance(sql_item, dict):
            sql = sql_item.get('formatted', sql_item.get('raw', ''))
        else:
            sql = str(sql_item)

        lines.append(sql + ';')
        lines.append('')
    
    return '\n'.join(lines)
