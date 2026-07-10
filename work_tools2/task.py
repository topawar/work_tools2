import os
import csv
import io
import sqlite3
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta

from django.conf import settings

from work_tools2.models import ImportTaskModel, TableRowCount

# 内存中的任务执行队列（FIFO）
task_queue = []
queue_lock = threading.Lock()
# 标记是否有任务正在执行
is_executing = False


def _decode_csv_bytes(raw_bytes):
    """将 CSV 字节流解码为字符串：优先 UTF-8，失败则尝试 GBK"""
    if isinstance(raw_bytes, str):
        return raw_bytes
    try:
        return raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return raw_bytes.decode('gbk', errors='replace')


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
    try:
        execute_import_task(task_id)
        print(f"[任务队列] 任务完成: {task_id}")
    except Exception as e:
        print(f"[任务队列] 任务执行异常: {task_id}, 错误: {str(e)}")

    # 任务完成后，标记为可执行下一个
    with queue_lock:
        is_executing = False

    # 检查是否还有待执行的任务
    process_task_queue()


def _update_task_status(task_id, **kwargs):
    """更新数据库中的任务状态"""
    try:
        ImportTaskModel.objects.filter(task_id=task_id).update(**kwargs)
    except Exception as e:
        print(f"[任务队列] 更新任务状态失败 {task_id}: {str(e)}")


def execute_import_task(task_id):
    """执行导入任务（在后台线程中运行）"""
    try:
        task_obj = ImportTaskModel.objects.get(task_id=task_id)
    except ImportTaskModel.DoesNotExist:
        print(f"[任务队列] 任务不存在: {task_id}")
        return

    # 将状态改为 running
    task_obj.status = 'running'
    task_obj.progress = 5
    task_obj.save(update_fields=['status', 'progress', 'processed_records'])

    conn = None
    temp_path = None
    try:
        # 优先从临时文件读取，避免把大文件内容反复加载到内存并写入任务表
        if task_obj.file_path and os.path.exists(task_obj.file_path):
            temp_path = task_obj.file_path
            with open(temp_path, 'rb') as f:
                raw_bytes = f.read()
            file_content = _decode_csv_bytes(raw_bytes)
        else:
            file_content = task_obj.file_content or ''
            if isinstance(file_content, bytes):
                file_content = _decode_csv_bytes(file_content)

        # 流式读取 CSV
        csv_file = io.StringIO(file_content)
        csv_reader = csv.reader(csv_file)

        # 读取表头
        try:
            headers = next(csv_reader)
        except StopIteration:
            raise ValueError('CSV文件为空，未找到表头')

        headers = [h.strip().replace(' ', '_').replace('-', '_') for h in headers]

        # 快速估算总行数（通过换行符数量 - 表头行），避免二次全量扫描
        total_records = max(0, file_content.count('\n') - 1)
        # 若文件末尾无换行，实际可能多一行，这里取保守值即可

        # 获取数据库连接
        db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 大批量导入性能优化：关闭同步、使用内存日志、加大缓存
        # 这些设置仅作用于本次连接，不影响全局数据库配置
        try:
            cursor.execute("PRAGMA synchronous = OFF")
            cursor.execute("PRAGMA journal_mode = MEMORY")
            cursor.execute("PRAGMA cache_size = -100000")
        except Exception:
            pass

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (task_obj.table_name,))
        if not cursor.fetchone():
            task_obj.status = 'failed'
            task_obj.progress = 100
            task_obj.message = f'表 {task_obj.table_name} 不存在'
            task_obj.completed_at = datetime.now()
            task_obj.save()
            conn.close()
            return

        # 获取表的字段信息
        cursor.execute(f"PRAGMA table_info({task_obj.table_name})")
        table_fields = {row[1]: row for row in cursor.fetchall()}
        table_fields_lower = {name.lower(): name for name in table_fields.keys()}

        # 过滤掉表中不存在的字段（大小写不敏感）
        valid_headers = []
        header_mapping = {}
        for h in headers:
            h_lower = h.lower()
            if h_lower in table_fields_lower:
                actual_field_name = table_fields_lower[h_lower]
                valid_headers.append(actual_field_name)
                header_mapping[h] = actual_field_name

        if not valid_headers:
            csv_headers_str = ', '.join(headers)
            table_fields_str = ', '.join(table_fields.keys())
            task_obj.status = 'failed'
            task_obj.progress = 100
            task_obj.message = f'CSV文件中的字段与表结构完全不匹配\n\nCSV文件表头: {csv_headers_str}\n\n表字段列表: {table_fields_str}'
            task_obj.completed_at = datetime.now()
            task_obj.save()
            conn.close()
            return

        errors = []
        invalid_headers = [h for h in headers if h.lower() not in table_fields_lower]
        if invalid_headers:
            errors.append(f"以下字段在表中不存在，将被忽略: {', '.join(invalid_headers)}")

        # 清空表（如果需要）
        if task_obj.truncate_before:
            cursor.execute(f"DELETE FROM {task_obj.table_name}")
            conn.commit()

        # 更新总记录数（扣除表头行）
        task_obj.total_records = total_records
        task_obj.progress = 10
        task_obj.save(update_fields=['total_records', 'progress'])

        # 批量插入数据
        placeholders = ','.join(['?' for _ in valid_headers])
        columns = ','.join(valid_headers)
        insert_sql = f"INSERT INTO {task_obj.table_name} ({columns}) VALUES ({placeholders})"

        batch_size = 10000
        inserted_count = 0
        failed_count = 0
        processed_records = 0
        pending_values = []
        last_reported_progress = 10
        batches_since_report = 0

        def convert_value(value, actual_field_name):
            if actual_field_name in table_fields:
                field_type = table_fields[actual_field_name][2]
                if field_type == 'INTEGER' and value:
                    try:
                        return int(value)
                    except ValueError:
                        return 0
                elif field_type == 'REAL' and value:
                    try:
                        return float(value)
                    except ValueError:
                        return 0.0
            return value

        def report_progress(force=False):
            nonlocal last_reported_progress, batches_since_report
            batches_since_report += 1
            progress = 10 + int((processed_records / total_records) * 90) if total_records > 0 else 100
            # 降低写库频率：每 5 批次 或 进度变化 >= 5% 或强制报告
            if force or batches_since_report >= 5 or abs(progress - last_reported_progress) >= 5:
                _update_task_status(
                    task_id,
                    progress=progress,
                    processed_records=processed_records,
                    inserted_count=inserted_count,
                    failed_count=failed_count,
                    errors=errors[:50]
                )
                last_reported_progress = progress
                batches_since_report = 0

        def flush_batch():
            nonlocal pending_values, inserted_count, failed_count
            if not pending_values:
                return
            try:
                cursor.executemany(insert_sql, pending_values)
                inserted_count += len(pending_values)
            except Exception as e:
                # executemany 失败后逐条执行，记录具体失败行
                for idx, values in enumerate(pending_values):
                    try:
                        cursor.execute(insert_sql, values)
                        inserted_count += 1
                    except Exception as row_e:
                        failed_count += 1
                        errors.append(f"第{processed_records - len(pending_values) + idx + 2}行: {str(row_e)}")
            pending_values = []
            conn.commit()

        for row in csv_reader:
            processed_records += 1
            try:
                if len(row) < len(headers):
                    row.extend([''] * (len(headers) - len(row)))

                values = []
                for j, header in enumerate(headers):
                    if header in header_mapping:
                        actual_field_name = header_mapping[header]
                        value = row[j].strip() if j < len(row) else ''
                        value = convert_value(value, actual_field_name)
                        values.append(value)

                if values:
                    pending_values.append(values)

                if len(pending_values) >= batch_size:
                    flush_batch()
                    report_progress()

            except Exception as e:
                failed_count += 1
                errors.append(f"第{processed_records + 1}行: {str(e)}")

        # 刷新剩余批次
        flush_batch()
        report_progress(force=True)

        conn.close()
        conn = None

        task_obj.refresh_from_db()
        task_obj.status = 'completed'
        task_obj.progress = 100
        task_obj.processed_records = processed_records
        task_obj.inserted_count = inserted_count
        task_obj.failed_count = failed_count
        task_obj.errors = errors[:50]
        task_obj.completed_at = datetime.now()
        task_obj.message = f'导入完成！成功: {inserted_count}, 失败: {failed_count}'
        task_obj.save()

        # 刷新该表行数缓存
        try:
            conn_count = sqlite3.connect(db_path)
            cursor_count = conn_count.cursor()
            cursor_count.execute(f"SELECT COUNT(*) FROM {task_obj.table_name}")
            count = cursor_count.fetchone()[0]
            conn_count.close()
            TableRowCount.objects.update_or_create(
                table_name=task_obj.table_name,
                defaults={'row_count': count}
            )
        except Exception:
            pass

        # 导入成功后清理临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    except Exception as e:
        import traceback
        task_obj.refresh_from_db()
        task_obj.status = 'failed'
        task_obj.progress = 100
        task_obj.completed_at = datetime.now()
        task_obj.message = f'导入失败: {str(e)}'
        task_obj.errors = (task_obj.errors or []) + [traceback.format_exc()]
        task_obj.save()
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def create_import_task(table_name, file_content=None, file_path=None, truncate_before=False, original_filename=''):
    """创建导入任务并加入队列

    优先使用 file_path：CSV 已经保存到临时文件，不再把大文件内容写入任务表。
    file_content 保留用于兼容旧任务。
    """
    task_id = str(uuid.uuid4())[:8]

    if file_content is not None and isinstance(file_content, bytes):
        file_content = file_content.decode('utf-8', errors='replace')

    # 持久化到数据库
    ImportTaskModel.objects.create(
        task_id=task_id,
        table_name=table_name,
        original_filename=original_filename,
        file_content=file_content or '',
        file_path=file_path or '',
        truncate_before=truncate_before,
        status='pending',
        progress=0,
        errors=[]
    )

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
    try:
        task = ImportTaskModel.objects.get(task_id=task_id)
        return task.to_dict()
    except ImportTaskModel.DoesNotExist:
        return None


def get_all_tasks(limit=100):
    """获取所有任务列表"""
    tasks = ImportTaskModel.objects.order_by('-created_at')[:limit]
    return [task.to_dict() for task in tasks]


def _remove_task_temp_file(task):
    """删除任务关联的临时 CSV 文件（失败时保留，便于排查）"""
    if task.status == 'failed':
        return
    path = task.file_path
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def cleanup_old_tasks(max_age_hours=24):
    """清理旧任务（超过指定时间的已完成/失败任务）"""
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    old_tasks = ImportTaskModel.objects.filter(
        created_at__lt=cutoff_time,
        status__in=['completed', 'failed']
    )
    for task in old_tasks:
        _remove_task_temp_file(task)
    old_tasks.delete()


def clear_completed_tasks():
    """清理所有已完成/失败的任务"""
    tasks = ImportTaskModel.objects.filter(
        status__in=['completed', 'failed']
    )
    for task in tasks:
        _remove_task_temp_file(task)
    deleted_count, _ = tasks.delete()
    return deleted_count
