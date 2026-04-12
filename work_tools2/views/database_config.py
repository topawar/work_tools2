# D:\project\codeProject\work_tools2\work_tools2\views\database_config.py
import csv
import io
import os
import sqlite3
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from work_tools2.task import get_all_tasks, create_import_task, get_task_status

# 系统表集合 - 这些表不允许删除、清空或修改
SYSTEM_TABLES = {
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

    # 业务核心表（根据实际需求添加）
    'work_tools2_formconfig',
    'work_tools2_formqueryitem',
    'work_tools2_formupdateitem',
    'work_tools2_componentconfig',
    'work_tools2_menu',
    '_table_metadata',
    'work_tools2_databaseipconfig'
}


def get_db_connection():
    """获取数据库连接"""
    db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def is_system_table(table_name):
    """检查是否为系统表"""
    return table_name in SYSTEM_TABLES or table_name.startswith('sqlite_') or table_name.startswith('django_')


@require_http_methods(["GET"])
def get_table_list(request):
    """获取所有表列表"""
    try:
        import os
        from datetime import datetime

        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取所有用户表（排除sqlite系统表和django系统表）
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name NOT LIKE 'sqlite_%'
                       ORDER BY name
                       """)

        tables = []
        for row in cursor.fetchall():
            table_name = row['name']

            # 过滤系统表
            if is_system_table(table_name):
                continue

            # 获取表的字段数
            cursor.execute(f"PRAGMA table_info({table_name})")
            fields = cursor.fetchall()
            field_count = len(fields)

            # 获取记录数
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            record_count = cursor.fetchone()['count']

            # 获取创建时间（从sqlite_master的create_time或使用文件修改时间）
            created_at = '-'
            updated_at = '-'

            # 尝试从表中获取最早和最晚的时间戳
            has_created_at = any(f['name'] == 'created_at' for f in fields)
            has_updated_at = any(f['name'] == 'updated_at' for f in fields)

            if has_created_at:
                try:
                    cursor.execute(f"SELECT MIN(created_at) as min_time FROM {table_name}")
                    result = cursor.fetchone()
                    if result and result['min_time']:
                        created_at = result['min_time']
                except:
                    pass

            if has_updated_at:
                try:
                    cursor.execute(f"SELECT MAX(updated_at) as max_time FROM {table_name}")
                    result = cursor.fetchone()
                    if result and result['max_time']:
                        updated_at = result['max_time']
                except:
                    pass

            # 如果表中没有时间字段，使用数据库文件的修改时间
            if created_at == '-':
                try:
                    db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
                    file_mtime = os.path.getmtime(db_path)
                    created_at = datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass

            # 获取表备注（从表注释或特殊标记中获取）
            comment = ''
            try:
                cursor.execute("SELECT comment FROM _table_metadata WHERE table_name = ?", (table_name,))
                meta = cursor.fetchone()
                if meta and meta['comment']:
                    comment = meta['comment']
            except:
                pass

            tables.append({
                'name': table_name,
                'comment': comment,
                'field_count': field_count,
                'record_count': record_count,
                'created_at': created_at,
                'updated_at': updated_at,
                'is_system': is_system_table(table_name)
            })

        conn.close()

        return JsonResponse({
            'success': True,
            'data': tables
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
def create_table(request):
    """创建新表"""
    try:
        import json
        data = json.loads(request.body)

        table_name = data.get('table_name', '').strip()
        table_comment = data.get('table_comment', '').strip()
        fields = data.get('fields', [])

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 验证表名格式
        if not table_name.replace('_', '').isalnum():
            return JsonResponse({
                'success': False,
                'message': '表名只能包含字母、数字和下划线'
            }, status=400)

        # 检查是否与系统表冲突
        if is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表名 "{table_name}" 是系统保留名称，不能使用'
            }, status=400)

        if not fields or len(fields) == 0:
            return JsonResponse({
                'success': False,
                'message': '至少需要定义一个字段'
            }, status=400)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查表是否已存在
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name = ?
                       """, (table_name,))

        if cursor.fetchone():
            conn.close()
            return JsonResponse({
                'success': False,
                'message': f'表 {table_name} 已存在'
            }, status=400)

        # 构建CREATE TABLE语句
        field_defs = ['id INTEGER PRIMARY KEY AUTOINCREMENT']

        for field in fields:
            field_name = field['name'].strip()
            field_type = field['type']
            not_null = field.get('notNull', False)
            unique = field.get('unique', False)
            default_value = field.get('default', None)

            # 验证字段名
            if not field_name.replace('_', '').isalnum():
                conn.close()
                return JsonResponse({
                    'success': False,
                    'message': f'字段名 "{field_name}" 格式不正确'
                }, status=400)

            # 构建字段定义
            field_def = f"{field_name} {field_type}"

            if not_null:
                field_def += " NOT NULL"

            if unique:
                field_def += " UNIQUE"

            if default_value is not None and default_value != '':
                if field_type in ['TEXT']:
                    field_def += f" DEFAULT '{default_value}'"
                else:
                    field_def += f" DEFAULT {default_value}"

            field_defs.append(field_def)

        # 添加时间戳字段（使用本地时间）
        field_defs.append("created_at DATETIME DEFAULT (datetime('now', 'localtime'))")
        field_defs.append("updated_at DATETIME DEFAULT (datetime('now', 'localtime'))")

        # 执行创建表
        create_sql = f"CREATE TABLE {table_name} (\n    " + ",\n    ".join(field_defs) + "\n)"
        cursor.execute(create_sql)

        # 如果有表备注，创建一个元数据记录（使用一个特殊的注释表）
        if table_comment:
            try:
                # 检查元数据表是否存在
                cursor.execute("""
                               SELECT name
                               FROM sqlite_master
                               WHERE type = 'table'
                                 AND name = '_table_metadata'
                               """)
                if not cursor.fetchone():
                    # 创建元数据表
                    cursor.execute("""
                                   CREATE TABLE _table_metadata
                                   (
                                       table_name TEXT PRIMARY KEY,
                                       comment    TEXT,
                                       created_at DATETIME DEFAULT (datetime('now', 'localtime')),
                                       updated_at DATETIME DEFAULT (datetime('now', 'localtime'))
                                   )
                                   """)

                # 插入表备注
                cursor.execute(
                    "INSERT OR REPLACE INTO _table_metadata (table_name, comment) VALUES (?, ?)",
                    (table_name, table_comment)
                )
            except Exception as e:
                print(f"保存表备注失败: {e}")

        conn.commit()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'表 {table_name} 创建成功',
            'sql': create_sql
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'创建表失败: {str(e)}'
        }, status=500)




@require_http_methods(["GET"])
def get_table_structure(request):
    """获取表结构"""
    try:
        table_name = request.GET.get('table_name', '')

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 检查是否为系统表
        if is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 是系统表，不允许查看结构'
            }, status=403)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取字段信息
        cursor.execute(f"PRAGMA table_info({table_name})")
        fields = cursor.fetchall()

        field_list = []
        for field in fields:
            field_list.append({
                'name': field['name'],
                'type': field['type'],
                'notNull': bool(field['notnull']),
                'default': field['dflt_value'],
                'primaryKey': bool(field['pk'])
            })

        # 获取记录数
        cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        record_count = cursor.fetchone()['count']

        conn.close()

        return JsonResponse({
            'success': True,
            'data': {
                'table_name': table_name,
                'fields': field_list,
                'record_count': record_count
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
def update_table_structure(request):
    """更新表结构（SQLite限制较多，仅支持重命名表和添加列）"""
    try:
        import json
        data = json.loads(request.body)

        table_name = data.get('table_name', '')
        fields = data.get('fields', [])

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 检查是否为系统表
        if is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 是系统表，不允许修改结构'
            }, status=403)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取现有字段
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_fields = {row['name']: row for row in cursor.fetchall()}

        # 找出新增的字段
        new_fields = []
        for field in fields:
            field_name = field['name']
            if field_name not in existing_fields and field_name != 'id':
                new_fields.append(field)

        # 添加新字段
        for field in new_fields:
            field_name = field['name']
            field_type = field['type']
            not_null = field.get('notNull', False)
            default_value = field.get('default', None)

            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {field_name} {field_type}"

            if not_null and default_value is not None:
                if field_type in ['TEXT']:
                    alter_sql += f" NOT NULL DEFAULT '{default_value}'"
                else:
                    alter_sql += f" NOT NULL DEFAULT {default_value}"
            elif default_value is not None:
                if field_type in ['TEXT']:
                    alter_sql += f" DEFAULT '{default_value}'"
                else:
                    alter_sql += f" DEFAULT {default_value}"

            cursor.execute(alter_sql)

        conn.commit()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'表 {table_name} 结构更新成功',
            'added_fields': len(new_fields)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'更新表结构失败: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def delete_table(request):
    """删除表"""
    try:
        import json
        data = json.loads(request.body)

        table_name = data.get('table_name', '')

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 检查是否为系统表
        if is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 是系统表，不允许删除'
            }, status=403)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name = ?
                       """, (table_name,))

        if not cursor.fetchone():
            conn.close()
            return JsonResponse({
                'success': False,
                'message': f'表 {table_name} 不存在'
            }, status=404)

        # 删除表
        cursor.execute(f"DROP TABLE {table_name}")
        conn.commit()
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'表 {table_name} 已删除'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'删除表失败: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def truncate_table(request):
    """清空表数据"""
    try:
        import json
        data = json.loads(request.body)

        table_name = data.get('table_name', '')

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 检查是否为系统表
        if is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 是系统表，不允许清空'
            }, status=403)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name = ?
                       """, (table_name,))

        if not cursor.fetchone():
            conn.close()
            return JsonResponse({
                'success': False,
                'message': f'表 {table_name} 不存在'
            }, status=404)

        # 获取清空前的大小
        db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
        size_before = os.path.getsize(db_path)

        # 清空表并提交
        cursor.execute(f"DELETE FROM {table_name}")
        conn.commit()

        # 关闭连接
        conn.close()

        # 重新打开连接执行VACUUM（必须在单独的事务中）
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("VACUUM")
        conn.commit()
        conn.close()

        # 获取清空后的大小
        size_after = os.path.getsize(db_path)
        saved_bytes = size_before - size_after
        saved_mb = round(saved_bytes / (1024 * 1024), 2)

        message = f'表 {table_name} 数据已清空'
        if saved_mb > 0:
            message += f'，释放了 {saved_mb} MB 空间'

        return JsonResponse({
            'success': True,
            'message': message
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'清空表失败: {str(e)}'
        }, status=500)



@csrf_exempt
@require_http_methods(["POST"])
def import_csv_data(request):
    """导入CSV数据"""
    try:
        table_name = request.POST.get('table_name', '')
        csv_file = request.FILES.get('csv_file')

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 检查是否为系统表
        if is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 是系统表，不允许导入数据'
            }, status=403)

        if not csv_file:
            return JsonResponse({
                'success': False,
                'message': '请选择CSV文件'
            }, status=400)

        # 读取CSV文件
        csv_content = csv_file.read().decode('utf-8')
        csv_reader = csv.reader(io.StringIO(csv_content))

        # 读取表头
        headers = next(csv_reader)

        # 清理表头（去除空格和特殊字符）
        headers = [h.strip().replace(' ', '_').replace('-', '_') for h in headers]

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name = ?
                       """, (table_name,))

        if not cursor.fetchone():
            conn.close()
            return JsonResponse({
                'success': False,
                'message': f'表 {table_name} 不存在'
            }, status=404)

        # 获取表的字段信息
        cursor.execute(f"PRAGMA table_info({table_name})")
        table_fields = {row['name']: row for row in cursor.fetchall()}

        # 过滤掉表中不存在的字段
        valid_headers = [h for h in headers if h in table_fields]

        if not valid_headers:
            conn.close()
            return JsonResponse({
                'success': False,
                'message': 'CSV文件中的字段与表结构不匹配'
            }, status=400)

        # 清空表（如果需要）
        truncate_before = request.POST.get('truncate_before', 'false').lower() == 'true'
        if truncate_before:
            cursor.execute(f"DELETE FROM {table_name}")

        # 批量插入数据
        inserted_count = 0
        failed_count = 0
        errors = []

        placeholders = ','.join(['?' for _ in valid_headers])
        columns = ','.join(valid_headers)
        insert_sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        for row_num, row in enumerate(csv_reader, start=2):
            try:
                if len(row) < len(headers):
                    # 补齐空值
                    row.extend([''] * (len(headers) - len(row)))

                # 提取有效字段的数据
                values = []
                for i, header in enumerate(headers):
                    if header in valid_headers:
                        value = row[i].strip() if i < len(row) else ''

                        # 数据类型转换
                        if header in table_fields:
                            field_type = table_fields[header]['type']
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
                    inserted_count += 1

                    # 每100条提交一次
                    if inserted_count % 100 == 0:
                        conn.commit()

            except Exception as e:
                failed_count += 1
                errors.append(f"第{row_num}行: {str(e)}")

        conn.commit()
        conn.close()

        result = {
            'success': True,
            'message': f'导入完成！成功: {inserted_count}, 失败: {failed_count}',
            'inserted_count': inserted_count,
            'failed_count': failed_count
        }

        if errors and len(errors) <= 10:
            result['errors'] = errors

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'导入失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def get_database_statistics(request):
    """获取数据库统计信息"""
    try:
        import os

        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取表数量（排除系统表）
        cursor.execute("""
                       SELECT COUNT(*) as count
                       FROM sqlite_master
                       WHERE type ='table' AND name NOT LIKE 'sqlite_%'
                       """)
        all_tables_count = cursor.fetchone()['count']

        # 获取用户表数量
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name NOT LIKE 'sqlite_%'
                       """)
        all_tables = cursor.fetchall()

        total_tables = 0
        total_records = 0

        for table in all_tables:
            table_name = table['name']
            if not is_system_table(table_name):
                total_tables += 1
                cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                total_records += cursor.fetchone()['count']

        conn.close()

        # 获取数据库文件大小
        db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
        db_size_bytes = os.path.getsize(db_path)
        db_size_mb = round(db_size_bytes / (1024 * 1024), 2)

        # 获取今日导入次数（从任务队列中统计）
        from work_tools2.task import import_tasks
        today = datetime.now().strftime('%Y-%m-%d')
        today_imports = 0

        for task in import_tasks.values():
            if task.created_at.startswith(today) and task.status == 'completed':
                today_imports += 1

        return JsonResponse({
            'success': True,
            'data': {
                'total_tables': total_tables,
                'total_records': total_records,
                'today_imports': today_imports,
                'db_size': f"{db_size_mb} MB"
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@require_http_methods(["POST"])
def execute_sql_query(request):
    """执行SQL查询（支持SELECT、INSERT、UPDATE、DELETE）"""
    try:
        import json
        data = json.loads(request.body)

        sql = data.get('sql', '').strip()
        table_name = data.get('table_name', '')

        if not sql:
            return JsonResponse({
                'success': False,
                'message': 'SQL语句不能为空'
            }, status=400)

        # 安全检查：只允许DML语句（SELECT、INSERT、UPDATE、DELETE）
        sql_upper = sql.upper().strip()
        allowed_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE']

        is_allowed = False
        for keyword in allowed_keywords:
            if sql_upper.startswith(keyword):
                is_allowed = True
                break

        if not is_allowed:
            return JsonResponse({
                'success': False,
                'message': '只允许执行 SELECT、INSERT、UPDATE、DELETE 语句'
            }, status=403)

        # 禁止危险操作
        dangerous_keywords = ['DROP', 'ALTER', 'CREATE', 'TRUNCATE', 'GRANT', 'REVOKE']
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                return JsonResponse({
                    'success': False,
                    'message': f'不允许执行包含 {keyword} 的语句'
                }, status=403)

        # 检查是否操作系统表
        if table_name and is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 是系统表，不允许操作'
            }, status=403)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 执行SQL
        cursor.execute(sql)

        # 判断是否为查询语句
        if sql_upper.startswith('SELECT'):
            # 获取查询结果
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()

            # 转换为字典列表
            results = []
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    # 处理特殊类型
                    if isinstance(value, bytes):
                        value = value.decode('utf-8', errors='ignore')
                    row_dict[col] = value
                results.append(row_dict)

            conn.close()

            return JsonResponse({
                'success': True,
                'data': {
                    'columns': columns,
                    'rows': results,
                    'count': len(results),
                    'is_query': True
                }
            })
        else:
            # 非查询语句（INSERT、UPDATE、DELETE）
            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()

            return JsonResponse({
                'success': True,
                'data': {
                    'affected_rows': affected_rows,
                    'is_query': False,
                    'message': f'成功影响 {affected_rows} 行记录'
                }
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'查询执行失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def import_csv_data(request):
    """导入CSV数据（异步任务）"""
    try:
        table_name = request.POST.get('table_name', '')
        csv_file = request.FILES.get('csv_file')

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 检查是否为系统表
        if is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 是系统表，不允许导入数据'
            }, status=403)

        if not csv_file:
            return JsonResponse({
                'success': False,
                'message': '请选择CSV文件'
            }, status=400)

        # 读取CSV文件内容
        csv_content = csv_file.read().decode('utf-8')
        truncate_before = request.POST.get('truncate_before', 'false').lower() == 'true'

        # 创建异步任务
        task_id = create_import_task(table_name, csv_content, truncate_before)

        return JsonResponse({
            'success': True,
            'message': '导入任务已创建，正在后台处理',
            'task_id': task_id
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'创建任务失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def get_import_task_status(request):
    """获取导入任务状态"""
    try:
        task_id = request.GET.get('task_id', '')

        if not task_id:
            return JsonResponse({
                'success': False,
                'message': '任务ID不能为空'
            }, status=400)

        task_status = get_task_status(task_id)

        if task_status:
            return JsonResponse({
                'success': True,
                'data': task_status
            })
        else:
            return JsonResponse({
                'success': False,
                'message': '任务不存在'
            }, status=404)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'获取任务状态失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def get_import_tasks_list(request):
    """获取所有导入任务列表"""
    try:
        tasks = get_all_tasks()

        return JsonResponse({
            'success': True,
            'data': tasks
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'获取任务列表失败: {str(e)}'
        }, status=500)
