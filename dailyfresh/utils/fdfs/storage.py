from django.core.files.storage import Storage
from django.conf import settings
from fdfs_client.client import Fdfs_client


class FDFSStorage(Storage):
    """fast dfs 文件储存类"""

    def __init__(self, client_conf=None, base_url=None):
        """初始化"""
        if client_conf is None:
            # 默认配置
            client_conf = settings.FDFS_CLIENT_CONF
        self.client_conf = client_conf

        if base_url is None:
            # 默认地址
            base_url = settings.FDFS_URL
        self.base_url = base_url

    def _open(self, name, mode='rb'):
        """打开文件时使用"""
        pass

    def _save(self, name, content):
        """上传/保存 文件时使用"""
        # name: 存储的文件名
        # content: 文件内容并且是一个File因此可以用方法对他进行读取
        # 获取一个 Fdfs_client对象用于和fast dfs交互
        client = Fdfs_client(self.client_conf)

        # 读取content对象的文件内容并通过Fdfs_client对象的upload_by_buffer进行文件内容上传
        # upload_by_buffer
        res = client.upload_by_buffer(content.read())

        # res返回的对象是一个dict 内容如下
        # dict
        # {
        #     'Group name': group_name,
        #     'Remote file_id': remote_file_id,
        #     'Status': 'Upload successed.',
        #     'Local file name': '',
        #     'Uploaded size': upload_size,
        #     'Storage IP': storage_ip
        # }

        if res.get('Status') != 'Upload successed.':
            # 上传失败 抛出异常
            raise Exception('上传失败')

        # 获取fast dfs的返回值中的用于之后链接的Remote file_id
        filename = res.get('Remote file_id')

        # 该类通常需要返回一个文件名
        return filename

    def exists(self, name):
        """判断文件名是否存在"""
        return False

    def url(self, name):
        """返回访问文件的url地址"""
        # name 等于此时fdfs返回的那串值
        return self.base_url + name + '.jpg'



