from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.core.cache import cache
from django.core.paginator import Paginator
from goods.models import GoodsType, GoodsSKU, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner
from order.models import OrderGoods
from django_redis import get_redis_connection
# Create your views here.


# http://127.0.0.1:8000/index
class IndexView(View):
    """首页"""

    # 收到get请求时
    def get(self, request):
        """get请求 显示首页"""
        # 判断是否有缓存
        context = cache.get('index_page_data')
        if context is None:
            print('设置缓存')
            # 获取首页左侧的商品分类信息，该类信息存在商品种类表(df_goods_type)中
            # ，需要使用GoodsType来获得信息
            # 获取商品种类信息
            types = GoodsType.objects.all()
            # 获取首页顶部中心部分轮播图信息，使用到IndexGoodsBanner来操控并且根据index属性进行排序
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')
            # 获取首页顶部右侧促销活动信息图，需要使用到IndexPromotionBanner同样更加index循序显示
            promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

            # 获取分类商品中的的各个种类的商品信息
            for type in types:
                # 获取各个种类的具体商品的信息 type表示一种商品
                # 筛选出type类的以图片在首页显示的商品
                image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
                # 筛选出type类的以文字标题在首页显示的商品
                title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')

                # 动态给type增加属性，分别保存首页分类商品的图片展示信息和文字展示信息
                # 给商品添加要在首页显示的商品的属性
                # 动态在于使用时添加，可变
                type.image_banners = image_banners
                type.title_banners = title_banners

            context = {'types': types,  # 商品种类
                       'goods_banners': goods_banners,  # 轮播商品信息
                       'promotion_banners': promotion_banners,  # 促销活动商品信息
                       }
            # 设置缓存 key value timeout
            cache.set('index_page_data', context, 3600)

        # 获取用户购物车中商品的数目
        # 获取访问对象
        user = request.user
        # 默认为0
        cart_count = 0
        # 判断是否登录
        if user.is_authenticated():
            # 用户已登录
            # 链接redis数据库存
            conn = get_redis_connection('default')
            # 获取当前用户在数据在数据库存放时用到键 假设为用户id
            cart_key = 'cart_%d' % user.id
            # 获取数据 hlen获取数据库中的key对应的全部数据 返回一个总条数值(类别值 不是总数量值)
            # cart_count 表示添加了几种商品
            cart_count = conn.hlen(cart_key)

        # 组织模板上下文
        context.update(cart_count=cart_count)

        # 使用模板
        return render(request, 'index.html', context)


# goods/good_id
class DetailView(View):
    """详情页"""
    def get(self, request, goods_id):
        """显示详情页"""
        # 获取对应商品的sku, 用于提供商品详细信息
        try:
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            return redirect(reverse('goods:index'))

        # 获取分类商品信息
        types = GoodsType.objects.all()

        # 获取商品评论
        # 先获取购买了的客户
        sku_orders = OrderGoods.objects.filter(sku=sku).exclude(comment='')

        # 获取同一类型商品的新品信息
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')[:2]

        # 获取同一种spu商品信息的sku
        same_spu_skus = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)
        # 获取用户购物车中商品的数目
        # 获取访问对象
        user = request.user
        # 默认为0
        cart_count = 0
        # 判断是否登录
        if user.is_authenticated():
            # 用户已登录
            # 链接redis数据库存
            conn = get_redis_connection('default')
            # 获取当前用户在数据在数据库存放时用到键 假设为用户id
            cart_key = 'cart_%d' % user.id
            # 获取数据 hlen获取数据库中的key对应的全部数据 返回一个总条数值(类别值 不是总数量值)
            # cart_count 表示添加了几种商品
            cart_count = conn.hlen(cart_key)

            # 添加用户历史浏览记录
            # 获取操作数据库的对象
            conn = get_redis_connection('default')
            # 用户在数据库中的键
            history_key = 'history_%d' % user.id
            # 清空当前数据库已存在的和当前访问对象一样的数据
            conn.lrem(history_key, 0, goods_id)
            # 从右侧插入
            conn.lpush(history_key, goods_id)
            # 裁剪数据库长度，留下五个数据
            conn.ltrim(history_key, 0, 4)

        context = {
            'sku': sku,
            'types': types,
            'sku_orders': sku_orders,
            'new_skus': new_skus,
            'cart_count': cart_count,
            'same_spu_skus': same_spu_skus
        }

        return render(request, 'detail.html', context)


# /list/种类_id/页码?sort=排序方式
class ListView(View):
    """列表页"""
    def get(self, request, type_id, page):
        """显示列表页"""
        # 获取要显示的种类ID
        try:
            type = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            # 种类不存在
            return redirect(reverse('good:index'))

        # 获取分类信息数据
        types = GoodsType.objects.all()

        # 获取要显示的排序方式
        sort = request.GET.get('sort')
        if sort == 'hot':  # 热度
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')
        elif sort == 'price':  # 价格
            skus = GoodsSKU.objects.filter(type=type).order_by('price')
        else:  # 默认按商品id排序
            sort = 'default'
            skus = GoodsSKU.objects.filter(type=type).order_by('-id')

        # 分页显示  1:表示每页显示条数
        paginator = Paginator(skus, 3)

        # 获取当前页码
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        # 获取第page页的实例对象 对象拥有sku对象一样的属性
        skus_page = paginator.page(page)

        #
        # 当前总页数
        num_pages = paginator.num_pages

        if num_pages < 5:
            # 总页数小于5 显示全部
            pages = range(1, num_pages+1)
        elif page <= 3:
            # 当处于前三页时 显示1-5页
            pages = range(1, 6)
        elif page >= num_pages-2:
            # 当处于后三页时 显示后五页
            pages = range(num_pages-4, num_pages+1)
        else:
            # 其他情况显示当前页前两页和后两页
            pages = range(page-2, page+3)

        # 获取同一类型商品的新品信息
        new_skus = GoodsSKU.objects.filter(type=type).order_by('-create_time')[:2]

        # 获取用户购物车中商品的数目
        # 获取访问对象
        user = request.user
        # 默认为0
        cart_count = 0
        # 判断是否登录
        if user.is_authenticated():
            # 用户已登录
            # 链接redis数据库存
            conn = get_redis_connection('default')
            # 获取当前用户在数据在数据库存放时用到键 假设为用户id
            cart_key = 'cart_%d' % user.id
            # 获取数据 hlen获取数据库中的key对应的全部数据 返回一个总条数值(类别值 不是总数量值)
            # cart_count 表示添加了几种商品
            cart_count = conn.hlen(cart_key)

        context = {
            'type': type,
            'types': types,
            'skus_page': skus_page,
            'new_skus': new_skus,
            'cart_count': cart_count,
            'sort': sort,
            'pages': pages
        }

        return render(request, 'list.html', context)
