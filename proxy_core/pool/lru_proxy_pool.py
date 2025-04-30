"""
LRU代理池实现 - 优化版
减少锁竞争，提高并发性能
"""

import threading
import time
import queue
from proxy_core.base.dual_proxy import DualProxy
from proxy_core.pool.proxy_pool_base import ProxyPoolBase
from proxy_core.pool.lru_manager import LRUManager
from proxy_core.pool.proxy_health import ProxyHealth
from proxy_core.utils.logger import get_logger

logger = get_logger('lru_proxy_pool')

class LRUProxyPool(ProxyPoolBase):
    """LRU代理池实现 - 优化版"""

    def __init__(self, proxy_file, max_active_proxies=100, port_start=10000):
        """初始化LRU代理池

        Args:
            proxy_file: 代理列表文件路径
            max_active_proxies: 最大活跃代理数量
            port_start: 本地代理起始端口
        """
        super().__init__(proxy_file, max_active_proxies, port_start)

        # 使用RLock替代Lock，允许同一线程多次获取锁
        self.lock = threading.RLock()

        # 增加锁超时时间
        self.lock_timeout = 3  # 3秒超时

        # LRU管理器
        self.lru_manager = LRUManager()

        # 健康检查（禁用）
        self.health_checker = ProxyHealth()

        # 设置当前端口
        self.current_port = self.port_start

        # 添加代理设置队列，减少锁竞争
        self.proxy_setup_queue = queue.Queue()

        # 启动代理设置工作线程
        self._start_proxy_setup_workers()

        # 初始化活跃代理（在后台线程中进行）
        threading.Thread(target=self._init_active_proxies, daemon=True).start()

        # 不启动健康检查
        # self.health_checker.start_health_check(self._check_active_proxies)

    def _start_proxy_setup_workers(self):
        """启动代理设置工作线程"""
        # 创建多个工作线程处理代理设置请求
        for _ in range(5):  # 5个工作线程
            worker = threading.Thread(target=self._proxy_setup_worker, daemon=True)
            worker.start()

    def _proxy_setup_worker(self):
        """代理设置工作线程"""
        while True:
            try:
                # 从队列获取任务
                local_port = self.proxy_setup_queue.get()

                # 设置代理
                self._setup_port_with_new_proxy(local_port)

                # 标记任务完成
                self.proxy_setup_queue.task_done()
            except Exception as e:
                logger.error(f"代理设置工作线程异常: {e}")
                # 继续工作，不退出循环

    def _init_active_proxies(self):
        """初始化活跃代理池"""
        # 初始化所有端口，每个端口对应一个远程代理
        if self.all_proxies:
            # 初始化所有端口
            logger.info(f"初始化所有端口，共 {self.max_active_proxies} 个")

            # 启动多个线程并行初始化代理
            threads = []
            for i in range(self.max_active_proxies):
                port = self.port_start + i
                thread = threading.Thread(
                    target=self._setup_port_with_new_proxy,
                    args=(port,)
                )
                thread.daemon = True
                thread.start()
                threads.append(thread)

            # 等待所有初始化线程完成
            for thread in threads:
                thread.join(timeout=1)  # 设置较短的超时，避免阻塞太久

            logger.info(f"代理池初始化完成，已初始化 {len(self.active_proxies)} 个代理")

    def _setup_port_with_new_proxy(self, local_port):
        """为指定端口设置新的代理"""
        # 第一阶段：获取代理信息（短锁）
        proxy_index = None
        proxy_info = None

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

            # 获取下一个代理索引，简单地使用循环方式
            if not hasattr(self, 'current_index') or self.current_index >= len(self.all_proxies):
                self.current_index = 0

            proxy_index = self.current_index
            self.current_index = (self.current_index + 1) % len(self.all_proxies)

            # 获取代理信息的副本
            if proxy_index < len(self.all_proxies):
                proxy_info = self.all_proxies[proxy_index].copy()
                # 标记代理为已使用
                self.lru_manager.mark_used(proxy_index)
            else:
                logger.error(f"代理索引 {proxy_index} 超出范围")
                self.lock.release()
                return False
        finally:
            # 确保释放锁
            if self.lock._is_owned():
                self.lock.release()

        if proxy_info is None:
            return False

        # 第二阶段：创建和启动代理（无锁）
        try:
            # 创建代理服务器
            proxy = DualProxy(
                local_host='127.0.0.1',
                local_port=local_port,
                remote_host=proxy_info['host'],
                remote_port=proxy_info['port'],
                username=proxy_info['username'],
                password=proxy_info['password']
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
                    'proxy_index': proxy_index,
                    'start_time': time.time(),
                    'connections': 0
                }
                self.used_ports[local_port] = proxy_index

                # 更新代理信息
                if proxy_index < len(self.all_proxies):
                    self.all_proxies[proxy_index]['status'] = 'ACTIVE'
                    self.all_proxies[proxy_index]['last_used'] = time.time()
            finally:
                self.lock.release()

            logger.info(f"端口 {local_port} 设置了新的代理 {proxy_index} ({proxy_info['host']}:{proxy_info['port']})")
            return True

        except Exception as e:
            logger.error(f"为端口 {local_port} 设置代理 {proxy_index} 失败: {e}")
            # 不标记为失败，只记录错误
            logger.error(f"代理 {proxy_index} ({proxy_info['host']}:{proxy_info['port']}) 设置失败: {e}")
            return False

    def _stop_proxy(self, local_port):
        """停止指定端口的代理"""
        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error(f"_stop_proxy: 获取锁超时，无法停止端口 {local_port} 的代理")
            return False

        try:
            if local_port not in self.active_proxies:
                return True

            # 获取代理数据的副本，然后释放锁
            proxy_data = self.active_proxies[local_port].copy()
            proxy_to_stop = proxy_data['proxy']
            proxy_index = proxy_data['proxy_index']

            # 释放锁后停止代理，避免长时间持有锁
            self.lock.release()

            # 停止代理（无锁）
            try:
                proxy_to_stop.stop()
            except Exception as e:
                logger.error(f"停止端口 {local_port} 的代理失败: {e}")

            # 重新获取锁更新状态
            if not self.lock.acquire(timeout=self.lock_timeout):
                logger.error(f"_stop_proxy: 重新获取锁超时，无法更新端口 {local_port} 的状态")
                return False

            try:
                # 确保端口仍然在活跃代理中（可能在我们释放锁期间被其他线程修改）
                if local_port in self.active_proxies and self.active_proxies[local_port]['proxy'] == proxy_to_stop:
                    # 更新状态
                    if proxy_index < len(self.all_proxies):
                        self.all_proxies[proxy_index]['status'] = 'INACTIVE'
                        # 从LRU跟踪中移除
                        self.lru_manager.remove_from_lru(proxy_index)

                    # 清理资源
                    del self.active_proxies[local_port]
                    if local_port in self.used_ports:
                        del self.used_ports[local_port]

                    # 将端口返回到池中
                    if local_port not in self.port_pool:
                        self.port_pool.append(local_port)

                    logger.info(f"端口 {local_port} 的代理已停止")
                    return True
            finally:
                self.lock.release()

            return True
        except Exception as e:
            logger.error(f"停止端口 {local_port} 的代理失败: {e}")
            # 确保释放锁
            if self.lock._is_owned():
                self.lock.release()
            return False

    def _start_proxy(self, proxy):
        """启动代理服务器"""
        try:
            proxy.start()
        except Exception as e:
            logger.error(f"代理服务器启动失败: {e}")

    def get_next_proxy(self):
        """获取下一个代理地址"""
        # 使用局部变量减少锁持有时间
        current_port = None

        # 添加超时保护，确保即使出现问题也能返回响应
        try:
            # 使用超时锁，避免长时间阻塞
            if not self.lock.acquire(timeout=self.lock_timeout):  # 使用更长的超时时间
                logger.error("get_next_proxy: 获取锁超时，返回递增端口")
                # 如果没有current_port属性，设置为起始端口
                if not hasattr(self, 'current_port'):
                    self.current_port = self.port_start
                # 返回当前端口并递增
                current_port = self.current_port
                self.current_port = (current_port - self.port_start + 1) % self.max_active_proxies + self.port_start
                return f"127.0.0.1:{current_port}"

            try:
                # 如果没有current_port属性，设置为起始端口
                if not hasattr(self, 'current_port'):
                    self.current_port = self.port_start

                # 获取当前端口
                current_port = self.current_port

                # 如果当前端口有活跃代理，增加连接计数
                if current_port in self.active_proxies:
                    self.active_proxies[current_port]['connections'] += 1
                    # 获取代理索引
                    proxy_index = self.active_proxies[current_port]['proxy_index']

                    # 计算下一个端口
                    next_port = (current_port - self.port_start + 1) % self.max_active_proxies + self.port_start
                    self.current_port = next_port

                    # 释放锁，然后更新代理使用情况
                    self.lock.release()

                    # 更新代理使用情况（无锁）
                    self.lru_manager.update_proxy_usage(proxy_index, self.all_proxies)

                    # 将端口添加到代理设置队列，而不是直接启动线程
                    self.proxy_setup_queue.put(current_port)
                else:
                    # 计算下一个端口
                    next_port = (current_port - self.port_start + 1) % self.max_active_proxies + self.port_start
                    self.current_port = next_port
                    self.lock.release()
            except Exception as e:
                logger.error(f"获取代理时出错: {e}")
                # 确保释放锁
                if self.lock._is_owned():
                    self.lock.release()
                # 如果出错，仍然返回一个有效的端口
                if not current_port:
                    if not hasattr(self, 'current_port'):
                        self.current_port = self.port_start
                    current_port = self.current_port
                    self.current_port = (current_port - self.port_start + 1) % self.max_active_proxies + self.port_start

            logger.info(f"返回代理地址: 127.0.0.1:{current_port}")
            return f"127.0.0.1:{current_port}"

        except Exception as e:
            logger.error(f"获取代理时出错: {e}")
            # 如果没有current_port属性，设置为起始端口
            if not hasattr(self, 'current_port'):
                self.current_port = self.port_start
            # 返回当前端口并递增
            current_port = self.current_port
            self.current_port = (current_port - self.port_start + 1) % self.max_active_proxies + self.port_start
            return f"127.0.0.1:{current_port}"

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
                if proxy_index is not None and proxy_index < len(self.all_proxies):
                    proxy_info = self.all_proxies[proxy_index]

                    # 获取LRU位置（使用新方法）
                    lru_position = self.lru_manager.get_lru_position(proxy_index)

                    stats.append({
                        'index': proxy_index,
                        'local_port': port,
                        'remote_host': proxy_info['host'],
                        'remote_port': proxy_info['port'],
                        'username': proxy_info['username'],
                        'last_used': proxy_info['last_used'],
                        'lru_position': lru_position,
                        'status': proxy_info['status'],
                        'connections': proxy_data.get('connections', 0)
                    })
            return stats
        except Exception as e:
            logger.error(f"获取代理统计信息时出错: {e}")
            return []
        finally:
            self.lock.release()

    def _check_active_proxies(self):
        """检查活跃代理的健康状态"""
        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error("_check_active_proxies: 获取锁超时，跳过健康检查")
            return

        try:
            logger.info(f"当前活跃代理数量: {len(self.active_proxies)}")

            # 收集需要初始化的端口
            ports_to_init = []
            for port in range(self.port_start, self.port_start + self.max_active_proxies):
                if port not in self.active_proxies:
                    ports_to_init.append(port)
        finally:
            self.lock.release()

        # 在锁外初始化端口，避免长时间持有锁
        for port in ports_to_init:
            logger.info(f"端口 {port} 没有活跃代理，添加到初始化队列")
            self.proxy_setup_queue.put(port)

    def stop_all(self):
        """停止所有代理服务器"""
        logger.info("正在停止所有代理服务器...")

        # 停止健康检查
        self.health_checker.stop_health_check()

        # 使用超时锁获取所有活跃端口
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error("stop_all: 获取锁超时，无法停止所有代理")
            return

        try:
            # 获取所有活跃端口的列表
            ports_to_stop = list(self.active_proxies.keys())
        finally:
            self.lock.release()

        # 在锁外停止所有代理，避免长时间持有锁
        for port in ports_to_stop:
            self._stop_proxy(port)

        logger.info("所有代理服务器已停止")
