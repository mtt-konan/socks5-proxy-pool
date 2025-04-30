import requests
import concurrent.futures
import time
import argparse
import json
import threading
from collections import Counter

def get_proxy_from_server(server_url="http://127.0.0.1:7777"):
    """从代理服务器获取代理地址"""
    try:
        response = requests.get(server_url, timeout=5)
        if response.status_code == 200:
            proxy = response.text.strip()
            return proxy
        else:
            print(f"获取代理失败: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"获取代理出错: {e}")
        return None

def test_proxy(proxy_url, test_url="https://httpbin.org/ip", timeout=10):
    """测试单个代理"""
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
                    "proxy": proxy_url,
                    "status": "成功",
                    "ip": ip,
                    "time": elapsed
                }
            except Exception as e:
                return {
                    "proxy": proxy_url,
                    "status": "解析失败",
                    "error": str(e),
                    "time": elapsed
                }
        else:
            return {
                "proxy": proxy_url,
                "status": f"HTTP错误: {response.status_code}",
                "time": elapsed
            }
    except requests.exceptions.ConnectTimeout:
        return {
            "proxy": proxy_url,
            "status": "连接超时",
            "time": time.time() - start_time
        }
    except requests.exceptions.ReadTimeout:
        return {
            "proxy": proxy_url,
            "status": "读取超时",
            "time": time.time() - start_time
        }
    except requests.exceptions.ProxyError:
        return {
            "proxy": proxy_url,
            "status": "代理错误",
            "time": time.time() - start_time
        }
    except Exception as e:
        return {
            "proxy": proxy_url,
            "status": "错误",
            "error": str(e),
            "time": time.time() - start_time
        }

def worker(server_url, test_url, timeout, results, lock):
    """工作线程，获取代理并测试"""
    proxy = get_proxy_from_server(server_url)
    if not proxy:
        with lock:
            results.append({
                "proxy": None,
                "status": "获取代理失败",
                "time": 0
            })
        return
    
    result = test_proxy(proxy, test_url, timeout)
    
    with lock:
        results.append(result)
        
    # 打印结果
    status = result["status"]
    if status == "成功":
        print(f"代理 {proxy}: 成功 - IP: {result['ip']} ({result['time']:.2f}秒)")
    else:
        error = result.get("error", "")
        print(f"代理 {proxy}: {status} {error} ({result['time']:.2f}秒)")

def run_high_concurrency_test(concurrency, server_url, test_url, timeout):
    """运行高并发测试"""
    results = []
    lock = threading.Lock()
    threads = []
    
    print(f"开始高并发测试，并发数: {concurrency}")
    print(f"代理服务器: {server_url}")
    print(f"测试URL: {test_url}")
    print("-" * 60)
    
    start_time = time.time()
    
    # 创建并启动所有线程
    for i in range(concurrency):
        thread = threading.Thread(
            target=worker,
            args=(server_url, test_url, timeout, results, lock)
        )
        thread.daemon = True
        thread.start()
        threads.append(thread)
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
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
            print(f"  {ip}: {count}个请求")
    
    # 统计错误
    errors = Counter(r["status"] for r in results if r["status"] != "成功")
    if errors:
        print("\n错误统计:")
        for error, count in errors.most_common():
            print(f"  {error}: {count}个请求")
    
    return results

def main():
    parser = argparse.ArgumentParser(description="高并发测试代理服务器")
    parser.add_argument("--concurrency", type=int, default=100, help="并发数")
    parser.add_argument("--server", default="http://127.0.0.1:7777", help="代理服务器URL")
    parser.add_argument("--url", default="https://httpbin.org/ip", help="测试URL")
    parser.add_argument("--timeout", type=int, default=10, help="请求超时时间(秒)")
    parser.add_argument("--output", help="输出结果到JSON文件")
    
    args = parser.parse_args()
    
    try:
        results = run_high_concurrency_test(
            args.concurrency,
            args.server,
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
