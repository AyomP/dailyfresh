from django.contrib.auth.decorators import login_required


# 实现过程 url配置中调用的as_view先调用多继承中的第一个父类LoginRequireMixin的方法
# 在父类方法中又调用了as_view方法此时就会去调用第二个父类的方法也就是View中的原先的定义好的方法
# 掉完之后返回一个as_view的配置url对象，最后返回一个用login_required包装过的能实现登陆验证的as_view方法
class LoginRequireMixin(object):
    """判断是否登入，未登入访问不了"""
    # 调用父类中的as_view方法
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(LoginRequireMixin, cls).as_view(**initkwargs)
        # 包装as_view 登入则返回正确的url 否则返回setting中配置的url
        return login_required(view)


