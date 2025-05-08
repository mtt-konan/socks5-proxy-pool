"""
HTTP协议处理器
"""

import re
import base64
from proxy_core.utils.logger import get_logger

logger = get_logger('http_handler')

class HttpHandler:
    """HTTP协议处理器"""

    @staticmethod
    def parse_http_request(client_socket):
        """解析HTTP请求，返回目标地址、端口和原始请求数据"""
        try:
            # 接收HTTP请求
            request_data = b''
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                request_data += chunk
                if b'\r\n\r\n' in request_data:
                    break

            if not request_data:
                logger.error("接收HTTP请求失败")
                return None, None, None

            # 解析HTTP请求
            request_lines = request_data.split(b'\r\n')
            if not request_lines:
                logger.error("无效的HTTP请求")
                return None, None, None

            # 解析请求行
            request_line = request_lines[0].decode('utf-8', errors='ignore')
            method, url, version = request_line.split(' ', 2)

            if method == 'CONNECT':
                # HTTPS请求 (隧道模式)
                if ':' in url:
                    target_addr, target_port = url.split(':', 1)
                    target_port = int(target_port)
                else:
                    target_addr = url
                    target_port = 443  # 默认HTTPS端口

                logger.debug(f"HTTP隧道目标: {target_addr}:{target_port}")
                return target_addr, target_port, request_data
            else:
                # 普通HTTP请求
                if url.startswith('http://'):
                    # 绝对URL
                    url = url[7:]  # 去掉 'http://'
                    if '/' in url:
                        target_addr, path = url.split('/', 1)
                        path = '/' + path
                    else:
                        target_addr = url
                        path = '/'

                    if ':' in target_addr:
                        target_addr, target_port = target_addr.split(':', 1)
                        target_port = int(target_port)
                    else:
                        target_port = 80  # 默认HTTP端口
                else:
                    # 相对URL，从Host头中获取目标地址
                    host_match = re.search(rb'Host: ([^\r\n]+)', request_data)
                    if not host_match:
                        logger.error("HTTP请求中没有Host头")
                        return None, None, None

                    host = host_match.group(1).decode('utf-8', errors='ignore')
                    if ':' in host:
                        target_addr, target_port = host.split(':', 1)
                        target_port = int(target_port)
                    else:
                        target_addr = host
                        target_port = 80  # 默认HTTP端口

                logger.debug(f"HTTP请求目标: {target_addr}:{target_port}")
                return target_addr, target_port, request_data

        except Exception as e:
            logger.error(f"解析HTTP请求失败: {e}")
            return None, None, None

    @staticmethod
    def is_connect_method(request_data):
        """检查是否是CONNECT方法的请求"""
        try:
            if not request_data:
                return False

            request_line = request_data.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            method = request_line.split(' ', 1)[0]
            return method == 'CONNECT'
        except Exception:
            return False

    @staticmethod
    def send_http_connect_response(client_socket):
        """发送HTTP CONNECT成功响应"""
        try:
            client_socket.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            return True
        except Exception as e:
            logger.error(f"发送HTTP CONNECT响应失败: {e}")
            return False

    @staticmethod
    def send_http_error_response(client_socket, status_code, reason):
        """发送HTTP错误响应"""
        try:
            response = f"HTTP/1.1 {status_code} {reason}\r\n"
            response += "Content-Type: text/plain\r\n"
            response += "Connection: close\r\n"
            response += f"Content-Length: {len(reason)}\r\n"
            response += "\r\n"
            response += reason

            client_socket.sendall(response.encode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"发送HTTP错误响应失败: {e}")
            return False

    @staticmethod
    def handle_http_request(client_socket, connect_to_remote_func):
        """处理HTTP客户端连接"""
        try:
            # 接收HTTP请求
            request_data = b''
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                request_data += chunk
                if b'\r\n\r\n' in request_data:
                    break

            if not request_data:
                logger.error("接收HTTP请求失败")
                return False

            # 解析HTTP请求
            request_lines = request_data.split(b'\r\n')
            if not request_lines:
                logger.error("无效的HTTP请求")
                return False

            # 解析请求行
            request_line = request_lines[0].decode('utf-8', errors='ignore')
            method, url, version = request_line.split(' ', 2)

            if method == 'CONNECT':
                # HTTPS请求 (隧道模式)
                return HttpHandler.handle_https_tunnel(client_socket, url, connect_to_remote_func)
            else:
                # 普通HTTP请求
                return HttpHandler.handle_http_normal(client_socket, request_data, method, url, connect_to_remote_func)

        except Exception as e:
            logger.error(f"处理HTTP客户端时出错: {e}")
            return False

    @staticmethod
    def handle_https_tunnel(client_socket, target, connect_to_remote_func):
        """处理HTTPS隧道请求"""
        try:
            # 解析目标地址和端口
            if ':' in target:
                target_addr, target_port = target.split(':', 1)
                target_port = int(target_port)
            else:
                target_addr = target
                target_port = 443  # 默认HTTPS端口

            logger.info(f"HTTP隧道目标: {target_addr}:{target_port}")

            # 连接到远程
            remote_socket = connect_to_remote_func(target_addr, target_port)
            if not remote_socket:
                client_socket.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                return False

            # 发送成功响应给客户端
            client_socket.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')

            return remote_socket

        except Exception as e:
            logger.error(f"处理HTTPS隧道时出错: {e}")
            return False

    @staticmethod
    def handle_http_normal(client_socket, request_data, method, url, connect_to_remote_func):
        """处理普通HTTP请求"""
        try:
            # 解析URL
            if url.startswith('http://'):
                # 绝对URL
                url = url[7:]  # 去掉 'http://'
                if '/' in url:
                    target_addr, path = url.split('/', 1)
                    path = '/' + path
                else:
                    target_addr = url
                    path = '/'

                if ':' in target_addr:
                    target_addr, target_port = target_addr.split(':', 1)
                    target_port = int(target_port)
                else:
                    target_port = 80  # 默认HTTP端口
            else:
                # 相对URL，从Host头中获取目标地址
                host_match = re.search(rb'Host: ([^\r\n]+)', request_data)
                if not host_match:
                    logger.error("HTTP请求中没有Host头")
                    client_socket.sendall(b'HTTP/1.1 400 Bad Request\r\n\r\n')
                    return False

                host = host_match.group(1).decode('utf-8', errors='ignore')
                if ':' in host:
                    target_addr, target_port = host.split(':', 1)
                    target_port = int(target_port)
                else:
                    target_addr = host
                    target_port = 80  # 默认HTTP端口

                path = url

            logger.info(f"HTTP请求目标: {target_addr}:{target_port}{path}")

            # 连接到远程
            remote_socket = connect_to_remote_func(target_addr, target_port)
            if not remote_socket:
                client_socket.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                return False

            # 修改请求，使其适合转发
            modified_request = HttpHandler.modify_http_request(request_data, target_addr, target_port, path)

            # 发送修改后的请求到远程代理
            remote_socket.sendall(modified_request)

            return remote_socket

        except Exception as e:
            logger.error(f"处理HTTP请求时出错: {e}")
            return False

    @staticmethod
    def modify_http_request(request_data, target_addr, target_port, path, username=None, password=None):
        """修改HTTP请求，使其适合转发"""
        try:
            lines = request_data.split(b'\r\n')

            # 修改请求行
            request_line = lines[0].decode('utf-8', errors='ignore')
            method, _, version = request_line.split(' ', 2)
            new_request_line = f"{method} {path} {version}"
            lines[0] = new_request_line.encode('utf-8')

            # 添加代理认证头 (如果需要)
            if username and password:
                auth_header = f"Proxy-Authorization: Basic {base64.b64encode(f'{username}:{password}'.encode()).decode()}"
                auth_header_bytes = auth_header.encode('utf-8')

                # 检查是否已经有Proxy-Authorization头
                has_auth_header = False
                for i, line in enumerate(lines):
                    if line.startswith(b'Proxy-Authorization:'):
                        lines[i] = auth_header_bytes
                        has_auth_header = True
                        break

                if not has_auth_header:
                    # 在空行之前插入认证头
                    empty_line_index = lines.index(b'')
                    lines.insert(empty_line_index, auth_header_bytes)

            # 重新组合请求
            return b'\r\n'.join(lines)

        except Exception as e:
            logger.error(f"修改HTTP请求时出错: {e}")
            return request_data  # 出错时返回原始请求
