from django.db import models
from django.contrib.auth.models import AbstractUser
from db.base_model import BaseModel
# Create your models here.


class User(AbstractUser, BaseModel):
    """用户模型类"""

    class Meta:
        db_table = 'df_user'
        verbose_name = '用户'
        verbose_name_plural = verbose_name


# 定义自定义模型管理器
class AddressManager(models.Manager):
    """模型管理器类"""
    # 改变原有查询结果集 (如 all()方法)
    # 封装对数据表操作的方法
    def get_default_address(self, user):
        """获得默认收获地址"""
        # 获得当前使用了当前对象的类也就是objects所在的类
        # self.model = Address Address.objects = AddressManager()
        # self.model.objects = AddressManager() = self
        try:
            address = self.get(user=user, is_default=True)
        except Address.DoesNotExist:
            # 没有默认地址
            address = None
        return address


class Address(BaseModel):
    """地址模型类"""
    user = models.ForeignKey('User', verbose_name='所属账户')
    receiver = models.CharField(max_length=20, verbose_name='收件人')
    addr = models.CharField(max_length=256, verbose_name='收件地址')
    zip_code = models.CharField(max_length=6, null=True, verbose_name='邮政编码')
    phone = models.CharField(max_length=11, verbose_name='联系电话')
    is_default = models.BooleanField(default=False, verbose_name='是否默认')

    objects = AddressManager()

    class Meta:
        db_table = 'df_address'
        verbose_name = '地址'
        verbose_name_plural = verbose_name
