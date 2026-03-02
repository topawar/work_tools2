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
