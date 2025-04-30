import socket
import socks
import requests
import json
import time
import concurrent.futures
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('proxy_tester')

def test_proxy(proxy_port):
    """测试单个代理"""
    proxy_host = '127.0.0.1'
    
    start_time = time.time()
    logger.info(f"测试代理 {proxy_host}:{proxy_port}")
    
    try:
        # 设置SOCKS5代理
        session = requests.Session()
        session.proxies = {
            'http': f'socks5://{proxy_host}:{proxy_port}',
            'https': f'socks5://{proxy_host}:{proxy_port}'
        }
        
        # 设置超时
        response = session.get('https://ipinfo.io/json', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            duration = time.time() - start_time
            logger.info(f"代理 {proxy_host}:{proxy_port} 可用 - IP: {data.get('ip')} - 位置: {data.get('country')}, {data.get('region')}, {data.get('city')} - 耗时: {duration:.2f}秒")
            return True, data, duration
        else:
            logger.error(f"代理 {proxy_host}:{proxy_port} 返回错误状态码: {response.status_code}")
            return False, None, time.time() - start_time
            
    except requests.exceptions.RequestException as e:
        duration = time.time() - start_time
        logger.error(f"代理 {proxy_host}:{proxy_port} 连接失败: {e} - 耗时: {duration:.2f}秒")
        return False, None, duration
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"代理 {proxy_host}:{proxy_port} 测试出错: {e} - 耗时: {duration:.2f}秒")
        return False, None, duration

def test_without_proxy():
    """测试不使用代理的情况"""
    try:
        logger.info("测试直接连接（不使用代理）")
        start_time = time.time()
        response = requests.get('https://ipinfo.io/json', timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            duration = time.time() - start_time
            logger.info(f"直接连接可用 - IP: {data.get('ip')} - 位置: {data.get('country')}, {data.get('region')}, {data.get('city')} - 耗时: {duration:.2f}秒")
            return True, data, duration
        else:
            logger.error(f"直接连接返回错误状态码: {response.status_code}")
            return False, None, time.time() - start_time
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"直接连接测试出错: {e} - 耗时: {duration:.2f}秒")
        return False, None, duration

def main():
    """主函数"""
    # 首先测试不使用代理的情况
    direct_result = test_without_proxy()
    
    # 测试本地代理
    start_port = 10000
    end_port = 10009
    results = []
    
    # 使用线程池并行测试所有代理
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_port = {executor.submit(test_proxy, port): port for port in range(start_port, end_port + 1)}
        
        for future in concurrent.futures.as_completed(future_to_port):
            port = future_to_port[future]
            try:
                success, data, duration = future.result()
                results.append({
                    'port': port,
                    'success': success,
                    'data': data,
                    'duration': duration
                })
            except Exception as e:
                logger.error(f"获取端口 {port} 的测试结果时出错: {e}")
    
    # 显示测试结果摘要
    logger.info("\n测试结果摘要:")
    logger.info(f"直接连接: {'成功' if direct_result[0] else '失败'} - IP: {direct_result[1].get('ip') if direct_result[1] else 'N/A'}")
    
    success_count = sum(1 for r in results if r['success'])
    logger.info(f"测试了 {len(results)} 个代理，其中 {success_count} 个成功，{len(results) - success_count} 个失败")
    
    # 显示成功的代理
    if success_count > 0:
        logger.info("\n成功的代理:")
        for result in sorted([r for r in results if r['success']], key=lambda x: x['duration']):
            ip = result['data'].get('ip', 'N/A')
            country = result['data'].get('country', 'N/A')
            logger.info(f"127.0.0.1:{result['port']} - IP: {ip} - 国家: {country} - 耗时: {result['duration']:.2f}秒")

if __name__ == "__main__":
    main()
