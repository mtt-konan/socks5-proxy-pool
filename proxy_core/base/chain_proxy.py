"""
代理链实现 - 支持双层代理
"""

import socket
import threading
from proxy_core.base.proxy_base import ProxyBase
from proxy_core.handlers.socks5_handler import Socks5Handler
from proxy_core.handlers.http_handler import HttpHandler
from proxy_core.utils.constants import SOCKS_VERSION
from proxy_core.utils.logger import get_logger

logger = get_logger('chain_proxy')

class ChainProxy(ProxyBase):
    """代理链实现，支持双层代理"""

    def __init__(self, local_host, local_port,
                 first_layer_host, first_layer_port, first_layer_username, first_layer_password,
                 second_layer_host, second_layer_port, second_layer_username, second_layer_password):
        """初始化代理链"""
        # 调用父类初始化，设置本地监听参数
        super().__init__(local_host, local_port)

        # 第一层代理信息
        self.first_layer_host = first_layer_host
        self.first_layer_port = first_layer_port
        self.first_layer_username = first_layer_username
        self.first_layer_password = first_layer_password

        # 第二层代理信息
        self.second_layer_host = second_layer_host
        self.second_layer_port = second_layer_port
        self.second_layer_username = second_layer_username
        self.second_layer_password = second_layer_password

        logger.debug(f"创建代理链: {local_host}:{local_port} -> {first_layer_host}:{first_layer_port} -> {second_layer_host}:{second_layer_port}")

    def handle_client(self, client_socket, client_address):
        """处理客户端连接，自动检测协议类型"""
        try:
            # 设置超时，以便我们可以检测协议类型
            client_socket.settimeout(5)

            # 读取第一个字节来确定协议类型
            first_byte = client_socket.recv(1, socket.MSG_PEEK)
            if not first_byte:
                logger.error("无法读取客户端数据")
                return

            # 重置超时
            client_socket.settimeout(None)

            # 检查协议类型
            if first_byte[0] == SOCKS_VERSION:
                # SOCKS5协议
                logger.debug("检测到SOCKS5协议")
                self.handle_socks5_client(client_socket)
            else:
                # 假设是HTTP协议
                logger.debug("检测到HTTP协议")
                self.handle_http_client(client_socket)

        except Exception as e:
            logger.error(f"处理客户端 {client_address} 时出错: {e}")
        finally:
            if not client_socket._closed:
                client_socket.close()

    def handle_socks5_client(self, client_socket):
        """处理SOCKS5客户端连接"""
        try:
            # 处理SOCKS5握手
            if not Socks5Handler.handle_socks5_negotiation(client_socket):
                return

            # 处理SOCKS5请求，获取目标地址和端口
            target_addr, target_port = Socks5Handler.parse_socks5_request(client_socket)
            if not target_addr or not target_port:
                return

            # 连接到目标（通过双层代理）
            remote_socket = self.connect_through_dual_proxy(target_addr, target_port)
            if remote_socket:
                # 发送SOCKS5连接成功响应
                Socks5Handler.send_socks5_response(client_socket, 0)

                # 开始在客户端和远程代理之间转发数据
                self.forward_data(client_socket, remote_socket)
            else:
                # 发送SOCKS5连接失败响应
                Socks5Handler.send_socks5_response(client_socket, 1)

        except Exception as e:
            logger.error(f"处理SOCKS5客户端时出错: {e}")

    def handle_http_client(self, client_socket):
        """处理HTTP客户端连接"""
        try:
            # 解析HTTP请求，获取目标地址和端口
            target_addr, target_port, request_data = HttpHandler.parse_http_request(client_socket)
            if not target_addr or not target_port:
                return

            # 连接到目标（通过双层代理）
            remote_socket = self.connect_through_dual_proxy(target_addr, target_port)
            if remote_socket:
                # 对于CONNECT请求，发送连接成功响应
                if HttpHandler.is_connect_method(request_data):
                    HttpHandler.send_http_connect_response(client_socket)
                else:
                    # 对于其他请求，转发原始请求
                    remote_socket.sendall(request_data)

                # 开始在客户端和远程代理之间转发数据
                self.forward_data(client_socket, remote_socket)
            else:
                # 发送HTTP错误响应
                HttpHandler.send_http_error_response(client_socket, 502, "Bad Gateway")

        except Exception as e:
            logger.error(f"处理HTTP客户端时出错: {e}")

    def connect_through_dual_proxy(self, target_addr, target_port):
        """通过双层代理连接到目标"""
        try:
            logger.debug(f"通过双层代理连接到 {target_addr}:{target_port}")

            # 第一步：连接到第一层代理
            first_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            first_socket.settimeout(10)

            try:
                first_socket.connect((self.first_layer_host, self.first_layer_port))
                logger.debug(f"已连接到第一层代理 {self.first_layer_host}:{self.first_layer_port}")
            except Exception as e:
                logger.error(f"连接到第一层代理失败: {e}")
                first_socket.close()
                return None

            # 第二步：与第一层代理进行SOCKS5握手
            if not Socks5Handler.send_socks5_handshake(first_socket, self.first_layer_username, self.first_layer_password):
                logger.error("与第一层代理握手失败")
                first_socket.close()
                return None

            # 第三步：通过第一层代理连接到第二层代理
            if not Socks5Handler.send_socks5_connect_command(first_socket, self.second_layer_host, self.second_layer_port):
                logger.error("通过第一层代理连接到第二层代理失败")
                first_socket.close()
                return None

            logger.debug(f"已通过第一层代理连接到第二层代理 {self.second_layer_host}:{self.second_layer_port}")

            # 第四步：通过第一层代理向第二层代理发送SOCKS5握手
            # 这里比较复杂，因为我们需要通过已建立的连接发送SOCKS5握手包

            # 发送支持多种认证方法的握手包
            if self.second_layer_username and self.second_layer_password:
                # 支持无认证(0x00)和用户名/密码认证(0x02)
                first_socket.sendall(bytes([0x05, 0x02, 0x00, 0x02]))
            else:
                # 只支持无认证(0x00)
                first_socket.sendall(bytes([0x05, 0x01, 0x00]))

            # 接收第二层代理的握手响应
            logger.debug(f"等待第二层代理握手响应...")
            response = first_socket.recv(2)
            logger.debug(f"收到第二层代理握手响应: {response.hex() if response else 'No response'}")

            if len(response) < 2:
                logger.error(f"第二层代理握手响应不完整: {response.hex() if response else 'No response'}")
                first_socket.close()
                return None

            # 检查SOCKS版本
            if response[0] != 0x05:
                logger.error(f"第二层代理不支持SOCKS5: {response.hex()}")
                first_socket.close()
                return None

            # 处理认证方法
            auth_method = response[1]
            logger.debug(f"第二层代理选择的认证方法: {auth_method}")

            if auth_method == 0x00:
                # 无认证，继续
                logger.debug("第二层代理不需要认证")
                pass
            elif auth_method == 0x02 and self.second_layer_username and self.second_layer_password:
                # 用户名/密码认证
                logger.debug("第二层代理需要用户名/密码认证")

                # 构建认证数据包
                auth_packet = bytearray([0x01])  # 认证协议版本

                # 用户名
                username_bytes = self.second_layer_username.encode('utf-8')
                auth_packet.append(len(username_bytes))
                auth_packet.extend(username_bytes)

                # 密码
                password_bytes = self.second_layer_password.encode('utf-8')
                auth_packet.append(len(password_bytes))
                auth_packet.extend(password_bytes)

                # 发送认证数据
                first_socket.sendall(auth_packet)

                # 接收认证响应
                auth_response = first_socket.recv(2)
                if len(auth_response) < 2:
                    logger.error(f"第二层代理认证响应不完整: {auth_response.hex() if auth_response else 'No response'}")
                    first_socket.close()
                    return None

                if auth_response[1] != 0x00:
                    logger.error(f"第二层代理认证失败: {auth_response.hex()}")
                    first_socket.close()
                    return None

                logger.debug("第二层代理认证成功")
            else:
                # 不支持的认证方法
                logger.error(f"第二层代理要求不支持的认证方法: {auth_method}")
                first_socket.close()
                return None

            # 第五步：通过第二层代理连接到目标
            # 构建CONNECT请求
            connect_request = bytearray([0x05, 0x01, 0x00])  # SOCKS5, CONNECT, 保留字段

            # 处理目标地址
            try:
                # 尝试作为IPv4处理
                socket.inet_aton(target_addr)
                connect_request.append(0x01)  # IPv4
                for part in socket.inet_aton(target_addr):
                    connect_request.append(part)
            except socket.error:
                try:
                    # 尝试作为IPv6处理
                    if ':' in target_addr:
                        socket.inet_pton(socket.AF_INET6, target_addr)
                        connect_request.append(0x04)  # IPv6
                        for part in socket.inet_pton(socket.AF_INET6, target_addr):
                            connect_request.append(part)
                    else:
                        # 作为域名处理
                        raise socket.error()
                except socket.error:
                    # 作为域名处理
                    domain_bytes = target_addr.encode('utf-8')
                    connect_request.append(0x03)  # 域名
                    connect_request.append(len(domain_bytes))
                    connect_request.extend(domain_bytes)

            # 添加端口（网络字节序，大端）
            connect_request.extend(target_port.to_bytes(2, 'big'))

            # 发送连接请求
            logger.debug(f"向第二层代理发送连接请求: {target_addr}:{target_port}")
            first_socket.sendall(connect_request)

            # 接收连接响应
            response = first_socket.recv(4)  # 先读取头部4字节
            if len(response) < 4:
                logger.error(f"第二层代理连接响应不完整: {response.hex() if response else 'No response'}")
                first_socket.close()
                return None

            # 检查响应状态
            if response[1] != 0x00:
                error_codes = {
                    0x01: "一般性失败",
                    0x02: "规则集不允许连接",
                    0x03: "网络不可达",
                    0x04: "主机不可达",
                    0x05: "连接被拒绝",
                    0x06: "TTL已过期",
                    0x07: "不支持的命令",
                    0x08: "不支持的地址类型",
                }
                error_msg = error_codes.get(response[1], f"未知错误: {response[1]}")
                logger.error(f"第二层代理连接失败: {error_msg}")
                first_socket.close()
                return None

            # 根据地址类型读取剩余数据
            atyp = response[3]
            if atyp == 0x01:  # IPv4
                first_socket.recv(4 + 2)  # 4字节IPv4地址 + 2字节端口
            elif atyp == 0x03:  # 域名
                domain_len = first_socket.recv(1)[0]
                first_socket.recv(domain_len + 2)  # 域名 + 2字节端口
            elif atyp == 0x04:  # IPv6
                first_socket.recv(16 + 2)  # 16字节IPv6地址 + 2字节端口
            else:
                logger.error(f"第二层代理返回了不支持的地址类型: {atyp}")
                first_socket.close()
                return None

            # 连接成功，返回socket
            logger.debug(f"成功通过双层代理连接到 {target_addr}:{target_port}")
            return first_socket

        except Exception as e:
            logger.error(f"通过双层代理连接失败: {e}")
            return None
