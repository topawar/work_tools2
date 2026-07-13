import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.db.models import Count, Q
from django.utils import timezone

from work_tools2.models import FormConfig, FormUsageLog, Menu


# 长期未使用统计的初始基准日期（观察期未满前固定为该日期）
INACTIVE_BASELINE_FLOOR = timezone.make_aware(datetime(2026, 7, 3, 0, 0, 0))
# 观察期天数
INACTIVE_DAYS = 90


def _get_form_module(form_config):
    """根据表单配置获取所属模块（一级菜单名称）和分组"""
    menu_url = f'/dynamic/{form_config.id}'
    menu = Menu.objects.filter(url=menu_url).first()
    if menu and menu.parent:
        return menu.parent.name or '未命名模块', menu.parent.group_name or ''
    if menu:
        return menu.name or '未命名模块', menu.group_name or ''
    return '未分组', ''


def _do_delete_form_config(form_config):
    """删除表单配置及其关联菜单，返回是否成功与消息"""
    try:
        menu_url = f'/dynamic/{form_config.id}'
        menu_to_delete = Menu.objects.filter(url=menu_url).first()

        if menu_to_delete and menu_to_delete.parent:
            parent_menu = menu_to_delete.parent
            sibling_count = Menu.objects.filter(parent=parent_menu).exclude(id=menu_to_delete.id).count()
            if sibling_count == 0:
                parent_menu.delete()

        Menu.objects.filter(url=menu_url).delete()
        form_config.delete()

        # 重新计算组件配置项使用次数
        from work_tools2.models import ComponentConfig, FormUpdateItem
        from django.db.models import Count as DbCount

        ComponentConfig.objects.all().update(usage_count=0)
        component_usage = FormUpdateItem.objects.filter(
            component_name__isnull=False
        ).exclude(component_name='').values('component_name').annotate(
            count=DbCount('id')
        )
        for usage in component_usage:
            ComponentConfig.objects.filter(name=usage['component_name']).update(
                usage_count=usage['count']
            )

        return True, None
    except Exception as e:
        return False, str(e)


def record_form_usage(form_config, source='dynamic'):
    """记录表单调用日志并更新缓存字段"""
    if not form_config:
        return
    now = timezone.now()
    form_config.call_count += 1
    form_config.last_called_at = now
    form_config.save(update_fields=['call_count', 'last_called_at'])
    FormUsageLog.objects.create(form_config=form_config, source=source)


def get_usage_statistics(request):
    """获取动态表单使用统计"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': '仅支持 GET 请求'}, status=405)

    try:
        now = timezone.now()

        configs = FormConfig.objects.all().order_by('-call_count', '-created_at')

        # 汇总数据
        total_forms = configs.count()
        total_calls = sum(c.call_count for c in configs)

        # 长期未使用：以基准日期为准，基准日期前创建且基准日期后无调用记录
        # 观察期未满前，基准固定为 INACTIVE_BASELINE_FLOOR；
        # 观察期结束后，基准随当前日期向后滚动（即 today - 90 天，但不早于 floor）
        inactive_baseline_date = max(INACTIVE_BASELINE_FLOOR, now - timedelta(days=INACTIVE_DAYS))
        inactive_check_date = inactive_baseline_date + timedelta(days=INACTIVE_DAYS)
        observation_period_ended = now >= (INACTIVE_BASELINE_FLOOR + timedelta(days=INACTIVE_DAYS))

        if observation_period_ended:
            inactive_ids = set(
                configs.filter(
                    Q(created_at__lt=inactive_baseline_date) &
                    (Q(last_called_at__isnull=True) | Q(last_called_at__lt=inactive_baseline_date))
                ).values_list('id', flat=True)
            )
        else:
            inactive_ids = set()
        inactive_count = len(inactive_ids)
        inactive_modules = set()

        # 从未调用表单数量（不再页面展示，保留字段避免前端兼容问题）
        never_called_count = configs.filter(call_count=0).count()

        # 按模块统计
        module_map = {}
        form_list = []
        for config in configs:
            module_name, group_name = _get_form_module(config)
            is_inactive = config.id in inactive_ids
            if is_inactive:
                inactive_modules.add(module_name)

            if module_name not in module_map:
                module_map[module_name] = {
                    'module': module_name,
                    'group': group_name,
                    'count': 0,
                    'forms': []
                }
            module_map[module_name]['count'] += config.call_count
            module_map[module_name]['forms'].append({
                'form_id': str(config.id),
                'form_name': config.form_name,
                'call_count': config.call_count,
                'last_called_at': config.last_called_at.strftime('%Y-%m-%d %H:%M:%S') if config.last_called_at else None,
            })

            days_since = None
            days_since_label = '-'
            if config.last_called_at:
                days_since = (now - config.last_called_at).days
                days_since_label = f'{days_since} 天'
            elif is_inactive:
                # 长期未使用：从当前基准日期起算未调用天数
                days_since = (now - inactive_baseline_date).days
                days_since_label = f'{days_since} 天'

            first_check_date = inactive_check_date.strftime('%Y-%m-%d')

            form_list.append({
                'form_id': str(config.id),
                'form_name': config.form_name,
                'module': module_name,
                'group': group_name,
                'call_count': config.call_count,
                'last_called_at': config.last_called_at.strftime('%Y-%m-%d %H:%M:%S') if config.last_called_at else None,
                'created_at': config.created_at.strftime('%Y-%m-%d %H:%M:%S') if config.created_at else None,
                'first_check_date': first_check_date,
                'days_since': days_since,
                'days_since_label': days_since_label,
                'is_inactive': is_inactive,
            })

        module_stats = sorted(module_map.values(), key=lambda x: x['count'], reverse=True)

        # 建议删除清单
        inactive_list = [f for f in form_list if f['is_inactive']]
        inactive_list.sort(key=lambda x: (x['days_since'] or 0), reverse=True)

        # 按模块统计建议删除数量
        inactive_module_stats = {}
        for item in inactive_list:
            module = item['module']
            inactive_module_stats[module] = inactive_module_stats.get(module, 0) + 1

        # 按月调用趋势（近 12 个月）
        months = []
        year, month = now.year, now.month
        for _ in range(12):
            months.append(f"{year}-{month:02d}")
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        months.reverse()

        twelve_months_ago = now - timedelta(days=365)
        logs = FormUsageLog.objects.filter(called_at__gte=twelve_months_ago)
        trend_map = {}
        for log in logs:
            key = log.called_at.strftime('%Y-%m')
            if key in set(months):
                trend_map[key] = trend_map.get(key, 0) + 1
        month_counts = [trend_map.get(m, 0) for m in months]

        # 按来源统计
        source_stats = {
            'dynamic': FormUsageLog.objects.filter(source='dynamic').count(),
            'merge': FormUsageLog.objects.filter(source='merge').count(),
        }

        return JsonResponse({
            'success': True,
            'data': {
                'summary': {
                    'total_forms': total_forms,
                    'total_calls': total_calls,
                    'inactive_count': inactive_count,
                    'never_called_count': never_called_count,
                    'inactive_modules': sorted(inactive_modules),
                    'inactive_module_stats': inactive_module_stats,
                    'source_stats': source_stats,
                    'stats_date': now.strftime('%Y-%m-%d'),
                    'inactive_baseline_date': inactive_baseline_date.strftime('%Y-%m-%d'),
                    'inactive_check_date': inactive_check_date.strftime('%Y-%m-%d'),
                    'observation_period_ended': observation_period_ended,
                },
                'module_stats': module_stats,
                'monthly_trend': {
                    'months': months,
                    'counts': month_counts,
                },
                'all_forms': form_list,
                'inactive_forms': inactive_list,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'获取统计失败：{str(e)}'}, status=500)


def batch_delete_inactive_forms(request):
    """批量删除长期未使用的表单（以固定基准日期判定）"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)

    try:
        data = json.loads(request.body)
        form_ids = data.get('form_ids', [])
        if not form_ids:
            return JsonResponse({'success': False, 'message': '请选择要删除的表单'}, status=400)

        success_ids = []
        failed_items = []
        for form_id in form_ids:
            try:
                config = FormConfig.objects.get(id=form_id)
                ok, msg = _do_delete_form_config(config)
                if ok:
                    success_ids.append(form_id)
                else:
                    failed_items.append({'form_id': form_id, 'message': msg or '删除失败'})
            except FormConfig.DoesNotExist:
                failed_items.append({'form_id': form_id, 'message': '表单不存在'})
            except Exception as e:
                failed_items.append({'form_id': form_id, 'message': str(e)})

        return JsonResponse({
            'success': True,
            'data': {
                'success_count': len(success_ids),
                'failed_count': len(failed_items),
                'success_ids': success_ids,
                'failed_items': failed_items,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'批量删除失败：{str(e)}'}, status=500)
