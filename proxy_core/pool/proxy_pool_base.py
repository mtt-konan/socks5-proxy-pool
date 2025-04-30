"""
代理池基类
"""

import threading
import socket
import time
from proxy_core.utils.logger import get_logger

logger = get_logger('proxy_pool_base')

class ProxyPoolBase:
    """代理池基类"""

    def __init__(self, proxy_file, max_active_proxies=100, port_start=10000):
        """初始化代理池

        Args:
            proxy_file: 代理列表文件路径
            max_active_proxies: 最大活跃代理数量
            port_start: 本地代理起始端口
        """
        self.proxy_file = proxy_file
        self.max_active_proxies = max_active_proxies
        self.port_start = port_start

        # 代理存储
        self.all_proxies = []  # 所有代理的基本信息
        self.active_proxies = {}  # 活跃代理 {port: proxy_info}
        self.failed_proxies = set()  # 失败的代理索引

        # 端口管理
        self.port_pool = list(range(port_start, port_start + max_active_proxies))
        self.used_ports = {}  # {port: proxy_index}

        # 状态跟踪
        self.current_index = 0

        # 线程锁
        self.lock = threading.Lock()

        # 初始化
        self._load_proxies()

    def _load_proxies(self):
        """从文件加载所有代理信息"""
        try:
            valid_count = 0
            invalid_count = 0
            with open(self.proxy_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue

                        parts = line.split()
                        if len(parts) >= 2:  # 至少需要IP和端口
                            # 提取IP和端口
                            host = parts[0]

                            # 尝试解析端口
                            try:
                                port = int(parts[1])
                                if port < 1 or port > 65535:
                                    logger.debug(f"第 {line_num} 行: 端口号超出范围: {port}")
                                    invalid_count += 1
                                    continue
                            except ValueError:
                                logger.debug(f"第 {line_num} 行: 端口号不是有效的整数: {parts[1]}")
                                invalid_count += 1
                                continue

                            # 提取用户名和密码（如果有）
                            username = parts[2] if len(parts) >= 3 else "1"
                            password = parts[3] if len(parts) >= 4 else "1"

                            # 添加代理，不验证IP地址格式
                            # 我们将在使用时验证IP地址格式
                            self.all_proxies.append({
                                'host': host,
                                'port': port,
                                'username': username,
                                'password': password,
                                'status': 'INACTIVE',
                                'last_used': 0,
                                'fail_count': 0
                            })
                            valid_count += 1
                    except Exception as e:
                        logger.debug(f"第 {line_num} 行解析失败: {e}")
                        invalid_count += 1

            if invalid_count > 0:
                logger.info(f"从文件 {self.proxy_file} 加载了 {valid_count} 个代理，忽略了 {invalid_count} 个无效条目")
            else:
                logger.info(f"从文件 {self.proxy_file} 加载了 {valid_count} 个代理")
        except Exception as e:
            logger.error(f"加载代理列表失败: {e}")

    def _validate_ip_address(self, ip):
        """验证IP地址格式"""
        try:
            socket.inet_aton(ip)
            return True
        except socket.error:
            return False

    def get_next_proxy(self):
        """获取下一个代理地址，子类需要实现此方法"""
        raise NotImplementedError("子类必须实现get_next_proxy方法")

    def get_proxy_stats(self):
        """获取代理统计信息，子类需要实现此方法"""
        raise NotImplementedError("子类必须实现get_proxy_stats方法")

    def stop_all(self):
        """停止所有代理服务器，子类需要实现此方法"""
        raise NotImplementedError("子类必须实现stop_all方法")
