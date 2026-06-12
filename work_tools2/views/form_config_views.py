import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from work_tools2.models import Menu, FormConfig, FormQueryItem, FormUpdateItem
from django.db import connection
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

@csrf_exempt
def get_menu_list(request):
    """获取一级菜单列表（用于选择父级菜单），过滤掉group_name为'系统设置'的菜单"""
    if request.method == 'GET':
        try:
            menus = Menu.objects.filter(
                parent_id__isnull=True
            ).exclude(
                group_name='系统设置'
            ).exclude(
                name__in=['首页', '表单合并']
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
                    group_name='主菜单',  # 一级菜单的group_name设置为主菜单
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
            database_ip_ids = data.get('databaseIpIds', [])
            parent_menu_id = data.get('parentMenuId')
            query_items = data.get('queryItems', [])
            update_items = data.get('updateItems', [])

            if not form_name:
                return JsonResponse({'success': False, 'message': '表单名称不能为空'}, status=400)

            if not table_name_list or len(table_name_list) == 0:
                return JsonResponse({'success': False, 'message': '至少需要配置一个表名'}, status=400)
            
            # 校验必须选择至少一个数据库配置
            if not database_ip_ids or len(database_ip_ids) == 0:
                return JsonResponse({'success': False, 'message': '必须选择至少一个数据库配置'}, status=400)
            
            # 校验表单名称唯一性（排除当前编辑的表单）
            existing_form = FormConfig.objects.filter(form_name=form_name).exclude(id=form_id).first()
            if existing_form:
                return JsonResponse({'success': False, 'message': f'表单名称“{form_name}”已存在，请使用其他名称'}, status=400)

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
                    config.database_ip_ids = database_ip_ids
                    config.query_mode = data.get('queryMode', 'strict')  # 添加查询模式，默认严格
                    config.append_ops_remark = data.get('appendOpsRemark', True)  # 添加操作备注配置，默认拼接
                    config.save()

                    menu_url = f'/dynamic/{form_id}'
                    
                    # 使用 pypinyin 生成拼音
                    try:
                        from pypinyin import pinyin, Style
                        pinyin_list = pinyin(form_name, style=Style.NORMAL)
                        pinyin_str = ''.join([item[0] for item in pinyin_list])
                    except ImportError:
                        pinyin_str = ''
                    
                    Menu.objects.update_or_create(
                        url=menu_url,
                        defaults={
                            'name': form_name,
                            'pinyin': pinyin_str,  # 保存拼音
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
                    database_ip_ids=database_ip_ids,
                    query_mode=data.get('queryMode', 'strict'),  # 添加查询模式，默认严格
                    append_ops_remark=data.get('appendOpsRemark', True),  # 添加操作备注配置，默认拼接
                    is_active=True,
                )
                form_id = config.id

                menu_url = f'/dynamic/{form_id}'
                
                # 使用 pypinyin 生成拼音
                try:
                    from pypinyin import pinyin, Style
                    pinyin_list = pinyin(form_name, style=Style.NORMAL)
                    pinyin_str = ''.join([item[0] for item in pinyin_list])
                except ImportError:
                    pinyin_str = ''
                
                Menu.objects.create(
                    name=form_name,
                    url=menu_url,
                    parent_id=parent_menu_id if parent_menu_id else None,
                    icon='bi-file-earmark-text',
                    pinyin=pinyin_str,  # 保存拼音
                    sort_order=0,
                    is_visible=True,
                    group_name=parent_menu_name,
                )

            FormQueryItem.objects.filter(form_config=config).delete()
            for item_data in query_items:
                print(f"[DEBUG SAVE] 保存查询字段: label={item_data.get('label')}, bindingKey={item_data.get('bindingKey')}, defaultValue='{item_data.get('defaultValue', '')}'")
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
                    component_name=item_data.get('componentName', ''),
                    main_table=item_data.get('mainTable', ''),
                    main_field=item_data.get('mainField', ''),
                    sub_fields=item_data.get('subFields', []),
                    options=item_data.get('options', []),
                    expressions=item_data.get('expressions', {}),  # 添加 expressions 字段
                )

            # 重新计算所有配置项的使用次数
            from work_tools2.models import ComponentConfig
            
            # 重置所有配置项的使用次数为0
            ComponentConfig.objects.all().update(usage_count=0)
            
            # 统计每个配置项被引用的次数
            from django.db.models import Count
            component_usage = FormUpdateItem.objects.filter(
                component_name__isnull=False
            ).exclude(
                component_name=''
            ).values(
                'component_name'
            ).annotate(
                count=Count('id')
            )
            
            # 更新每个配置项的使用次数
            for usage in component_usage:
                component_name = usage['component_name']
                count = usage['count']
                ComponentConfig.objects.filter(name=component_name).update(usage_count=count)

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
                # 获取父级菜单名称
                parent_menu_name = ''
                menu_url = f'/dynamic/{config.id}'
                menu = Menu.objects.filter(url=menu_url).first()
                if menu and menu.parent_id:
                    parent_menu = Menu.objects.filter(id=menu.parent_id).first()
                    if parent_menu:
                        parent_menu_name = parent_menu.name
                
                config_list.append({
                    'id': config.id,
                    'form_name': config.form_name,
                    'table_name_list': config.table_name_list,
                    'parent_menu_name': parent_menu_name,  # 添加父菜单名称
                    'query_mode': config.query_mode,  # 添加查询模式
                    'append_ops_remark': config.append_ops_remark,  # 添加操作备注配置
                    'created_at': config.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                })

            return JsonResponse({'success': True, 'data': config_list})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'获取失败：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)


def get_form_config_detail(request, form_id):
    """获取单个表单配置详情"""
    if request.method == 'GET':
        try:
            from work_tools2.models import ComponentConfig

            config = FormConfig.objects.get(id=form_id)

            # 获取父级菜单名称
            parent_menu_name = ''
            menu_url = f'/dynamic/{form_id}'
            menu = Menu.objects.filter(url=menu_url).first()
            if menu and menu.parent_id:
                parent_menu = Menu.objects.filter(id=menu.parent_id).first()
                if parent_menu:
                    parent_menu_name = parent_menu.name

            query_items = []
            all_query_items = list(config.query_items.all())


            for idx, item in enumerate(all_query_items):

                query_item_data = {
                    'label': item.label,
                    'type': item.field_type,
                    'defaultValue': item.default_value,
                    'bindingKey': item.binding_key,
                    'sortOrder': item.sort_order,
                    'connectedTable': item.connected_table,
                    'ValidRule': item.valid_rule,
                }
                query_items.append(query_item_data)
            
            print(f"[DEBUG] 总共返回 {len(query_items)} 个查询字段")

            update_items = []
            for item in config.update_items.all():
                # print(f"[DEBUG LOAD] 加载更新字段: {item.label}, inputType={item.input_type}, expressions={item.expressions}")  # 调试日志
                update_item = {
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
                    'componentName': item.component_name,
                    'mainTable': item.main_table,
                    'mainField': item.main_field,
                    'subFields': item.sub_fields,
                    'expressions': item.expressions,  # 添加 expressions 字段
                }

                # 如果有componentName，从ComponentConfig表获取最新的options
                if item.component_name:
                    component = ComponentConfig.objects.filter(name=item.component_name).first()
                    if component:
                        update_item['options'] = component.options
                    else:
                        # 如果配置项不存在，使用保存的options或空列表
                        update_item['options'] = item.options or []
                else:
                    # 没有componentName，使用保存的options
                    update_item['options'] = item.options or []

                update_items.append(update_item)

            return JsonResponse({
                'success': True,
                'data': {
                    'formId': config.id,
                    'formName': config.form_name,
                    'tableNameList': config.table_name_list,
                    'databaseIpIds': config.database_ip_ids,
                    'queryMode': config.query_mode,  # 添加查询模式
                    'appendOpsRemark': config.append_ops_remark,  # 添加操作备注配置
                    'parentMenuName': parent_menu_name,
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

            # 获取表单对应的菜单
            menu_url = f'/dynamic/{form_id}'
            menu_to_delete = Menu.objects.filter(url=menu_url).first()
            
            # 如果找到菜单且有父菜单，检查是否是最后一个子菜单
            if menu_to_delete and menu_to_delete.parent:
                parent_menu = menu_to_delete.parent
                # 统计父菜单下剩余的子菜单数量（排除当前要删除的）
                sibling_count = Menu.objects.filter(parent=parent_menu).exclude(id=menu_to_delete.id).count()
                
                # 如果是最后一个子菜单，连同父菜单一起删除
                if sibling_count == 0:
                    parent_menu.delete()
            
            # 删除表单对应的菜单
            Menu.objects.filter(url=menu_url).delete()

            # 删除表单配置
            config.delete()
            
            # 重新计算所有配置项的使用次数
            from work_tools2.models import ComponentConfig
            from django.db.models import Count
            
            # 重置所有配置项的使用次数为0
            ComponentConfig.objects.all().update(usage_count=0)
            
            # 统计每个配置项被引用的次数
            component_usage = FormUpdateItem.objects.filter(
                component_name__isnull=False
            ).exclude(
                component_name=''
            ).values(
                'component_name'
            ).annotate(
                count=Count('id')
            )
            
            # 更新每个配置项的使用次数
            for usage in component_usage:
                component_name = usage['component_name']
                count = usage['count']
                ComponentConfig.objects.filter(name=component_name).update(usage_count=count)

            return JsonResponse({'success': True, 'message': '删除成功'})
        except FormConfig.DoesNotExist:
            return JsonResponse({'success': False, 'message': '表单配置不存在'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'删除失败：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'message': '仅支持 DELETE 请求'}, status=405)



@csrf_exempt
def get_database_tables(request):
    """获取数据库中所有表名列表（过滤系统表）"""
    if request.method == 'GET':
        try:
            # 定义需要过滤的系统表和业务核心表
            system_tables = {
                # Django系统表
                'django_migrations',
                'django_content_type',
                'auth_permission',
                'auth_group',
                'auth_user',
                'auth_user_groups',
                'auth_user_user_permissions',
                'auth_group_permissions',
                'django_admin_log',
                'django_session',

                # 业务核心表
                'work_tools2_formconfig',
                'work_tools2_formqueryitem',
                'work_tools2_formupdateitem',
                'work_tools2_componentconfig',
                'work_tools2_menu',
                '_table_metadata',
                'work_tools2_databaseipconfig',
                'work_tools2_filepathconfig',
                '_query_sql_config'
            }

            # 对于 SQLite，使用 sqlite_master 表查询
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
                all_tables = [row[0] for row in cursor.fetchall()]

                # 过滤系统表和业务表
                tables = [
                    table for table in all_tables
                    if table not in system_tables
                       and not table.startswith('django_')
                       and not table.startswith('sqlite_')
                ]

            return JsonResponse({
                'success': True,
                'data': tables
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'获取表列表失败：{str(e)}'
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': '仅支持 GET 请求'
    }, status=405)



@csrf_exempt
def get_table_fields(request):
    """获取指定表的所有字段信息（排除自动管理字段）"""
    if request.method == 'GET':
        try:
            table_name = request.GET.get('table_name', '').strip()

            if not table_name:
                return JsonResponse({
                    'success': False,
                    'message': '表名不能为空'
                }, status=400)

            # 定义需要排除的自动管理字段
            excluded_fields = {
                'id',
                'created_at', 'updated_at',
                'create_time', 'update_time',
                'created_time', 'updated_time'
            }

            # 对于 SQLite，使用 PRAGMA table_info 查询字段信息
            with connection.cursor() as cursor:
                cursor.execute(f"PRAGMA table_info([{table_name}])")
                columns = cursor.fetchall()

                fields = []
                for col in columns:
                    field_name = col[1]
                    # 跳过自动管理字段
                    if field_name in excluded_fields:
                        continue

                    fields.append({
                        'name': field_name,  # 字段名
                        'type': col[2],  # 数据类型
                        'not_null': bool(col[3]),  # 是否非空
                        'default_value': col[4],  # 默认值
                        'is_primary_key': bool(col[5])  # 是否主键
                    })

            return JsonResponse({
                'success': True,
                'data': {
                    'table_name': table_name,
                    'fields': fields
                }
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'获取字段列表失败：{str(e)}'
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': '仅支持 GET 请求'
    }, status=405)




@csrf_exempt
def query_supplement_data(request):
    """查询补充框数据（支持分页）"""
    try:
        # 支持GET和POST请求
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
            except Exception as e:
                # 如果body解析失败，尝试从 POST数据获取
                data = request.POST
        elif request.method == 'GET':
            # GET请求从query参数获取
            data = request.GET
        else:
            return JsonResponse({
                'success': False,
                'message': '仅支持 GET 和 POST 请求'
            }, status=405)
        
        table_name = data.get('tableName', '').strip()
        main_field = data.get('mainField', '').strip()
        sub_fields = data.get('subFields', [])
        search_value = data.get('searchValue', '').strip()
        # 分页参数
        page = int(data.get('page', 1))
        limit = int(data.get('limit', 5))
        # 是否是精确搜索（二次搜索）
        is_exact_search_raw = data.get('isExactSearch', False)
        # 处理布尔值的字符串形式
        if isinstance(is_exact_search_raw, str):
            is_exact_search = is_exact_search_raw.lower() == 'true'
        else:
            is_exact_search = bool(is_exact_search_raw)

        # 是否是快速检查模式（只判断是否只有1条数据）
        is_quick_check_raw = data.get('quickCheck', False)
        if isinstance(is_quick_check_raw, str):
            is_quick_check = is_quick_check_raw.lower() == 'true'
        else:
            is_quick_check = bool(is_quick_check_raw)

        # 处理subFields可能是JSON字符串的情况
        if isinstance(sub_fields, str) and sub_fields:
            try:
                sub_fields = json.loads(sub_fields)
            except:
                sub_fields = []

        if not table_name or not main_field:
            return JsonResponse({
                'success': False,
                'message': '表名和主字段不能为空'
            }, status=400)

        # 构建要查询的字段列表
        select_fields = [main_field]
        for sub_field in sub_fields:
            if isinstance(sub_field, dict):
                field_name = sub_field.get('dbField') or sub_field.get('bindingKey')
                if field_name:
                    select_fields.append(field_name)
            elif isinstance(sub_field, str):
                select_fields.append(sub_field)

        # 构建 SELECT 语句
        fields_str = ', '.join(select_fields)
        base_sql = "SELECT " + fields_str + " FROM " + table_name

        # 如果有搜索值，添加 WHERE 条件
        where_clause = ""
        if search_value:
            if is_exact_search:
                # 精确搜索（二次搜索）
                where_clause = " WHERE " + main_field + " = '" + search_value.replace("'", "''") + "'"
            else:
                # 模糊搜索（初始查询）
                where_clause = " WHERE " + main_field + " LIKE '%" + search_value.replace("'", "''") + "%'"

        # 判断查询模式：quickCheck 只需判断是否只有1条数据
        if is_quick_check:
            # 快速检查模式：只查 LIMIT 2，不需要 COUNT
            # 返回0条=无数据，1条=唯一数据，2条=多条数据
            query_sql = base_sql + where_clause + " ORDER BY " + main_field + " LIMIT 2"

            with connection.cursor() as cursor:
                cursor.execute(query_sql)
                rows = cursor.fetchall()

                result = []
                for row in rows:
                    row_dict = {}
                    for idx, field in enumerate(select_fields):
                        row_dict[field] = row[idx]
                    result.append(row_dict)

            return JsonResponse({
                'success': True,
                'data': result,
                'count': len(result),  # 快速检查模式返回实际条数
                'quickCheck': True
            })

        # 正常分页查询模式（表格选择器使用）
        # 构建总数查询SQL（不带LIMIT）
        count_sql = "SELECT COUNT(*) FROM " + table_name + where_clause

        # 构建分页查询SQL
        offset = (page - 1) * limit
        query_sql = base_sql + where_clause + " ORDER BY " + main_field + " LIMIT " + str(limit) + " OFFSET " + str(offset)

        # 执行查询
        with connection.cursor() as cursor:
            # 先查询总数
            cursor.execute(count_sql)
            total_count = cursor.fetchone()[0]

            # 再查询分页数据
            cursor.execute(query_sql)
            rows = cursor.fetchall()

            # 将结果转换为字典列表
            result = []
            for row in rows:
                row_dict = {}
                for idx, field in enumerate(select_fields):
                    row_dict[field] = row[idx]
                result.append(row_dict)

        return JsonResponse({
            'success': True,
            'data': result,
            'count': total_count  # 返回总数，用于前端分页
        })
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return JsonResponse({
            'success': False,
            'message': '查询失败：' + str(e),
            'error_detail': error_detail
        }, status=500)


@csrf_exempt
def batch_query_supplement_data(request):
    """批量查询补充框数据（通过IN查询提高效率）"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            table_name = data.get('tableName', '').strip()
            main_field = data.get('mainField', '').strip()
            sub_fields = data.get('subFields', [])
            main_values = data.get('mainValues', [])  # 主字段的值列表

            if not table_name or not main_field:
                return JsonResponse({
                    'success': False,
                    'message': '表名和主字段不能为空'
                }, status=400)

            if not main_values or len(main_values) == 0:
                return JsonResponse({
                    'success': True,
                    'data': [],
                    'count': 0
                })

            # 去重并过滤空值
            main_values = list(set([v for v in main_values if v and str(v).strip()]))

            if len(main_values) == 0:
                return JsonResponse({
                    'success': True,
                    'data': [],
                    'count': 0
                })

            # 构建要查询的字段列表
            select_fields = [main_field]
            for sub_field in sub_fields:
                if isinstance(sub_field, dict):
                    field_name = sub_field.get('dbField') or sub_field.get('bindingKey')
                    if field_name:
                        select_fields.append(field_name)
                elif isinstance(sub_field, str):
                    select_fields.append(sub_field)

            # 构建 SELECT 语句
            fields_str = ', '.join(select_fields)

            # 使用 IN 查询
            values_str = ', '.join(["'" + str(v).replace("'", "''") + "'" for v in main_values])
            sql = "SELECT " + fields_str + " FROM " + table_name + " WHERE " + main_field + " IN (" + values_str + ")"

            print("=" * 50)
            print("批量补充框查询SQL:")
            print("  SQL:", sql)
            print("  表名:", table_name)
            print("  主字段:", main_field)
            print("  查询值数量:", len(main_values))
            print("=" * 50)

            # 执行查询
            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()

                # 将结果转换为字典列表
                result = []
                for row in rows:
                    row_dict = {}
                    for idx, field in enumerate(select_fields):
                        row_dict[field] = row[idx]
                    result.append(row_dict)

            print("查询结果:", len(result), "条记录")

            return JsonResponse({
                'success': True,
                'data': result,
                'count': len(result)
            })
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print("=" * 50)
            print("批量查询异常:")
            print(error_detail)
            print("=" * 50)
            return JsonResponse({
                'success': False,
                'message': '查询失败：' + str(e),
                'error_detail': error_detail
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': '仅支持 POST 请求'
    }, status=405)


@csrf_exempt
def duplicate_form_config(request, form_id):
    """复制表单配置（除了主键外，完全复制所有信息）"""
    if request.method == 'POST':
        try:
            from work_tools2.models import ComponentConfig
            
            # 获取原表单配置
            original_config = FormConfig.objects.get(id=form_id)
            
            # 生成新的表单名称（原名称 + _副本）
            new_form_name = f"{original_config.form_name}_副本"
            
            # 检查新名称是否已存在，如果存在则添加序号
            counter = 1
            while FormConfig.objects.filter(form_name=new_form_name).exists():
                new_form_name = f"{original_config.form_name}_副本{counter}"
                counter += 1
            
            # 创建新的表单配置
            new_config = FormConfig.objects.create(
                form_name=new_form_name,
                table_name_list=original_config.table_name_list,
                database_ip_ids=original_config.database_ip_ids,
                query_mode=original_config.query_mode,
                append_ops_remark=original_config.append_ops_remark,
                is_active=original_config.is_active,
            )
            
            # 复制查询字段
            for item in original_config.query_items.all():
                FormQueryItem.objects.create(
                    form_config=new_config,
                    label=item.label,
                    field_type=item.field_type,
                    binding_key=item.binding_key,
                    sort_order=item.sort_order,
                    connected_table=item.connected_table,
                    valid_rule=item.valid_rule,
                    default_value=item.default_value,
                )
            
            # 复制更新字段
            for item in original_config.update_items.all():
                FormUpdateItem.objects.create(
                    form_config=new_config,
                    label=item.label,
                    field_type=item.field_type,
                    binding_key=item.binding_key,
                    sort_order=item.sort_order,
                    input_type=item.input_type,
                    connected_table=item.connected_table,
                    new_valid_rule=item.new_valid_rule,
                    origin_valid_rule=item.origin_valid_rule,
                    origin_default_value=item.origin_default_value,
                    new_default_value=item.new_default_value,
                    component_name=item.component_name,
                    main_table=item.main_table,
                    main_field=item.main_field,
                    sub_fields=item.sub_fields,
                    options=item.options,
                    expressions=item.expressions,
                )
            
            # 创建新的菜单
            try:
                from pypinyin import pinyin, Style
                pinyin_list = pinyin(new_form_name, style=Style.NORMAL)
                pinyin_str = ''.join([item[0] for item in pinyin_list])
            except ImportError:
                pinyin_str = ''
            
            # 获取原菜单的父级菜单
            original_menu_url = f'/dynamic/{form_id}'
            original_menu = Menu.objects.filter(url=original_menu_url).first()
            parent_menu_id = original_menu.parent_id if original_menu else None
            parent_menu_name = ''
            if parent_menu_id:
                parent_menu = Menu.objects.filter(id=parent_menu_id).first()
                if parent_menu:
                    parent_menu_name = parent_menu.name
            
            new_menu_url = f'/dynamic/{new_config.id}'
            Menu.objects.create(
                name=new_form_name,
                url=new_menu_url,
                parent_id=parent_menu_id,
                icon='bi-file-earmark-text',
                pinyin=pinyin_str,
                sort_order=0,
                is_visible=True,
                group_name=parent_menu_name,
            )
            
            # 重新计算配置项的使用次数
            ComponentConfig.objects.all().update(usage_count=0)
            from django.db.models import Count
            component_usage = FormUpdateItem.objects.filter(
                component_name__isnull=False
            ).exclude(
                component_name=''
            ).values(
                'component_name'
            ).annotate(
                count=Count('id')
            )
            for usage in component_usage:
                component_name = usage['component_name']
                count = usage['count']
                ComponentConfig.objects.filter(name=component_name).update(usage_count=count)
            
            return JsonResponse({
                'success': True,
                'message': '复制成功',
                'new_form_id': new_config.id,
                'new_form_name': new_form_name
            })
            
        except FormConfig.DoesNotExist:
            return JsonResponse({'success': False, 'message': '表单配置不存在'}, status=404)
        except Exception as e:
            import traceback
            print(f"复制表单配置失败: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({'success': False, 'message': f'复制失败：{str(e)}'}, status=500)
    
    return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)


@csrf_exempt
def export_form_config(request, form_id):
    """导出单个表单配置为JSON文件"""
    if request.method == 'GET':
        try:
            from work_tools2.models import ComponentConfig, DatabaseIPConfig
            from datetime import datetime
            
            # 获取表单配置
            config = FormConfig.objects.get(id=form_id)
            
            # 获取父级菜单名称
            parent_menu_name = ''
            menu_url = f'/dynamic/{form_id}'
            menu = Menu.objects.filter(url=menu_url).first()
            if menu and menu.parent_id:
                parent_menu = Menu.objects.filter(id=menu.parent_id).first()
                if parent_menu:
                    parent_menu_name = parent_menu.name
            elif menu:
                # 一级菜单没有parent_id，使用group_name
                parent_menu_name = menu.group_name or '主菜单'

            # 构建导出数据
            export_data = {
                'version': '1.0',
                'exportTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'formConfig': {
                    'formName': config.form_name,
                    'tableNameList': config.table_name_list,
                    'parentMenuName': parent_menu_name,
                    'queryMode': config.query_mode,
                    'appendOpsRemark': config.append_ops_remark,
                    'isActive': config.is_active,
                },
                'queryItems': [],
                'updateItems': [],
                'databaseConfigs': [],
                'componentConfigs': []
            }
            
            # 导出查询字段
            for item in config.query_items.all().order_by('sort_order'):
                export_data['queryItems'].append({
                    'label': item.label,
                    'fieldType': item.field_type,
                    'bindingKey': item.binding_key,
                    'sortOrder': item.sort_order,
                    'connectedTable': item.connected_table,
                    'validRule': item.valid_rule,
                    'defaultValue': item.default_value,
                })
            
            # 导出更新字段
            component_names = set()  # 收集所有引用的组件名称
            for item in config.update_items.all().order_by('sort_order'):
                update_item = {
                    'label': item.label,
                    'fieldType': item.field_type,
                    'bindingKey': item.binding_key,
                    'sortOrder': item.sort_order,
                    'inputType': item.input_type,
                    'connectedTable': item.connected_table,
                    'newValidRule': item.new_valid_rule,
                    'originValidRule': item.origin_valid_rule,
                    'originDefaultValue': item.origin_default_value,
                    'newDefaultValue': item.new_default_value,
                    'componentName': item.component_name,
                    'mainTable': item.main_table,
                    'mainField': item.main_field,
                    'subFields': item.sub_fields,
                    'options': item.options,
                    'expressions': item.expressions,
                }
                export_data['updateItems'].append(update_item)
                
                # 收集组件名称
                if item.component_name:
                    component_names.add(item.component_name)
            
            # 导出数据库配置
            if config.database_ip_ids:
                db_configs = DatabaseIPConfig.objects.filter(id__in=config.database_ip_ids)
                for db_config in db_configs:
                    export_data['databaseConfigs'].append({
                        'name': db_config.name,
                        'ipAddress': db_config.ip_address,
                        'databaseName': db_config.database_name,
                        'isActive': db_config.is_active,
                    })
            
            # 导出引用的组件配置
            for comp_name in component_names:
                component = ComponentConfig.objects.filter(name=comp_name).first()
                if component:
                    export_data['componentConfigs'].append({
                        'name': component.name,
                        'componentType': component.component_type,
                        'options': component.options,
                    })
            
            # 生成JSON响应
            import json
            response = HttpResponse(
                json.dumps(export_data, ensure_ascii=False, indent=2),
                content_type='application/json; charset=utf-8'
            )
            response['Content-Disposition'] = f'attachment; filename={config.form_name}_配置导出.json'
            
            return response
            
        except FormConfig.DoesNotExist:
            return JsonResponse({'success': False, 'message': '表单配置不存在'}, status=404)
        except Exception as e:
            import traceback
            print(f"导出表单配置失败: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({'success': False, 'message': f'导出失败：{str(e)}'}, status=500)
    
    return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)


@csrf_exempt
def batch_export_form_configs(request):
    """批量导出多个表单配置为ZIP文件（使用GET请求避免CSRF问题）"""
    if request.method == 'GET':
        try:
            import json
            import zipfile
            import io
            from datetime import datetime
            from work_tools2.models import ComponentConfig, DatabaseIPConfig
            
            # 从 URL 参数获取 form_ids
            form_ids_str = request.GET.get('form_ids', '')
            
            if not form_ids_str:
                return JsonResponse({'success': False, 'message': '请至少选择一个表单配置'}, status=400)
            
            # 解析 form_ids （逗号分隔的字符串）
            try:
                form_ids = [int(id.strip()) for id in form_ids_str.split(',') if id.strip()]
            except ValueError:
                return JsonResponse({'success': False, 'message': '无效的表单ID格式'}, status=400)
            
            if not form_ids:
                return JsonResponse({'success': False, 'message': '请至少选择一个表单配置'}, status=400)
            
            print(f"批量导出表单IDs: {form_ids}")
            
            # 创建内存中的ZIP文件
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for form_id in form_ids:
                    try:
                        config = FormConfig.objects.get(id=form_id)
                        
                        # 获取父级菜单名称
                        parent_menu_name = ''
                        menu_url = f'/dynamic/{form_id}'
                        menu = Menu.objects.filter(url=menu_url).first()
                        if menu and menu.parent_id:
                            parent_menu = Menu.objects.filter(id=menu.parent_id).first()
                            if parent_menu:
                                parent_menu_name = parent_menu.name
                        elif menu:
                            parent_menu_name = menu.group_name or '主菜单'

                        # 构建导出数据（与单个导出相同）
                        export_data = {
                            'version': '1.0',
                            'exportTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'formConfig': {
                                'formName': config.form_name,
                                'tableNameList': config.table_name_list,
                                'parentMenuName': parent_menu_name,
                                'queryMode': config.query_mode,
                                'appendOpsRemark': config.append_ops_remark,
                                'isActive': config.is_active,
                            },
                            'queryItems': [],
                            'updateItems': [],
                            'databaseConfigs': [],
                            'componentConfigs': []
                        }
                        
                        # 导出查询字段
                        for item in config.query_items.all().order_by('sort_order'):
                            export_data['queryItems'].append({
                                'label': item.label,
                                'fieldType': item.field_type,
                                'bindingKey': item.binding_key,
                                'sortOrder': item.sort_order,
                                'connectedTable': item.connected_table,
                                'validRule': item.valid_rule,
                                'defaultValue': item.default_value,
                            })
                        
                        # 导出更新字段
                        component_names = set()
                        for item in config.update_items.all().order_by('sort_order'):
                            update_item = {
                                'label': item.label,
                                'fieldType': item.field_type,
                                'bindingKey': item.binding_key,
                                'sortOrder': item.sort_order,
                                'inputType': item.input_type,
                                'connectedTable': item.connected_table,
                                'newValidRule': item.new_valid_rule,
                                'originValidRule': item.origin_valid_rule,
                                'originDefaultValue': item.origin_default_value,
                                'newDefaultValue': item.new_default_value,
                                'componentName': item.component_name,
                                'mainTable': item.main_table,
                                'mainField': item.main_field,
                                'subFields': item.sub_fields,
                                'options': item.options,
                                'expressions': item.expressions,
                            }
                            export_data['updateItems'].append(update_item)
                            
                            if item.component_name:
                                component_names.add(item.component_name)
                        
                        # 导出数据库配置
                        if config.database_ip_ids:
                            db_configs = DatabaseIPConfig.objects.filter(id__in=config.database_ip_ids)
                            for db_config in db_configs:
                                export_data['databaseConfigs'].append({
                                    'name': db_config.name,
                                    'ipAddress': db_config.ip_address,
                                    'databaseName': db_config.database_name,
                                    'isActive': db_config.is_active,
                                })
                        
                        # 导出引用的组件配置
                        for comp_name in component_names:
                            component = ComponentConfig.objects.filter(name=comp_name).first()
                            if component:
                                export_data['componentConfigs'].append({
                                    'name': component.name,
                                    'componentType': component.component_type,
                                    'options': component.options,
                                })
                        
                        # 将JSON添加到ZIP文件
                        json_content = json.dumps(export_data, ensure_ascii=False, indent=2)
                        safe_filename = f"{config.form_name}_配置导出.json"
                        zip_file.writestr(safe_filename, json_content)
                        
                    except FormConfig.DoesNotExist:
                        print(f"表单ID {form_id} 不存在，跳过")
                        continue
            
            # 设置ZIP文件指针到开头
            zip_buffer.seek(0)
            
            # 生成ZIP响应
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            response = HttpResponse(
                zip_buffer.getvalue(),
                content_type='application/zip'
            )
            response['Content-Disposition'] = f'attachment; filename=表单配置批量导出_{timestamp}.zip'
            
            print(f"批量导出成功，共 {len(form_ids)} 个表单")
            return response
            
        except Exception as e:
            import traceback
            print(f"批量导出表单配置失败: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({'success': False, 'message': f'批量导出失败：{str(e)}'}, status=500)
    
    return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)


@csrf_exempt
def import_form_config(request):
    """导入表单配置从JSON文件或ZIP文件（支持批量导入）"""
    if request.method == 'POST':
        try:
            from work_tools2.models import ComponentConfig, DatabaseIPConfig
            import json
            import zipfile
            import io
            
            # 获取上传的文件
            file = request.FILES.get('file')
            if not file:
                return JsonResponse({'success': False, 'message': '请上传配置文件'}, status=400)
            
            file_name = file.name.lower()
            results = []  # 记录导入结果
            
            # 判断是ZIP文件还是JSON文件
            if file_name.endswith('.zip'):
                # ZIP文件 - 批量导入
                zip_content = file.read()
                zip_buffer = io.BytesIO(zip_content)
                
                with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
                    json_files = [f for f in zip_file.namelist() if f.endswith('.json')]
                    
                    if not json_files:
                        return JsonResponse({'success': False, 'message': 'ZIP文件中没有找到JSON配置文件'}, status=400)
                    
                    print(f"ZIP文件包含 {len(json_files)} 个配置文件")
                    
                    # 逐个处理JSON文件
                    for json_filename in json_files:
                        try:
                            # 读取JSON内容
                            json_content = zip_file.read(json_filename).decode('utf-8')
                            import_data = json.loads(json_content)
                            
                            # 调用单个导入逻辑
                            result = _import_single_config(import_data, json_filename)
                            results.append(result)
                            
                        except Exception as e:
                            results.append({
                                'filename': json_filename,
                                'success': False,
                                'message': f'导入失败：{str(e)}'
                            })
            else:
                # JSON文件 - 单个导入
                file_content = file.read().decode('utf-8')
                import_data = json.loads(file_content)
                
                result = _import_single_config(import_data, file_name)
                results.append(result)
            
            # 统计结果
            success_count = sum(1 for r in results if r['success'])
            fail_count = len(results) - success_count
            
            return JsonResponse({
                'success': True,
                'message': f'导入完成：成功 {success_count} 个，失败 {fail_count} 个',
                'results': results,
                'total': len(results),
                'success_count': success_count,
                'fail_count': fail_count
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'JSON 解析失败，请确保文件格式正确'}, status=400)
        except Exception as e:
            import traceback
            print(f"导入表单配置失败: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({'success': False, 'message': f'导入失败：{str(e)}'}, status=500)
    
    return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)


def _import_single_config(import_data, filename='unknown.json'):
    """导入单个表单配置（内部函数）"""
    try:
        import json
        from work_tools2.models import ComponentConfig, DatabaseIPConfig
        
        # 验证版本
        version = import_data.get('version')
        if not version:
            return {
                'filename': filename,
                'success': False,
                'message': '无效的配置文件格式'
            }
        
        # 获取表单配置
        form_config_data = import_data.get('formConfig', {})
        form_name = form_config_data.get('formName', '')
        
        if not form_name:
            return {
                'filename': filename,
                'success': False,
                'message': '配置文件中缺少表单名称'
            }
        
        # 检查表单名称是否已存在
        if FormConfig.objects.filter(form_name=form_name).exists():
            return {
                'filename': filename,
                'success': False,
                'message': f'表单名称"{form_name}"已存在，请先删除或重命名'
            }
        
        # 创建数据库配置（如果不存在则创建）
        database_ip_ids = []
        for db_config_data in import_data.get('databaseConfigs', []):
            db_name = db_config_data.get('name', '')
            ip_address = db_config_data.get('ipAddress', '')
            database_name = db_config_data.get('databaseName', '')
            
            # 查找是否已存在相同的配置
            db_config = DatabaseIPConfig.objects.filter(
                name=db_name,
                ip_address=ip_address,
                database_name=database_name
            ).first()
            
            if not db_config:
                # 创建新的数据库配置
                db_config = DatabaseIPConfig.objects.create(
                    name=db_name,
                    ip_address=ip_address,
                    database_name=database_name,
                    is_active=db_config_data.get('isActive', True),
                )
            
            database_ip_ids.append(db_config.id)
        
        # 创建组件配置（如果不存在则创建）
        for comp_config_data in import_data.get('componentConfigs', []):
            comp_name = comp_config_data.get('name', '')
            if comp_name:
                component = ComponentConfig.objects.filter(name=comp_name).first()
                if not component:
                    ComponentConfig.objects.create(
                        name=comp_name,
                        component_type=comp_config_data.get('componentType', 'select'),
                        options=comp_config_data.get('options', []),
                    )
        
        # 创建表单配置
        new_config = FormConfig.objects.create(
            form_name=form_name,
            table_name_list=form_config_data.get('tableNameList', []),
            database_ip_ids=database_ip_ids,
            query_mode=form_config_data.get('queryMode', 'strict'),
            append_ops_remark=form_config_data.get('appendOpsRemark', True),
            is_active=form_config_data.get('isActive', True),
        )
        
        # 创建查询字段
        for item_data in import_data.get('queryItems', []):
            FormQueryItem.objects.create(
                form_config=new_config,
                label=item_data.get('label', ''),
                field_type=item_data.get('fieldType', 'text'),
                binding_key=item_data.get('bindingKey', ''),
                sort_order=item_data.get('sortOrder', 0),
                connected_table=item_data.get('connectedTable', []),
                valid_rule=item_data.get('validRule', 'required'),
                default_value=item_data.get('defaultValue', ''),
            )
        
        # 创建更新字段
        for item_data in import_data.get('updateItems', []):
            FormUpdateItem.objects.create(
                form_config=new_config,
                label=item_data.get('label', ''),
                field_type=item_data.get('fieldType', 'text'),
                binding_key=item_data.get('bindingKey', ''),
                sort_order=item_data.get('sortOrder', 0),
                input_type=item_data.get('inputType', 'input'),
                connected_table=item_data.get('connectedTable', []),
                new_valid_rule=item_data.get('newValidRule', 'required'),
                origin_valid_rule=item_data.get('originValidRule', 'required'),
                origin_default_value=item_data.get('originDefaultValue', ''),
                new_default_value=item_data.get('newDefaultValue', ''),
                component_name=item_data.get('componentName', ''),
                main_table=item_data.get('mainTable', ''),
                main_field=item_data.get('mainField', ''),
                sub_fields=item_data.get('subFields', []),
                options=item_data.get('options', []),
                expressions=item_data.get('expressions', {}),
            )
        
        # 获取或创建父级菜单
        parent_menu_name = form_config_data.get('parentMenuName', '')
        parent_menu_id = None
        if parent_menu_name:
            # 查找是否已存在同名的一级菜单
            parent_menu = Menu.objects.filter(
                name=parent_menu_name,
                parent_id__isnull=True
            ).first()
            if not parent_menu:
                # 创建新的父级菜单
                parent_menu = Menu.objects.create(
                    name=parent_menu_name,
                    url='#',
                    parent_id=None,
                    icon='bi-folder',
                    pinyin='',
                    sort_order=Menu.objects.filter(parent_id__isnull=True).count(),
                    is_visible=True,
                    group_name='主菜单',
                )
            parent_menu_id = parent_menu.id
        else:
            parent_menu_name = '主菜单'

        # 创建菜单
        try:
            from pypinyin import pinyin, Style
            pinyin_list = pinyin(form_name, style=Style.NORMAL)
            pinyin_str = ''.join([item[0] for item in pinyin_list])
        except ImportError:
            pinyin_str = ''

        menu_url = f'/dynamic/{new_config.id}'
        Menu.objects.create(
            name=form_name,
            url=menu_url,
            parent_id=parent_menu_id,
            icon='bi-file-earmark-text',
            pinyin=pinyin_str,
            sort_order=0,
            is_visible=True,
            group_name=parent_menu_name,
        )
        
        # 重新计算配置项的使用次数
        ComponentConfig.objects.all().update(usage_count=0)
        from django.db.models import Count
        component_usage = FormUpdateItem.objects.filter(
            component_name__isnull=False
        ).exclude(
            component_name=''
        ).values(
            'component_name'
        ).annotate(
            count=Count('id')
        )
        for usage in component_usage:
            component_name = usage['component_name']
            count = usage['count']
            ComponentConfig.objects.filter(name=component_name).update(usage_count=count)
        
        return {
            'filename': filename,
            'success': True,
            'message': '导入成功',
            'form_id': new_config.id,
            'form_name': form_name
        }
        
    except Exception as e:
        import traceback
        print(f"导入单个配置失败 [{filename}]: {str(e)}")
        print(traceback.format_exc())
        return {
            'filename': filename,
            'success': False,
            'message': f'导入失败：{str(e)}'
        }
