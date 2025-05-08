"""
双层代理池实现 - v2.0.0
支持通过两层代理转发流量，提高匿名性
"""

import threading
import time
import random
import queue
from proxy_core.base.chain_proxy import ChainProxy
from proxy_core.pool.lru_proxy_pool import LRUProxyPool
from proxy_core.utils.logger import get_logger

logger = get_logger('dual_layer_proxy_pool')

class DualLayerProxyPool(LRUProxyPool):
    """双层代理池实现 - 支持双层代理转发"""

    def __init__(self, proxy_file, max_active_proxies=100, port_start=10000):
        """初始化双层代理池

        Args:
            proxy_file: 代理列表文件路径
            max_active_proxies: 最大活跃代理数量
            port_start: 本地代理起始端口
        """
        super().__init__(proxy_file, max_active_proxies, port_start)

        # 代理链管理
        self.proxy_chains = {}  # {local_port: {'first_layer': idx1, 'second_layer': idx2}}

        logger.info("初始化双层代理池")

    def _setup_port_with_new_proxy(self, local_port):
        """为指定端口设置新的代理链"""
        # 第一阶段：获取代理信息（短锁）
        first_layer_index = None
        second_layer_index = None
        first_proxy_info = None
        second_proxy_info = None

        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error(f"_setup_port_with_new_proxy: 获取锁超时，无法为端口 {local_port} 设置代理")
            return False

        try:
            # 如果端口已经在使用，先停止旧的代理
            if local_port in self.active_proxies:
                # 释放锁后停止代理，避免长时间持有锁
                proxy_to_stop = self.active_proxies[local_port]['proxy']
                self.lock.release()

                try:
                    proxy_to_stop.stop()
                except Exception as e:
                    logger.error(f"停止端口 {local_port} 的旧代理失败: {e}")

                # 重新获取锁
                if not self.lock.acquire(timeout=self.lock_timeout):
                    logger.error(f"_setup_port_with_new_proxy: 重新获取锁超时，无法为端口 {local_port} 设置代理")
                    return False

                # 清理资源
                if local_port in self.active_proxies:
                    proxy_index_to_remove = self.active_proxies[local_port].get('proxy_index')
                    if proxy_index_to_remove is not None and proxy_index_to_remove < len(self.all_proxies):
                        self.all_proxies[proxy_index_to_remove]['status'] = 'INACTIVE'
                        # 从LRU跟踪中移除
                        self.lru_manager.remove_from_lru(proxy_index_to_remove)

                    # 清理资源
                    del self.active_proxies[local_port]
                    if local_port in self.used_ports:
                        del self.used_ports[local_port]

                    # 将端口返回到池中
                    if local_port not in self.port_pool:
                        self.port_pool.append(local_port)

            # 获取第一层代理索引
            if not hasattr(self, 'current_index') or self.current_index >= len(self.all_proxies):
                self.current_index = 0

            first_layer_index = self.current_index
            self.current_index = (self.current_index + 1) % len(self.all_proxies)

            # 获取第二层代理索引（确保与第一层不同）
            second_layer_index = self._get_different_proxy_index(first_layer_index)

            # 获取代理信息的副本
            if first_layer_index < len(self.all_proxies) and second_layer_index < len(self.all_proxies):
                first_proxy_info = self.all_proxies[first_layer_index].copy()
                second_proxy_info = self.all_proxies[second_layer_index].copy()

                # 标记代理为已使用
                self.lru_manager.mark_used(first_layer_index)
                self.lru_manager.mark_used(second_layer_index)

                # 记录代理链信息
                self.proxy_chains[local_port] = {
                    'first_layer': first_layer_index,
                    'second_layer': second_layer_index
                }
            else:
                logger.error(f"代理索引超出范围: 第一层={first_layer_index}, 第二层={second_layer_index}")
                self.lock.release()
                return False
        finally:
            # 确保释放锁
            if self.lock._is_owned():
                self.lock.release()

        if first_proxy_info is None or second_proxy_info is None:
            return False

        # 第二阶段：创建和启动代理（无锁）
        try:
            # 创建代理链
            proxy = ChainProxy(
                local_host='127.0.0.1',
                local_port=local_port,
                first_layer_host=first_proxy_info['host'],
                first_layer_port=first_proxy_info['port'],
                first_layer_username=first_proxy_info['username'],
                first_layer_password=first_proxy_info['password'],
                second_layer_host=second_proxy_info['host'],
                second_layer_port=second_proxy_info['port'],
                second_layer_username=second_proxy_info['username'],
                second_layer_password=second_proxy_info['password']
            )

            # 启动代理线程
            proxy_thread = threading.Thread(target=self._start_proxy, args=(proxy,))
            proxy_thread.daemon = True
            proxy_thread.start()

            # 第三阶段：更新状态（短锁）
            if not self.lock.acquire(timeout=self.lock_timeout):
                logger.error(f"_setup_port_with_new_proxy: 获取锁超时，无法更新端口 {local_port} 的状态")
                # 尝试停止已启动的代理
                try:
                    proxy.stop()
                except Exception as e:
                    logger.error(f"停止新创建的代理失败: {e}")
                return False

            try:
                # 更新状态
                self.active_proxies[local_port] = {
                    'proxy': proxy,
                    'thread': proxy_thread,
                    'proxy_index': first_layer_index,  # 仍然使用第一层索引作为主索引
                    'start_time': time.time(),
                    'connections': 0
                }
                self.used_ports[local_port] = first_layer_index

                # 更新代理信息
                if first_layer_index < len(self.all_proxies):
                    self.all_proxies[first_layer_index]['status'] = 'ACTIVE'
                    self.all_proxies[first_layer_index]['last_used'] = time.time()
                if second_layer_index < len(self.all_proxies):
                    self.all_proxies[second_layer_index]['status'] = 'ACTIVE'
                    self.all_proxies[second_layer_index]['last_used'] = time.time()
            finally:
                self.lock.release()

            logger.info(f"端口 {local_port} 设置了新的代理链: 第一层={first_layer_index} ({first_proxy_info['host']}:{first_proxy_info['port']}), 第二层={second_layer_index} ({second_proxy_info['host']}:{second_proxy_info['port']})")
            return True

        except Exception as e:
            logger.error(f"为端口 {local_port} 设置代理链失败: {e}")
            return False

    def _get_different_proxy_index(self, exclude_index):
        """获取一个与指定索引不同的代理索引"""
        if len(self.all_proxies) <= 1:
            return 0  # 如果只有一个代理，没有选择

        # 创建可用索引列表（排除指定索引）
        available_indices = [i for i in range(len(self.all_proxies)) if i != exclude_index]

        if not available_indices:
            logger.warning("没有可用的不同代理索引，返回原索引")
            return exclude_index

        # 随机打乱索引列表
        random.shuffle(available_indices)

        # 返回第一个索引
        return available_indices[0]

    def get_proxy_stats(self):
        """获取代理统计信息"""
        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error("get_proxy_stats: 获取锁超时，返回空统计信息")
            return []

        try:
            stats = []
            for port, proxy_data in self.active_proxies.items():
                proxy_index = proxy_data.get('proxy_index')

                # 获取代理链信息
                chain_info = self.proxy_chains.get(port, {})
                first_layer_index = chain_info.get('first_layer')
                second_layer_index = chain_info.get('second_layer')

                if proxy_index is not None and proxy_index < len(self.all_proxies):
                    first_proxy_info = self.all_proxies[first_layer_index] if first_layer_index is not None else {}
                    second_proxy_info = self.all_proxies[second_layer_index] if second_layer_index is not None else {}

                    # 获取LRU位置
                    lru_position = self.lru_manager.get_lru_position(proxy_index)

                    stats.append({
                        'index': proxy_index,
                        'local_port': port,
                        'first_layer_host': first_proxy_info.get('host'),
                        'first_layer_port': first_proxy_info.get('port'),
                        'second_layer_host': second_proxy_info.get('host'),
                        'second_layer_port': second_proxy_info.get('port'),
                        'last_used': first_proxy_info.get('last_used', 0),
                        'lru_position': lru_position,
                        'status': first_proxy_info.get('status', 'UNKNOWN'),
                        'connections': proxy_data.get('connections', 0)
                    })
            return stats
        except Exception as e:
            logger.error(f"获取代理统计信息时出错: {e}")
            return []
        finally:
            self.lock.release()
