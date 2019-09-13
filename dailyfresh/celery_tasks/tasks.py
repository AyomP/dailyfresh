"""使用celery"""
from celery import Celery
from django.conf import settings
from django.template import loader, RequestContext
from django.core.mail import send_mail

# 以下注释在任务者端打开
import os
# import django
#
# # 初始化
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dailyfresh.settings")
# django.setup()
#                        商品类型表  轮播商品表          活动信息表            展示用的商品表
from goods.models import GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner
from django_redis import get_redis_connection

# 配置任务中间人 中间人 将数据通过redis 8号数据库设置成监听点
app = Celery('celery_tasks.tasks', broker='redis://127.0.0.1:6379/8')

# 定义任务函数


# 将以下方法装饰成 Celery中的worker
@app.task
def send_register_active_email(to_email, username, token):
    """发送激活邮件"""
    # email标题
    subject = '天天生鲜欢迎信息'
    # 邮件正文
    message = ''
    # 发送人
    sender = settings.EMAIL_FROM
    # 收件人列表
    receiver = [to_email]
    # 带有html标签格式的内容
    html_message = '<h1>恭喜%s成为我们天天生鲜注册会员</h1><br/>' \
                   '<a href="http://127.0.0.1:8000/user/active/%s">' \
                   'http://127.0.0.1:8000/user/active/%s</a>' % (username, token, token)
    send_mail(subject, message, sender, receiver, html_message=html_message)


@app.task
def generate_static_index_html():
    """产生首页静态页面"""
    # 静态页面存在元素如下
    # 1.商品种类 2.各种类的展示商品 3.轮播图 4.活动图
    # 获取首页左侧的商品分类信息，该类信息存在商品种类表(df_goods_type)中
    # ，需要使用GoodsType来获得信息
    # 获取商品种类信息
    types = GoodsType.objects.all()
    # 获取首页顶部中心部分轮播图信息，使用到IndexGoodsBanner来操控并且根据index属性进行排序
    goods_banners = IndexGoodsBanner.objects.all().order_by('index')
    # 获取首页顶部右侧促销活动信息图，需要使用到IndexPromotionBanner同样更加index循序显示
    promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

    # 获取分类商品中的的各个种类的商品信息(用于展示)
    for type in types:
        # 获取各个种类的具体商品的信息 type表示一种商品
        # 筛选出type类的以图片在首页显示的商品
        image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
        # 筛选出type类的以文字标题在首页显示的商品
        title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')

        # 动态给type增加属性，分别保存首页分类商品的图片展示信息和文字展示信息
        # 给商品添加要在首页显示的商品的属性（添加展示物品属性）
        # 动态在于使用时添加，可变，展示商品变了，这属性也随之改变
        type.image_banners = image_banners
        type.title_banners = title_banners

    # 组织模板上下文
    context = {'types': types,  # 商品种类
               'goods_banners': goods_banners,  # 轮播商品信息
               'promotion_banners': promotion_banners,  # 促销活动商品信息
               }

    # 使用模板
    # 1.加载模板文件,返回模板对象
    temp = loader.get_template('static_index.html')
    # 2.模板渲染
    static_index_html = temp.render(context)

    # 生成首页对应静态文件
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    # save_path = 'D:\\Nginx\\nginx-1.6.3\\html'
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(static_index_html)

