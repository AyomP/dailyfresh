from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.http import HttpResponse
from django_redis import get_redis_connection

from utils.mixin import LoginRequireMixin
from user.models import User, Address
from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods

from celery_tasks.tasks import send_register_active_email
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
import re
# Create your views here.


# /user/register
# GET POST DELETE OPTION PUT
def register(request):
    """注册"""
    # 判断请求方式
    if request.method == 'GET':
        return render(request, 'register.html')
    else:
        # POST请求 进行数据处理
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')
        # 进行数据校验
        # 验证数据是否完整
        if not all([username, password, email]):
            return render(request, 'register.html', {'errmsg': '数据不完整'})

        # 进行邮箱认证
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式错误'})

        # 用户同意协议是否勾选
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请勾选用户协议'})
        # 判断用户名是否已经存在
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户已经存在
            user = None

        if user:
            return render(request, 'register.html', {'errmsg': '该用户名已存在'})

        # 进行业务处理: 添加用户 admin用户管理器自带方法create_user
        user = User.objects.create_user(username=username, password=password, email=email)
        user.is_active = 0
        user.save()
        # 返回应答
        return redirect(reverse('goods:index'))


# /user/register_handle
def register_handle(request):
    """进行注册处理"""
    # 接收数据
    username = request.POST.get('user_name')
    password = request.POST.get('pwd')
    email = request.POST.get('email')
    allow = request.POST.get('allow')
    # 进行数据校验
    # 验证数据是否完整
    if not all([username, password, email]):
        return render(request, 'register.html', {'errmsg': '数据不完整'})

    # 进行邮箱认证
    if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
        return render(request, 'register.html', {'errmsg': '邮箱格式错误'})

    # 用户同意协议是否勾选
    if allow != 'on':
        return render(request, 'register.html', {'errmsg': '请勾选用户协议'})
    # 判断用户名是否已经存在
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        # 用户已经存在
        user = None

    if user:
        return render(request, 'register.html', {'errmsg': '该用户名已存在'})

    # 进行业务处理: 添加用户
    user = User.objects.create_user(username=username, password=password, email=email)
    user.is_active = 0
    user.save()
    # 返回应答
    return redirect(reverse('goods:index'))


# /user/register
class RegisterView(View):
    """注册"""
    def get(self, request):
        """显示注册界面"""
        return render(request, 'register.html')

    def post(self, request):
        """响应注册请求"""
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')
        # 进行数据校验
        # 验证数据是否完整
        if not all([username, password, email]):
            return render(request, 'register.html', {'errmsg': '数据不完整'})

        # 进行邮箱认证
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式错误'})

        # 用户同意协议是否勾选
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请勾选用户协议'})
        # 判断用户名是否已经存在
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户已经存在
            user = None

        if user:
            return render(request, 'register.html', {'errmsg': '该用户名已存在'})

        # 进行业务处理: 添加用户
        user = User.objects.create_user(username=username, password=password, email=email)
        user.is_active = 0
        user.save()

        # 发送激活邮件 邮件需要标识用户 因此需要在激活添加用户信息
        # 为了网站稳定需要对用户信息进行加密处理(http//127.0.0.1:8000/user/action/用户加密的信息）
        # 加密用户身份信息，生成激活token
        serializer = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm': user.id}
        token = serializer.dumps(info)  # bytes数据 需要解码
        token = token.decode()

        # 发邮件 Celery中的任务发起者
        send_register_active_email.delay(email, username, token)
        # 返回应答
        return redirect(reverse('goods:index'))


# /user/Active/密文
class ActiveView(View):
    """用户激活"""
    def get(self, request, token):
        """进行激活处理"""
        serializer = Serializer(settings.SECRET_KEY, 3600)
        # 判断激活邮件是否过期，若过期会抛出异常，不进行用户数据获取
        try:
            # 进行解密获取用户信息
            info = serializer.loads(token.encode())
            # 获得对应信息
            user_id = info['confirm']
            # 获取数据库中对应的对象
            user = User.objects.get(id=user_id)
            # 激活邮件
            user.is_active = 1
            user.save()
            # 转到登入界面
            return redirect(reverse('user:login'))
        except SignatureExpired as e:
            # 邮件过期 返回一个邮件过期消息（实际项目需再返回一个处理界面）
            return HttpResponse("激活链接已过期")


# /user/login
class LoginView(View):
    """登录"""
    def get(self, request):
        """显示登录界面"""
        # 判断是否记住了用户名
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            checked = 'checked'
        else:
            username = ''
            checked = ''
        return render(request, 'login.html', {'username': username, 'checked': checked})

    def post(self, request):
        """进行登录处理"""
        # 接收数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')
        # 数据校验
        if not all([username, password]):
            # 数据不完整
            return render(request, 'login.html', {'errmsg': '数据不完整'})

        # 登录校验
        user = authenticate(username=username, password=password)
        if user is not None:
            # 用户已注册
            if user.is_active:
                # 用户已激活
                # 设置session用于后续要登录才能进入的界面
                login(request, user)
                # 获取需要跳转到的界面 默认跳转到首页
                next_url = request.GET.get('next', reverse('goods:index'))
                # 返回跳转页面
                response = redirect(next_url)
                # 判断是否需要记住用户名
                remember = request.POST.get('remember')
                if remember == 'on':
                    response.set_cookie('username', username, max_age=7*3600*24)
                else:
                    response.delete_cookie('username')
                return response

            else:
                # 用户未激活
                return render(request, 'login.html', {'errmsg': '用户未激活'})
        else:
            # 该用户未注册
            return render(request, 'login.html', {'errmsg': '用户名或密码错误'})


# /user/logout
class LogoutView(View):
    """用户退出登入"""
    def get(self, request):
        """注销"""
        # 清除当前保存的session值
        logout(request)
        # 返回到首页
        return render(request, 'index.html')


# /user
class UserInfoView(LoginRequireMixin, View):
    """用户中心-信息页"""
    def get(self, request):
        """显示"""
        # 用于选择此时html元素谁处于active状态
        page = 'user'

        # 当访问Django网站时Django会自动生成一个request.user对象
        # 当用户处于未登入状态时会产生一个AnonymousUser对象并将它传给模板文件
        # 当用户处于登陆状态时会产生一个User类的实例并将它传给模板文件
        # is_authenticated()方法对应未登陆的对象返回False 因此可用于判断是否登入

        user = request.user
        # 获取当前对象默认地址信息
        address = Address.objects.get_default_address(user)

        # 设置历史浏览记录
        # 获取用于存储数据的数据库
        conn = get_redis_connection('default')
        # 获取数据库中的数据 一个用户对应一条数据
        history_key = 'history_%s' % user.id
        # 获取数据库中靠前的5条数据的商品的ID列表
        sku_ids = conn.lrange(history_key, 0, 4)
        goods_li = []
        for good_id in sku_ids:
            goods = GoodsSKU.objects.get(id=good_id)
            goods_li.append(goods)

        # 定义上下文
        context = {
            'page': page,  # 用于显示当前那个html元素处于active
            'address': address,  # 当前默认地址
            'goods_li': goods_li  # 历史浏览记录中前五记录

        }

        return render(request, 'user_center_info.html', context)


# /user/order
class UserOrderView(LoginRequireMixin, View):
        """用户中心-订单页"""

        def get(self, request, page):
            user = request.user
            orders = OrderInfo.objects.filter(user=user).order_by('-create_time')

            # 获取订单信息
            for order in orders:
                # 根据order_id查询订单商品信息
                order_skus = OrderGoods.objects.filter(order_id=order.order_id)
                for order_sku in order_skus:
                    # 计算小计
                    amount = order_sku.count * order_sku.price
                    # 动态给order_sku增加属性amount,保存订单商品的小计
                    order_sku.amount = amount

                    # 动态给order增加属性，保存订单状态标题
                order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
                # 动态给order增加属性，保存订单商品的信息
                order.order_skus = order_skus

            # 分页
            paginator = Paginator(orders, 3)

            # 获取第page页的内容
            try:
                page = int(page)
            except Exception as e:
                page = 1

            if page > paginator.num_pages:
                page = 1

            # 获取第page页的Page实例对象
            order_page = paginator.page(page)

            # todo: 进行页码的控制，页面上最多显示5个页码
            # 1.总页数小于5页，页面上显示所有页码
            # 2.如果当前页是前3页，显示1-5页
            # 3.如果当前页是后3页，显示后5页
            # 4.其他情况，显示当前页的前2页，当前页，当前页的后2页
            num_pages = paginator.num_pages
            if num_pages < 5:
                pages = range(1, num_pages + 1)
            elif page <= 3:
                pages = range(1, 6)
            elif num_pages - page <= 2:
                pages = range(num_pages - 4, num_pages + 1)
            else:
                pages = range(page - 2, page + 3)

            # 组织上下文
            context = {'order_page': order_page,
                       'pages': pages,
                       'page': 'order'}

            # 使用模板
            return render(request, 'user_center_order.html', context)


# /user/address
class AddressView(LoginRequireMixin, View):
    """用户中心-地址页"""
    def get(self, request):
        page = 'address'
        user = request.user
        # 获取默认地址信息
        address = Address.objects.get_default_address(user)

        return render(request, 'user_center_site.html', {'page': page, 'address': address})

    def post(self, request):
        """添加地址信息请求"""
        # 接收数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')
        # 校验数据
        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html', {'errmsg': '数据不完整'})

        if not re.match(r'^1((3[\d])|(4[75])|(5[^3|4])|(66)|(7[013678])|(8[\d])|(9[89]))\d{8}$', phone):
            return render(request, 'user_center_site.html', {'errmsg': '手机格式错误'})
        # 处理数据
        # 获取当前用户信息
        user = request.user
        # 获取默认地址信息
        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        # 通过Address模型对象往数据库添加一条信息
        Address.objects.create(
            user=user,
            receiver=receiver,
            addr=addr,
            zip_code=zip_code,
            phone=phone,
            is_default=is_default
        )

        # 应答 （本次应答为刷新当前界面get请求）
        return redirect(reverse('user:address'))





