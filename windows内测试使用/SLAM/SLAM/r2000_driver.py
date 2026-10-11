import socket
import struct
import threading
import time
import numpy as np
import requests
from queue import Queue

# ================= 配置区域 =================
LIDAR_IP = "192.168.192.100"

class R2000Driver(threading.Thread):
    def __init__(self, freq=35, samples=2400):
        super().__init__()
        self.daemon = True
        self.running = True
        self.freq = freq
        self.samples = samples
        
        # SLAM 专用的帧队列 (建议长度设小一点，保证实时性)
        self.frame_queue = Queue(maxsize=10)
        
        self.data_lock = threading.Lock()
        self._buf_x, self._buf_y = [], []
        self.handle = None

    def run(self):
        """核心数据获取循环"""
        try:
            # 1. 初始化雷达参数
            requests.get(f"http://{LIDAR_IP}/cmd/release_handle?handle=all", timeout=1)
            requests.get(f"http://{LIDAR_IP}/cmd/set_parameter", 
                         params={'scan_frequency': self.freq, 'samples_per_scan': self.samples}, timeout=1)
            
            # 2. 请求 TCP 通道
            res = requests.get(f"http://{LIDAR_IP}/cmd/request_handle_tcp", 
                               params={'packet_type': 'C', 'watchdogtimeout': 5000}, timeout=1).json()
            self.handle, port = res['handle'], res['port']
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((LIDAR_IP, port))
            requests.get(f"http://{LIDAR_IP}/cmd/start_scanoutput", params={'handle': self.handle}, timeout=1)
            
            # 3. 启动心跳
            threading.Thread(target=self._watchdog, daemon=True).start()
            print(f"[Driver] R2000 已连接，频率: {self.freq}Hz, 点数: {self.samples}")
        except Exception as e:
            print(f"[Driver] 连接失败: {e}"); return

        raw_buffer = b""
        while self.running:
            try:
                chunk = sock.recv(65536)
                if not chunk: break
                raw_buffer += chunk
                while len(raw_buffer) >= 72:
                    magic_idx = raw_buffer.find(b'\x5c\xa2')
                    if magic_idx == -1: raw_buffer = raw_buffer[-1:]; break
                    if magic_idx > 0: raw_buffer = raw_buffer[magic_idx:]
                    if len(raw_buffer) < 12: break
                    p_size = struct.unpack('<I', raw_buffer[4:8])[0]
                    h_size = struct.unpack('<H', raw_buffer[8:10])[0]
                    if len(raw_buffer) < p_size: break 
                    packet = raw_buffer[:p_size]
                    raw_buffer = raw_buffer[p_size:]
                    
                    # 每一圈开始（packet_number=0）时打包数据
                    if struct.unpack('<H', packet[42:44])[0] == 0:
                        if self._buf_x:
                            # --- SLAM 核心重构：打包成字典并推入队列 ---
                            timestamp = time.time()
                            pts_x = np.concatenate(self._buf_x)
                            pts_y = np.concatenate(self._buf_y)
                            
                            # 转换为米(m)，SLAM 算法标准单位
                            points = np.vstack((pts_x, pts_y)).T / 1000.0
                            
                            frame = {
                                "timestamp": timestamp,
                                "points": points # shape: (N, 2)
                            }
                            
                            # 保持队列最新
                            if self.frame_queue.full():
                                try: self.frame_queue.get_nowait()
                                except: pass
                            self.frame_queue.put(frame)
                            
                            self._buf_x, self._buf_y = [], []
                    
                    payload = packet[h_size:]
                    raw_data = np.frombuffer(payload, dtype=np.uint32)
                    if raw_data.size > 0:
                        dist = (raw_data & 0x000FFFFF).astype(np.float32)
                        valid = (dist < 1048575) & (dist > 20) 
                        if np.any(valid):
                            d, idx = dist[valid], np.arange(len(valid))[valid]
                            rad = np.deg2rad((struct.unpack('<i', packet[44:48])[0] + idx * struct.unpack('<i', packet[48:52])[0]) / 10000.0)
                            self._buf_x.append(-d * np.sin(rad)) 
                            self._buf_y.append(d * np.cos(rad))
            except Exception as e:
                print(f"[Driver] 数据接收异常: {e}"); break

    def _watchdog(self):
        while self.running:
            time.sleep(2)
            if self.handle:
                try: requests.get(f"http://{LIDAR_IP}/cmd/feed_watchdog", params={'handle': self.handle}, timeout=0.5)
                except: pass

    def stop(self):
        self.running = False
        if self.handle:
            requests.get(f"http://{LIDAR_IP}/cmd/release_handle", params={'handle': self.handle}, timeout=0.5)

# --- 测试用例：验证驱动是否能独立运行 ---
if __name__ == "__main__":
    driver = R2000Driver(freq=20, samples=1200) # SLAM 建议先用低频调试
    driver.start()
    try:
        while True:
            if not driver.frame_queue.empty():
                frame = driver.frame_queue.get()
                print(f"收到帧: 时间={frame['timestamp']:.4f}, 点数={len(frame['points'])}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        driver.stop()