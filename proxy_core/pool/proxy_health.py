"""
代理健康检查
"""

import threading
import time
import socket
from proxy_core.utils.logger import get_logger

logger = get_logger('proxy_health')

class ProxyHealth:
    """代理健康检查"""

    def __init__(self, check_interval=300):
        """初始化健康检查

        Args:
            check_interval: 健康检查间隔（秒）
        """
        self.check_interval = check_interval
        self.running = False
        self.check_thread = None

    def start_health_check(self, check_func):
        """启动健康检查线程

        Args:
            check_func: 健康检查函数
        """
        self.running = True
        self.check_thread = threading.Thread(target=self._health_check_loop, args=(check_func,))
        self.check_thread.daemon = True
        self.check_thread.start()
        logger.info("健康检查线程已启动")

    def stop_health_check(self):
        """停止健康检查线程"""
        self.running = False
        if self.check_thread:
            self.check_thread.join(timeout=1)
        logger.info("健康检查线程已停止")

    def _health_check_loop(self, check_func):
        """健康检查循环"""
        while self.running:
            try:
                check_func()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"健康检查出错: {e}")
                time.sleep(60)  # 出错后等待较短时间再重试

    @staticmethod
    def validate_proxy(host, port, timeout=5):
        """验证代理是否可用

        Args:
            host: 代理主机
            port: 代理端口
            timeout: 超时时间（秒）

        Returns:
            bool: 代理是否可用
        """
        try:
            # 验证IP地址格式
            socket.inet_aton(host)
            
            # 尝试连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            return True
        except (socket.error, socket.timeout):
            return False
        except Exception as e:
            logger.error(f"验证代理 {host}:{port} 时出错: {e}")
            return False
