# D:\project\codeProject\work_tools2\work_tools2\views\database_config.py
import csv
import io
import os
import re
import sqlite3
import tempfile
import time
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from work_tools2.task import get_all_tasks, create_import_task, get_task_status
from work_tools2.models import (
    FormConfig, FormQueryItem, FormUpdateItem, ImportTaskModel,
    TableRowCount, TableImportConfig
)

def is_system_table(table_name):
    """仅过滤 SQLite 内部表，其余表均视为可由前端动态控制"""
    return table_name.startswith('sqlite_')


def get_db_connection():
    """获取数据库连接"""
    db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_cached_row_count(table_name):
    """从 TableRowCount 读取缓存行数，不存在返回 None"""
    try:
        rc = TableRowCount.objects.filter(table_name=table_name).first()
        if rc:
            return rc.row_count
    except Exception:
        pass
    return None


def _refresh_row_count(table_name):
    """重新计算并缓存指定表的行数"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        count = cursor.fetchone()['count']
        conn.close()
        TableRowCount.objects.update_or_create(
            table_name=table_name,
            defaults={'row_count': count}
        )
        return count
    except Exception:
        return None


def _remove_row_count(table_name):
    """删除表行数缓存"""
    try:
        TableRowCount.objects.filter(table_name=table_name).delete()
    except Exception:
        pass


def _rename_row_count(old_name, new_name):
    """重命名表行数缓存"""
    try:
        TableRowCount.objects.filter(table_name=old_name).update(table_name=new_name)
    except Exception:
        pass


def _get_import_config_map():
    """获取所有表导入配置映射"""
    try:
        return {c.table_name: c.allow_import for c in TableImportConfig.objects.all()}
    except Exception:
        return {}


def _is_table_import_allowed(table_name):
    """判断表是否允许 CSV 导入；未配置时默认允许导入"""
    try:
        config = TableImportConfig.objects.filter(table_name=table_name).first()
        if config:
            return config.allow_import
    except Exception:
        pass
    return True


def _set_import_config(table_name, allow_import):
    """设置表导入开关"""
    try:
        TableImportConfig.objects.update_or_create(
            table_name=table_name,
            defaults={'allow_import': bool(allow_import)}
        )
        return True
    except Exception:
        return False


def _remove_import_config(table_name):
    """删除表导入配置"""
    try:
        TableImportConfig.objects.filter(table_name=table_name).delete()
    except Exception:
        pass


def _rename_import_config(old_name, new_name):
    """重命名表导入配置"""
    try:
        TableImportConfig.objects.filter(table_name=old_name).update(table_name=new_name)
    except Exception:
        pass


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

        # 预加载所有行数缓存和导入配置，避免循环内多次查询
        cache_map = {}
        try:
            for rc in TableRowCount.objects.all():
                cache_map[rc.table_name] = rc
        except Exception:
            pass

        import_config_map = _get_import_config_map()

        tables = []
        for row in cursor.fetchall():
            table_name = row['name']

            # 过滤 SQLite 内部表
            if is_system_table(table_name):
                continue

            # 过滤未开启导入开关的表（由前端导入表配置控制是否显示）
            allow_import = import_config_map.get(table_name, True)
            if not allow_import:
                continue

            # 获取表的字段数
            cursor.execute(f"PRAGMA table_info({table_name})")
            fields = cursor.fetchall()
            field_count = len(fields)

            # 获取记录数：优先读取缓存表，没有缓存再 COUNT(*)
            rc = cache_map.get(table_name)
            if rc:
                record_count = rc.row_count
            else:
                record_count = _refresh_row_count(table_name) or 0

            # 时间直接取自缓存记录，避免大表 MIN/MAX 扫描
            created_at = '-'
            updated_at = '-'
            if rc:
                if rc.created_at:
                    created_at = rc.created_at.strftime('%Y-%m-%d %H:%M:%S')
                if rc.updated_at:
                    updated_at = rc.updated_at.strftime('%Y-%m-%d %H:%M:%S')

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
                'is_system': is_system_table(table_name),
                'allow_import': allow_import
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

        # 初始化行数缓存和导入配置（网页新建的表默认允许导入）
        try:
            TableRowCount.objects.create(table_name=table_name, row_count=0)
        except Exception:
            pass
        try:
            TableImportConfig.objects.create(table_name=table_name, allow_import=True)
        except Exception:
            pass

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
    """更新表结构（支持添加和删除字段）"""
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

        # 找出新增的字段和要保留的字段
        new_fields = []
        kept_field_names = set()
        
        for field in fields:
            field_name = field['name']
            kept_field_names.add(field_name)
            if field_name not in existing_fields and field_name != 'id':
                new_fields.append(field)

        # 找出要删除的字段（排除自动管理字段）
        auto_fields = {'id', 'created_at', 'updated_at', 'create_time', 'update_time', 'created_time', 'updated_time'}
        fields_to_delete = [name for name in existing_fields.keys() 
                           if name not in kept_field_names and name not in auto_fields]

        # 如果没有变化，直接返回
        if not new_fields and not fields_to_delete:
            conn.close()
            return JsonResponse({
                'success': True,
                'message': f'表 {table_name} 结构没有变化',
                'added_fields': 0,
                'deleted_fields': 0
            })

        # 如果只有新增字段，使用简单的 ALTER TABLE
        if new_fields and not fields_to_delete:
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
                'added_fields': len(new_fields),
                'deleted_fields': 0
            })

        # 如果有删除字段，需要重建表
        if fields_to_delete:
            # 开始事务
            cursor.execute("BEGIN TRANSACTION")
            
            try:
                # 1. 创建临时表名
                temp_table_name = f"{table_name}_temp_{int(time.time())}"
                
                # 2. 构建新表的字段定义
                field_defs = []
                
                # 首先添加 id 主键
                if 'id' in existing_fields:
                    field_defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
                
                # 添加用户定义的字段
                for field in fields:
                    field_name = field['name']
                    field_type = field['type']
                    not_null = field.get('notNull', False)
                    unique = field.get('unique', False)
                    default_value = field.get('default', None)
                    
                    col_def = f"{field_name} {field_type}"
                    if not_null:
                        col_def += " NOT NULL"
                    if unique:
                        col_def += " UNIQUE"
                    if default_value is not None:
                        if field_type in ['TEXT']:
                            col_def += f" DEFAULT '{default_value}'"
                        else:
                            col_def += f" DEFAULT {default_value}"
                    
                    field_defs.append(col_def)
                
                # 添加自动管理字段
                field_defs.append("created_at DATETIME DEFAULT (datetime('now', 'localtime'))")
                field_defs.append("updated_at DATETIME DEFAULT (datetime('now', 'localtime'))")
                
                # 3. 创建新表
                create_sql = f"CREATE TABLE {temp_table_name} (\n    " + ",\n    ".join(field_defs) + "\n)"
                cursor.execute(create_sql)
                
                # 4. 复制数据（只复制保留的字段）
                columns_to_copy = [f['name'] for f in fields if f['name'] in existing_fields]
                if 'id' in existing_fields:
                    columns_to_copy.insert(0, 'id')
                
                columns_str = ', '.join(columns_to_copy)
                insert_sql = f"INSERT INTO {temp_table_name} ({columns_str}) SELECT {columns_str} FROM {table_name}"
                cursor.execute(insert_sql)
                
                # 5. 删除旧表
                cursor.execute(f"DROP TABLE {table_name}")
                
                # 6. 重命名新表
                cursor.execute(f"ALTER TABLE {temp_table_name} RENAME TO {table_name}")
                
                # 提交事务
                cursor.execute("COMMIT")
                
                conn.close()
                
                return JsonResponse({
                    'success': True,
                    'message': f'表 {table_name} 结构更新成功',
                    'added_fields': len(new_fields),
                    'deleted_fields': len(fields_to_delete),
                    'deleted_field_names': fields_to_delete
                })
                
            except Exception as e:
                # 回滚事务
                cursor.execute("ROLLBACK")
                conn.close()
                raise e

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

        # 删除行数缓存和导入配置
        _remove_row_count(table_name)
        _remove_import_config(table_name)

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

        # 行数缓存置 0
        try:
            TableRowCount.objects.update_or_create(
                table_name=table_name,
                defaults={'row_count': 0}
            )
        except Exception:
            pass

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
def rename_table(request):
    """重命名表，并同步更新表单配置中的表名引用"""
    try:
        import json
        data = json.loads(request.body)

        old_name = data.get('old_name', '').strip()
        new_name = data.get('new_name', '').strip()

        if not old_name or not new_name:
            return JsonResponse({
                'success': False,
                'message': '旧表名和新表名均不能为空'
            }, status=400)

        if old_name == new_name:
            return JsonResponse({
                'success': False,
                'message': '新表名与旧表名相同'
            }, status=400)

        if not re.match(r'^[a-zA-Z0-9_]+$', new_name):
            return JsonResponse({
                'success': False,
                'message': '新表名只能包含字母、数字和下划线'
            }, status=400)

        # 检查是否为系统表
        if is_system_table(old_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{old_name}" 是系统表，不允许重命名'
            }, status=403)

        if is_system_table(new_name):
            return JsonResponse({
                'success': False,
                'message': f'表名 "{new_name}" 与系统表冲突'
            }, status=403)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查旧表是否存在
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name = ?
                       """, (old_name,))
        if not cursor.fetchone():
            conn.close()
            return JsonResponse({
                'success': False,
                'message': f'表 {old_name} 不存在'
            }, status=404)

        # 检查新表名是否已存在
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name = ?
                       """, (new_name,))
        if cursor.fetchone():
            conn.close()
            return JsonResponse({
                'success': False,
                'message': f'表名 {new_name} 已存在'
            }, status=409)

        # 执行重命名
        cursor.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
        conn.commit()
        conn.close()

        # 同步更新行数缓存和导入配置表名
        _rename_row_count(old_name, new_name)
        _rename_import_config(old_name, new_name)

        # 同步更新表单配置中的表名引用
        updated_configs = 0
        for config in FormConfig.objects.all():
            if isinstance(config.table_name_list, list) and old_name in config.table_name_list:
                config.table_name_list = [
                    new_name if name == old_name else name
                    for name in config.table_name_list
                ]
                config.save(update_fields=['table_name_list'])
                updated_configs += 1

        updated_query_items = 0
        for item in FormQueryItem.objects.all():
            if isinstance(item.connected_table, list) and old_name in item.connected_table:
                item.connected_table = [
                    new_name if name == old_name else name
                    for name in item.connected_table
                ]
                item.save(update_fields=['connected_table'])
                updated_query_items += 1

        updated_update_items = 0
        for item in FormUpdateItem.objects.all():
            if isinstance(item.connected_table, list) and old_name in item.connected_table:
                item.connected_table = [
                    new_name if name == old_name else name
                    for name in item.connected_table
                ]
                # 补充框的主表字段也可能引用该表名
                if item.main_table == old_name:
                    item.main_table = new_name
                    item.save(update_fields=['connected_table', 'main_table'])
                else:
                    item.save(update_fields=['connected_table'])
                updated_update_items += 1

        return JsonResponse({
            'success': True,
            'message': f'表 {old_name} 已重命名为 {new_name}，并更新了 {updated_configs} 个表单配置、{updated_query_items} 个查询字段、{updated_update_items} 个更新字段的表名引用'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'重命名表失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_database_statistics(request):
    """获取数据库统计信息（仅统计允许展示的表）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取所有非 SQLite 内部表
        cursor.execute("""
                       SELECT name
                       FROM sqlite_master
                       WHERE type = 'table'
                         AND name NOT LIKE 'sqlite_%'
                       """)
        all_tables = cursor.fetchall()
        conn.close()

        import_config_map = _get_import_config_map()

        total_tables = 0
        total_records = 0

        for table in all_tables:
            table_name = table['name']
            if is_system_table(table_name):
                continue
            # 只统计被允许展示的表
            if not import_config_map.get(table_name, True):
                continue
            total_tables += 1
            cached = _get_cached_row_count(table_name)
            if cached is not None:
                total_records += cached
            else:
                total_records += _refresh_row_count(table_name) or 0

        # 获取今日导入次数（从持久化任务中统计）
        today = datetime.now().strftime('%Y-%m-%d')
        today_imports = ImportTaskModel.objects.filter(
            status='completed',
            completed_at__date=today
        ).count()

        return JsonResponse({
            'success': True,
            'data': {
                'total_tables': total_tables,
                'total_records': total_records,
                'today_imports': today_imports
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

            # 刷新该行数缓存
            if table_name and not is_system_table(table_name):
                _refresh_row_count(table_name)

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

        # 检查是否为系统表或不允许导入
        if is_system_table(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 是系统表，不允许导入数据'
            }, status=403)

        if not _is_table_import_allowed(table_name):
            return JsonResponse({
                'success': False,
                'message': f'表 "{table_name}" 未开启导入权限，请在导入表配置中开启'
            }, status=403)

        if not csv_file:
            return JsonResponse({
                'success': False,
                'message': '请选择CSV文件'
            }, status=400)

        # 直接保存原始字节到临时文件，避免解码再编码导致换行符异常（如 \r\n 被写成 \r\r\n）
        raw_bytes = csv_file.read()
        truncate_before = request.POST.get('truncate_before', 'false').lower() == 'true'

        temp_dir = os.path.join(settings.BASE_DIR, '临时文件', 'import_tasks')
        os.makedirs(temp_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            suffix='.csv',
            prefix=f'import_{table_name}_',
            dir=temp_dir
        )
        try:
            with os.fdopen(fd, 'wb') as tmpf:
                tmpf.write(raw_bytes)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            raise

        # 创建异步任务
        task_id = create_import_task(
            table_name=table_name,
            file_path=temp_path,
            truncate_before=truncate_before,
            original_filename=csv_file.name
        )

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


# ==================== 查询SQL保存/加载 ====================

def ensure_query_sql_table():
    """确保查询SQL配置表存在"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _query_sql_config (
                table_name TEXT PRIMARY KEY,
                query_sql TEXT NOT NULL,
                saved_at DATETIME DEFAULT (datetime('now', 'localtime')),
                updated_at DATETIME DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.commit()
    finally:
        conn.close()


@require_http_methods(["POST"])
def save_query_sql(request):
    """保存查询SQL（每个表独立保存，持久化到数据库）"""
    try:
        import json
        import re
        
        data = json.loads(request.body)
        sql = data.get('sql', '').strip()
        table_name = data.get('table_name', '').strip()

        if not sql:
            return JsonResponse({
                'success': False,
                'message': 'SQL语句不能为空'
            }, status=400)

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 安全检查：去除注释后检查是否为SELECT语句
        # 移除单行注释（-- 开头的行）
        sql_no_comments = re.sub(r'--[^\n]*', '', sql)
        # 移除多行注释（/* ... */）
        sql_no_comments = re.sub(r'/\*.*?\*/', '', sql_no_comments, flags=re.DOTALL)
        # 去除空白字符
        sql_no_comments = sql_no_comments.strip()
        
        sql_upper = sql_no_comments.upper()
        if not sql_upper.startswith('SELECT'):
            return JsonResponse({
                'success': False,
                'message': '只允许保存SELECT查询语句'
            }, status=400)

        # 禁止危险操作（在原始SQL中检查）
        dangerous_keywords = ['DROP', 'ALTER', 'CREATE', 'TRUNCATE', 'DELETE', 'UPDATE', 'INSERT']
        sql_upper_original = sql.upper()
        for keyword in dangerous_keywords:
            # 使用正则表达式匹配完整的单词，避免误判（如SELECT中的ECT不会被DELETE匹配）
            if re.search(r'\b' + keyword + r'\b', sql_upper_original):
                return JsonResponse({
                    'success': False,
                    'message': f'SQL语句中包含不允许的关键字: {keyword}'
                }, status=400)

        # 确保配置表存在
        ensure_query_sql_table()
        
        # 保存到数据库（使用INSERT OR REPLACE实现更新）
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO _query_sql_config (table_name, query_sql, updated_at)
                VALUES (?, ?, datetime('now', 'localtime'))
            """, (table_name, sql))
            conn.commit()
        finally:
            conn.close()

        return JsonResponse({
            'success': True,
            'message': f'表 {table_name} 的查询SQL已保存'
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'JSON格式错误'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'保存失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def load_query_sql(request):
    """加载指定表的已保存查询SQL（从数据库读取）"""
    try:
        table_name = request.GET.get('table_name', '').strip()

        if not table_name:
            return JsonResponse({
                'success': False,
                'message': '表名不能为空'
            }, status=400)

        # 确保配置表存在
        ensure_query_sql_table()
        
        # 从数据库读取
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT query_sql, saved_at
                FROM _query_sql_config
                WHERE table_name = ?
            """, (table_name,))
            result = cursor.fetchone()
        finally:
            conn.close()

        if result:
            return JsonResponse({
                'success': True,
                'data': {
                    'sql': result['query_sql'],
                    'saved_at': result['saved_at']
                }
            })
        else:
            return JsonResponse({
                'success': True,
                'data': None,
                'message': f'表 {table_name} 没有保存的查询SQL'
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'加载失败: {str(e)}'
        }, status=500)


# ==================== 表数据管理（查询/新增/编辑/删除）====================

@csrf_exempt
@require_http_methods(["POST"])
def query_table_data(request):
    """分页查询表数据，支持按字段模糊/精确匹配"""
    try:
        import json
        data = json.loads(request.body)
        table_name = data.get('table_name', '').strip()
        conditions = data.get('conditions', {})
        page = int(data.get('page', 1))
        page_size = int(data.get('page_size', 20))

        if not table_name:
            return JsonResponse({'success': False, 'message': '表名不能为空'}, status=400)

        if is_system_table(table_name):
            return JsonResponse({'success': False, 'message': '系统表禁止操作'}, status=403)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            conn.close()
            return JsonResponse({'success': False, 'message': f'表 {table_name} 不存在'}, status=404)

        # 获取字段信息
        cursor.execute(f"PRAGMA table_info({table_name})")
        fields = [row['name'] for row in cursor.fetchall()]

        # 构建 WHERE 子句
        where_clauses = []
        params = []
        for field, value in conditions.items():
            if field in fields and value:
                where_clauses.append(f"{field} LIKE ?")
                params.append(f'%{value}%')

        where_sql = ''
        if where_clauses:
            where_sql = 'WHERE ' + ' AND '.join(where_clauses)

        # 查询总数
        count_sql = f"SELECT COUNT(*) as total FROM {table_name} {where_sql}"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()['total']

        # 分页查询
        offset = (page - 1) * page_size
        query_sql = f"SELECT * FROM {table_name} {where_sql} LIMIT ? OFFSET ?"
        cursor.execute(query_sql, params + [page_size, offset])
        rows = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return JsonResponse({
            'success': True,
            'data': {
                'fields': fields,
                'rows': rows,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': max(1, (total + page_size - 1) // page_size)
            }
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'查询失败: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def insert_table_data(request):
    """向表中插入单条记录"""
    try:
        import json
        data = json.loads(request.body)
        table_name = data.get('table_name', '').strip()
        record = data.get('record', {})

        if not table_name:
            return JsonResponse({'success': False, 'message': '表名不能为空'}, status=400)

        if is_system_table(table_name):
            return JsonResponse({'success': False, 'message': '系统表禁止操作'}, status=403)

        if not record:
            return JsonResponse({'success': False, 'message': '插入数据不能为空'}, status=400)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            conn.close()
            return JsonResponse({'success': False, 'message': f'表 {table_name} 不存在'}, status=404)

        # 过滤掉空值，避免违反非空约束
        valid_fields = {k: v for k, v in record.items() if v is not None and str(v).strip() != ''}

        if not valid_fields:
            conn.close()
            return JsonResponse({'success': False, 'message': '没有有效的字段数据'}, status=400)

        columns = ', '.join(valid_fields.keys())
        placeholders = ', '.join(['?' for _ in valid_fields])
        values = list(valid_fields.values())

        cursor.execute(f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})", values)
        conn.commit()
        conn.close()

        # 刷新行数缓存
        _refresh_row_count(table_name)

        return JsonResponse({
            'success': True,
            'message': '数据插入成功',
            'data': {'inserted_id': cursor.lastrowid}
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'插入失败: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def update_table_data(request):
    """更新表中记录，必须指定 WHERE 条件"""
    try:
        import json
        data = json.loads(request.body)
        table_name = data.get('table_name', '').strip()
        record = data.get('record', {})
        where_conditions = data.get('where_conditions', {})

        if not table_name:
            return JsonResponse({'success': False, 'message': '表名不能为空'}, status=400)

        if is_system_table(table_name):
            return JsonResponse({'success': False, 'message': '系统表禁止操作'}, status=403)

        if not where_conditions:
            return JsonResponse({'success': False, 'message': '更新操作必须指定 WHERE 条件'}, status=400)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            conn.close()
            return JsonResponse({'success': False, 'message': f'表 {table_name} 不存在'}, status=404)

        set_clauses = []
        set_values = []
        for k, v in record.items():
            set_clauses.append(f"{k} = ?")
            set_values.append(v)

        where_clauses = []
        where_values = []
        for k, v in where_conditions.items():
            where_clauses.append(f"{k} = ?")
            where_values.append(v)

        sql = f"UPDATE {table_name} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"
        cursor.execute(sql, set_values + where_values)
        conn.commit()
        affected_rows = cursor.rowcount
        conn.close()

        return JsonResponse({
            'success': True,
            'message': f'更新成功，影响 {affected_rows} 行',
            'data': {'affected_rows': affected_rows}
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'更新失败: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@csrf_exempt
@require_http_methods(["POST"])
def clear_import_tasks(request):
    """清空所有已完成/失败的导入任务"""
    try:
        from work_tools2.task import clear_completed_tasks
        deleted_count = clear_completed_tasks()
        return JsonResponse({
            'success': True,
            'message': f'已清理 {deleted_count} 个已完成/失败的任务'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'清理任务失败: {str(e)}'
        }, status=500)


def delete_table_data(request):
    """删除表中记录，必须指定 WHERE 条件"""
    try:
        import json
        data = json.loads(request.body)
        table_name = data.get('table_name', '').strip()
        where_conditions = data.get('where_conditions', {})

        if not table_name:
            return JsonResponse({'success': False, 'message': '表名不能为空'}, status=400)

        if is_system_table(table_name):
            return JsonResponse({'success': False, 'message': '系统表禁止操作'}, status=403)

        if not where_conditions:
            return JsonResponse({'success': False, 'message': '删除操作必须指定 WHERE 条件'}, status=400)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            conn.close()
            return JsonResponse({'success': False, 'message': f'表 {table_name} 不存在'}, status=404)

        where_clauses = []
        where_values = []
        for k, v in where_conditions.items():
            where_clauses.append(f"{k} = ?")
            where_values.append(v)

        sql = f"DELETE FROM {table_name} WHERE {' AND '.join(where_clauses)}"
        cursor.execute(sql, where_values)
        conn.commit()
        affected_rows = cursor.rowcount
        conn.close()

        # 刷新行数缓存
        _refresh_row_count(table_name)

        return JsonResponse({
            'success': True,
            'message': f'删除成功，影响 {affected_rows} 行',
            'data': {'affected_rows': affected_rows}
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'删除失败: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def get_import_configs(request):
    """获取所有非系统表的 CSV 导入配置（未配置时默认允许导入）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        table_names = [row['name'] for row in cursor.fetchall() if not is_system_table(row['name'])]
        conn.close()

        config_map = _get_import_config_map()

        configs = []
        for table_name in table_names:
            configs.append({
                'table_name': table_name,
                'allow_import': config_map.get(table_name, True),
                'updated_at': '-',
            })
        return JsonResponse({'success': True, 'data': configs})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_import_config(request):
    """保存单张表的 CSV 导入开关"""
    try:
        import json
        data = json.loads(request.body)
        table_name = data.get('table_name', '').strip()
        allow_import = data.get('allow_import', True)

        if not table_name:
            return JsonResponse({'success': False, 'message': '表名不能为空'}, status=400)

        if is_system_table(table_name):
            return JsonResponse({'success': False, 'message': '系统表不允许配置'}, status=403)

        _set_import_config(table_name, allow_import)
        return JsonResponse({
            'success': True,
            'message': f'表 {table_name} 已{"允许" if allow_import else "禁止"}导入'
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON 格式错误'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def save_import_configs_batch(request):
    """批量保存表的 CSV 导入开关"""
    try:
        import json
        data = json.loads(request.body)
        configs = data.get('configs', [])

        if not isinstance(configs, list):
            return JsonResponse({'success': False, 'message': 'configs 必须是数组'}, status=400)

        changed = 0
        failed = []
        for cfg in configs:
            table_name = str(cfg.get('table_name', '')).strip()
            allow_import = cfg.get('allow_import', True)
            if not table_name:
                continue
            if is_system_table(table_name):
                failed.append(table_name)
                continue
            if _set_import_config(table_name, allow_import):
                changed += 1
            else:
                failed.append(table_name)

        if failed:
            return JsonResponse({
                'success': False,
                'message': f'保存 {changed} 项成功，{len(failed)} 项失败: {", ".join(failed)}'
            }, status=500)

        return JsonResponse({
            'success': True,
            'message': f'已保存 {changed} 项导入配置'
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON 格式错误'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
