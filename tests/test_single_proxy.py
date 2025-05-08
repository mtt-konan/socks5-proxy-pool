"""
测试单个代理连接
"""

import socket
import sys
import time
import argparse

def socks5_handshake(sock, username=None, password=None):
    """执行SOCKS5握手"""
    print("开始SOCKS5握手...")
    
    # 发送握手包
    if username and password:
        # 支持无认证和用户名/密码认证
        sock.sendall(bytes([0x05, 0x02, 0x00, 0x02]))
    else:
        # 只支持无认证
        sock.sendall(bytes([0x05, 0x01, 0x00]))
    
    # 接收响应
    response = sock.recv(2)
    print(f"握手响应: {response.hex()}")
    
    if len(response) < 2:
        print("握手响应不完整")
        return False
    
    if response[0] != 0x05:
        print(f"不支持的SOCKS版本: {response[0]}")
        return False
    
    # 处理认证方法
    auth_method = response[1]
    print(f"服务器选择的认证方法: {auth_method}")
    
    if auth_method == 0x00:
        # 无认证
        print("服务器不需要认证")
        return True
    elif auth_method == 0x02 and username and password:
        # 用户名/密码认证
        print("服务器需要用户名/密码认证")
        
        # 构建认证数据包
        auth_packet = bytearray([0x01])  # 认证协议版本
        
        # 用户名
        username_bytes = username.encode('utf-8')
        auth_packet.append(len(username_bytes))
        auth_packet.extend(username_bytes)
        
        # 密码
        password_bytes = password.encode('utf-8')
        auth_packet.append(len(password_bytes))
        auth_packet.extend(password_bytes)
        
        # 发送认证数据
        sock.sendall(auth_packet)
        print(f"发送认证数据: {auth_packet.hex()}")
        
        # 接收认证响应
        auth_response = sock.recv(2)
        print(f"认证响应: {auth_response.hex()}")
        
        if len(auth_response) < 2:
            print("认证响应不完整")
            return False
        
        if auth_response[1] != 0x00:
            print(f"认证失败: {auth_response[1]}")
            return False
        
        print("认证成功")
        return True
    else:
        print(f"不支持的认证方法: {auth_method}")
        return False

def socks5_connect(sock, target_addr, target_port):
    """通过SOCKS5代理连接到目标"""
    print(f"开始连接到目标: {target_addr}:{target_port}")
    
    # 构建CONNECT请求
    connect_request = bytearray([0x05, 0x01, 0x00])  # SOCKS5, CONNECT, 保留字段
    
    # 处理目标地址
    try:
        # 尝试作为IPv4处理
        socket.inet_aton(target_addr)
        connect_request.append(0x01)  # IPv4
        for part in socket.inet_aton(target_addr):
            connect_request.append(part)
        print(f"目标地址作为IPv4处理: {target_addr}")
    except socket.error:
        try:
            # 尝试作为IPv6处理
            if ':' in target_addr:
                socket.inet_pton(socket.AF_INET6, target_addr)
                connect_request.append(0x04)  # IPv6
                for part in socket.inet_pton(socket.AF_INET6, target_addr):
                    connect_request.append(part)
                print(f"目标地址作为IPv6处理: {target_addr}")
            else:
                # 作为域名处理
                raise socket.error()
        except socket.error:
            # 作为域名处理
            domain_bytes = target_addr.encode('utf-8')
            connect_request.append(0x03)  # 域名
            connect_request.append(len(domain_bytes))
            connect_request.extend(domain_bytes)
            print(f"目标地址作为域名处理: {target_addr}")
    
    # 添加端口（网络字节序，大端）
    connect_request.extend(target_port.to_bytes(2, 'big'))
    
    # 发送连接请求
    print(f"发送连接请求: {connect_request.hex()}")
    sock.sendall(connect_request)
    
    # 接收连接响应
    response = sock.recv(4)  # 先读取头部4字节
    print(f"连接响应头部: {response.hex()}")
    
    if len(response) < 4:
        print("连接响应不完整")
        return False
    
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
        print(f"连接失败: {error_msg}")
        return False
    
    # 根据地址类型读取剩余数据
    atyp = response[3]
    if atyp == 0x01:  # IPv4
        addr_port = sock.recv(4 + 2)  # 4字节IPv4地址 + 2字节端口
        print(f"绑定地址(IPv4): {addr_port.hex()}")
    elif atyp == 0x03:  # 域名
        domain_len = sock.recv(1)[0]
        addr_port = sock.recv(domain_len + 2)  # 域名 + 2字节端口
        print(f"绑定地址(域名): {addr_port.hex()}")
    elif atyp == 0x04:  # IPv6
        addr_port = sock.recv(16 + 2)  # 16字节IPv6地址 + 2字节端口
        print(f"绑定地址(IPv6): {addr_port.hex()}")
    else:
        print(f"不支持的地址类型: {atyp}")
        return False
    
    print("连接成功")
    return True

def test_proxy(proxy_host, proxy_port, username, password, target_url="httpbin.org", target_port=80):
    """测试代理连接"""
    print(f"测试代理: {proxy_host}:{proxy_port}")
    print(f"用户名: {username}, 密码: {password}")
    print(f"目标: {target_url}:{target_port}")
    
    try:
        # 连接到代理
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        print(f"连接到代理服务器 {proxy_host}:{proxy_port}...")
        sock.connect((proxy_host, proxy_port))
        print("连接到代理服务器成功")
        
        # SOCKS5握手
        if not socks5_handshake(sock, username, password):
            print("SOCKS5握手失败")
            sock.close()
            return False
        
        # 通过代理连接到目标
        if not socks5_connect(sock, target_url, target_port):
            print("通过代理连接到目标失败")
            sock.close()
            return False
        
        # 如果是HTTP请求，发送简单的HTTP请求
        if target_port == 80:
            http_request = f"GET / HTTP/1.1\r\nHost: {target_url}\r\nConnection: close\r\n\r\n"
            sock.sendall(http_request.encode('utf-8'))
            print(f"发送HTTP请求: {http_request.strip()}")
            
            # 接收响应
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if len(response) > 1024:  # 只显示前1KB
                    break
            
            print(f"收到响应: {response[:1024].decode('utf-8', errors='ignore')}")
        
        sock.close()
        print("测试成功")
        return True
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="测试单个代理连接")
    parser.add_argument("--host", required=True, help="代理服务器主机地址")
    parser.add_argument("--port", type=int, required=True, help="代理服务器端口")
    parser.add_argument("--username", default="", help="代理用户名")
    parser.add_argument("--password", default="", help="代理密码")
    parser.add_argument("--target", default="httpbin.org", help="目标URL")
    parser.add_argument("--target-port", type=int, default=80, help="目标端口")
    
    args = parser.parse_args()
    
    # 如果用户名或密码为空，则设置为None
    username = args.username if args.username else None
    password = args.password if args.password else None
    
    # 测试代理
    success = test_proxy(
        args.host, 
        args.port, 
        username, 
        password, 
        args.target, 
        args.target_port
    )
    
    # 返回状态码
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
