#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import time
import serial
import math
import pygame
from threading import Event
from pymodbus.client import ModbusSerialClient
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# ======================== 全局配置 ========================
SERIAL_PORT = "/dev/ttyCH341USB0"
BAUD_RATE = 115200

# ---------------- 喷绘机器人 核心参数（严格按照你的配置） ----------------
OFFSET_CM = 20.0          # 喷笔偏移旋转中心后方20cm
WHEEL_BASE = 50.0         # 轮距/车轴长50cm
WHEEL_DIAMETER = 13.97     # 轮径13.97cm（5.5英寸）
WHEEL_CM = math.pi * WHEEL_DIAMETER  # 车轮周长≈43.89cm

# ---------------- 手柄配置 ----------------
RT_BUTTON = 7             # RT键按钮编号
AXIS_LEFT = 1              # 左摇杆纵轴
AXIS_RIGHT = 3             # 右摇杆纵轴
DEAD_ZONE = 0.15
MAX_JOY_RPM = 10           # 单轮最大转速10rpm

# ---------------- IO 继电器指令 ----------------
DO_COMMANDS = {
    1: {"on": "FE050000FF009835", "off": "FE0500000000D9C5"},
    2: {"on": "FE050001FF00C9F5", "off": "FE05000100008805"},
    3: {"on": "FE050002FF0039F5", "off": "FE05000200007805"},
    4: {"on": "FE050003FF006835", "off": "FE050003000029C5"},
    5: {"on": "FE050004FF00D9F4", "off": "FE05000400009804"},
    6: {"on": "FE050005FF008834", "off": "FE0500050000C9C4"},
    7: {"on": "FE050006FF007834", "off": "FE050006000039C4"},
    8: {"on": "FE050007FF0029F4", "off": "FE05000700006804"},
    9: {"on": "FE050008FF0019F7", "off": "FE05000800005807"},
    10: {"on": "FE050009FF004837", "off": "FE050009000009C7"}
}
GLOBAL_COMMANDS = {
    "all_on": "FE0F0000001002FFFFA664",
    "all_off": "FE0F00000010020000A7D4"
}
relay_status = {k: False for k in DO_COMMANDS.keys()}

# ---------------- 驱动器参数 ----------------
DRIVER_ADDR = 1
BASE_SPEED = 5             # 机器人中心的基础转速RPM
ROTATE_SPEED = 5           # 原地旋转时的单轮转速RPM

REG = {
    "RUN_MODE": 0x200D,
    "CONTROL_WORD": 0x200E,
    "LEFT_ACCEL": 0x2080,
    "RIGHT_ACCEL": 0x2081,
    "LEFT_DECEL": 0x2082,
    "RIGHT_DECEL": 0x2083,
    "LEFT_TARGET_SPEED": 0x2088,
    "RIGHT_TARGET_SPEED": 0x2089,
}

stop_event = Event()
is_running = False

# ======================== IO 控制（完全手动） ========================
def io_send(channel, on):
    try:
        s = serial.Serial(SERIAL_PORT, BAUD_RATE, parity=serial.PARITY_NONE, stopbits=1, bytesize=8, timeout=0.1)
        cmd = DO_COMMANDS[channel]["on"] if on else DO_COMMANDS[channel]["off"]
        s.write(bytes.fromhex(cmd))
        time.sleep(0.1)
        s.close()
        relay_status[channel] = on
        return True
    except Exception as e:
        print(f"IO发送失败: {e}")
        return False

def io_all(on):
    try:
        s = serial.Serial(SERIAL_PORT, BAUD_RATE, parity=serial.PARITY_NONE, stopbits=1, bytesize=8, timeout=0.1)
        cmd = GLOBAL_COMMANDS["all_on"] if on else GLOBAL_COMMANDS["all_off"]
        s.write(bytes.fromhex(cmd))
        time.sleep(0.1)
        s.close()
        for k in relay_status: relay_status[k] = on
        return True
    except Exception as e:
        print(f"IO全局发送失败: {e}")
        return False

# ======================== 驱动器控制 ========================
class Driver:
    def __init__(self):
        self.mutex = QMutex()

    def _write_reg(self, reg_addr, value):
        try:
            with QMutexLocker(self.mutex):
                client = ModbusSerialClient(
                    port=SERIAL_PORT,
                    baudrate=BAUD_RATE,
                    parity="N",
                    stopbits=1,
                    bytesize=8,
                    timeout=0.2
                )
                if not client.connect():
                    print("驱动器串口打开失败")
                    return False
                
                ival = int(round(value))
                if ival < 0:
                    ival = 65536 + ival
                ival = ival & 0xFFFF
                
                result = not client.write_register(reg_addr, ival, slave=DRIVER_ADDR).isError()
                client.close()
                return result
        except Exception as e:
            print(f"驱动器写入异常: {e}")
            return False

    def init(self):
        self._write_reg(REG["RUN_MODE"], 3)
        time.sleep(0.1)
        self._write_reg(REG["LEFT_ACCEL"], 500)
        self._write_reg(REG["RIGHT_ACCEL"], 500)
        self._write_reg(REG["LEFT_DECEL"], 500)
        self._write_reg(REG["RIGHT_DECEL"], 500)
        time.sleep(0.1)
        self._write_reg(REG["CONTROL_WORD"], 0x06)
        time.sleep(0.1)
        self._write_reg(REG["CONTROL_WORD"], 0x08)
        time.sleep(0.2)
        return True

    def set_speed(self, left_rpm, right_rpm):
        # 左轮正转写负数值，右轮正转写正数值
        left_reg = -left_rpm
        right_reg = right_rpm
        print(f"DEBUG: 下发速度 | 目标RPM: 左={left_rpm}, 右={right_rpm} | 实际寄存器: 左={left_reg}, 右={right_reg}")
        self._write_reg(REG["LEFT_TARGET_SPEED"], left_reg)
        self._write_reg(REG["RIGHT_TARGET_SPEED"], right_reg)

    def stop(self):
        self.set_speed(0, 0)
        time.sleep(0.2)

    def lock(self):
        return self._write_reg(REG["CONTROL_WORD"], 0x08)

    def unlock(self):
        return self._write_reg(REG["CONTROL_WORD"], 0x07)

driver = Driver()

# ======================== 运动线程（严格按照你的运动学分析） ========================
class MoveThread(QThread):
    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, distance_cm=0):
        super().__init__()
        stop_event.clear()
        self.distance = distance_cm

    def run(self):
        if self.distance == 0:
            self.log.emit("❌ 距离不能为0")
            self.finished.emit()
            return

        direction = 1 if self.distance > 0 else -1
        abs_distance = abs(self.distance)
        dir_text = "前进" if direction > 0 else "后退"
        
        self.log.emit(f"🚀 开始{dir_text}：{abs_distance}cm")
        t = abs_distance / WHEEL_CM * 60 / BASE_SPEED
        self.log.emit(f"⏱️ 预计时间：{t:.1f}s")
        
        start = time.time()
        while time.time() - start < t and not stop_event.is_set():
            driver.set_speed(BASE_SPEED * direction, BASE_SPEED * direction)
            time.sleep(0.1)
        
        driver.stop()
        self.log.emit(f"✅ {dir_text}完成")
        self.finished.emit()

    def run_dist(self, cm, L, R):
        """🔧 核心修复：根据距离正负自动反转方向，实现正确的前进/后退"""
        # 计算方向系数：距离为负，自动反转速度方向
        direction = 1 if cm >= 0 else -1
        abs_cm = abs(cm)
        
        t = abs_cm / WHEEL_CM * 60 / BASE_SPEED
        start = time.time()
        while time.time() - start < t and not stop_event.is_set():
            # 速度乘以方向系数，负距离自动反转
            driver.set_speed(L * direction, R * direction)
            time.sleep(0.1)
        driver.stop()

    def run_spin(self, clockwise):
        """严格按照你的分析实现精确原地旋转90度"""
        self.log.emit("🔄 开始精确原地旋转90度")
        
        # 1. 计算90度旋转的单轮弧长：L_arc = (π * D_track) / 4
        rotate_arc_length = (math.pi * WHEEL_BASE) / 4
        self.log.emit(f"   旋转弧长：{rotate_arc_length:.2f}cm")
        
        # 2. 计算单轮线速度：V = (RPM / 60) * C_wheel
        linear_speed = (ROTATE_SPEED / 60) * WHEEL_CM
        self.log.emit(f"   单轮线速度：{linear_speed:.3f}cm/s")
        
        # 3. 计算精确旋转时间：T = L_arc / V
        rotate_time = rotate_arc_length / linear_speed
        self.log.emit(f"   精确旋转时间：{rotate_time:.2f}s")
        
        # 4. 确定左右轮速度（反向转动实现纯原地旋转）
        if clockwise:
            # 顺时针：左轮+5RPM前进，右轮-5RPM后退
            v_left = ROTATE_SPEED
            v_right = -ROTATE_SPEED
            self.log.emit("   旋转方向：顺时针 | 左轮+5RPM，右轮-5RPM")
        else:
            # 逆时针：左轮-5RPM后退，右轮+5RPM前进
            v_left = -ROTATE_SPEED
            v_right = ROTATE_SPEED
            self.log.emit("   旋转方向：逆时针 | 左轮-5RPM，右轮+5RPM")
        
        # 5. 执行精确旋转
        start = time.time()
        while time.time() - start < rotate_time and not stop_event.is_set():
            driver.set_speed(v_left, v_right)
            time.sleep(0.1)
        
        driver.stop()
        self.log.emit("✅ 精确原地旋转90度完成")
        time.sleep(0.2)

# ======================== 圆形线程（严格运动学公式） ========================
class CircleThread(MoveThread):
    def __init__(self, diameter_cm, clockwise):
        super().__init__()
        self.D = diameter_cm    # 圆直径，单位cm
        self.R = diameter_cm / 2  # 圆半径，单位cm
        self.cw = clockwise     # 顺逆时针方向

    def run(self):
        if self.D < 50:
            self.log.emit("❌ 圆直径必须≥50cm（最小转弯半径25cm）")
            self.finished.emit()
            return
        
        b = WHEEL_BASE
        v_center = BASE_SPEED
        
        if not self.cw:
            v_left = v_center * (1 - b / (2 * self.R))
            v_right = v_center * (1 + b / (2 * self.R))
            self.log.emit(f"🔄 逆时针画圆 | 直径{self.D}cm | 中心R={self.R}cm")
        else:
            v_left = v_center * (1 + b / (2 * self.R))
            v_right = v_center * (1 - b / (2 * self.R))
            self.log.emit(f"🔄 顺时针画圆 | 直径{self.D}cm | 中心R={self.R}cm")

        if abs(self.R - 25) < 0.1:
            self.log.emit("⚠️  极限模式：R=25cm，圆心落在内侧轮上")
            if not self.cw:
                v_left = 0
                v_right = 2 * v_center
            else:
                v_left = 2 * v_center
                v_right = 0

        circumference = math.pi * self.D
        t = circumference / WHEEL_CM * 60 / v_center
        self.log.emit(f"⚪ 圆周长{circumference:.1f}cm | 预计时间{t:.1f}s")

        start = time.time()
        while time.time() - start < t and not stop_event.is_set():
            driver.set_speed(v_left, v_right)
            time.sleep(0.1)
        
        driver.stop()
        self.log.emit("✅ 画圆完成")
        self.finished.emit()

# ======================== 矩形线程（完美直角4步流程） ========================
class RectThread(MoveThread):
    def __init__(self, a, b, cw):
        super().__init__()
        self.a = a
        self.b = b
        self.cw = cw

    def run(self):
        self.log.emit("📌 开始喷绘矩形（完美直角4步流程）")
        sides = [self.a, self.b, self.a, self.b]

        for idx, L in enumerate(sides):
            if stop_event.is_set(): break
            
            # 第1步：直线喷绘（你手动开喷笔）
            self.log.emit(f"--- 第{idx+1}边：直线前进{L}cm ---")
            self.run_dist(L, BASE_SPEED, BASE_SPEED)
            
            if idx == 3: break
            
            # 第2步：后退补偿20cm（让ICR与拐点重合）
            self.log.emit("→ 完美直角Step1/3：后退20cm补偿")
            self.run_dist(-OFFSET_CM, BASE_SPEED, BASE_SPEED)
            
            # 第3步：精确原地旋转90度
            self.log.emit("→ 完美直角Step2/3：精确原地旋转90度")
            self.run_spin(self.cw)
            
            # 第4步：前进补偿20cm（让喷笔回到拐点）
            self.log.emit("→ 完美直角Step3/3：前进20cm补偿")
            self.run_dist(OFFSET_CM, BASE_SPEED, BASE_SPEED)

        self.log.emit("✅ 矩形喷绘完成（完美直角）")
        self.finished.emit()

# ======================== 手柄监听线程 ========================
class JoystickThread(QThread):
    log = pyqtSignal(str)
    interrupt_task = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.running = True
        self.rt_was_pressed = False
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.log.emit(f"✅ 检测到手柄：{self.joystick.get_name()}")
        else:
            self.log.emit("⚠️  未检测到手柄")

    def run(self):
        while self.running:
            if not self.joystick:
                time.sleep(0.1)
                continue
            pygame.event.pump()
            rt_pressed = self.joystick.get_button(RT_BUTTON)
            
            if rt_pressed:
                if not self.rt_was_pressed:
                    self.interrupt_task.emit()
                    self.rt_was_pressed = True
                
                jl_raw = self.joystick.get_axis(AXIS_LEFT)
                jr_raw = self.joystick.get_axis(AXIS_RIGHT)
                l_val = jl_raw if abs(jl_raw) > DEAD_ZONE else 0.0
                r_val = -jr_raw if abs(jr_raw) > DEAD_ZONE else 0.0
                l_rpm = int(l_val * MAX_JOY_RPM)
                r_rpm = int(r_val * MAX_JOY_RPM)
                driver.set_speed(l_rpm, r_rpm)
            else:
                if self.rt_was_pressed:
                    driver.set_speed(0, 0)
                    self.rt_was_pressed = False
            
            time.sleep(0.05)

    def stop(self):
        self.running = False
        self.wait()

# ======================== 预览画布 ========================
class PreviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.mode = "none"
        self.val1 = self.val2 = 0
        self.clockwise = True
        self.setMinimumHeight(240)
        self.setStyleSheet("background:white; border:1px solid #999;")

    def set_circle(self, d, clockwise=True):
        self.mode = "circle"
        self.val1 = d
        self.clockwise = clockwise
        self.update()

    def set_rect(self, a, b, clockwise=True):
        self.mode = "rect"
        self.val1, self.val2 = a, b
        self.clockwise = clockwise
        self.update()

    def reset(self):
        self.mode = "none"
        self.update()

    def paintEvent(self, e):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w//2, h//2

        qp.setPen(QPen(Qt.black, 2))
        qp.setBrush(Qt.NoBrush)

        if self.mode == "circle" and self.val1 > 0:
            r = min(w, h) * 0.3
            qp.drawEllipse(QPoint(cx, cy), int(r), int(r))
            qp.setPen(QPen(Qt.blue, 3))
            if self.clockwise:
                self.draw_arrow(qp, cx + int(r), cy, 90)
            else:
                self.draw_arrow(qp, cx + int(r), cy, 270)

        elif self.mode == "rect" and self.val1 > 0 and self.val2 > 0:
            aspect_ratio = self.val1 / self.val2
            max_w = w * 0.8
            max_h = h * 0.8
            if max_w / max_h > aspect_ratio:
                draw_h = max_h
                draw_w = draw_h * aspect_ratio
            else:
                draw_w = max_w
                draw_h = draw_w / aspect_ratio
            x1 = cx - draw_w / 2
            y1 = cy - draw_h / 2
            qp.drawRect(int(x1), int(y1), int(draw_w), int(draw_h))
            qp.setPen(QPen(Qt.blue, 3))
            if self.clockwise:
                self.draw_arrow(qp, x1 + draw_w/2, y1, 0)
            else:
                self.draw_arrow(qp, x1, y1 + draw_h/2, 90)

    def draw_arrow(self, qp, x, y, angle):
        arrow_len = 15
        arrow_w = 8
        rad = math.radians(angle)
        x2 = x + arrow_len * math.cos(rad)
        y2 = y + arrow_len * math.sin(rad)
        rad1 = math.radians(angle + 150)
        rad2 = math.radians(angle - 150)
        x3 = x2 + arrow_w * math.cos(rad1)
        y3 = y2 + arrow_w * math.sin(rad1)
        x4 = x2 + arrow_w * math.cos(rad2)
        y4 = y2 + arrow_w * math.sin(rad2)
        qp.drawLine(int(x), int(y), int(x2), int(y2))
        qp.drawLine(int(x2), int(y2), int(x3), int(y3))
        qp.drawLine(int(x2), int(y2), int(x4), int(y4))

# ======================== 主窗口 ========================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("喷绘机器人 - 完美直角 + 精确原地旋转")
        self.setGeometry(100, 100, 1000, 750)
        self.task = None

        self.ui = QWidget()
        self.setCentralWidget(self.ui)
        lay = QVBoxLayout(self.ui)
        lay.setSpacing(14)
        lay.setContentsMargins(24,24,24,24)

        # 预览
        self.preview = PreviewWidget()
        lay.addWidget(QLabel("📊 路径预览"))
        lay.addWidget(self.preview)

        # IO
        g1 = QGroupBox("🔌 继电器 / 喷笔控制（完全手动）")
        gl = QHBoxLayout(g1)
        self.relay_btns = {}
        for i in range(1,11):
            b = QPushButton(f"DO{i}")
            b.clicked.connect(lambda _,x=i: self.toggle_relay(x))
            gl.addWidget(b)
            self.relay_btns[i] = b
        gl.addWidget(QPushButton("全开", clicked=lambda: self.relay_all(True)))
        gl.addWidget(QPushButton("全关", clicked=lambda: self.relay_all(False)))
        lay.addWidget(g1)

        # 运动面板
        g2 = QGroupBox("路径控制")
        ml = QGridLayout(g2)

        ml.addWidget(QLabel("直线(cm)"), 0,0)
        self.e_line = QLineEdit()
        self.e_line.setPlaceholderText("正数前进，负数后退")
        ml.addWidget(self.e_line,0,1)
        ml.addWidget(QPushButton("启动直线", clicked=self.start_line),0,2)

        ml.addWidget(QLabel("圆直径(cm)"),1,0)
        self.e_cir = QLineEdit()
        self.e_cir.setPlaceholderText("最小50cm（R≥25cm）")
        ml.addWidget(self.e_cir,1,1)
        self.cir_dir = QComboBox()
        self.cir_dir.addItems(["顺时针","逆时针"])
        ml.addWidget(self.cir_dir,1,2)
        ml.addWidget(QPushButton("预览", clicked=self.prev_circle),1,3)
        ml.addWidget(QPushButton("启动圆", clicked=self.start_cir),1,4)

        ml.addWidget(QLabel("边长1(cm)"),2,0)
        self.e_r1 = QLineEdit()
        ml.addWidget(self.e_r1,2,1)
        ml.addWidget(QLabel("边长2(cm)"),2,2)
        self.e_r2 = QLineEdit()
        ml.addWidget(self.e_r2,2,3)
        self.rdir = QComboBox()
        self.rdir.addItems(["顺时针","逆时针"])
        ml.addWidget(self.rdir,2,4)
        ml.addWidget(QPushButton("预览矩形", clicked=self.prev_rect),2,5)
        ml.addWidget(QPushButton("启动矩形", clicked=self.start_rect),2,6)

        lay.addWidget(g2)

        # 控制栏
        ct = QHBoxLayout()
        ct.addWidget(QPushButton("锁轴", clicked=lambda: driver.lock() and self.logs("🔒 驱动器已锁轴")))
        ct.addWidget(QPushButton("解轴", clicked=lambda: driver.unlock() and self.logs("🔓 驱动器已解轴")))
        ct.addWidget(QPushButton("取消任务", clicked=self.cancel, minimumWidth=140))
        ct.addWidget(QPushButton("安全退出", clicked=self.close, minimumWidth=140))
        lay.addLayout(ct)

        # 日志
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        lay.addWidget(QLabel("📋 状态日志"))
        lay.addWidget(self.log)

        # 初始化硬件
        self.init_hardware()

        # 启动手柄监听
        self.joy_thread = JoystickThread()
        self.joy_thread.log.connect(self.logs)
        self.joy_thread.interrupt_task.connect(self.cancel)
        self.joy_thread.start()

        self.logs("✅ 系统启动 ｜ 完美直角4步流程 ｜ 精确原地旋转 ｜ IO完全手动控制")

    def logs(self, m):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {m}")

    def init_hardware(self):
        if driver.init():
            self.logs("✅ 驱动器初始化成功（速度模式+使能）")
        else:
            self.logs("❌ 驱动器初始化失败")

    def toggle_relay(self, ch):
        global relay_status
        new_state = not relay_status[ch]
        if io_send(ch, new_state):
            relay_status[ch] = new_state
            self.relay_btns[ch].setText(f"DO{ch}\n{'开' if new_state else '关'}")
            self.logs(f"DO{ch} {'开' if new_state else '关'}")

    def relay_all(self, on):
        global relay_status
        if io_all(on):
            for ch in relay_status:
                relay_status[ch] = on
                self.relay_btns[ch].setText(f"DO{ch}\n{'开' if on else '关'}")
            self.logs(f"所有继电器已{'全开' if on else '全关'}")

    def start_line(self):
        try:
            v = float(self.e_line.text())
            self.run_task(MoveThread(v))
        except:
            self.logs("❌ 请输入有效长度")

    def prev_circle(self):
        try:
            d = float(self.e_cir.text() or 0)
            cw = self.cir_dir.currentIndex()==0
            self.preview.set_circle(d, cw)
        except:
            pass

    def start_cir(self):
        try:
            d = float(self.e_cir.text())
            cw = self.cir_dir.currentIndex()==0
            self.run_task(CircleThread(d, cw))
        except:
            self.logs("❌ 请输入有效直径")

    def prev_rect(self):
        try:
            a = float(self.e_r1.text() or 0)
            b = float(self.e_r2.text() or 0)
            cw = self.rdir.currentIndex()==0
            self.preview.set_rect(a, b, cw)
        except:
            pass

    def start_rect(self):
        try:
            a = float(self.e_r1.text())
            b = float(self.e_r2.text())
            cw = self.rdir.currentIndex()==0
            self.run_task(RectThread(a, b, cw))
        except:
            self.logs("❌ 请输入有效边长")

    def run_task(self, thr):
        global is_running
        if is_running:
            self.logs("⚠️  已有任务正在运行")
            return
        is_running = True
        self.task = thr
        thr.log.connect(self.logs)
        thr.finished.connect(self.task_finish)
        thr.start()

    def task_finish(self):
        global is_running
        is_running = False
        self.task = None
        self.preview.reset()

    def cancel(self):
        global is_running
        if is_running:
            stop_event.set()
            self.logs("🛑 任务已取消（手柄接管或手动取消）")
            driver.stop()

    def closeEvent(self, e):
        self.cancel()
        time.sleep(0.2)
        self.joy_thread.stop()
        driver.stop()
        driver.unlock()
        self.logs("👋 安全退出")
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
