"""
代理Web服务器
"""

import http.server
import socketserver
import threading
import os
import signal
import sys
import time
import argparse
from proxy_core.web.request_handlers import ProxyHandler
from proxy_core.utils.logger import get_logger

logger = get_logger('web_server')

class ProxyServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """代理Web服务器"""

    def __init__(self, server_address, RequestHandlerClass, proxy_pool):
        """初始化服务器"""
        self.proxy_pool = proxy_pool
        super().__init__(server_address, RequestHandlerClass)


def run_server(host='127.0.0.1', port=7777, proxy_pool=None):
    """运行代理Web服务器

    Args:
        host: Web服务器主机地址
        port: Web服务器端口
        proxy_pool: 代理池实例
    """
    if proxy_pool is None:
        logger.error("未提供代理池实例")
        return

    # 创建并启动Web服务器
    server = ProxyServer((host, port), ProxyHandler, proxy_pool)

    # 设置信号处理，以便优雅地关闭服务器
    def signal_handler(sig, frame):
        logger.info("接收到中断信号，正在关闭服务器...")
        server.shutdown()
        proxy_pool.stop_all()
        logger.info("服务器已关闭")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # 在单独的线程中启动服务器
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    logger.info(f"代理Web服务器已启动在 {host}:{port}")

    try:
        # 保持主线程运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭服务器...")
        server.shutdown()
        proxy_pool.stop_all()
        logger.info("服务器已关闭")
