# 数据库迁移说明

## 新增模型

已添加 `ComponentConfig` 模型到 `work_tools2/models.py`，用于存储表单组件配置项。

### 模型字段：
- `name`: 配置项名称（唯一）
- `component_type`: 组件类型（select/radio）
- `options`: 选项配置（JSON格式）
- `usage_count`: 使用次数
- `created_at`: 创建时间
- `updated_at`: 更新时间

## 迁移步骤

请在项目根目录执行以下命令：

```bash
# 1. 创建迁移文件
python manage.py makemigrations

# 2. 应用迁移到数据库
python manage.py migrate

# 3. （可选）查看迁移状态
python manage.py showmigrations
```

## 新增的API端点

- `GET /api/components/` - 获取组件列表（支持分页和搜索）
- `GET /api/components/<id>/` - 获取组件详情
- `POST /api/components/save/` - 创建或更新组件
- `DELETE /api/components/delete/<id>/` - 删除组件
- `GET /api/components/<id>/usage/` - 查看组件使用情况

## 前端更新

已更新 `templates/component_config.html` 中的JavaScript代码：
- 移除了所有模拟数据
- 实现了真实的API调用
- 支持完整的增删改查功能
- 支持分页和搜索
- 支持查看引用情况
