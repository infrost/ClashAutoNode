"""
程序支持接收其他程序请求，从而立即更换ip，默认端口20210
# 使用例子
import socket
from ipautochange import send_switch_request
send_switch_request() # 立即切换ip
"""
import requests
import time
import logging
import os
import json
from concurrent.futures import ThreadPoolExecutor
import threading
import socket
from urllib.parse import quote
import re
import sys

# 初始化日志配置
log_dir = './logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

program_log_path = os.path.join(log_dir, 'program.log')
delay_list_path = os.path.join(log_dir, 'delaylist.txt')

# 创建日志记录器
logger = logging.getLogger('program_logger')
logger.setLevel(logging.INFO)

# 创建文件处理器
file_handler = logging.FileHandler(program_log_path, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# 创建控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

#加载配置
def load_config():
    base_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_path, 'config.json')
    with open(config_path, 'r', encoding = 'utf-8') as f:
        return json.load(f)

logger.info("config loaded")

config = load_config()
clash_api_url = config['global']['clash_api_url']
secret = config['global']['secret']
com_port = int(config['global']['com_port'])
# Selector： GLOBAL、Direct、<ProxyGroup>里标注的等
clash_selector = config['global']['selector']
#这个和selector是两个概念，clash_mode指的是模式，比如Global、Rule、Direct等
clash_mode = config['global']['mode']

delay_tolerance = int(config['delay_list']['tolerance'])
skip_startwith_keywords = config['delay_list']['skip_keywords']['start_with']
skip_contains_keywords = config['delay_list']['skip_keywords']['contains']
skip_endwith_keywords = config['delay_list']['skip_keywords']['end_with']
keywords_reverse = bool(config['delay_list']['skip_keywords']['reverse'])
update_interval = int(config['delay_list']['update_interval'])

ipautochange_enable = bool(config['ipautochange']["enable"])
refresh_interval = int(config['ipautochange']['refresh_interval'])


def get_current_config():
    response = requests.get(f'{clash_api_url}/configs', headers=headers)
    response.raise_for_status()
    return response.json()

def switch_to_mode(clash_mode):
    payload = {'mode': f"{clash_mode}"}
    response = requests.patch(f'{clash_api_url}/configs', headers=headers, json=payload)
    response.raise_for_status()
    if response.status_code == 204:
        logger.info(f"Successfully switched to {clash_mode} mode")
    else:
        logger.info(f"Failed to switch mode. Status code: {response.status_code}")

# 获取所有代理节点
headers = {'Authorization': f'Bearer {secret}'}
def get_proxies():
    response = requests.get(f'{clash_api_url}/proxies', headers=headers)
    response.raise_for_status()
    proxies = response.json()['proxies']
    return proxies

# 获取单个代理节点的延迟
def get_proxy_delay(proxy_name):
    try:
        encoded_proxy_name = quote(proxy_name, safe='')
        response = requests.get(
            f'{clash_api_url}/proxies/{proxy_name}/delay',
            headers=headers,
            params={'timeout': 3000, 'url': 'http://www.google.com'}
        )
        response.raise_for_status()
        return proxy_name, response.json()['delay']
    except requests.RequestException:
        return proxy_name, float('inf')

# 更新延迟表
def update_delay_log(proxies):
    with ThreadPoolExecutor() as executor:
        proxy_delays = list(executor.map(get_proxy_delay, proxies))
    
    with open(delay_list_path, 'w', encoding='utf-8') as f:
        for proxy_name, delay in proxy_delays:
            skip = (
                any(proxy_name.startswith(keyword) for keyword in skip_startwith_keywords) or
                any(keyword in proxy_name for keyword in skip_contains_keywords) or
                any(proxy_name.endswith(keyword) for keyword in skip_endwith_keywords)
            )
            if keywords_reverse:
                skip = not skip
            if not skip:
                f.write(f'{proxy_name} {delay}\n')
                logger.info(f'Updated delay for proxy: {proxy_name} - {delay}')

def load_delay_log():
    with open(delay_list_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    proxy_delays = []
    for line in lines:
        match = re.match(r'^(.*)\s+(\d+)$', line.strip())
        if match:
            proxy_name = match.group(1)
            delay = match.group(2)
            if delay != 'inf':
                try:
                    delay = int(delay)
                    if delay < delay_tolerance:
                        proxy_delays.append({'name': proxy_name, 'delay': delay})
                except ValueError:
                    pass
    
    return proxy_delays

#获取代理后的ip地址
def get_current_ip():
    try:
        ip_response = requests.get('http://ipinfo.io/ip')
        ip_response.raise_for_status()
        current_ip = ip_response.text.strip()
        return current_ip
    except requests.RequestException as e:
        logger.error(f'Failed to get current IP address, error: {e}')
        return None

# 切换代理
def switch_proxy(proxy_name):

    try:
        logger.info(f"Switching proxy using URL: {f'{clash_api_url}/proxies/{clash_selector}'}")
        encoded_proxy_name = quote(proxy_name, safe='')
        response = requests.put(
            f'{clash_api_url}/proxies/{clash_selector}',
            headers=headers,
            json={'name': proxy_name}
        )
        response.raise_for_status()
        logger.info(f'Successfully switched to proxy: {proxy_name}')
        current_ip = get_current_ip()
        if current_ip:
            logger.info(f'Current IP address: {current_ip}')
    except requests.RequestException as e:
        logger.error(f'Failed to switch proxy: {proxy_name}, error: {e}')

def proxy_manager(proxy_index_lock, proxy_index):
    last_update_time = 0
    try:
        current_config = get_current_config()
        current_mode = current_config.get('mode')
        
        logger.info(f"Current mode: {current_mode}")
        
        if current_mode == '{clash_mode}':
            logger.info(f"已位于{clash_mode}模式")
        else:
            switch_to_mode(clash_mode)
            logger.info("正在接管所有系统流量...")
    
    except requests.exceptions.RequestException as e:
        logger.error(f"An error occurred: {e}")

    while True:
        current_time = time.time()

        # 每20分钟更新一次延迟表
        if current_time - last_update_time >= update_interval:
            logger.info("Updating delay log...")
            proxies = get_proxies()
            update_delay_log(proxies)
            last_update_time = current_time

        # 从延迟表中读取代理节点
        valid_proxies = load_delay_log()

        # 每60秒刷新一次IP
        if not valid_proxies:
            logger.warning("No valid proxies found. Please check your delay log.")
        else:
            if ipautochange_enable:
                with proxy_index_lock:
                    # 循环切换代理
                    if proxy_index[0] >= len(valid_proxies):
                        proxy_index[0] = 0  # 重置代理索引
                    switch_proxy(valid_proxies[proxy_index[0]]['name'])
                    proxy_index[0] = (proxy_index[0] + 1) % len(valid_proxies)  # 更新代理索引
                time.sleep(refresh_interval)
            else:
                # 选择延迟最低的节点
                best_proxy = min(valid_proxies, key=lambda p: p['delay'])
                logger.info(f"Minimal delay: {best_proxy}")
                switch_proxy(best_proxy['name'])
                time.sleep(refresh_interval)

def handle_client(client_socket, valid_proxies, proxy_index_lock, proxy_index):
    data = client_socket.recv(1024)
    if data == b"switch":
        logger.info("Received switch request")
        with proxy_index_lock:
            switch_proxy(valid_proxies[proxy_index[0]]['name'])
            proxy_index[0] = (proxy_index[0] + 1) % len(valid_proxies)  # 更新代理索引
    client_socket.close()

def server(proxy_index_lock, proxy_index):
    valid_proxies = load_delay_log()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('localhost', com_port))
    server_socket.listen(1)
    logger.info(f"Server started, waiting for connections, listening on {com_port}...")

    while True:
        client_socket, addr = server_socket.accept()
        logger.info(f"Connection from {addr}")
        client_handler = threading.Thread(
            target=handle_client,
            args=(client_socket, valid_proxies, proxy_index_lock, proxy_index)
        )
        client_handler.start()

def send_switch_request():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('localhost', com_port))
    client_socket.sendall(b"switch")
    client_socket.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    proxy_index = [0]  # 使用列表来保持可变性
    proxy_index_lock = threading.Lock()

    # 创建并启动代理管理线程
    proxy_thread = threading.Thread(target=proxy_manager, args=(proxy_index_lock, proxy_index), daemon=True)
    proxy_thread.start()

    # 启动服务器线程
    server_thread = threading.Thread(target=server, args=(proxy_index_lock, proxy_index), daemon=True)
    server_thread.start()

    # 等待两个线程结束
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
