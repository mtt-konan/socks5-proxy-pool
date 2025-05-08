"""
测试所有代理
"""

import concurrent.futures
import argparse
import time
import json
import os
import sys
import socket
import requests

def test_proxy(proxy_info, timeout=5):
    """测试单个代理"""
    host = proxy_info['host']
    port = proxy_info['port']
    username = proxy_info['username']
    password = proxy_info['password']
    
    # 构建代理URL
    if username and password:
        proxy_url = f"socks5://{username}:{password}@{host}:{port}"
    else:
        proxy_url = f"socks5://{host}:{port}"
    
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }
    
    start_time = time.time()
    try:
        # 测试连接
        response = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=timeout)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            try:
                # 解析响应，获取IP地址
                data = response.json()
                ip = data.get("origin", "未知")
                return {
                    "host": host,
                    "port": port,
                    "username": username,
                    "password": password,
                    "status": "成功",
                    "ip": ip,
                    "time": elapsed
                }
            except Exception as e:
                return {
                    "host": host,
                    "port": port,
                    "username": username,
                    "password": password,
                    "status": "解析失败",
                    "error": str(e),
                    "time": elapsed
                }
        else:
            return {
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "status": f"HTTP错误: {response.status_code}",
                "time": elapsed
            }
    except requests.exceptions.ConnectTimeout:
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "status": "连接超时",
            "time": time.time() - start_time
        }
    except requests.exceptions.ReadTimeout:
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "status": "读取超时",
            "time": time.time() - start_time
        }
    except requests.exceptions.ProxyError:
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "status": "代理错误",
            "time": time.time() - start_time
        }
    except Exception as e:
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "status": "错误",
            "error": str(e),
            "time": time.time() - start_time
        }

def load_proxies(proxy_file):
    """从文件加载代理列表"""
    proxies = []
    try:
        with open(proxy_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split()
                if len(parts) >= 2:
                    host = parts[0]
                    try:
                        port = int(parts[1])
                    except ValueError:
                        print(f"跳过无效端口: {parts[1]}")
                        continue
                    
                    username = parts[2] if len(parts) >= 3 else ""
                    password = parts[3] if len(parts) >= 4 else ""
                    
                    proxies.append({
                        'host': host,
                        'port': port,
                        'username': username,
                        'password': password
                    })
        
        print(f"从文件 {proxy_file} 加载了 {len(proxies)} 个代理")
        return proxies
    except Exception as e:
        print(f"加载代理列表失败: {e}")
        return []

def test_all_proxies(proxies, max_workers=10, timeout=5):
    """测试所有代理"""
    results = []
    successful = 0
    total = len(proxies)
    
    print(f"开始测试 {total} 个代理，最大并发数: {max_workers}，超时: {timeout}秒")
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_proxy = {executor.submit(test_proxy, proxy, timeout): proxy for proxy in proxies}
        
        # 处理结果
        for i, future in enumerate(concurrent.futures.as_completed(future_to_proxy)):
            proxy = future_to_proxy[future]
            try:
                result = future.result()
                results.append(result)
                
                # 打印进度
                status = result['status']
                if status == "成功":
                    successful += 1
                    print(f"[{i+1}/{total}] 代理 {proxy['host']}:{proxy['port']} 成功 - IP: {result.get('ip', '未知')} ({result['time']:.2f}秒)")
                else:
                    print(f"[{i+1}/{total}] 代理 {proxy['host']}:{proxy['port']} 失败: {status}")
                
            except Exception as e:
                print(f"[{i+1}/{total}] 代理 {proxy['host']}:{proxy['port']} 测试异常: {e}")
    
    total_time = time.time() - start_time
    
    print(f"\n测试完成! 总耗时: {total_time:.2f}秒")
    print(f"成功率: {successful}/{total} ({successful/total*100:.1f}%)")
    
    return results

def save_working_proxies(results, output_file):
    """保存可用的代理到文件"""
    working_proxies = [r for r in results if r['status'] == "成功"]
    
    if not working_proxies:
        print("没有找到可用的代理")
        return
    
    # 按响应时间排序
    working_proxies.sort(key=lambda x: x['time'])
    
    # 保存到文件
    with open(output_file, 'w') as f:
        for proxy in working_proxies:
            f.write(f"{proxy['host']} {proxy['port']} {proxy['username']} {proxy['password']}\n")
    
    print(f"已将 {len(working_proxies)} 个可用代理保存到 {output_file}")

def main():
    parser = argparse.ArgumentParser(description="测试所有代理")
    parser.add_argument("--proxy-file", default="all_proxies.txt", help="代理列表文件")
    parser.add_argument("--output", default="working_proxies.txt", help="可用代理输出文件")
    parser.add_argument("--workers", type=int, default=10, help="最大并发数")
    parser.add_argument("--timeout", type=int, default=5, help="请求超时时间(秒)")
    parser.add_argument("--limit", type=int, default=0, help="测试代理数量限制(0表示全部)")
    
    args = parser.parse_args()
    
    # 检查代理文件是否存在
    if not os.path.exists(args.proxy_file):
        print(f"代理列表文件 {args.proxy_file} 不存在")
        return
    
    # 加载代理
    proxies = load_proxies(args.proxy_file)
    
    # 限制测试数量
    if args.limit > 0 and args.limit < len(proxies):
        print(f"限制测试数量为前 {args.limit} 个代理")
        proxies = proxies[:args.limit]
    
    # 测试代理
    results = test_all_proxies(proxies, args.workers, args.timeout)
    
    # 保存可用代理
    save_working_proxies(results, args.output)
    
    # 保存详细结果
    with open("proxy_test_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"详细测试结果已保存到 proxy_test_results.json")

if __name__ == "__main__":
    main()
