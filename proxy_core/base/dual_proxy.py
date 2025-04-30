"""
双协议代理服务器实现
"""

import socket
import threading
from proxy_core.base.proxy_base import ProxyBase
from proxy_core.handlers.socks5_handler import Socks5Handler
from proxy_core.handlers.http_handler import HttpHandler
from proxy_core.utils.constants import SOCKS_VERSION
from proxy_core.utils.logger import get_logger

logger = get_logger('dual_proxy')

class DualProxy(ProxyBase):
    """同时支持HTTP和SOCKS5协议的代理服务器"""

    def __init__(self, local_host, local_port, remote_host, remote_port, username, password):
        """初始化双协议代理服务器

        Args:
            local_host: 本地监听主机
            local_port: 本地监听端口
            remote_host: 远程代理主机
            remote_port: 远程代理端口
            username: 远程代理用户名
            password: 远程代理密码
        """
        super().__init__(local_host, local_port)
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.username = username
        self.password = password

    def start(self):
        """启动代理服务器"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.local_host, self.local_port))
        self.server_socket.listen(100)
        self.running = True

        logger.info(f"双协议代理服务器启动在 {self.local_host}:{self.local_port}")
        logger.info(f"转发到远程代理 {self.remote_host}:{self.remote_port} (用户: {self.username})")

        try:
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    logger.info(f"接受来自 {client_address} 的连接")

                    # 为每个客户端连接创建一个新线程
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except Exception as e:
                    if self.running:
                        logger.error(f"接受连接时出错: {e}")
                    break
        finally:
            if self.server_socket:
                self.server_socket.close()
                logger.info("代理服务器已关闭")

    def handle_client(self, client_socket, client_address):
        """处理客户端连接，自动检测协议类型"""
        try:
            # 设置超时，以便我们可以检测协议类型
            client_socket.settimeout(5)

            # 读取第一个字节来确定协议类型
            first_byte = client_socket.recv(1, socket.MSG_PEEK)
            if not first_byte:
                logger.error("无法读取客户端数据")
                return

            # 重置超时
            client_socket.settimeout(None)

            # 检查协议类型
            if first_byte[0] == SOCKS_VERSION:
                # SOCKS5协议
                logger.info("检测到SOCKS5协议")
                self.handle_socks5_client(client_socket)
            else:
                # 假设是HTTP协议
                logger.info("检测到HTTP协议")
                self.handle_http_client(client_socket)

        except Exception as e:
            logger.error(f"处理客户端 {client_address} 时出错: {e}")
        finally:
            if not client_socket._closed:
                client_socket.close()

    def handle_socks5_client(self, client_socket):
        """处理SOCKS5客户端连接"""
        try:
            # 处理SOCKS5握手
            if not Socks5Handler.handle_socks5_negotiation(client_socket):
                return

            # 处理SOCKS5请求
            remote_socket = Socks5Handler.handle_socks5_request(client_socket, self.connect_to_remote_socks5_proxy)
            if remote_socket:
                # 开始在客户端和远程代理之间转发数据
                self.forward_data(client_socket, remote_socket)

        except Exception as e:
            logger.error(f"处理SOCKS5客户端时出错: {e}")

    def handle_http_client(self, client_socket):
        """处理HTTP客户端连接"""
        remote_socket = HttpHandler.handle_http_request(client_socket, self.connect_to_remote_socks5_proxy)
        if remote_socket:
            # 开始在客户端和远程代理之间转发数据
            self.forward_data(client_socket, remote_socket)

    def connect_to_remote_socks5_proxy(self, target_addr, target_port):
        """连接到远程SOCKS5代理"""
        return Socks5Handler.connect_to_remote_socks5(
            self.remote_host,
            self.remote_port,
            self.username,
            self.password,
            target_addr,
            target_port
        )

# 为了兼容性，保留原来的Socks5Proxy类名
class Socks5Proxy(DualProxy):
    """兼容原来的Socks5Proxy类"""
    pass
