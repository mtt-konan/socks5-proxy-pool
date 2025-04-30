"""
代理服务器基类
"""

import socket
import threading
import select
import time

from proxy_core.utils.logger import get_logger

logger = get_logger('proxy_base')

class ProxyBase:
    """代理服务器基类"""

    def __init__(self, local_host, local_port):
        """初始化代理服务器

        Args:
            local_host: 本地监听主机
            local_port: 本地监听端口
        """
        self.local_host = local_host
        self.local_port = local_port
        self.server_socket = None
        self.running = False

    def start(self):
        """启动代理服务器"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.local_host, self.local_port))
        self.server_socket.listen(100)
        self.running = True

        logger.info(f"代理服务器启动在 {self.local_host}:{self.local_port}")

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

    def stop(self):
        """停止代理服务器"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()

    def handle_client(self, client_socket, client_address):
        """处理客户端连接，子类需要实现此方法"""
        raise NotImplementedError("子类必须实现handle_client方法")

    def forward_data(self, client_socket, remote_socket):
        """在客户端和远程代理之间转发数据"""
        client_socket.setblocking(False)
        remote_socket.setblocking(False)

        try:
            while True:
                # 等待可读取的套接字
                readable, _, exceptional = select.select(
                    [client_socket, remote_socket], [], [client_socket, remote_socket], 60
                )

                if exceptional:
                    break

                for sock in readable:
                    # 从一个套接字读取数据并发送到另一个套接字
                    if sock is client_socket:
                        data = client_socket.recv(4096)
                        if not data:
                            return
                        remote_socket.sendall(data)
                    else:
                        data = remote_socket.recv(4096)
                        if not data:
                            return
                        client_socket.sendall(data)

        except Exception as e:
            logger.error(f"转发数据时出错: {e}")
        finally:
            if not client_socket._closed:
                client_socket.close()
            if not remote_socket._closed:
                remote_socket.close()
