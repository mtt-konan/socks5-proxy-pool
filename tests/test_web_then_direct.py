import requests
import concurrent.futures
import time
import argparse
import json
from collections import Counter

def get_proxies_from_server(server_url="http://127.0.0.1:7777", count=100):
    """从代理服务器获取多个代理地址"""
    proxies = []
    print(f"从服务器 {server_url} 获取 {count} 个代理...")
    
    for i in range(count):
        try:
            response = requests.get(server_url, timeout=5)
            if response.status_code == 200:
                proxy = response.text.strip()
                if proxy and proxy not in proxies:
                    proxies.append(proxy)
                    if (i+1) % 10 == 0:
                        print(f"已获取 {i+1} 个代理...")
            else:
                print(f"获取代理失败: HTTP {response.status_code}")
        except Exception as e:
            print(f"获取代理出错: {e}")
    
    # 提取端口号
    proxy_ports = []
    for proxy in proxies:
        try:
            port = int(proxy.split(':')[1])
            proxy_ports.append(port)
        except (IndexError, ValueError):
            print(f"无法解析代理地址: {proxy}")
    
    unique_ports = len(set(proxy_ports))
    print(f"获取了 {len(proxies)} 个代理，其中包含 {unique_ports} 个唯一端口")
    return proxy_ports

def test_proxy(port, test_url="https://httpbin.org/ip", timeout=10):
    """测试单个代理端口"""
    proxy_url = f"127.0.0.1:{port}"
    proxies = {
        "http": f"socks5://{proxy_url}",
        "https": f"socks5://{proxy_url}"
    }
    
    start_time = time.time()
    try:
        response = requests.get(test_url, proxies=proxies, timeout=timeout)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            try:
                # 解析响应，获取IP地址
                data = response.json()
                ip = data.get("origin", "未知")
                return {
                    "port": port,
                    "status": "成功",
                    "ip": ip,
                    "time": elapsed
                }
            except Exception as e:
                return {
                    "port": port,
                    "status": "解析失败",
                    "error": str(e),
                    "time": elapsed
                }
        else:
            return {
                "port": port,
                "status": f"HTTP错误: {response.status_code}",
                "time": elapsed
            }
    except requests.exceptions.ConnectTimeout:
        return {
            "port": port,
            "status": "连接超时",
            "time": time.time() - start_time
        }
    except requests.exceptions.ReadTimeout:
        return {
            "port": port,
            "status": "读取超时",
            "time": time.time() - start_time
        }
    except requests.exceptions.ProxyError:
        return {
            "port": port,
            "status": "代理错误",
            "time": time.time() - start_time
        }
    except Exception as e:
        return {
            "port": port,
            "status": "错误",
            "error": str(e),
            "time": time.time() - start_time
        }

def run_test(ports, concurrency, test_url, timeout):
    """测试多个代理端口"""
    results = []
    
    print(f"\n开始测试 {len(ports)} 个代理端口，并发数: {concurrency}")
    print(f"测试URL: {test_url}")
    print("-" * 60)
    
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        # 提交所有任务
        future_to_port = {
            executor.submit(test_proxy, port, test_url, timeout): port 
            for port in ports
        }
        
        # 处理结果
        for future in concurrent.futures.as_completed(future_to_port):
            port = future_to_port[future]
            try:
                result = future.result()
                results.append(result)
                
                # 打印结果
                status = result["status"]
                if status == "成功":
                    ip = result["ip"]
                    print(f"端口 {port}: 成功 - IP: {ip} ({result['time']:.2f}秒)")
                else:
                    error = result.get("error", "")
                    print(f"端口 {port}: {status} {error} ({result['time']:.2f}秒)")
                    
            except Exception as e:
                print(f"端口 {port}: 测试异常 - {str(e)}")
                results.append({
                    "port": port,
                    "status": "测试异常",
                    "error": str(e),
                    "time": 0
                })
    
    total_time = time.time() - start_time
    
    # 统计结果
    successful = sum(1 for r in results if r["status"] == "成功")
    unique_ips = set(r["ip"] for r in results if r["status"] == "成功")
    ip_counter = Counter(r["ip"] for r in results if r["status"] == "成功")
    
    # 打印汇总信息
    print("\n" + "=" * 60)
    print(f"测试完成! 总耗时: {total_time:.2f}秒")
    print(f"成功率: {successful}/{len(results)} ({successful/len(results)*100:.1f}%)")
    print(f"唯一IP数量: {len(unique_ips)}")
    
    if unique_ips:
        print("\n唯一IP列表:")
        for ip, count in ip_counter.most_common():
            print(f"  {ip}: {count}个端口")
    
    # 统计错误
    errors = Counter(r["status"] for r in results if r["status"] != "成功")
    if errors:
        print("\n错误统计:")
        for error, count in errors.most_common():
            print(f"  {error}: {count}个端口")
    
    return results

def main():
    parser = argparse.ArgumentParser(description="先从Web服务器获取代理，然后直接测试")
    parser.add_argument("--server", default="http://127.0.0.1:7777", help="代理服务器URL")
    parser.add_argument("--count", type=int, default=100, help="获取代理数量")
    parser.add_argument("--concurrency", type=int, default=20, help="测试并发数")
    parser.add_argument("--url", default="https://httpbin.org/ip", help="测试URL")
    parser.add_argument("--timeout", type=int, default=15, help="请求超时时间(秒)")
    parser.add_argument("--output", help="输出结果到JSON文件")
    
    args = parser.parse_args()
    
    try:
        # 第一步：从Web服务器获取代理
        proxy_ports = get_proxies_from_server(args.server, args.count)
        
        if not proxy_ports:
            print("没有获取到代理，测试终止")
            return
        
        # 第二步：测试获取到的代理
        results = run_test(
            proxy_ports,
            args.concurrency,
            args.url,
            args.timeout
        )
        
        # 保存结果到文件
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到: {args.output}")
            
    except KeyboardInterrupt:
        print("\n测试被用户中断!")
    except Exception as e:
        print(f"\n测试出错: {e}")

if __name__ == "__main__":
    main()
