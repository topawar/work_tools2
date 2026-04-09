from django.db import models


class Test(models.Model):
    name = models.CharField(max_length=20)


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


class FormConfig(models.Model):
    """动态表单配置主表"""

    form_id = models.CharField(max_length=50, unique=True, verbose_name="表单ID")
    form_name = models.CharField(max_length=100, verbose_name="表单名称")
    table_name_list = models.JSONField(verbose_name="表名列表", default=list)
    description = models.TextField(blank=True, verbose_name="描述")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "表单配置"
        verbose_name_plural = "表单配置"

    def __str__(self):
        return f"{self.form_name} ({self.form_id})"


class FormQueryItem(models.Model):
    """表单查询字段配置"""

    FORM_TYPES = [
        ('text', '文本'),
        ('number', '数字'),
        ('date', '日期'),
        ('select', '下拉框'),
    ]

    VALID_RULES = [
        ('required', '必填'),
        ('requiredReverse', '不必填'),
        ('defaultNull', '默认空值'),
        ('defaultField', '默认字段'),
    ]

    form_config = models.ForeignKey(
        FormConfig,
        on_delete=models.CASCADE,
        related_name='query_items',
        verbose_name="所属表单"
    )
    label = models.CharField(max_length=50, verbose_name="标签")
    field_type = models.CharField(max_length=20, choices=FORM_TYPES, default='text', verbose_name="字段类型")
    binding_key = models.CharField(max_length=50, verbose_name="绑定键")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    connected_table = models.JSONField(verbose_name="关联表", default=list)
    valid_rule = models.CharField(max_length=20, choices=VALID_RULES, default='required', verbose_name="验证规则")
    default_value = models.CharField(max_length=200, blank=True, verbose_name="默认值")

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "查询字段"
        verbose_name_plural = "查询字段"
        unique_together = ['form_config', 'binding_key']

    def __str__(self):
        return f"{self.form_config.form_name} - {self.label}"


class FormUpdateItem(models.Model):
    """表单更新字段配置"""

    FIELD_TYPES = [
        ('text', '文本'),
        ('number', '数字'),
        ('date', '日期'),
        ('string', '字符串'),
        ('boolean', '布尔值'),
        ('supplement', '补充框'),
    ]

    INPUT_TYPES = [
        ('input', '输入框'),
        ('select', '下拉框'),
        ('radio', '单选框'),
        ('supplement', '补充框'),
    ]

    VALID_RULES = [
        ('required', '必填'),
        ('requiredReverse', '不必填'),
        ('defaultNull', '默认空值'),
        ('defaultField', '默认字段'),
    ]

    form_config = models.ForeignKey(
        FormConfig,
        on_delete=models.CASCADE,
        related_name='update_items',
        verbose_name="所属表单"
    )
    label = models.CharField(max_length=50, verbose_name="标签")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='text', verbose_name="字段类型")
    binding_key = models.CharField(max_length=50, verbose_name="绑定键")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    input_type = models.CharField(max_length=20, choices=INPUT_TYPES, default='input', verbose_name="输入类型")
    connected_table = models.JSONField(verbose_name="关联表", default=list)
    new_valid_rule = models.CharField(max_length=20, choices=VALID_RULES, default='required',
                                      verbose_name="新值验证规则")
    origin_valid_rule = models.CharField(max_length=20, choices=VALID_RULES, default='required',
                                         verbose_name="原值验证规则")
    origin_default_value = models.CharField(max_length=200, blank=True, verbose_name="原值默认值")
    new_default_value = models.CharField(max_length=200, blank=True, verbose_name="新值默认值")

    # 补充框相关字段
    main_field = models.CharField(max_length=50, blank=True, verbose_name="主字段名")
    sub_fields = models.JSONField(blank=True, default=list, verbose_name="子字段配置")

    # 选项配置（用于 select 和 radio）
    options = models.JSONField(blank=True, default=list, verbose_name="选项配置")

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "更新字段"
        verbose_name_plural = "更新字段"
        unique_together = ['form_config', 'binding_key']

    def __str__(self):
        return f"{self.form_config.form_name} - {self.label}"

