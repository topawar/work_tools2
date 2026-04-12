import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from work_tools2.models import FormConfig, FormQueryItem, FormUpdateItem
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl import load_workbook
from datetime import datetime
from io import BytesIO
import os


@csrf_exempt
def download_merge_template(request):
    """下载合并模板（多Sheet Excel）"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            form_ids = data.get('formIds', [])
            file_prefix = data.get('filePrefix', 'merge')

            if not form_ids or len(form_ids) == 0:
                return JsonResponse({
                    'success': False,
                    'message': '请至少选择一个表单'
                }, status=400)

            # 创建Excel工作簿
            wb = openpyxl.Workbook()
            # 删除默认创建的sheet
            if 'Sheet' in wb.sheetnames:
                del wb['Sheet']

            # 为每个选中的表单创建一个Sheet
            for form_id in form_ids:
                try:
                    config = FormConfig.objects.get(id=form_id)

                    # 创建Sheet，使用表单名称作为Sheet名
                    ws = wb.create_sheet(title=config.form_name)

                    # 设置表头样式
                    header_font = Font(bold=True, color='FFFFFF')
                    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
                    header_alignment = Alignment(horizontal='center', vertical='center')

                    # 构建表头：查询字段 + 更新字段
                    headers = []

                    # 添加查询字段
                    query_items = FormQueryItem.objects.filter(form_config=config).order_by('sort_order')
                    for item in query_items:
                        headers.append(f'{item.label}')

                    # 添加更新字段
                    update_items = FormUpdateItem.objects.filter(form_config=config).order_by('sort_order')
                    for item in update_items:
                        # 跳过计算字段，计算字段由表达式自动生成
                        if item.input_type == 'calculated':
                            continue

                        if item.input_type == 'supplement':
                            # 补充框：主字段（新值和原值都需要用户填写）
                            headers.append(f'新{item.label}')
                            headers.append(f'原{item.label}')

                            # 添加子字段（只有原值需要填写，新值自动查询）
                            sub_fields = item.sub_fields or []
                            for sub_field in sub_fields:
                                if isinstance(sub_field, dict):
                                    sub_label = sub_field.get('label', sub_field.get('bindingKey', ''))
                                    headers.append(f'原{sub_label}')
                                else:
                                    headers.append(f'原{sub_field}')
                        else:
                            # 普通字段：新值和原值
                            headers.append(f'新{item.label}')
                            headers.append(f'原{item.label}')

                    # 写入表头
                    for col_idx, header in enumerate(headers, 1):
                        cell = ws.cell(row=1, column=col_idx, value=header)
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment

                    # 添加示例数据行（第二行）
                    example_row = []
                    for item in query_items:
                        example_row.append(item.default_value or '')

                    for item in update_items:
                        # 跳过计算字段
                        if item.input_type == 'calculated':
                            continue

                        if item.input_type == 'supplement':
                            example_row.append(item.new_default_value or '')  # 主字段新值
                            example_row.append(item.origin_default_value or '')  # 主字段原值

                            sub_fields = item.sub_fields or []
                            for sub_field in sub_fields:
                                example_row.append('')  # 子字段原值（新值自动查询，不需要填写）
                        else:
                            example_row.append(item.new_default_value or '')
                            example_row.append(item.origin_default_value or '')

                        for col_idx, value in enumerate(example_row, 1):
                            ws.cell(row=2, column=col_idx, value=value)

                        # 设置列宽 - 根据表头和内容自适应
                        from openpyxl.utils import get_column_letter

                        for col_idx in range(1, len(headers) + 1):
                            column_letter = get_column_letter(col_idx)

                            # 获取表头的长度（中文按2个字符计算）
                            header_value = headers[col_idx - 1] if col_idx <= len(headers) else ''
                            max_length = len(str(header_value).encode('utf-8'))

                            # 遍历该列的所有单元格，找到最长的内容
                            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
                                for cell in row:
                                    if cell.value is not None:
                                        # 中文按2个字符宽度计算
                                        cell_length = len(str(cell.value).encode('utf-8'))
                                        if cell_length > max_length:
                                            max_length = cell_length

                            # 设置列宽：最大长度 + 额外空间（2-4个字符），最小10，最大50
                            adjusted_width = min(max(max_length + 4, 10), 50)
                            ws.column_dimensions[column_letter].width = adjusted_width

                except FormConfig.DoesNotExist:
                    continue

            # 保存Excel到内存
            from io import BytesIO
            output = BytesIO()
            wb.save(output)
            output.seek(0)

            # 返回Excel文件
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename={file_prefix}_合并模板.xlsx'

            return response

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'JSON 解析失败'
            }, status=400)
        except Exception as e:
            import traceback
            print(f"生成模板异常: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({
                'success': False,
                'message': f'生成失败：{str(e)}'
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': '仅支持 POST 请求'
    }, status=405)
