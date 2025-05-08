"""
代理服务器主程序 v2.0.0
支持单层代理和双层代理模式
"""

import argparse
import os
import sys
from proxy_core.pool.lru_proxy_pool import LRUProxyPool
from proxy_core.pool.dual_layer_proxy_pool import DualLayerProxyPool
from proxy_core.web.web_server import run_server
from proxy_core.utils.logger import get_logger

# 版本号
VERSION = "2.0.0"

logger = get_logger('main')

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description=f'启动代理轮换系统 v{VERSION}')
    parser.add_argument('--host', default='127.0.0.1', help='Web服务器主机地址')
    parser.add_argument('--port', type=int, default=7777, help='Web服务器端口')
    parser.add_argument('--proxy-file', default='all_proxies.txt', help='代理列表文件')
    parser.add_argument('--max-active-proxies', type=int, default=200, help='最大活跃代理数量（默认200，支持高并发）')
    parser.add_argument('--dual-proxy', action='store_true', help='启用双层代理模式')

    args = parser.parse_args()

    # 检查代理文件是否存在
    if not os.path.exists(args.proxy_file):
        logger.error(f"代理列表文件 {args.proxy_file} 不存在")
        return

    # 根据参数选择代理池类型
    if args.dual_proxy:
        logger.info(f"使用双层代理模式 (v{VERSION})")
        logger.info(f"从文件 {args.proxy_file} 加载代理")
        proxy_pool = DualLayerProxyPool(
            args.proxy_file,
            max_active_proxies=args.max_active_proxies
        )
    else:
        logger.info(f"使用单层代理模式 (v{VERSION})")
        logger.info(f"从文件 {args.proxy_file} 加载代理")
        proxy_pool = LRUProxyPool(args.proxy_file, max_active_proxies=args.max_active_proxies)

    logger.info(f"读取到 {len(proxy_pool.all_proxies)} 个远程代理")
    logger.info(f"最大活跃代理数量: {args.max_active_proxies}")

    # 启动服务器
    run_server(
        host=args.host,
        port=args.port,
        proxy_pool=proxy_pool
    )

if __name__ == "__main__":
    main()
