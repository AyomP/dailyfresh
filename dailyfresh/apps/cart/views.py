from django.shortcuts import render
from django.views.generic import View
from django.http import JsonResponse

from goods.models import GoodsSKU
from utils.mixin import LoginRequireMixin
from django_redis import get_redis_connection
# Create your views here.

# 添加商品到购物车:
# 1）请求方式，采用ajax post
# 如果涉及到数据的修改(新增，更新，删除), 采用post
# 如果只涉及到数据的获取，采用get
# 2) 传递参数: 商品id(sku_id) 商品数量(count)
# ajax发起的请求都在后台，在浏览器中看不到效果


# /cart/add
class CartAddView(View):
    """购物车记录添加视图"""
    def post(self, request):
        """数据接收处理"""
        # 接收数据
        user = request.user
        # 判断用户是否登入
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})
        sku_id = request.POST.get("sku_id")
        count = request.POST.get("count")

        # 数据校验
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})
        # 商品数目格式是否正确
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目格式错误'})
        # 商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 业务处理 数据添加 修改
        # 获取redis链接对象
        conn = get_redis_connection('default')
        cart_key = "cart_%d" % user.id
        # 先尝试获取sku_id的值 -> hget cart_key 属性
        # 如果sku_id在hash中不存在，hget返回None
        cart_count = conn.hget(cart_key, sku_id)
        if cart_count:
            count += int(cart_count)
        # 判断库存是否足够
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '库存不足'})
        # 设置hash中sku_id对应的值
        # hset->如果sku_id已经存在，更新数据， 如果sku_id不存在，添加数据
        conn.hset(cart_key, sku_id, count)

        # 获取购物车中总条目数
        total_count = conn.hlen(cart_key)

        # 应答
        return JsonResponse({'res': 5, 'total_count':total_count, 'message': '记录添加成功'})


# /cart/
class CartInfoView(LoginRequireMixin, View):
    """购物车页面显示"""
    def get(self, request):
        # 从redis数据库中获取数据
        # 获取用户
        user = request.user
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # 获取sku_id count
        cart_dict = conn.hgetall(cart_key)
        skus = []
        total_price = 0
        total_count = 0
        for sku_id, count in cart_dict.items():
            # 获取一种对象
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取一类商品小计
            amount = sku.price*int(count)
            # 为sku动态添加amount 和 count 属性 用于传输给前端
            sku.amount = amount
            sku.count = count
            # 购物车中所有商品种类
            skus.append(sku)
            # 购物车中所有商品数量
            total_count += int(count)
            # 购物车中所有商品价格
            total_price += amount

        # 整理上下文
        context = {
            'total_count': total_count,
            'total_price': total_price,
            'skus': skus
        }
        return render(request, 'cart.html', context)


# 更新购物车商品
# ajax post请求方式
# 接收sku_id 和 count这两个属性
# /cart/update
class CartUpdateView(View):
    """购物车记录更新"""
    def post(self, request):
        # 接收数据
        user = request.user
        # 判断用户是否登入
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})
        sku_id = request.POST.get("sku_id")
        count = request.POST.get("count")

        # 数据校验
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})
        # 商品数目格式是否正确
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目格式错误'})
        # 商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 业务处理 数据添加 修改
        # 获取redis链接对象
        conn = get_redis_connection('default')
        cart_key = "cart_%d" % user.id
        # 判断库存是否足够
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '库存不足'})
        # 业务处理
        # 更新
        conn.hset(cart_key, sku_id, count)

        # 获取购物车中商品总数
        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 5, 'total_count': total_count, 'message': '更新成功'})


# 购物车记录删除
# post请求
# 接收参数：商品ID sku_id
# /cart/delete
class CartDeleteView(View):
    """购物车记录删除"""
    def post(self, request):
        """删除记录"""
        # 判断用户是否登入
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})
        # 接收参数
        sku_id = request.POST.get('sku_id')
        # 校验数据
        if not sku_id:
            return JsonResponse({'res': 1, 'errmsg': '无效ID'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 业务处理
        # 获取redis链接对象
        conn = get_redis_connection('default')
        cart_key = "cart_%d" % user.id
        # 删除数据库中商品
        conn.hdel(cart_key, sku_id)

        # 获取当前购物车中商品件数
        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 3, 'total_count': total_count, 'message': '删除成功'})
