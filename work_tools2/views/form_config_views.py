import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from work_tools2.models import Menu, FormConfig, FormQueryItem, FormUpdateItem


@csrf_exempt
def get_menu_list(request):
    """获取一级菜单列表（用于选择父级菜单），过滤掉group_name为'系统设置'的菜单"""
    if request.method == 'GET':
        try:
            menus = Menu.objects.filter(
                parent_id__isnull=True
            ).exclude(
                group_name='系统设置'
            ).order_by('sort_order')

            menu_list = []
            for menu in menus:
                menu_list.append({
                    'id': menu.id,
                    'name': menu.name,
                    'url': menu.url,
                })

            return JsonResponse({
                'success': True,
                'data': menu_list
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'获取失败：{str(e)}'
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': '仅支持 GET 请求'
    }, status=405)


@csrf_exempt
def create_or_get_menu(request):
    """创建或获取一级菜单（支持手动输入新菜单名）"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            menu_name = data.get('menuName', '').strip()

            if not menu_name:
                return JsonResponse({
                    'success': False,
                    'message': '菜单名称不能为空'
                }, status=400)

            existing_menu = Menu.objects.filter(
                name=menu_name,
                parent_id__isnull=True
            ).first()

            if existing_menu:
                return JsonResponse({
                    'success': True,
                    'data': {
                        'id': existing_menu.id,
                        'name': existing_menu.name,
                        'isNew': False
                    }
                })
            else:
                new_menu = Menu.objects.create(
                    name=menu_name,
                    url='#',
                    parent_id=None,
                    icon='bi-folder',
                    pinyin='',
                    sort_order=Menu.objects.filter(parent_id__isnull=True).count(),
                    is_visible=True,
                    group_name='',
                )

                return JsonResponse({
                    'success': True,
                    'data': {
                        'id': new_menu.id,
                        'name': new_menu.name,
                        'isNew': True
                    }
                })
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'JSON 解析失败'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'创建失败：{str(e)}'
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': '仅支持 POST 请求'
    }, status=405)


@csrf_exempt
def save_form_config(request):
    """保存表单配置（新增或更新）"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            form_id = data.get('formId')
            form_name = data.get('formName')
            table_name_list = data.get('tableNameList', [])
            parent_menu_id = data.get('parentMenuId')
            query_items = data.get('queryItems', [])
            update_items = data.get('updateItems', [])

            if not form_name:
                return JsonResponse({'success': False, 'message': '表单名称不能为空'}, status=400)

            if not table_name_list or len(table_name_list) == 0:
                return JsonResponse({'success': False, 'message': '至少需要配置一个表名'}, status=400)

            parent_menu_name = ''
            if parent_menu_id:
                try:
                    parent_menu = Menu.objects.get(id=parent_menu_id)
                    parent_menu_name = parent_menu.name
                except Menu.DoesNotExist:
                    pass

            if form_id:
                try:
                    config = FormConfig.objects.get(id=form_id)
                    config.form_name = form_name
                    config.table_name_list = table_name_list
                    config.save()

                    menu_url = f'/dynamic/{form_id}'
                    Menu.objects.update_or_create(
                        url=menu_url,
                        defaults={
                            'name': form_name,
                            'parent_id': parent_menu_id if parent_menu_id else None,
                            'group_name': parent_menu_name,
                            'is_visible': True,
                        }
                    )
                except FormConfig.DoesNotExist:
                    return JsonResponse({'success': False, 'message': '表单配置不存在'}, status=404)
            else:
                config = FormConfig.objects.create(
                    form_name=form_name,
                    table_name_list=table_name_list,
                    is_active=True,
                )
                form_id = config.id

                menu_url = f'/dynamic/{form_id}'
                Menu.objects.create(
                    name=form_name,
                    url=menu_url,
                    parent_id=parent_menu_id if parent_menu_id else None,
                    icon='bi-file-earmark-text',
                    pinyin='',
                    sort_order=0,
                    is_visible=True,
                    group_name=parent_menu_name,
                )

            FormQueryItem.objects.filter(form_config=config).delete()
            for item_data in query_items:
                FormQueryItem.objects.create(
                    form_config=config,
                    label=item_data.get('label'),
                    field_type=item_data.get('type', 'text'),
                    binding_key=item_data.get('bindingKey'),
                    sort_order=item_data.get('sortOrder', 0),
                    connected_table=item_data.get('connectedTable', []),
                    valid_rule=item_data.get('ValidRule', 'required'),
                    default_value=item_data.get('defaultValue', ''),
                )

            FormUpdateItem.objects.filter(form_config=config).delete()
            for item_data in update_items:
                FormUpdateItem.objects.create(
                    form_config=config,
                    label=item_data.get('label'),
                    field_type=item_data.get('type', 'text'),
                    binding_key=item_data.get('bindingKey'),
                    sort_order=item_data.get('sortOrder', 0),
                    input_type=item_data.get('inputType', 'input'),
                    connected_table=item_data.get('connectedTable', []),
                    new_valid_rule=item_data.get('newValidRule', 'required'),
                    origin_valid_rule=item_data.get('originValidRule', 'required'),
                    origin_default_value=item_data.get('originDefaultValue', ''),
                    new_default_value=item_data.get('newDefaultValue', ''),
                    main_field=item_data.get('mainField', ''),
                    sub_fields=item_data.get('subFields', []),
                    options=item_data.get('options', []),
                )

            return JsonResponse({
                'success': True,
                'message': '保存成功',
                'form_id': form_id
            })
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'JSON 解析失败'}, status=400)
        except Exception as e:
            import traceback
            print(f"保存异常: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({'success': False, 'message': f'保存失败：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)


@csrf_exempt
def get_form_configs(request):
    """获取所有表单配置列表"""
    if request.method == 'GET':
        try:
            configs = FormConfig.objects.all().order_by('-created_at')
            config_list = []

            for config in configs:
                config_list.append({
                    'id': config.id,
                    'form_name': config.form_name,
                    'table_name_list': config.table_name_list,
                    'created_at': config.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                })

            return JsonResponse({'success': True, 'data': config_list})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'获取失败：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)


@csrf_exempt
def get_form_config_detail(request, form_id):
    """获取单个表单配置详情"""
    if request.method == 'GET':
        try:
            config = FormConfig.objects.get(id=form_id)

            query_items = []
            for item in config.query_items.all():
                query_items.append({
                    'label': item.label,
                    'type': item.field_type,
                    'defaultValue': item.default_value,
                    'bindingKey': item.binding_key,
                    'sortOrder': item.sort_order,
                    'connectedTable': item.connected_table,
                    'ValidRule': item.valid_rule,
                })

            update_items = []
            for item in config.update_items.all():
                update_items.append({
                    'label': item.label,
                    'type': item.field_type,
                    'originDefaultValue': item.origin_default_value,
                    'newDefaultValue': item.new_default_value,
                    'bindingKey': item.binding_key,
                    'sortOrder': item.sort_order,
                    'inputType': item.input_type,
                    'connectedTable': item.connected_table,
                    'newValidRule': item.new_valid_rule,
                    'originValidRule': item.origin_valid_rule,
                    'mainField': item.main_field,
                    'subFields': item.sub_fields,
                    'options': item.options,
                })

            return JsonResponse({
                'success': True,
                'data': {
                    'formId': config.id,
                    'formName': config.form_name,
                    'tableNameList': config.table_name_list,
                    'queryItems': query_items,
                    'updateItems': update_items,
                }
            })
        except FormConfig.DoesNotExist:
            return JsonResponse({'success': False, 'message': '表单配置不存在'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'获取失败：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)


@csrf_exempt
def delete_form_config(request, form_id):
    """删除表单配置"""
    if request.method == 'DELETE':
        try:
            config = FormConfig.objects.get(id=form_id)

            menu_url = f'/dynamic/{form_id}'
            Menu.objects.filter(url=menu_url).delete()

            config.delete()

            return JsonResponse({'success': True, 'message': '删除成功'})
        except FormConfig.DoesNotExist:
            return JsonResponse({'success': False, 'message': '表单配置不存在'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'删除失败：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 DELETE 请求'}, status=405)
