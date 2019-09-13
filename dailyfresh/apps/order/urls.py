from django.conf.urls import url
from order.views import OrderPlaceView, OrderCommitView, OrderPayView, PayCheckView, CommentView, DetailPlaceView

urlpatterns = [
   url(r'^place$', OrderPlaceView.as_view(), name='place'),  # 提交订单页面显示
   url(r'^detail/place$', DetailPlaceView.as_view(), name='detail_place'),  # 详情页提交订单页面显示
   url(r'^commit$', OrderCommitView.as_view(), name='commit'),  # 订单创建
   url(r'^pay$', OrderPayView.as_view(), name='pay'),  # 订单支付
   url(r'^check$', PayCheckView.as_view(), name='check'),  # 交易查询
   url(r'^comment/(?P<order_id>.+)$', CommentView.as_view(), name='comment'),  # 订单评论
]
