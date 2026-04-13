import os
import csv
import io
import sqlite3
import threading
import time
from datetime import datetime
from django.conf import settings

# 全局任务队列
import_tasks = {}
task_lock = threading.Lock()
# 任务执行队列（FIFO）
task_queue = []
queue_lock = threading.Lock()
# 标记是否有任务正在执行
is_executing = False


class ImportTask:
    """导入任务类"""
    
    def __init__(self, task_id, table_name, file_content, truncate_before=False):
        self.task_id = task_id
        self.table_name = table_name
        self.file_content = file_content
        self.truncate_before = truncate_before
        self.status = 'pending'  # pending, running, completed, failed
        self.progress = 0
        self.total_records = 0
        self.processed_records = 0
        self.inserted_count = 0
        self.failed_count = 0
        self.errors = []
        self.created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.completed_at = None
        self.message = ''
    
    def to_dict(self):
        return {
            'task_id': self.task_id,
            'table_name': self.table_name,
            'status': self.status,
            'progress': self.progress,
            'total_records': self.total_records,
            'processed_records': self.processed_records,
            'inserted_count': self.inserted_count,
            'failed_count': self.failed_count,
            'errors': self.errors[:10],  # 只返回前10个错误
            'created_at': self.created_at,
            'completed_at': self.completed_at,
            'message': self.message
        }


def process_task_queue():
    """处理任务队列（FIFO）"""
    global is_executing
    
    with queue_lock:
        # 如果正在执行或队列为空，直接返回
        if is_executing or not task_queue:
            return
        
        # 取出第一个任务
        task_id = task_queue.pop(0)
        is_executing = True
        print(f"[任务队列] 开始执行任务: {task_id}, 队列剩余: {len(task_queue)}")
    
    # 在锁外执行任务
    with task_lock:
        task = import_tasks.get(task_id)
    
    if task:
        try:
            execute_import_task(task)
            print(f"[任务队列] 任务完成: {task_id}, 状态: {task.status}")
        except Exception as e:
            print(f"[任务队列] 任务执行异常: {task_id}, 错误: {str(e)}")
    else:
        print(f"[任务队列] 任务不存在: {task_id}")
    
    # 任务完成后，标记为可执行下一个
    with queue_lock:
        is_executing = False
    
    # 检查是否还有待执行的任务
    process_task_queue()


def execute_import_task(task):
    """执行导入任务（在后台线程中运行）"""
    try:
        task.status = 'running'
        task.progress = 10
        
        # 读取CSV内容
        csv_reader = csv.reader(io.StringIO(task.file_content))
        
        # 读取表头
        headers = next(csv_reader)
        headers = [h.strip().replace(' ', '_').replace('-', '_') for h in headers]
        
        # 获取数据库连接
        db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (task.table_name,))
        if not cursor.fetchone():
            task.status = 'failed'
            task.message = f'表 {task.table_name} 不存在'
            conn.close()
            return
        
        # 获取表的字段信息
        cursor.execute(f"PRAGMA table_info({task.table_name})")
        table_fields = {row[1]: row for row in cursor.fetchall()}
        
        # 创建小写字段名映射（用于大小写不敏感匹配）
        table_fields_lower = {name.lower(): name for name in table_fields.keys()}

        # 过滤掉表中不存在的字段（大小写不敏感）
        valid_headers = []
        header_mapping = {}  # CSV表头 -> 表字段名的映射
        for h in headers:
            h_lower = h.lower()
            if h_lower in table_fields_lower:
                actual_field_name = table_fields_lower[h_lower]
                valid_headers.append(actual_field_name)
                header_mapping[h] = actual_field_name

        if not valid_headers:
            task.status = 'failed'
            csv_headers_str = ', '.join(headers)
            table_fields_str = ', '.join(table_fields.keys())
            task.message = f'CSV文件中的字段与表结构完全不匹配\n\nCSV文件表头: {csv_headers_str}\n\n表字段列表: {table_fields_str}\n\n请检查CSV文件的列名是否正确'
            conn.close()
            return

        # 如果有部分字段不匹配，记录警告信息
        invalid_headers = [h for h in headers if h.lower() not in table_fields_lower]
        if invalid_headers:
            task.errors.append(f"以下字段在表中不存在，将被忽略: {', '.join(invalid_headers)}")

    # 清空表（如果需要）
        if task.truncate_before:
            cursor.execute(f"DELETE FROM {task.table_name}")
            conn.commit()
        
        # 计算总记录数（用于进度显示）
        all_rows = list(csv_reader)
        task.total_records = len(all_rows)
        task.progress = 20
        
        # 批量插入数据
        placeholders = ','.join(['?' for _ in valid_headers])
        columns = ','.join(valid_headers)
        insert_sql = f"INSERT INTO {task.table_name} ({columns}) VALUES ({placeholders})"
        
        batch_size = 100
        for i in range(0, len(all_rows), batch_size):
            batch = all_rows[i:i + batch_size]
            
            for row_num, row in enumerate(batch, start=i):
                try:
                    if len(row) < len(headers):
                        row.extend([''] * (len(headers) - len(row)))
                    
                    # 提取有效字段的数据
                    values = []
                    for j, header in enumerate(headers):
                        # 使用映射后的实际字段名
                        if header in header_mapping:
                            actual_field_name = header_mapping[header]
                            value = row[j].strip() if j < len(row) else ''
                            
                            # 数据类型转换
                            if actual_field_name in table_fields:
                                field_type = table_fields[actual_field_name][2]
                                if field_type == 'INTEGER' and value:
                                    try:
                                        value = int(value)
                                    except ValueError:
                                        value = 0
                                elif field_type == 'REAL' and value:
                                    try:
                                        value = float(value)
                                    except ValueError:
                                        value = 0.0
                            
                            values.append(value)
                    
                    if values:
                        cursor.execute(insert_sql, values)
                        task.inserted_count += 1
                    
                    task.processed_records += 1
                    
                except Exception as e:
                    task.failed_count += 1
                    task.errors.append(f"第{task.processed_records + 2}行: {str(e)}")
            
            # 每批提交一次
            conn.commit()
            
            # 更新进度
            task.progress = 20 + int((task.processed_records / task.total_records) * 80)
        
        conn.close()
        
        task.status = 'completed'
        task.progress = 100
        task.completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        task.message = f'导入完成！成功: {task.inserted_count}, 失败: {task.failed_count}'
        
    except Exception as e:
        task.status = 'failed'
        task.completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        task.message = f'导入失败: {str(e)}'
        import traceback
        task.errors.append(traceback.format_exc())


def create_import_task(table_name, file_content, truncate_before=False):
    """创建导入任务并加入队列"""
    import uuid
    
    task_id = str(uuid.uuid4())[:8]
    task = ImportTask(task_id, table_name, file_content, truncate_before)
    
    with task_lock:
        import_tasks[task_id] = task
    
    # 将任务ID加入队列
    with queue_lock:
        task_queue.append(task_id)
    
    # 启动队列处理器（如果还没有在运行）
    thread = threading.Thread(target=process_task_queue)
    thread.daemon = True
    thread.start()
    
    return task_id


def get_task_status(task_id):
    """获取任务状态"""
    with task_lock:
        task = import_tasks.get(task_id)
        if task:
            return task.to_dict()
        return None


def get_all_tasks():
    """获取所有任务列表"""
    with task_lock:
        return [task.to_dict() for task in sorted(
            import_tasks.values(),
            key=lambda x: x.created_at,
            reverse=True
        )]


def cleanup_old_tasks(max_age_hours=24):
    """清理旧任务（超过指定时间的已完成/失败任务）"""
    from datetime import timedelta
    
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    
    with task_lock:
        to_remove = []
        for task_id, task in import_tasks.items():
            task_time = datetime.strptime(task.created_at, '%Y-%m-%d %H:%M:%S')
            if task_time < cutoff_time and task.status in ['completed', 'failed']:
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del import_tasks[task_id]
