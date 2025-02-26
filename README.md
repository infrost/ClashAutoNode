# ClashAutoNode
一个利用clash api的自动低延迟节点选择、自动节点切换工具，支持规则定义。An automatic low-latency node selection and automatic ip switching tool using the clash api, with support for rule definitions.

### config.json 配置说明

```json
{
    "global":{
        "clash_api_url": "http://127.0.0.1:9999", # clash外部控制器的地址，不是clash的http代理地址！
        "secret": "you_secret", #clash控制器的密钥
        "com_port": "20210", #这个是程序监听的端口，支持从这个端口发送指令让程序切换ip
        "selector": "GLOBAL", # 这个Selector： GLOBAL、Direct、<ProxyGroup>里标注的等，每个订阅的selector都是不一样的
        "mode": "global" # 这个和selector是两个概念，这里的是比如Global（全局）、Rule（规则）、Direct（直连）等
    },
    "delay_list":{
        "tolerance": 3000, # 大于该延迟值（ms）的会被忽略
        "skip_keywords":{
            "start_with":["GLOBAL", "DIRECT", "REJECT", "剩余流量", "套餐到期","推荐使用", "故障转移", "电报群", "自动选择", "节点用不了"], #以特定字符开头
            "end_with": "", #以特定字符结尾
            "contains": ["-4x"], # 只要节点包含“-4x”字符的均会被跳过
            "reverse": false
        },
        "update_interval": "1200" # 延迟表刷新间隔（s）
    },
    "ipautochange": {
        "enable": false, # enable以启动定时更换ip地址
        "refresh_interval": "60" # ip自动切换间隔（s）
    }
}
```

### 从外部发送指令立即更换ip

使用以下代码/将以下代码集成到你的项目中即可：
```python
import socket

def send_switch_request():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('localhost', com_port))
    client_socket.sendall(b"switch")
    client_socket.close()

send_switch_request() # 立即切换ip
