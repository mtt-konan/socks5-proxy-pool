"""
SOCKS5协议处理器
"""

import socket
from proxy_core.utils.constants import SOCKS_VERSION, CONNECT, IPV4, IPV6, DOMAIN
from proxy_core.utils.logger import get_logger

logger = get_logger('socks5_handler')

class Socks5Handler:
    """SOCKS5协议处理器"""

    @staticmethod
    def create_socks5_handshake_packet(username=None, password=None):
        """创建SOCKS5握手数据包"""
        if username and password:
            # 带认证的握手包
            packet = bytearray([SOCKS_VERSION, 1, 0x02])  # 支持用户名/密码认证
        else:
            # 无认证的握手包
            packet = bytearray([SOCKS_VERSION, 1, 0x00])  # 不需要认证
        return packet

    @staticmethod
    def create_socks5_auth_packet(username, password):
        """创建SOCKS5认证数据包"""
        username_bytes = username.encode('utf-8')
        password_bytes = password.encode('utf-8')

        packet = bytearray([1])  # 认证子版本
        packet.append(len(username_bytes))
        packet.extend(username_bytes)
        packet.append(len(password_bytes))
        packet.extend(password_bytes)

        return packet

    @staticmethod
    def create_socks5_connect_packet(addr, port):
        """创建SOCKS5连接请求数据包"""
        packet = bytearray([SOCKS_VERSION, CONNECT, 0x00])  # 命令：CONNECT

        # 地址类型和地址
        try:
            # 尝试作为IPv4处理
            socket.inet_aton(addr)
            packet.append(IPV4)
            for part in socket.inet_aton(addr):
                packet.append(part)
        except socket.error:
            try:
                # 尝试作为IPv6处理
                if ':' in addr:
                    socket.inet_pton(socket.AF_INET6, addr)
                    packet.append(IPV6)
                    for part in socket.inet_pton(socket.AF_INET6, addr):
                        packet.append(part)
                else:
                    # 作为域名处理
                    raise socket.error()
            except socket.error:
                # 作为域名处理
                packet.append(DOMAIN)
                addr_bytes = addr.encode('utf-8')
                packet.append(len(addr_bytes))
                packet.extend(addr_bytes)

        # 端口
        packet.extend(port.to_bytes(2, 'big'))

        return packet

    @staticmethod
    def send_socks5_handshake(socket_obj, username=None, password=None):
        """发送SOCKS5握手请求"""
        try:
            # 发送握手包
            if username and password:
                socket_obj.sendall(bytes([SOCKS_VERSION, 2, 0x00, 0x02]))  # 支持无认证和用户名/密码认证
            else:
                socket_obj.sendall(bytes([SOCKS_VERSION, 1, 0x00]))  # 只支持无认证

            # 接收响应
            response = socket_obj.recv(2)
            if not response or len(response) < 2:
                logger.error("接收SOCKS5握手响应失败")
                return False

            version, auth_method = response
            if version != SOCKS_VERSION:
                logger.error(f"不支持的SOCKS版本: {version}")
                return False

            # 处理认证方法
            if auth_method == 0x00:
                # 无认证
                return True
            elif auth_method == 0x02 and username and password:
                # 用户名/密码认证
                auth_packet = Socks5Handler.create_socks5_auth_packet(username, password)
                socket_obj.sendall(auth_packet)

                # 接收认证响应
                auth_response = socket_obj.recv(2)
                if not auth_response or len(auth_response) < 2:
                    logger.error("接收认证响应失败")
                    return False

                _, auth_status = auth_response
                if auth_status != 0x00:
                    logger.error(f"认证失败: {auth_status}")
                    return False

                return True
            else:
                logger.error(f"不支持的认证方法: {auth_method}")
                return False

        except Exception as e:
            logger.error(f"发送SOCKS5握手请求失败: {e}")
            return False

    @staticmethod
    def send_socks5_connect_command(socket_obj, addr, port):
        """发送SOCKS5连接命令"""
        try:
            # 创建并发送连接请求
            connect_packet = Socks5Handler.create_socks5_connect_packet(addr, port)
            socket_obj.sendall(connect_packet)

            # 接收响应
            response = socket_obj.recv(4)
            if not response or len(response) < 4:
                logger.error("接收SOCKS5连接响应失败")
                return False

            version, status, _, address_type = response
            if version != SOCKS_VERSION:
                logger.error(f"不支持的SOCKS版本: {version}")
                return False

            if status != 0x00:
                logger.error(f"连接失败: {status}")
                return False

            # 跳过绑定地址和端口
            if address_type == IPV4:
                socket_obj.recv(4)  # IPv4地址
            elif address_type == IPV6:
                socket_obj.recv(16)  # IPv6地址
            elif address_type == DOMAIN:
                domain_length = socket_obj.recv(1)[0]
                socket_obj.recv(domain_length)  # 域名

            socket_obj.recv(2)  # 端口

            return True

        except Exception as e:
            logger.error(f"发送SOCKS5连接命令失败: {e}")
            return False

    @staticmethod
    def send_socks5_response(socket_obj, status):
        """发送SOCKS5响应"""
        try:
            response = bytearray()
            response.append(SOCKS_VERSION)  # VER
            response.append(status)  # 状态码
            response.append(0x00)  # RSV
            response.append(IPV4)  # ATYP: IPv4

            # 绑定地址 (0.0.0.0)
            response.extend([0, 0, 0, 0])

            # 绑定端口 (0)
            response.extend([0, 0])

            socket_obj.sendall(response)
            return True
        except Exception as e:
            logger.error(f"发送SOCKS5响应失败: {e}")
            return False

    @staticmethod
    def parse_socks5_request(socket_obj):
        """解析SOCKS5请求，返回目标地址和端口"""
        try:
            # 接收请求头
            data = socket_obj.recv(4)
            if not data or len(data) < 4:
                logger.error("接收请求头失败")
                return None, None

            version, cmd, _, address_type = data

            if version != SOCKS_VERSION:
                logger.error(f"不支持的SOCKS版本: {version}")
                return None, None

            if cmd != CONNECT:
                logger.error(f"不支持的命令: {cmd}")
                return None, None

            # 解析地址
            target_addr = None
            if address_type == IPV4:
                addr_data = socket_obj.recv(4)
                if not addr_data or len(addr_data) != 4:
                    logger.error("接收IPv4地址失败")
                    return None, None
                target_addr = socket.inet_ntoa(addr_data)
            elif address_type == DOMAIN:
                domain_length = socket_obj.recv(1)[0]
                domain = socket_obj.recv(domain_length)
                if not domain or len(domain) != domain_length:
                    logger.error("接收域名失败")
                    return None, None
                target_addr = domain.decode('utf-8')
            elif address_type == IPV6:
                addr_data = socket_obj.recv(16)
                if not addr_data or len(addr_data) != 16:
                    logger.error("接收IPv6地址失败")
                    return None, None
                target_addr = socket.inet_ntop(socket.AF_INET6, addr_data)
            else:
                logger.error(f"不支持的地址类型: {address_type}")
                return None, None

            # 解析端口
            port_data = socket_obj.recv(2)
            if not port_data or len(port_data) != 2:
                logger.error("接收端口失败")
                return None, None
            target_port = int.from_bytes(port_data, 'big')

            logger.debug(f"SOCKS5目标: {target_addr}:{target_port}")
            return target_addr, target_port

        except Exception as e:
            logger.error(f"解析SOCKS5请求失败: {e}")
            return None, None

    @staticmethod
    def handle_socks5_negotiation(client_socket):
        """处理SOCKS5协议握手"""
        try:
            # 接收客户端的认证方法列表
            data = client_socket.recv(2)
            if not data or len(data) < 2:
                logger.error("接收认证方法列表失败")
                return False

            version, nmethods = data[0], data[1]
            if version != SOCKS_VERSION:
                logger.error(f"不支持的SOCKS版本: {version}")
                return False

            # 接收客户端支持的认证方法
            methods = client_socket.recv(nmethods)
            if not methods or len(methods) != nmethods:
                logger.error("接收认证方法失败")
                return False

            # 我们告诉客户端我们接受无认证方式 (0x00)
            client_socket.sendall(bytes([SOCKS_VERSION, 0x00]))
            return True

        except Exception as e:
            logger.error(f"SOCKS5握手失败: {e}")
            return False

    @staticmethod
    def handle_socks5_request(client_socket, connect_to_remote_func):
        """处理SOCKS5请求"""
        try:
            # 接收客户端请求
            data = client_socket.recv(4)
            if not data or len(data) < 4:
                logger.error("接收请求头失败")
                return False

            version, cmd, _, address_type = data

            if version != SOCKS_VERSION:
                logger.error(f"不支持的SOCKS版本: {version}")
                return False

            if cmd != CONNECT:
                logger.error(f"不支持的命令: {cmd}")
                client_socket.sendall(bytes([SOCKS_VERSION, 0x07, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
                return False

            # 获取目标地址和端口
            target_addr = None
            target_port = None

            if address_type == IPV4:
                addr_data = client_socket.recv(4)
                if not addr_data or len(addr_data) != 4:
                    logger.error("接收IPv4地址失败")
                    return False
                target_addr = socket.inet_ntoa(addr_data)
            elif address_type == DOMAIN:
                domain_length = client_socket.recv(1)[0]
                domain = client_socket.recv(domain_length)
                if not domain or len(domain) != domain_length:
                    logger.error("接收域名失败")
                    return False
                target_addr = domain.decode('utf-8')
            elif address_type == IPV6:
                addr_data = client_socket.recv(16)
                if not addr_data or len(addr_data) != 16:
                    logger.error("接收IPv6地址失败")
                    return False
                target_addr = socket.inet_ntop(socket.AF_INET6, addr_data)
            else:
                logger.error(f"不支持的地址类型: {address_type}")
                client_socket.sendall(bytes([SOCKS_VERSION, 0x08, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
                return False

            # 获取端口
            port_data = client_socket.recv(2)
            if not port_data or len(port_data) != 2:
                logger.error("接收端口失败")
                return False
            target_port = int.from_bytes(port_data, 'big')

            logger.info(f"SOCKS5目标: {target_addr}:{target_port}")

            # 连接到远程
            remote_socket = connect_to_remote_func(target_addr, target_port)
            if not remote_socket:
                client_socket.sendall(bytes([SOCKS_VERSION, 0x04, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
                return False

            # 告诉客户端连接已建立
            bind_addr = remote_socket.getsockname()[0]
            bind_port = remote_socket.getsockname()[1]

            response = bytearray()
            response.append(SOCKS_VERSION)  # VER
            response.append(0x00)  # SUCCESS
            response.append(0x00)  # RSV

            # 绑定地址
            if ":" in bind_addr:  # IPv6
                response.append(IPV6)
                for part in socket.inet_pton(socket.AF_INET6, bind_addr):
                    response.append(part)
            else:  # IPv4
                response.append(IPV4)
                for part in socket.inet_aton(bind_addr):
                    response.append(part)

            # 绑定端口
            response.extend(bind_port.to_bytes(2, 'big'))

            client_socket.sendall(response)

            return remote_socket

        except Exception as e:
            logger.error(f"处理SOCKS5请求失败: {e}")
            return False

    @staticmethod
    def connect_to_remote_socks5(remote_host, remote_port, username, password, target_addr, target_port):
        """连接到远程SOCKS5代理"""
        try:
            # 创建到远程代理的连接
            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # 设置超时，避免长时间阻塞
            remote_socket.settimeout(10)  # 减少超时时间，更快地跳过不可用代理

            # 尝试验证IP地址格式
            try:
                socket.inet_aton(remote_host)
            except socket.error:
                logger.error(f"无效的IP地址格式: {remote_host}")
                return None

            # 尝试连接
            try:
                remote_socket.connect((remote_host, int(remote_port)))
            except socket.error as e:
                logger.error(f"连接到远程代理 {remote_host}:{remote_port} 失败: {e}")
                remote_socket.close()
                return None

            # SOCKS5握手
            try:
                # 发送版本和认证方法 (同时支持无认证和用户名/密码认证)
                remote_socket.sendall(bytes([SOCKS_VERSION, 2, 0x00, 0x02]))

                # 接收服务器响应
                data = remote_socket.recv(2)
                if not data or len(data) < 2:
                    logger.error("接收远程代理认证响应失败")
                    remote_socket.close()
                    return None

                version, auth_method = data
                if version != SOCKS_VERSION:
                    logger.error(f"远程代理不支持SOCKS5: {version}")
                    remote_socket.close()
                    return None

                # 根据服务器选择的认证方法进行认证
                if auth_method == 0x00:
                    # 无认证
                    logger.debug("远程代理选择了无认证方式")
                    pass
                elif auth_method == 0x02:
                    # 用户名/密码认证
                    logger.debug("远程代理选择了用户名/密码认证方式")

                    # 发送用户名/密码认证
                    auth = bytearray()
                    auth.append(0x01)  # 认证版本

                    # 用户名
                    username_bytes = username.encode('utf-8')
                    auth.append(len(username_bytes))
                    auth.extend(username_bytes)

                    # 密码
                    password_bytes = password.encode('utf-8')
                    auth.append(len(password_bytes))
                    auth.extend(password_bytes)

                    remote_socket.sendall(auth)

                    # 接收认证响应
                    auth_response = remote_socket.recv(2)
                    if not auth_response or len(auth_response) < 2:
                        logger.error("接收远程代理认证结果失败")
                        remote_socket.close()
                        return None

                    _, auth_status = auth_response  # 忽略版本号
                    if auth_status != 0x00:
                        logger.error(f"远程代理认证失败: {auth_status}")
                        remote_socket.close()
                        return None
                else:
                    # 不支持的认证方法
                    logger.error(f"远程代理选择了不支持的认证方法: {auth_method}")
                    remote_socket.close()
                    return None
            except Exception as e:
                logger.error(f"SOCKS5握手失败: {e}")
                remote_socket.close()
                return None

            try:
                # 发送CONNECT请求
                request = bytearray()
                request.append(SOCKS_VERSION)  # VER
                request.append(CONNECT)  # CMD: CONNECT
                request.append(0x00)  # RSV

                # 目标地址
                try:
                    if target_addr.count('.') == 3:  # IPv4
                        # 验证IP地址格式
                        try:
                            socket.inet_aton(target_addr)
                            request.append(IPV4)
                            for part in socket.inet_aton(target_addr):
                                request.append(part)
                        except socket.error:
                            # 如果IP地址无效，尝试作为域名处理
                            # 移除不必要的警告，因为域名是正常情况
                            request.append(DOMAIN)
                            addr_bytes = target_addr.encode('utf-8')
                            request.append(len(addr_bytes))
                            request.extend(addr_bytes)
                    elif ':' in target_addr:  # IPv6
                        try:
                            socket.inet_pton(socket.AF_INET6, target_addr)
                            request.append(IPV6)
                            for part in socket.inet_pton(socket.AF_INET6, target_addr):
                                request.append(part)
                        except socket.error:
                            # 如果IPv6地址无效，尝试作为域名处理
                            # 移除不必要的警告，因为域名是正常情况
                            request.append(DOMAIN)
                            addr_bytes = target_addr.encode('utf-8')
                            request.append(len(addr_bytes))
                            request.extend(addr_bytes)
                    else:  # 域名
                        request.append(DOMAIN)
                        addr_bytes = target_addr.encode('utf-8')
                        request.append(len(addr_bytes))
                        request.extend(addr_bytes)
                except Exception as e:
                    logger.error(f"处理目标地址时出错: {e}")
                    remote_socket.close()
                    return None

                # 目标端口
                try:
                    request.extend(target_port.to_bytes(2, 'big'))
                except Exception as e:
                    logger.error(f"处理目标端口时出错: {e}")
                    remote_socket.close()
                    return None

                remote_socket.sendall(request)

                # 接收响应
                try:
                    response = remote_socket.recv(4)
                    if not response or len(response) < 4:
                        logger.error("接收远程代理连接响应失败")
                        remote_socket.close()
                        return None

                    version, status, _, address_type = response
                    if status != 0x00:
                        logger.error(f"远程代理连接失败: {status}")
                        remote_socket.close()
                        return None

                    # 跳过绑定地址和端口
                    if address_type == IPV4:
                        remote_socket.recv(4)  # IPv4地址
                    elif address_type == IPV6:
                        remote_socket.recv(16)  # IPv6地址
                    elif address_type == DOMAIN:
                        domain_length = remote_socket.recv(1)[0]
                        remote_socket.recv(domain_length)  # 域名

                    remote_socket.recv(2)  # 端口
                except Exception as e:
                    logger.error(f"处理SOCKS5响应时出错: {e}")
                    remote_socket.close()
                    return None

                logger.info(f"成功连接到远程SOCKS5代理 {remote_host}:{remote_port}")
                return remote_socket
            except Exception as e:
                logger.error(f"发送CONNECT请求时出错: {e}")
                if 'remote_socket' in locals():
                    remote_socket.close()
                return None

        except Exception as e:
            logger.error(f"连接到远程SOCKS5代理失败: {e}")
            if 'remote_socket' in locals():
                remote_socket.close()
            return None
