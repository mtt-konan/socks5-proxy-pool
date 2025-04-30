import requests
import argparse
import sys

def test_http_proxy(proxy_url, test_url="http://httpbin.org/ip"):
    """测试HTTP代理"""
    try:
        print(f"使用HTTP代理 {proxy_url} 访问 {test_url}")
        
        proxies = {
            "http": f"http://{proxy_url}",
            "https": f"http://{proxy_url}"
        }
        
        response = requests.get(test_url, proxies=proxies, timeout=10)
        
        if response.status_code == 200:
            print(f"成功! 状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return True
        else:
            print(f"失败! 状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_https_proxy(proxy_url, test_url="https://httpbin.org/ip"):
    """测试HTTPS代理"""
    try:
        print(f"使用HTTPS代理 {proxy_url} 访问 {test_url}")
        
        proxies = {
            "http": f"http://{proxy_url}",
            "https": f"http://{proxy_url}"
        }
        
        response = requests.get(test_url, proxies=proxies, timeout=10, verify=True)
        
        if response.status_code == 200:
            print(f"成功! 状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return True
        else:
            print(f"失败! 状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_socks5_proxy(proxy_url, test_url="https://httpbin.org/ip"):
    """测试SOCKS5代理"""
    try:
        print(f"使用SOCKS5代理 {proxy_url} 访问 {test_url}")
        
        proxies = {
            "http": f"socks5://{proxy_url}",
            "https": f"socks5://{proxy_url}"
        }
        
        response = requests.get(test_url, proxies=proxies, timeout=10)
        
        if response.status_code == 200:
            print(f"成功! 状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return True
        else:
            print(f"失败! 状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
    except Exception as e:
        print(f"错误: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="测试HTTP/HTTPS/SOCKS5代理")
    parser.add_argument("--proxy", default="127.0.0.1:10000", help="代理地址 (默认: 127.0.0.1:10000)")
    parser.add_argument("--url", default="https://httpbin.org/ip", help="测试URL (默认: https://httpbin.org/ip)")
    parser.add_argument("--protocol", choices=["http", "https", "socks5", "all"], default="all", 
                        help="测试协议 (默认: all)")
    
    args = parser.parse_args()
    
    success = True
    
    if args.protocol in ["http", "all"]:
        print("\n=== 测试 HTTP 代理 ===")
        if not test_http_proxy(args.proxy, args.url.replace("https://", "http://")):
            success = False
    
    if args.protocol in ["https", "all"]:
        print("\n=== 测试 HTTPS 代理 ===")
        if not test_https_proxy(args.proxy, args.url):
            success = False
    
    if args.protocol in ["socks5", "all"]:
        print("\n=== 测试 SOCKS5 代理 ===")
        if not test_socks5_proxy(args.proxy, args.url):
            success = False
    
    if success:
        print("\n所有测试都成功!")
        return 0
    else:
        print("\n部分测试失败!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
