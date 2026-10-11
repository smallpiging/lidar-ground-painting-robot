import sys, socket, struct, threading, time
import numpy as np
import requests
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, QMainWindow, QGraphicsEllipseItem, QGraphicsLineItem, 
                             QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QComboBox, QMessageBox)
from PyQt5.QtGui import QPainterPath, QColor
from PyQt5.QtCore import QTimer, Qt
from pyqtgraph import TextItem

# ================= 配置区域 =================
LIDAR_IP = "192.168.192.100"
DEFAULT_FREQ = 35        
DEFAULT_SAMPLES = 2400        
# ===========================================

class R2000HighSpeedClient(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.data_lock = threading.Lock()
        self.latest_cloud = (np.array([]), np.array([]))
        self._buf_x, self._buf_y = [], []
        self.handle = None

    def run(self):
        try:
            # 初始清理与参数设置
            requests.get(f"http://{LIDAR_IP}/cmd/release_handle?handle=all", timeout=1)
            requests.get(f"http://{LIDAR_IP}/cmd/set_parameter", 
                         params={'scan_frequency': DEFAULT_FREQ, 'samples_per_scan': DEFAULT_SAMPLES}, timeout=1)
            
            # 请求 TCP 通道
            res = requests.get(f"http://{LIDAR_IP}/cmd/request_handle_tcp", 
                               params={'packet_type': 'C', 'watchdogtimeout': 5000}, timeout=1).json()
            self.handle, port = res['handle'], res['port']
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((LIDAR_IP, port))
            requests.get(f"http://{LIDAR_IP}/cmd/start_scanoutput", params={'handle': self.handle}, timeout=1)
            
            # 启动独立心跳线程
            threading.Thread(target=self._watchdog, daemon=True).start()
        except Exception as e:
            print(f"后端连接失败: {e}"); return

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
                    
                    # 每一圈开始时（packet_number=0），提交上一圈数据
                    if struct.unpack('<H', packet[42:44])[0] == 0:
                        if self._buf_x:
                            with self.data_lock:
                                self.latest_cloud = (np.concatenate(self._buf_x), np.concatenate(self._buf_y))
                            self._buf_x, self._buf_y = [], []
                    
                    payload = packet[h_size:]
                    raw_data = np.frombuffer(payload, dtype=np.uint32)
                    if raw_data.size > 0:
                        dist = (raw_data & 0x000FFFFF).astype(np.float32)
                        valid = (dist < 1048575) & (dist > 20) 
                        if np.any(valid):
                            d, idx = dist[valid], np.arange(len(valid))[valid]
                            rad = np.deg2rad((struct.unpack('<i', packet[44:48])[0] + idx * struct.unpack('<i', packet[48:52])[0]) / 10000.0)
                            # 修复雷达左右反转
                            self._buf_x.append(-d * np.sin(rad)) 
                            self._buf_y.append(d * np.cos(rad))
            except: break

    def _watchdog(self):
        while self.running:
            time.sleep(2)
            if self.handle:
                try: requests.get(f"http://{LIDAR_IP}/cmd/feed_watchdog", params={'handle': self.handle}, timeout=0.5)
                except: pass

class RadarApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("R2000 Pro 工业监控终端")
        self.resize(1600, 800)
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout(self.main_widget)

        # 采样点数与分辨率映射 
        self.sample_map = {
            "1200": "0.300°", "2400": "0.150°", "3600": "0.100°", 
            "4200": "0.086°", "7200": "0.050°", "8400": "0.043°"
        }

        # --- 1. 参数设置行 ---
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("扫描点数:"))
        self.combo_samples = QComboBox()
        self.combo_samples.addItems(self.sample_map.keys())
        self.combo_samples.setCurrentText(str(DEFAULT_SAMPLES))
        self.combo_samples.currentTextChanged.connect(self.validate_params)
        config_layout.addWidget(self.combo_samples)

        self.label_res = QLabel(" (0.300°/点)")
        self.label_res.setStyleSheet("color: #00FFFF; font-weight: bold; min-width: 80px;")
        config_layout.addWidget(self.label_res)

        config_layout.addWidget(QLabel("频率 (10-50Hz):"))
        self.combo_freq = QComboBox()
        self.combo_freq.addItems([str(i) for i in range(10, 51)])
        self.combo_freq.setCurrentText(str(DEFAULT_FREQ))
        self.combo_freq.currentTextChanged.connect(self.validate_params)
        config_layout.addWidget(self.combo_freq)

        self.btn_apply = QPushButton("应用配置")
        self.btn_apply.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold; height: 30px;")
        self.btn_apply.clicked.connect(self.apply_params)
        config_layout.addWidget(self.btn_apply)
        self.layout.addLayout(config_layout)

        # --- 2. 滤波控制行 ---
        filter_layout = QHBoxLayout()
        self.filters = {"无滤波": "none", "均值滤波": "average", "中值滤波": "median", "最大值滤波": "maximum", "反射率滤波": "remission"}
        self.filter_btns = {}
        for name, val in self.filters.items():
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, n=name, v=val: self.set_lidar_filter(n, v))
            filter_layout.addWidget(btn)
            self.filter_btns[name] = btn
        self.filter_btns["无滤波"].setChecked(True)
        self.layout.addLayout(filter_layout)

        # --- 3. 辅助按键行 ---
        assist_layout = QHBoxLayout()
        self.btn_connect = QPushButton("连接扫描点: 关")
        self.btn_connect.setCheckable(True)
        self.btn_connect.clicked.connect(self.toggle_connect_mode)
        
        
        
        assist_layout.addWidget(self.btn_connect)
        
        self.layout.addLayout(assist_layout)

        # --- 4. 绘图区 ---
        self.plot = pg.PlotWidget()
        self.layout.addWidget(self.plot)
        self.plot.setAspectLocked(True)
        self.plot.setBackground('#050505')
        self.plot.setRange(xRange=[-8000, 8000], yRange=[-8000, 8000])

       # --- 5. 几何数据统计行 ---
        geo_layout = QHBoxLayout()
        self.label_perimeter = QLabel("周长: 0.00 m")
        self.label_area = QLabel("面积: 0.00 m²")
        # 设置样式让数据更醒目
        style = "color: #00FF00; font-family: 'Consolas'; font-size: 14px; font-weight: bold; background: #222; padding: 5px;"
        self.label_perimeter.setStyleSheet(style)
        self.label_area.setStyleSheet(style)
        geo_layout.addWidget(self.label_perimeter)
        geo_layout.addWidget(self.label_area)
        self.layout.addLayout(geo_layout)

        # 绘制背景网格与刻度
        self._init_grid()

        # 箭头与点云
        self.arrow = pg.ScatterPlotItem(pos=[[0, 0]], size=40, pen='r', brush='r', symbol='arrow_up', angle=180)
        self.plot.addItem(self.arrow)
        self.scatter = pg.ScatterPlotItem(size=3, brush='#00FF00', pxMode=True)
        self.curve = pg.PlotCurveItem(pen=pg.mkPen('#00FF00', width=1))
        self.plot.addItem(self.scatter); self.plot.addItem(self.curve); self.curve.hide()

        # 启动后端与定时器
        self.client = R2000HighSpeedClient()
        self.client.start()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(30)

    def _init_grid(self):
        grid_pen = pg.mkPen(color=(100, 100, 100, 50), width=1)
        for r in range(100, 10001, 100):
            c = QGraphicsEllipseItem(-r, -r, r*2, r*2)
            c.setPen(grid_pen); self.plot.addItem(c)
            t = TextItem(text=f"{r/1000:.1f}m", color=(150, 150, 150), anchor=(0, 1))
            t.setPos(0, r); self.plot.addItem(t)
        for deg in range(0, 360, 5):
            rad = np.deg2rad(deg)
            l = QGraphicsLineItem(0, 0, 10000 * np.sin(rad), 10000 * np.cos(rad))
            l.setPen(grid_pen); self.plot.addItem(l)
            at = TextItem(text=f"{deg}°", color=(100, 100, 100), anchor=(0.5, 0.5))
            at.setPos(2000 * np.sin(rad), 2000 * np.cos(rad)); self.plot.addItem(at)

    def validate_params(self):
        """实时校验 频率 x 点数 <= 84000"""
        f = int(self.combo_freq.currentText())
        s_str = self.combo_samples.currentText()
        s = int(s_str)
        
        # 更新分辨率显示
        self.label_res.setText(f" ({self.sample_map.get(s_str)}/点)")
        
        # 计算负载
        load = f * s
        if load > 84000:
            self.btn_apply.setEnabled(False)
            self.btn_apply.setText(f"负载过高({load})")
            self.btn_apply.setStyleSheet("background-color: #aa0000; color: white; font-weight: bold;")
        else:
            self.btn_apply.setEnabled(True)
            self.btn_apply.setText("应用配置")
            self.btn_apply.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")

    def apply_params(self):
        f = int(self.combo_freq.currentText())
        s = int(self.combo_samples.currentText())
        try:
            res = requests.get(f"http://{LIDAR_IP}/cmd/set_parameter", 
                               params={'scan_frequency': f, 'samples_per_scan': s}, timeout=1)
            if res.status_code == 200:
                QMessageBox.information(self, "设置成功", f"雷达已更新:\n频率: {f}Hz\n点数: {s}")
            else:
                QMessageBox.warning(self, "雷达错误", f"雷达拒绝请求: {res.text}")
        except Exception as e:
            QMessageBox.critical(self, "通讯错误", f"无法连接雷达: {e}")

    def set_lidar_filter(self, name, val):
        for n, btn in self.filter_btns.items():
            btn.setChecked(n == name)
        try:
            requests.get(f"http://{LIDAR_IP}/cmd/set_parameter", params={'filter_type': val, 'filter_width': 4}, timeout=1)
        except: pass

    def toggle_range_mask(self):
        if self.btn_range.isChecked():
            self.btn_range.setText("显示测量范围: 开"); self.range_mask.show()
        else:
            self.btn_range.setText("显示测量范围: 关"); self.range_mask.hide()

    def toggle_connect_mode(self):
        if self.btn_connect.isChecked():
            self.btn_connect.setText("连接扫描点: 开")
            self.btn_connect.setStyleSheet("background-color: #009664; color: white;")
            self.curve.show(); self.scatter.hide()
        else:
            self.btn_connect.setText("连接扫描点: 关")
            self.btn_connect.setStyleSheet("background-color: #444; color: white;")
            self.curve.hide(); self.scatter.show()

    def update_ui(self):
        with self.client.data_lock:
            x, y = self.client.latest_cloud
    
        if x.size > 2:  # 至少需要3个点才能构成图形
            if self.btn_connect.isChecked():
                # --- 连线模式下的闭合逻辑 ---
                # 为了形成封闭图形，将第一个点追加到末尾
                x_closed = np.append(x, x[0])
                y_closed = np.append(y, y[0])
                self.curve.setData(x_closed, y_closed)
            
                # --- 计算周长 ---
                dx = np.diff(x_closed)
                dy = np.diff(y_closed)
                dist = np.sqrt(dx**2 + dy**2)
                perimeter = np.sum(dist) / 1000.0  # 转为米
            
                # --- 计算面积 (Shoelace Formula) ---
                area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
                area_m2 = area / 1000000.0  # mm² 转 m²
            
                # 更新 UI 显示
                self.label_perimeter.setText(f"周长: {perimeter:.2f} m")
                self.label_area.setText(f"面积: {area_m2:.2f} m²")
            
            else:
                # 散点模式不显示几何数据
                self.scatter.setData(x, y)
                self.label_perimeter.setText("周长: ---")
                self.label_area.setText("面积: ---")





if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = RadarApp()
    win.show()
    sys.exit(app.exec_())