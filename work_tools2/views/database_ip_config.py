# D:\project\codeProject\work_tools2\work_tools2\views\database_ip_config.py
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from ..models import DatabaseIPConfig


@csrf_exempt
@require_http_methods(["GET"])
def get_database_ip_configs(request):
    """获取所有数据库IP配置列表"""
    try:
        configs = DatabaseIPConfig.objects.all().order_by('-created_at')
        config_list = []
        
        for config in configs:
            config_list.append({
                'id': config.id,
                'name': config.name,
                'ip_address': config.ip_address,
                'database_name': config.database_name,
                'is_active': config.is_active,
                'created_at': config.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': config.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        
        return JsonResponse({
            'success': True,
            'data': config_list
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'获取失败：{str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_database_ip_config(request):
    """保存数据库IP配置"""
    try:
        data = json.loads(request.body)
        
        config_id = data.get('id')
        name = data.get('name', '').strip()
        ip_address = data.get('ip_address', '').strip()
        database_name = data.get('database_name', '').strip()
        is_active = data.get('is_active', True)
        
        # 验证必填字段
        if not name:
            return JsonResponse({
                'success': False,
                'message': '配置名称不能为空'
            }, status=400)
        
        if not ip_address:
            return JsonResponse({
                'success': False,
                'message': 'IP地址不能为空'
            }, status=400)
        
        if not database_name:
            return JsonResponse({
                'success': False,
                'message': '数据库名不能为空'
            }, status=400)
        
        if config_id:
            # 更新现有配置
            try:
                config = DatabaseIPConfig.objects.get(id=config_id)
                
                # 检查名称是否已被其他配置使用
                if DatabaseIPConfig.objects.filter(name=name).exclude(id=config_id).exists():
                    return JsonResponse({
                        'success': False,
                        'message': '配置名称已存在'
                    }, status=400)
                
                config.name = name
                config.ip_address = ip_address
                config.database_name = database_name
                config.is_active = is_active
                config.save()
                
                return JsonResponse({
                    'success': True,
                    'message': '更新成功',
                    'data': {'id': config.id}
                })
            except DatabaseIPConfig.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': '配置不存在'
                }, status=404)
        else:
            # 新建配置
            # 检查名称是否已存在
            if DatabaseIPConfig.objects.filter(name=name).exists():
                return JsonResponse({
                    'success': False,
                    'message': '配置名称已存在'
                }, status=400)
            
            config = DatabaseIPConfig.objects.create(
                name=name,
                ip_address=ip_address,
                database_name=database_name,
                is_active=is_active
            )
            
            return JsonResponse({
                'success': True,
                'message': '创建成功',
                'data': {'id': config.id}
            })
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'JSON 解析失败'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'保存失败：{str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_database_ip_config(request, config_id):
    """删除数据库IP配置"""
    try:
        config = DatabaseIPConfig.objects.get(id=config_id)
        config.delete()
        
        return JsonResponse({
            'success': True,
            'message': '删除成功'
        })
    except DatabaseIPConfig.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': '配置不存在'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'删除失败：{str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_database_ip_config_detail(request, config_id):
    """获取单个数据库IP配置详情"""
    try:
        config = DatabaseIPConfig.objects.get(id=config_id)
        
        return JsonResponse({
            'success': True,
            'data': {
                'id': config.id,
                'name': config.name,
                'ip_address': config.ip_address,
                'database_name': config.database_name,
                'is_active': config.is_active,
            }
        })
    except DatabaseIPConfig.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': '配置不存在'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'获取失败：{str(e)}'
        }, status=500)
