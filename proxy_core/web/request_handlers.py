"""
HTTP请求处理器
"""

import time
import http.server
from proxy_core.utils.logger import get_logger

logger = get_logger('request_handlers')

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """处理代理请求的HTTP处理器"""

    def do_GET(self):
        """处理GET请求"""
        # 获取客户端信息
        client_address = self.client_address[0]
        client_port = self.client_address[1]

        # 记录请求
        logger.info(f"收到来自 {client_address}:{client_port} 的请求: {self.path}")

        # 根据路径处理不同的请求
        if self.path == '/stats':
            self._handle_stats_request()
        elif self.path == '/favicon.ico':
            # 忽略浏览器的图标请求
            self.send_response(404)
            self.end_headers()
        else:
            # 默认路径，获取代理
            self._handle_proxy_request(client_address, client_port)

    def _handle_proxy_request(self, client_address, client_port):
        """处理获取代理的请求"""
        try:
            # 获取下一个代理
            proxy_address = self.server.proxy_pool.get_next_proxy()

            # 返回代理地址（只返回地址，不包含任何额外文本）
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')  # 允许跨域访问
            self.end_headers()
            self.wfile.write(proxy_address.encode('utf-8'))

            # 记录请求
            logger.info(f"客户端 {client_address}:{client_port} 请求代理，返回 {proxy_address}")
        except Exception as e:
            logger.error(f"处理代理请求时出错: {e}")
            try:
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')  # 允许跨域访问
                self.end_headers()
                self.wfile.write("127.0.0.1:10000".encode('utf-8'))
            except Exception as ex:
                logger.error(f"发送错误响应时出错: {ex}")
                pass

    def _handle_stats_request(self):
        """处理统计信息请求"""
        # 获取代理统计信息
        stats = self.server.proxy_pool.get_proxy_stats()

        # 按照LRU位置排序
        stats.sort(key=lambda x: x['lru_position'])

        # 构建纯文本响应
        text_response = ""

        # 添加标题行
        text_response += "索引,本地端口,远程主机,远程端口,用户名,最后使用时间,LRU位置\n"

        # 添加数据行
        for stat in stats:
            # 格式化最后使用时间
            last_used_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat['last_used']))

            # 添加一行数据
            text_response += f"{stat['index']},{stat['local_port']},{stat['remote_host']},{stat['remote_port']},{stat['username']},{last_used_time},{stat['lru_position']}\n"

        # 返回纯文本响应
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')  # 允许跨域访问
        self.end_headers()
        self.wfile.write(text_response.encode('utf-8'))

        logger.info(f"客户端 {self.client_address[0]}:{self.client_address[1]} 请求统计信息")

    def log_message(self, format, *args):
        """覆盖默认的日志方法，使用我们自己的日志器"""
        return
