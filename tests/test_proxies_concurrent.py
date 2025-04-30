import requests
import concurrent.futures
import time
import argparse
import json
from urllib.parse import urlparse

def test_proxy(proxy_port, test_url="https://httpbin.org/ip", timeout=10):
    """测试单个代理"""
    proxy_url = f"127.0.0.1:{proxy_port}"
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
                    "time": f"{elapsed:.2f}秒"
                }
            except Exception as e:
                return {
                    "proxy": proxy_url,
                    "status": "解析失败",
                    "error": str(e),
                    "time": f"{elapsed:.2f}秒"
                }
        else:
            return {
                "proxy": proxy_url,
                "status": f"HTTP错误: {response.status_code}",
                "time": f"{elapsed:.2f}秒"
            }
    except requests.exceptions.ConnectTimeout:
        return {
            "proxy": proxy_url,
            "status": "连接超时",
            "time": f"{time.time() - start_time:.2f}秒"
        }
    except requests.exceptions.ReadTimeout:
        return {
            "proxy": proxy_url,
            "status": "读取超时",
            "time": f"{time.time() - start_time:.2f}秒"
        }
    except requests.exceptions.ProxyError:
        return {
            "proxy": proxy_url,
            "status": "代理错误",
            "time": f"{time.time() - start_time:.2f}秒"
        }
    except Exception as e:
        return {
            "proxy": proxy_url,
            "status": "错误",
            "error": str(e),
            "time": f"{time.time() - start_time:.2f}秒"
        }

def run_concurrent_tests(start_port, num_ports, concurrency, test_url, timeout):
    """并发测试多个代理"""
    ports = list(range(start_port, start_port + num_ports))
    results = []
    successful = 0
    unique_ips = set()
    
    print(f"开始测试 {len(ports)} 个代理端口，并发数: {concurrency}")
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
                    unique_ips.add(ip)
                    successful += 1
                    print(f"端口 {port}: 成功 - IP: {ip} ({result['time']})")
                else:
                    print(f"端口 {port}: {status} ({result['time']})")
                    
            except Exception as e:
                print(f"端口 {port}: 测试异常 - {str(e)}")
                results.append({
                    "proxy": f"127.0.0.1:{port}",
                    "status": "测试异常",
                    "error": str(e)
                })
    
    total_time = time.time() - start_time
    
    # 打印汇总信息
    print("\n" + "=" * 60)
    print(f"测试完成! 总耗时: {total_time:.2f}秒")
    print(f"成功率: {successful}/{len(ports)} ({successful/len(ports)*100:.1f}%)")
    print(f"唯一IP数量: {len(unique_ips)}")
    
    if unique_ips:
        print("\n唯一IP列表:")
        for ip in sorted(unique_ips):
            count = sum(1 for r in results if r.get("status") == "成功" and r.get("ip") == ip)
            print(f"  {ip}: {count}个代理")
    
    return results

def main():
    parser = argparse.ArgumentParser(description="并发测试多个SOCKS5代理")
    parser.add_argument("--start-port", type=int, default=10000, help="起始端口号")
    parser.add_argument("--num-ports", type=int, default=10, help="测试端口数量")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--url", default="https://httpbin.org/ip", help="测试URL")
    parser.add_argument("--timeout", type=int, default=10, help="请求超时时间(秒)")
    parser.add_argument("--output", help="输出结果到JSON文件")
    
    args = parser.parse_args()
    
    try:
        results = run_concurrent_tests(
            args.start_port, 
            args.num_ports, 
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
