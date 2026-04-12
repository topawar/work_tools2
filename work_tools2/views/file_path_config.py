"""
文件路径配置相关视图
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from work_tools2.models import FilePathConfig
from work_tools2.path_utils import get_file_path_config_path, ensure_directory_exists


@csrf_exempt
@require_http_methods(["GET"])
def get_file_path_configs(request):
    """获取文件路径配置列表"""
    try:
        configs = FilePathConfig.objects.all().order_by('-is_default', '-created_at')
        
        data = []
        for config in configs:
            data.append({
                'id': config.id,
                'name': config.name,
                'base_path': config.base_path,
                'save_mode': config.save_mode,
                'date_format': config.date_format,
                'is_active': config.is_active,
                'is_default': config.is_default,
                'remark': config.remark,
                'get_display_save_mode': config.get_display_save_mode(),
                'get_display_date_format': config.get_display_date_format(),
                'created_at': config.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'获取配置失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_file_path_config(request, config_id):
    """获取单个文件路径配置详情"""
    try:
        config = FilePathConfig.objects.filter(id=config_id).first()
        
        if not config:
            return JsonResponse({
                'success': False,
                'message': '配置不存在'
            }, status=404)
        
        return JsonResponse({
            'success': True,
            'data': {
                'id': config.id,
                'name': config.name,
                'base_path': config.base_path,
                'save_mode': config.save_mode,
                'date_format': config.date_format,
                'is_active': config.is_active,
                'is_default': config.is_default,
                'remark': config.remark,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'获取配置失败: {str(e)}'
        }, status=500)


@csrf_exempt
def save_file_path_config(request):
    """保存文件路径配置"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            config_id = data.get('id')
            name = data.get('name', '').strip()
            base_path = data.get('base_path', '').strip()
            save_mode = data.get('save_mode', 'single')
            date_format = data.get('date_format', 'ymd_slash')
            is_active = data.get('is_active', True)
            is_default = data.get('is_default', False)
            remark = data.get('remark', '').strip()
            
            if not name:
                return JsonResponse({
                    'success': False,
                    'message': '请输入配置名称'
                }, status=400)
            
            if not base_path:
                return JsonResponse({
                    'success': False,
                    'message': '请输入基础路径'
                }, status=400)
            
            # 检查名称唯一性
            existing = FilePathConfig.objects.filter(name=name).exclude(id=config_id)
            if existing.exists():
                return JsonResponse({
                    'success': False,
                    'message': '配置名称已存在'
                }, status=400)
            
            # 如果设置为默认配置，需要将其他配置的默认标志取消
            if is_default:
                FilePathConfig.objects.filter(is_default=True).exclude(id=config_id).update(is_default=False)
            
            if config_id:
                # 更新
                config = FilePathConfig.objects.filter(id=config_id).first()
                if not config:
                    return JsonResponse({
                        'success': False,
                        'message': '配置不存在'
                    }, status=404)
                
                config.name = name
                config.base_path = base_path
                config.save_mode = save_mode
                config.date_format = date_format
                config.is_active = is_active
                config.is_default = is_default
                config.remark = remark
                config.save()
                
                return JsonResponse({
                    'success': True,
                    'message': '更新成功',
                    'data': {'id': config.id}
                })
            else:
                # 创建
                config = FilePathConfig.objects.create(
                    name=name,
                    base_path=base_path,
                    save_mode=save_mode,
                    date_format=date_format,
                    is_active=is_active,
                    is_default=is_default,
                    remark=remark
                )
                
                return JsonResponse({
                    'success': True,
                    'message': '创建成功',
                    'data': {'id': config.id}
                })
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'JSON解析失败'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'保存失败: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': '仅支持POST请求'}, status=405)


@csrf_exempt
@require_http_methods(["POST"])
def delete_file_path_config(request, config_id):
    """删除文件路径配置"""
    try:
        config = FilePathConfig.objects.filter(id=config_id).first()
        
        if not config:
            return JsonResponse({
                'success': False,
                'message': '配置不存在'
            }, status=404)
        
        # 不允许删除默认配置
        if config.is_default:
            return JsonResponse({
                'success': False,
                'message': '不能删除默认配置'
            }, status=400)
        
        config.delete()
        
        return JsonResponse({
            'success': True,
            'message': '删除成功'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'删除失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_default_file_path_config(request):
    """获取默认文件路径配置"""
    try:
        config = FilePathConfig.objects.filter(is_default=True, is_active=True).first()
        
        if not config:
            # 如果没有默认配置，返回第一个启用配置
            config = FilePathConfig.objects.filter(is_active=True).first()
        
        if not config:
            return JsonResponse({
                'success': False,
                'message': '没有可用的路径配置'
            }, status=404)
        
        save_path = get_file_path_config_path(config)
        
        return JsonResponse({
            'success': True,
            'data': {
                'id': config.id,
                'name': config.name,
                'save_path': save_path,
                'save_mode': config.save_mode,
                'date_format': config.date_format,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'获取默认配置失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def select_directory_dialog(request):
    """调用系统文件夹选择对话框（使用 tkinter）"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        # 创建隐藏的根窗口
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        root.attributes('-topmost', True)  # 置顶显示
        
        # 打开文件夹选择对话框
        folder_path = filedialog.askdirectory(
            title='选择文件输出目录',
            initialdir='C:\\'  # 初始目录
        )
        
        # 销毁窗口
        root.destroy()
        
        if folder_path:
            # Windows 路径转换（tkinter 可能返回正斜杠）
            folder_path = folder_path.replace('/', '\\')
            return JsonResponse({
                'success': True,
                'path': folder_path
            })
        else:
            return JsonResponse({
                'success': False,
                'message': '用户取消了选择'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'打开对话框失败: {str(e)}'
        }, status=500)


def get_save_path_from_config():
    """
    根据配置获取保存路径
    
    Returns:
        str: 保存路径
    """
    try:
        config = FilePathConfig.objects.filter(is_default=True, is_active=True).first()
        
        if not config:
            # 如果没有默认配置，返回第一个启用配置
            config = FilePathConfig.objects.filter(is_active=True).first()
        
        if config:
            save_path = get_file_path_config_path(config)
            ensure_directory_exists(save_path)
            return save_path
    except Exception as e:
        print(f"获取保存路径失败: {e}")
    
    # 回退到默认路径
    from datetime import datetime
    now = datetime.now()
    year_month = now.strftime('%Y%m')
    day = now.strftime('%d')
    save_dir = f"D:\\临时文件\\{year_month}\\{day}"
    ensure_directory_exists(save_dir)
    return save_dir
