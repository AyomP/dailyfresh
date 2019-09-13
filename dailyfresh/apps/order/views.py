from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.http import JsonResponse
from django.db import transaction
from django.conf import settings
from django.views.generic import View

from user.models import Address
from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods

from django_redis import get_redis_connection
from utils.mixin import LoginRequireMixin
from datetime import datetime
from alipay import AliPay
import os
# Create your views here.


# /order/place
class OrderPlaceView(LoginRequireMixin, View):
    """提交订单页面显示"""

    def post(self, request):
        """提交订单页面显示"""
        # 获取登录的用户
        user = request.user
        # 获取参数sku_ids （来自cart.html中的表单）
        # request.POST.getlist（'sku_ids'）接收post请求中的name='sku_ids'的value并组成一个列表
        sku_ids = request.POST.getlist('sku_ids')  # [1,26]

        # 校验参数
        if not sku_ids:
            # 跳转到购物车页面
            return redirect(reverse('cart:show'))

        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        skus = []
        # 保存商品的总件数和总价格
        total_count = 0
        total_price = 0
        # 遍历sku_ids获取用户要购买的商品的信息
        for sku_id in sku_ids:
            # 根据商品的id获取商品的信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取用户所要购买的商品的数量
            count = conn.hget(cart_key, sku_id)
            # 计算商品的小计
            amount = sku.price*int(count)
            # 动态给sku增加属性count,保存购买商品的数量
            sku.count = count
            # 动态给sku增加属性amount,保存购买商品的小计
            sku.amount = amount
            # 追加
            skus.append(sku)
            # 累加计算商品的总件数和总价格
            total_count += int(count)
            total_price += amount

        # 运费:实际开发的时候，属于一个子系统
        transit_price = 10  # 写死

        # 实付款
        total_pay = total_price + transit_price

        # 获取用户的收件地址
        addrs = Address.objects.filter(user=user)

        # 组织上下文
        sku_ids = ','.join(sku_ids)  # [1,25]->1,25
        context = {'skus': skus,
                   'total_count': total_count,
                   'total_price': total_price,
                   'transit_price': transit_price,
                   'total_pay': total_pay,
                   'addrs': addrs,
                   'sku_ids': sku_ids}

        # 使用模板
        return render(request, 'place_order.html', context)


# /order/detail/place
class DetailPlaceView(LoginRequireMixin, View):
    """详情页直接提交订单页面显示"""

    def post(self, request):
        """提交订单页面显示"""
        # 获取登录的用户
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        # 获取参数sku_ids （来自cart.html中的表单）
        # request.POST.getlist（'sku_ids'）接收post请求中的name='sku_ids'的value并组成一个列表
        sku_id = request.POST.get('sku_id')  # [1,26]
        count = request.POST.get('count')

        # 校验参数
        if not all([sku_id, count]):
            # 跳转到购物车页面
            return redirect(reverse('goods:detail'))

        skus = []

        # 根据商品的id获取商品的信息
        sku = GoodsSKU.objects.get(id=sku_id)
        # 计算商品的小计
        amount = sku.price*int(count)
        # 动态给sku增加属性count,保存购买商品的数量
        sku.count = count
        # 动态给sku增加属性amount,保存购买商品的小计
        sku.amount = amount
        # 追加
        skus.append(sku)
        # 保存商品的总件数和总价格
        total_count = int(count)
        total_price = amount

        # 运费:实际开发的时候，属于一个子系统
        transit_price = 10  # 写死

        # 实付款
        total_pay = total_price + transit_price

        # 获取用户的收件地址
        addrs = Address.objects.filter(user=user)

        # 组织上下文
        context = {'skus': skus,
                   'total_count': total_count,
                   'total_price': total_price,
                   'transit_price': transit_price,
                   'total_pay': total_pay,
                   'addrs': addrs,
                   'sku_ids': sku_id}

        # 使用模板
        return render(request, 'place_order.html', context)

# /order/commit
# 前端传递的参数:地址id(addr_id) 支付方式(pay_method) 用户要购买的商品id字符串(sku_ids)
# mysql事务: 一组sql操作，要么都成功，要么都失败
# 高并发:秒杀
# 支付宝支付
class OrderCommitView1(View):  # 悲观锁
    """订单创建"""
    # @transaction.atomic 以下对数据库的操作都在一个事务中
    @transaction.atomic
    def post(self, request):
        """订单创建"""
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')  # 1,3

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '参数不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法的支付方式'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 3, 'errmsg': '地址非法'})

        # todo: 创建订单核心业务

        # 组织参数
        # 订单id: 20190908104330+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S')+str(user.id)

        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()
        try:
            # todo: 向df_order_info表中添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)

            # todo: 用户的订单中有几个商品，需要向df_order_goods表中加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                # 获取商品的信息
                try:
                    # select * from df_goods_sku where id=sku_id for update;
                    # for update 查询并且加锁 处理并发
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except:
                    # 商品不存在
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                print('user:%d stock:%d' % (user.id, sku.stock))
                import time
                time.sleep(10)

                # 从redis中获取用户所要购买的商品的数量
                count = conn.hget(cart_key, sku_id)

                # todo: 判断商品的库存
                if int(count) > sku.stock:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                # todo: 向df_order_goods表中添加一条记录
                OrderGoods.objects.create(order=order,
                                          sku=sku,
                                          count=count,
                                          price=sku.price)

                # todo: 更新商品的库存和销量 （悲观锁）
                sku.stock -= int(count)
                sku.sales += int(count)
                # .save()将模型类对象保存进数据库
                sku.save()

                # todo: 累加计算订单商品的总数量和总价格
                amount = sku.price*int(count)
                total_count += int(count)
                total_price += amount

            # todo: 更新订单信息表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单失败'})

        # 提交事务
        transaction.savepoint_commit(save_id)

        # todo: 清除用户购物车中对应的记录
        # *[] 将列表拆包
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({'res': 5, 'message': '创建成功'})


class OrderCommitView(View):  # 乐观锁
    """订单创建"""
    # @transaction.atomic 以下对数据库的操作都在一个事务中
    @transaction.atomic
    def post(self, request):
        """订单创建"""
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')  # 1,3

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '参数不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法的支付方式'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 3, 'errmsg': '地址非法'})

        # todo: 创建订单核心业务

        # 组织参数
        # 订单id: 20190908104330+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S')+str(user.id)

        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()
        try:
            # todo: 向df_order_info表中添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)

            # todo: 用户的订单中有几个商品，需要向df_order_goods表中加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                for i in range(3):
                    # 获取商品的信息
                    try:
                        # select * from df_goods_sku where id=sku_id for update;
                        # for update 查询并且加锁 处理并发
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except:
                        # 商品不存在
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                    # print('user:%d stock:%d' % (user.id, sku.stock))
                    # import time
                    # time.sleep(10)

                    # 从redis中获取用户所要购买的商品的数量
                    try:
                        count = conn.hget(cart_key, sku_id)
                        if count is None:
                            # 默认获取为空时 当前采用直接购买方式
                            count = request.POST.get('count')
                    except:
                        return JsonResponse({'res': 6, 'errmsg': '购买商品数获取失败'})

                    # todo: 判断商品的库存
                    if int(count) > sku.stock:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 7, 'errmsg': '商品库存不足'})

                    # todo: 更新商品的库存和销量 （乐观锁）
                    origin_stock = sku.stock
                    now_stock = origin_stock - int(count)
                    now_sales = sku.sales + int(count)

                    # 查询数据库 返回受影响row数 0更新失败，1更新成功
                    res = GoodsSKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=now_stock, sales=now_sales)
                    if res == 0:
                        if i == 2:
                            # 第三次查询失败
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 8, 'errmsg': '下单失败'})
                        # 再次尝试
                        continue

                    # todo: 向df_order_goods表中添加一条记录
                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=count,
                                              price=sku.price)

                    # todo: 累加计算订单商品的总数量和总价格
                    amount = sku.price*int(count)
                    total_count += int(count)
                    total_price += amount
                    # 修改完成，退出循环
                    break

            # todo: 更新订单信息表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 9, 'errmsg': '下单失败'})

        # 提交事务
        transaction.savepoint_commit(save_id)

        # todo: 清除用户购物车中对应的记录
        # *[] 将列表拆包
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({'res': 5, 'message': '创建'})


# Ajax POST请求
# /order/pay
class OrderPayView(View):
    """订单支付"""
    def post(self, request):
        """接收订单支付的post请求"""
        # 用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # todo 业务处理

        # 对接支付宝
        # 初始化支付宝对象
        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        alipay = AliPay(
            appid="2016101400683431",  # 应用id
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False
        )

        total_pay = order.total_price+order.transit_price
        # 支付处理
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,
            total_amount=str(total_pay),
            subject='天天生鲜{}'.format(order_id),
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        # 返回应答
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res': 3, 'pay_url': pay_url})


# Ajax POST请求 传递参数 order_id
# /order/check
class PayCheckView(View):
    """交易结果查询"""
    def post(self, request):
        """交易结果查询"""
        # 用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # todo 业务处理

        # 对接支付宝
        # 初始化支付宝对象
        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        alipay = AliPay(
            appid="2016101400683431",  # 应用id
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False
        )

        while True:
            # 调用alipay的api_alipay_trade_query接口获取交易结果
            response = alipay.api_alipay_trade_query(out_trade_no=order_id)
            # response = {
            #         "trade_no": "2017032121001004070200176844",  # 支付宝交易号
            #         "code": "10000",  # API状态码
            #         "invoice_amount": "20.00",
            #         "open_id": "20880072506750308812798160715407",
            #         "fund_bill_list": [
            #             {
            #                 "amount": "20.00",
            #                 "fund_channel": "ALIPAYACCOUNT"
            #             }
            #         ],
            #         "buyer_logon_id": "csq***@sandbox.com",
            #         "send_pay_date": "2017-03-21 13:29:17",
            #         "receipt_amount": "20.00",
            #         "out_trade_no": "out_trade_no15",
            #         "buyer_pay_amount": "20.00",
            #         "buyer_user_id": "2088102169481075",
            #         "msg": "Success",
            #         "point_amount": "0.00",
            #         "trade_status": "TRADE_SUCCESS",  # 交易结果
            #         "total_amount": "20.00"
            #     }

            if response.get('code') == '10000' and response.get('trade_status') == 'TRADE_SUCCESS':
                # 交易成功
                # 获取交易号
                trade_no = response.get('trade_no')

                # 订单状态改变
                order.trade_no = trade_no
                order.order_status = 4
                order.save()

                return JsonResponse({'res': 3, 'message': '支付成功'})

            elif response.get('code') == '40004' or (response.get('code') == '10000' and response.get('trade_status') == 'WAIT_BUYER_PAY'):
                # 订单创建 但未支付
                # 40004 表示当时业务处理失败， 但之后可以成功
                import time
                time.sleep(5)
                continue
            else:
                # 订单创建失败
                return JsonResponse({'res': 4, 'errmsg': '支付失败'})


# POST请求 传输参数order_id
# /order/comment/order_id
class CommentView(View, LoginRequireMixin):
    """订单评论"""
    def get(self, request, order_id):
        """订单评论页面显示"""
        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user
                                          )
        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order'))

        # 获取信息
        # 根据订单的状态获取订单的状态标题,并且动态链接到order上
        order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

        # 获取order中的sku
        order_skus = OrderGoods.objects.filter(order_id=order_id)
        for order_sku in order_skus:
            # 计算商品的小计
            amount = order_sku.count * order_sku.price
            # 动态给order_sku增加属性amount,保存商品小计
            order_sku.amount = amount
        # 动态给order增加属性order_skus, 保存订单商品信息
        order.order_skus = order_skus

        # 使用模板
        return render(request, "order_comment.html", {"order": order})

    def post(self, request, order_id):
        """表单提交的评价"""
        user = request.user
        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order"))

        # 获取评论条数
        total_count = request.POST.get("total_count")
        total_count = int(total_count)

        for i in range(1, total_count+1):
            sku_id = request.POST.get('sku_{}'.format(i))
            content = request.POST.get('content_{}'.format(i))
            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue
            order_goods.comment = content
            order_goods.save()

        order.order_status = 5  # 已完成
        order.save()

        return redirect(reverse("user:order", kwargs={"page": 1}))

