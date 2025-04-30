"""
日志配置
"""

import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_logger(name):
    """获取指定名称的日志器"""
    return logging.getLogger(name)
