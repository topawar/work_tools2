"""
文件路径生成工具模块
用于根据配置动态生成文件保存路径
"""
import os
from datetime import datetime, timedelta
from calendar import monthrange


def get_week_range(dt):
    """
    获取指定日期所在月份的第几周的范围
    
    Args:
        dt: datetime对象
    
    Returns:
        tuple: (week_start_date, week_end_date, week_number)
    """
    # 获取该月的第一天
    first_day = dt.replace(day=1)
    
    # 计算第一天是星期几 (0=周一, 6=周日)
    first_weekday = first_day.weekday()
    
    # 计算该日期是第几周（从1开始）
    day_of_month = dt.day
    week_number = (day_of_month + first_weekday - 1) // 7 + 1
    
    # 计算该周的开始日期（周一）
    days_since_monday = dt.weekday()
    week_start = dt - timedelta(days=days_since_monday)
    
    # 计算该周的结束日期（周日）
    week_end = week_start + timedelta(days=6)
    
    # 确保周日期在当月范围内
    last_day = dt.replace(day=monthrange(dt.year, dt.month)[1])
    if week_start < first_day:
        week_start = first_day
    if week_end > last_day:
        week_end = last_day
    
    return week_start, week_end, week_number


def generate_save_path(base_path, save_mode='single', date_format='ymd_slash'):
    """
    根据配置生成文件保存路径
    
    Args:
        base_path: 基础路径，如 "D:\\SQL输出"
        save_mode: 保存模式，'single' 或 'date_layered'
        date_format: 日期格式，仅分层模式有效
            - 'ymd_slash': 年/月/日 (2025/12/07)
            - 'ymd_concat': 年月日 (20251207)
            - 'ym_slash_d': 年月/日 (202512/07)
            - 'week': 按周格式 (202512\20251207-20251212)
    
    Returns:
        str: 完整的保存路径
    """
    now = datetime.now()
    
    # 单一文件夹模式：直接返回基础路径
    if save_mode == 'single':
        return base_path
    
    # 按日期分层模式
    if save_mode == 'date_layered':
        if date_format == 'ymd_slash':
            # 年/月/日 (2025/12/07)
            sub_path = now.strftime('%Y/%m/%d')
        elif date_format == 'ymd_concat':
            # 年月日 (20251207)
            sub_path = now.strftime('%Y%m%d')
        elif date_format == 'ym_slash_d':
            # 年月/日 (202512/07)
            sub_path = now.strftime('%Y%m/%d')
        elif date_format == 'week':
            # 按周格式 (202512\20251207-20251212)
            week_start, week_end, week_num = get_week_range(now)
            year_month = now.strftime('%Y%m')
            week_range = f"{week_start.strftime('%Y%m%d')}-{week_end.strftime('%Y%m%d')}"
            sub_path = os.path.join(year_month, week_range)
        else:
            # 默认使用年月/日
            sub_path = now.strftime('%Y%m/%d')
        
        return os.path.join(base_path, sub_path)
    
    # 默认返回基础路径
    return base_path


def ensure_directory_exists(path):
    """
    确保目录存在，如果不存在则创建
    
    Args:
        path: 目录路径
    
    Returns:
        bool: 是否成功创建或已存在
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        print(f"创建目录失败: {path}, 错误: {e}")
        return False


def get_file_path_config_path(config):
    """
    根据FilePathConfig对象生成路径
    
    Args:
        config: FilePathConfig对象
    
    Returns:
        str: 完整的保存路径
    """
    return generate_save_path(
        base_path=config.base_path,
        save_mode=config.save_mode,
        date_format=config.date_format
    )


def get_save_path_from_config():
    """
    根据配置获取保存路径
    
    Returns:
        str: 保存路径
    """
    try:
        from work_tools2.models import FilePathConfig
        
        # 获取默认配置
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
    now = datetime.now()
    year_month = now.strftime('%Y%m')
    day = now.strftime('%d')
    save_dir = f"D:\\临时文件\\{year_month}\\{day}"
    ensure_directory_exists(save_dir)
    return save_dir
