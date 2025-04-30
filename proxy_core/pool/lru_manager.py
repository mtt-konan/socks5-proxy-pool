"""
LRU代理管理器 - 优化版
使用更高效的数据结构和锁机制
"""

import threading
import time
import collections
from proxy_core.utils.logger import get_logger

logger = get_logger('lru_manager')

class LRUManager:
    """LRU代理管理器 - 优化版"""

    def __init__(self):
        """初始化LRU管理器"""
        self.used_proxies = set()  # 已使用过的代理索引
        # 使用OrderedDict替代列表，提高效率
        self.lru_tracker = collections.OrderedDict()  # 跟踪代理使用顺序
        # 使用RLock允许同一线程多次获取锁
        self.lock = threading.RLock()
        # 增加锁超时时间
        self.lock_timeout = 3  # 3秒超时

    def mark_used(self, proxy_index):
        """标记代理为已使用"""
        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error(f"LRUManager.mark_used: 获取锁超时")
            return False

        try:
            self.used_proxies.add(proxy_index)
            # 更新LRU跟踪 - 使用OrderedDict更高效
            self.lru_tracker.pop(proxy_index, None)  # 如果存在则删除
            self.lru_tracker[proxy_index] = time.time()  # 添加到末尾并记录时间
            return True
        except Exception as e:
            logger.error(f"LRUManager.mark_used: 处理异常 {e}")
            return False
        finally:
            self.lock.release()

    def get_next_available_index(self, all_proxies, active_proxies, failed_proxies, current_index):
        """获取下一个可用的代理索引"""
        if not all_proxies:
            return None

        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error(f"LRUManager.get_next_available_index: 获取锁超时")
            # 返回当前索引作为备选
            return current_index

        try:
            # 如果所有代理都已使用过，重置已使用代理集合
            if len(self.used_proxies) >= len(all_proxies) - len(failed_proxies):
                logger.info("所有代理都已使用过，重置已使用代理集合")
                self.used_proxies = set(failed_proxies)  # 只保留失败的代理

            # 尝试次数
            attempts = 0
            max_attempts = min(len(all_proxies), 100)  # 限制尝试次数，避免长时间循环
            next_index = None

            # 创建活跃代理索引集合，避免重复查询
            active_indices = {port_info.get('proxy_index') for port_info in active_proxies.values()}

            while attempts < max_attempts:
                # 获取当前索引
                index = current_index
                current_index = (current_index + 1) % len(all_proxies)
                attempts += 1

                # 跳过失败的代理和已使用的代理
                if index in failed_proxies or index in self.used_proxies:
                    continue

                # 跳过已经在使用的代理
                if index in active_indices:
                    continue

                next_index = index
                break

            return next_index if next_index is not None else current_index
        except Exception as e:
            logger.error(f"LRUManager.get_next_available_index: 处理异常 {e}")
            return current_index
        finally:
            self.lock.release()

    def get_lru_index(self):
        """获取最近最少使用的代理索引"""
        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error(f"LRUManager.get_lru_index: 获取锁超时")
            return None

        try:
            if not self.lru_tracker:
                return None
            # 返回OrderedDict中的第一个键（最早使用的）
            return next(iter(self.lru_tracker))
        except Exception as e:
            logger.error(f"LRUManager.get_lru_index: 处理异常 {e}")
            return None
        finally:
            self.lock.release()

    def remove_from_lru(self, proxy_index):
        """从LRU跟踪中移除代理"""
        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error(f"LRUManager.remove_from_lru: 获取锁超时")
            return

        try:
            # 从OrderedDict中删除
            self.lru_tracker.pop(proxy_index, None)
        except Exception as e:
            logger.error(f"LRUManager.remove_from_lru: 处理异常 {e}")
        finally:
            self.lock.release()

    def update_proxy_usage(self, proxy_index, all_proxies):
        """更新代理使用情况"""
        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error(f"LRUManager.update_proxy_usage: 获取锁超时")
            return

        try:
            # 标记为已使用
            self.used_proxies.add(proxy_index)

            # 更新LRU跟踪
            self.lru_tracker.pop(proxy_index, None)  # 如果存在则删除
            self.lru_tracker[proxy_index] = time.time()  # 添加到末尾并记录时间

            # 更新使用时间
            if proxy_index < len(all_proxies):
                all_proxies[proxy_index]['last_used'] = time.time()
        except Exception as e:
            logger.error(f"LRUManager.update_proxy_usage: 处理异常 {e}")
        finally:
            self.lock.release()

    def get_lru_position(self, proxy_index):
        """获取代理在LRU中的位置"""
        # 使用超时锁
        if not self.lock.acquire(timeout=self.lock_timeout):
            logger.error(f"LRUManager.get_lru_position: 获取锁超时")
            return -1

        try:
            if not self.lru_tracker or proxy_index not in self.lru_tracker:
                return -1
            # 获取在OrderedDict中的位置
            position = 0
            for idx in self.lru_tracker:
                if idx == proxy_index:
                    return position
                position += 1
            return -1
        except Exception as e:
            logger.error(f"LRUManager.get_lru_position: 处理异常 {e}")
            return -1
        finally:
            self.lock.release()
