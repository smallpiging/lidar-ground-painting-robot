# zlac8015d_core.py
# -*- coding: utf-8 -*-
from pymodbus.client import ModbusSerialClient
import time

# ===================== 核心配置（复用+精简） =====================
# 驱动器串口配置（用户可根据实际修改）
SERIAL_PORT = "COM7"       # 替换为你的驱动器串口
BAUDRATE = 115200
DRIVER_ADDR = 1

# 驱动器基础参数（复用）
MAX_SPEED = 50             # 最大支持速度（可调整，预留余量）
ACCEL_TIME = 500           # 加减速时间（ms）
SPEED_RESOLUTION = 1       # 你的驱动器1单位=1RPM（已适配）
DRIVER_SPEED_MIN = -32768  # 16位有符号寄存器最小值
DRIVER_SPEED_MAX = 32767   # 16位有符号寄存器最大值

# 轮胎参数（复用，用于距离/时间换算）
TIRE_DIAMETER_INCH = 5.5  # 轮胎直径5.5英寸
TIRE_DIAMETER_METER = TIRE_DIAMETER_INCH * 0.0254  # 转换为米
TIRE_CIRCUMFERENCE = 3.14159 * TIRE_DIAMETER_METER  # 车轮周长（米）
TIRE_CIRCUMFERENCE_MM = TIRE_CIRCUMFERENCE * 1000   # 车轮周长（毫米，方便矩形计算）

# 寄存器地址（ZLAC8015D标准，复用）
REG = {
    "RUN_MODE": 0x200D,        # 运行模式：3=速度模式
    "CONTROL_WORD": 0x200E,    # 控制字：0x05=急停，0x06=清故障，0x07=停机，0x08=使能
    "LEFT_ACCEL": 0x2080,      # 左电机加速时间
    "RIGHT_ACCEL": 0x2081,     # 右电机加速时间
    "LEFT_DECEL": 0x2082,      # 左电机减速时间
    "RIGHT_DECEL": 0x2083,     # 右电机减速时间
    "LEFT_TARGET_SPEED": 0x2088,  # 左电机目标速度
    "RIGHT_TARGET_SPEED": 0x2089, # 右电机目标速度
    "LEFT_ACTUAL_SPEED": 0x20AB,  # 左电机实际速度
    "RIGHT_ACTUAL_SPEED": 0x20AC, # 右电机实际速度
    "LEFT_FAULT": 0x20A5,      # 左电机故障码
    "RIGHT_FAULT": 0x20A6,     # 右电机故障码
    "BUS_VOLTAGE": 0x20A1,     # 母线电压
}

# 故障码映射（复用）
FAULT_MAP = {
    0x0000: ("无故障", "正常运行"),
    0x0001: ("过压", "电源电压超48V"),
    0x0002: ("欠压", "电源电压低于24V"),
    0x0004: ("过流", "电机电流超限/堵转"),
    0x0008: ("过载", "电机负载过大"),
    0x0020: ("编码器超差", "编码器接线/堵转"),
    0x0800: ("编码器错误", "编码器接线反/损坏"),
}

# ===================== 驱动器通信类（完整复用，无修改） =====================
class ZLAC8015D_Driver:
    def __init__(self, port=SERIAL_PORT, baudrate=BAUDRATE, addr=DRIVER_ADDR):
        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            parity="N",
            stopbits=1,
            bytesize=8,
            timeout=3
        )
        self.addr = addr
        self.connected = False
        self.port = port

    def connect(self):
        """连接驱动器"""
        self.connected = self.client.connect()
        if self.connected:
            print(f"✅ 驱动器连接成功（串口：{self.port}）")
            return True
        else:
            print(f"❌ 驱动器连接失败，请检查串口/接线/电源")
            return False

    def write_register(self, reg_addr, value):
        """写16位有符号寄存器（修复数值超限问题）"""
        try:
            value = max(DRIVER_SPEED_MIN, min(DRIVER_SPEED_MAX, value))
            if value < 0:
                value = 65536 + value  # 负数转补码
            response = self.client.write_register(
                address=reg_addr,
                value=value,
                slave=self.addr
            )
            if response.isError():
                print(f"❌ 写寄存器0x{reg_addr:04X}失败：{response}")
                return False
            return True
        except Exception as e:
            print(f"❌ 写寄存器0x{reg_addr:04X}异常：{str(e)}")
            return False

    def read_register(self, reg_addr, is_signed=False):
        """读16位寄存器（支持有符号解析）"""
        try:
            response = self.client.read_holding_registers(
                address=reg_addr,
                count=1,
                slave=self.addr
            )
            if response.isError():
                print(f"❌ 读寄存器0x{reg_addr:04X}失败：{response}")
                return None
            value = response.registers[0]
            if is_signed and value > 32767:
                value -= 65536
            return value
        except Exception as e:
            print(f"❌ 读寄存器0x{reg_addr:04X}异常：{str(e)}")
            return None

    def init_speed_mode(self):
        """初始化速度模式（复用）"""
        print("\n🔧 初始化速度模式...")
        # 1. 设置速度模式
        ret1 = self.write_register(REG["RUN_MODE"], 3)
        # 2. 设置加减速时间
        ret2 = (self.write_register(REG["LEFT_ACCEL"], ACCEL_TIME) and
                self.write_register(REG["RIGHT_ACCEL"], ACCEL_TIME) and
                self.write_register(REG["LEFT_DECEL"], ACCEL_TIME) and
                self.write_register(REG["RIGHT_DECEL"], ACCEL_TIME))
        # 3. 清故障+使能
        time.sleep(0.1)
        self.write_register(REG["CONTROL_WORD"], 0x06)
        time.sleep(0.1)
        ret3 = self.write_register(REG["CONTROL_WORD"], 0x08)
        # 4. 验证模式
        current_mode = self.read_register(REG["RUN_MODE"])
        
        if ret1 and ret2 and ret3 and current_mode == 3:
            print("✅ 速度模式初始化完成")
            return True
        else:
            print("❌ 初始化失败，检查故障码")
            self.print_fault()
            return False

    def set_wheel_speed(self, left_wheel_speed, right_wheel_speed):
        """设置车轮速度（复用，适配分辨率）"""
        # 1. 速度限幅
        left_wheel_speed = max(-MAX_SPEED, min(MAX_SPEED, left_wheel_speed))
        right_wheel_speed = max(-MAX_SPEED, min(MAX_SPEED, right_wheel_speed))
        # 2. 适配驱动器分辨率
        left_reg = int(left_wheel_speed * SPEED_RESOLUTION)
        right_reg = int(right_wheel_speed * SPEED_RESOLUTION)
        # 3. 写入寄存器
        left_ok = self.write_register(REG["LEFT_TARGET_SPEED"], left_reg)
        right_ok = self.write_register(REG["RIGHT_TARGET_SPEED"], right_reg)
        return left_ok and right_ok

    def read_feedback(self):
        """读取车轮实时状态（复用）"""
        feedback = {
            "left_wheel_speed": 0.0, "right_wheel_speed": 0.0,
            "bus_voltage": 0.0, "left_fault": 0, "right_fault": 0,
            "is_ok": True
        }
        # 读取实际速度
        left_actual = self.read_register(REG["LEFT_ACTUAL_SPEED"], is_signed=True)
        right_actual = self.read_register(REG["RIGHT_ACTUAL_SPEED"], is_signed=True)
        if left_actual is not None:
            feedback["left_wheel_speed"] = left_actual / SPEED_RESOLUTION
        if right_actual is not None:
            feedback["right_wheel_speed"] = right_actual / SPEED_RESOLUTION
        # 读取母线电压
        bus_volt = self.read_register(REG["BUS_VOLTAGE"])
        if bus_volt is not None:
            feedback["bus_voltage"] = bus_volt / 100.0
        # 读取故障码
        feedback["left_fault"] = self.read_register(REG["LEFT_FAULT"]) or 0
        feedback["right_fault"] = self.read_register(REG["RIGHT_FAULT"]) or 0
        if feedback["left_fault"] != 0 or feedback["right_fault"] != 0:
            feedback["is_ok"] = False
            self.print_fault(feedback["left_fault"], feedback["right_fault"])
        return feedback

    def print_fault(self, left_fault=None, right_fault=None):
        """打印故障信息（复用）"""
        if left_fault is None:
            left_fault = self.read_register(REG["LEFT_FAULT"]) or 0
        if right_fault is None:
            right_fault = self.read_register(REG["RIGHT_FAULT"]) or 0
        print("\n⚠️  故障报警：")
        left_info = FAULT_MAP.get(left_fault, (f"未知故障(0x{left_fault:04X})", "联系厂商"))
        right_info = FAULT_MAP.get(right_fault, (f"未知故障(0x{right_fault:04X})", "联系厂商"))
        print(f"   左轮电机：{left_info[0]} → {left_info[1]}")
        print(f"   右轮电机：{right_info[0]} → {right_info[1]}")

    def emergency_stop(self):
        """急停（复用）"""
        if self.write_register(REG["CONTROL_WORD"], 0x05):
            print("\n🛑 急停指令已发送")
            time.sleep(1)
            self.write_register(REG["CONTROL_WORD"], 0x06)
            time.sleep(0.5)
            self.init_speed_mode()
            return True
        else:
            print("\n❌ 急停指令发送失败")
            return False

    def stop(self):
        """正常停机（复用）"""
        if self.write_register(REG["CONTROL_WORD"], 0x07):
            print("\n🛑 正常停机")
            return True
        else:
            print("\n❌ 停机指令失败")
            return False

    def close(self):
        """关闭连接（复用）"""
        self.stop()
        self.client.close()
        print(f"\n🔌 驱动器连接已关闭（串口：{self.port}）")
