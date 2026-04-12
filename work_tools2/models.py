import uuid
from django.db import models


VALID_RULES = [
    ('required', '必填'),
    ('requiredReverse', '不必填'),
    ('defaultNull', '默认空值'),
    ('defaultField', '默认字段'),
]


class FormConfig(models.Model):
    """动态表单配置主表"""
    form_name = models.CharField(max_length=100, verbose_name="表单名称")
    table_name_list = models.JSONField(verbose_name="表名列表", default=list)
    database_ip_ids = models.JSONField(verbose_name="数据库IP配置ID列表", default=list)
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 'work_tools2_formconfig'
        verbose_name = '表单配置'
        verbose_name_plural = '表单配置'

    def __str__(self):
        return f"{self.form_name} (ID: {self.id})"


class FormQueryItem(models.Model):
    """表单查询字段配置"""
    form_config = models.ForeignKey(FormConfig, on_delete=models.CASCADE, related_name='query_items')
    label = models.CharField(max_length=50, verbose_name="标签")
    field_type = models.CharField(max_length=20, default='text', verbose_name="字段类型")
    binding_key = models.CharField(max_length=50, verbose_name="绑定键")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    connected_table = models.JSONField(default=list, verbose_name="关联表")
    valid_rule = models.CharField(max_length=20, choices=VALID_RULES, default='required', verbose_name="验证规则")
    default_value = models.CharField(max_length=200, blank=True, default='', verbose_name="默认值")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        db_table = 'work_tools2_formqueryitem'
        ordering = ['sort_order']
        verbose_name = '查询字段配置'
        verbose_name_plural = '查询字段配置'

    def __str__(self):
        return f"{self.label} ({self.binding_key})"


class FormUpdateItem(models.Model):
    """表单更新字段配置"""
    form_config = models.ForeignKey(FormConfig, on_delete=models.CASCADE, related_name='update_items')
    label = models.CharField(max_length=50, verbose_name="标签")
    field_type = models.CharField(max_length=20, verbose_name="字段类型")
    binding_key = models.CharField(max_length=50, verbose_name="绑定键")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    input_type = models.CharField(max_length=20, default='input', verbose_name="输入类型")
    connected_table = models.JSONField(default=list, verbose_name="关联表")
    new_valid_rule = models.CharField(max_length=20, choices=VALID_RULES, default='required', verbose_name="新值验证规则")
    origin_valid_rule = models.CharField(max_length=20, choices=VALID_RULES, default='required', verbose_name="原值验证规则")
    origin_default_value = models.CharField(max_length=200, blank=True, default='', verbose_name="原值默认值")
    new_default_value = models.CharField(max_length=200, blank=True, default='', verbose_name="新值默认值")
    component_name = models.CharField(max_length=100, blank=True, default='', verbose_name="引用配置项名称")
    main_table = models.CharField(max_length=100, blank=True, default='', verbose_name="主表名")
    main_field = models.CharField(max_length=50, blank=True, default='', verbose_name="主字段名")
    sub_fields = models.JSONField(default=list, verbose_name="子字段配置")
    options = models.JSONField(default=list, verbose_name="选项配置")
    expressions = models.JSONField(default=dict, verbose_name="计算表达式配置")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        db_table = 'work_tools2_formupdateitem'
        ordering = ['sort_order']
        verbose_name = '更新字段配置'
        verbose_name_plural = '更新字段配置'

    def __str__(self):
        return f"{self.label} ({self.binding_key})"


class ComponentConfig(models.Model):
    """表单组件配置项（可复用的下拉框、单选框等配置）"""
    COMPONENT_TYPES = [
        ('select', '下拉框'),
        ('radio', '单选框'),
    ]

    name = models.CharField(max_length=100, unique=True, verbose_name="配置项名称")
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPES, default='select', verbose_name="组件类型")
    options = models.JSONField(default=list, verbose_name="选项配置")
    usage_count = models.IntegerField(default=0, verbose_name="使用次数")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 'work_tools2_componentconfig'
        ordering = ['-created_at']
        verbose_name = '组件配置项'
        verbose_name_plural = '组件配置项'

    def __str__(self):
        return f"{self.name} ({self.get_component_type_display()})"

    def get_option_count(self):
        """获取选项数量"""
        return len(self.options) if isinstance(self.options, list) else 0


class Menu(models.Model):
    """侧边栏菜单模型"""

    name = models.CharField(max_length=50, verbose_name="菜单名称")
    pinyin = models.CharField(max_length=100, blank=True, verbose_name="拼音")
    icon = models.CharField(max_length=50, blank=True, verbose_name="图标")
    url = models.CharField(max_length=200, blank=True, verbose_name="URL")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        verbose_name="父级菜单",
    )
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    is_visible = models.BooleanField(default=True, verbose_name="是否显示")
    group_name = models.CharField(max_length=50, blank=True, verbose_name="分组名称")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["group_name", "sort_order"]
        verbose_name = "菜单"
        verbose_name_plural = "菜单"

    def __str__(self):
        return self.name


class DatabaseIPConfig(models.Model):
    """数据库IP配置模型"""
    
    name = models.CharField(max_length=100, unique=True, verbose_name="配置名称")
    ip_address = models.CharField(max_length=50, verbose_name="IP地址")
    database_name = models.CharField(max_length=100, verbose_name="数据库名")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 'work_tools2_databaseipconfig'
        ordering = ['-created_at']
        verbose_name = '数据库IP配置'
        verbose_name_plural = '数据库IP配置'

    def __str__(self):
        return f"{self.name} ({self.ip_address})"


class FilePathConfig(models.Model):
    """文件输出路径配置模型"""
    
    SAVE_MODES = [
        ('single', '单一文件夹模式'),
        ('date_layered', '按日期分层模式'),
    ]
    
    DATE_FORMATS = [
        ('ymd_slash', '年/月/日 (2025/12/07)'),
        ('ymd_concat', '年月日 (20251207)'),
        ('ym_slash_d', '年月/日 (202512/07)'),
        ('week', '按周格式 (202512\\20251207-20251212)'),
    ]
    
    name = models.CharField(max_length=100, unique=True, verbose_name="配置名称")
    base_path = models.CharField(max_length=500, verbose_name="基础路径")
    save_mode = models.CharField(max_length=20, choices=SAVE_MODES, default='single', verbose_name="保存模式")
    date_format = models.CharField(max_length=20, choices=DATE_FORMATS, default='ymd_slash', verbose_name="日期格式")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    is_default = models.BooleanField(default=False, verbose_name="是否默认配置")
    remark = models.TextField(blank=True, default='', verbose_name="备注说明")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 'work_tools2_filepathconfig'
        ordering = ['-is_default', '-created_at']
        verbose_name = '文件输出路径配置'
        verbose_name_plural = '文件输出路径配置'

    def __str__(self):
        return f"{self.name} - {self.base_path}"
    
    def get_display_save_mode(self):
        """获取保存模式的显示名称"""
        mode_dict = dict(self.SAVE_MODES)
        return mode_dict.get(self.save_mode, self.save_mode)
    
    def get_display_date_format(self):
        """获取日期格式的显示名称"""
        format_dict = dict(self.DATE_FORMATS)
        return format_dict.get(self.date_format, self.date_format)
