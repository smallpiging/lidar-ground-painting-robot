# -*- coding: utf-8 -*-
from pymodbus.client import ModbusSerialClient
import pygame
import time
import sys

# ===================== 核心配置（低速控制适配 + 轮胎参数） =====================
# 驱动器串口配置
SERIAL_PORT = "COM9"       # 替换为你的驱动器串口
BAUDRATE = 115200
DRIVER_ADDR = 1

# 低速控制参数（关键调整：分辨率=1，解决100RPM问题）
MAX_SPEED = 50            # 最大速度10RPM（实际生效）
ACCEL_TIME = 500           # 加速度调大（减速更平缓），单位ms
DEAD_ZONE = 0.05           # 更小的死区（提升低速精度）
SPEED_RESOLUTION = 1       # 你的驱动器1单位=1RPM，无需放大（核心修改）

# 轮胎参数与线速度计算常量（5.5×2轮胎）
TIRE_DIAMETER_INCH = 5.5  # 轮胎直径（英寸）：5.5×2中的5.5（宽度2不影响线速度）
TIRE_DIAMETER_METER = TIRE_DIAMETER_INCH * 0.0254  # 单位转换：英寸→米（1英寸=0.0254米）
TIRE_CIRCUMFERENCE = 3.14159 * TIRE_DIAMETER_METER  # 车轮周长（米）= π×直径（每转一圈移动距离）

# 16位有符号寄存器范围（-32768 ~ 32767），适配ZLAC8015D驱动器
DRIVER_SPEED_MIN = -32768
DRIVER_SPEED_MAX = 32767

# 寄存器地址（ZLAC8015D标准）
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

# 故障码映射（简化版）
FAULT_MAP = {
    0x0000: ("无故障", "正常运行"),
    0x0001: ("过压", "电源电压超48V"),
    0x0002: ("欠压", "电源电压低于24V"),
    0x0004: ("过流", "电机电流超限/堵转"),
    0x0008: ("过载", "电机负载过大"),
    0x0020: ("编码器超差", "编码器接线/堵转"),
    0x0800: ("编码器错误", "编码器接线反/损坏"),
}

# ===================== 驱动器通信类 =====================
class ZLAC8015D_Driver:
    def __init__(self, port, baudrate, addr):
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
            # 严格限制在16位有符号范围，解决"argument out of range"异常
            value = max(DRIVER_SPEED_MIN, min(DRIVER_SPEED_MAX, value))
            # 转换为16位有符号整数（适配Modbus协议）
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
            # 处理有符号数（转换补码为负数）
            if is_signed and value > 32767:
                value -= 65536
            return value
        except Exception as e:
            print(f"❌ 读寄存器0x{reg_addr:04X}异常：{str(e)}")
            return None

    def init_speed_mode(self):
        """初始化低速速度模式"""
        print("\n🔧 初始化低速速度模式（MAX_SPEED=10RPM）...")
        # 1. 设置速度模式
        ret1 = self.write_register(REG["RUN_MODE"], 3)
        # 2. 设置平缓的加速/减速时间（500ms，更慢的加减速）
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
            print("✅ 低速模式初始化完成")
            return True
        else:
            print("❌ 初始化失败，检查故障码")
            self.print_fault()
            return False

    def set_wheel_speed(self, left_wheel_speed, right_wheel_speed):
        """设置车轮速度（适配分辨率=1，左摇杆控左轮、右摇杆控右轮）"""
        # 1. 速度限幅（-10 ~ 10 RPM）
        left_wheel_speed = max(-MAX_SPEED, min(MAX_SPEED, left_wheel_speed))
        right_wheel_speed = max(-MAX_SPEED, min(MAX_SPEED, right_wheel_speed))
        # 2. 适配驱动器分辨率（1单位=1RPM，直接转换为寄存器值）
        left_reg = int(left_wheel_speed * SPEED_RESOLUTION)
        right_reg = int(right_wheel_speed * SPEED_RESOLUTION)
        # 3. 写入寄存器
        left_ok = self.write_register(REG["LEFT_TARGET_SPEED"], left_reg)
        right_ok = self.write_register(REG["RIGHT_TARGET_SPEED"], right_reg)
        return left_ok and right_ok

    def read_feedback(self):
        """读取车轮实时状态（新增：计算并返回左右轮线速度）"""
        feedback = {
            "left_wheel_speed": 0.0, "right_wheel_speed": 0.0,
            "left_line_speed_m/s": 0.0, "right_line_speed_m/s": 0.0,  # 新增：米/秒线速度（直观）
            "bus_voltage": 0.0, "left_fault": 0, "right_fault": 0,
            "is_ok": True
        }
        # 读取实际速度（转换为RPM，支持有符号，适配分辨率参数）
        left_actual = self.read_register(REG["LEFT_ACTUAL_SPEED"], is_signed=True)
        right_actual = self.read_register(REG["RIGHT_ACTUAL_SPEED"], is_signed=True)
        
        if left_actual is not None:
            feedback["left_wheel_speed"] = left_actual / SPEED_RESOLUTION
            # 计算左轮线速度（核心：周长×转速 → 转换为米/秒）
            line_speed_m_min = TIRE_CIRCUMFERENCE * feedback["left_wheel_speed"]
            feedback["left_line_speed_m/s"] = line_speed_m_min / 60.0
        
        if right_actual is not None:
            feedback["right_wheel_speed"] = right_actual / SPEED_RESOLUTION
            # 计算右轮线速度（核心：周长×转速 → 转换为米/秒）
            line_speed_m_min = TIRE_CIRCUMFERENCE * feedback["right_wheel_speed"]
            feedback["right_line_speed_m/s"] = line_speed_m_min / 60.0
        
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
        """打印故障信息"""
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
        """急停（短路制动）"""
        if self.write_register(REG["CONTROL_WORD"], 0x05):
            print("\n🛑 急停指令已发送")
            time.sleep(1)
            self.write_register(REG["CONTROL_WORD"], 0x06)  # 清故障
            time.sleep(0.5)
            self.init_speed_mode()
            return True
        else:
            print("\n❌ 急停指令发送失败")
            return False

    def stop(self):
        """正常停机"""
        if self.write_register(REG["CONTROL_WORD"], 0x07):
            print("\n🛑 正常停机")
            return True
        else:
            print("\n❌ 停机指令失败")
            return False

    def close(self):
        """关闭连接"""
        self.stop()
        self.client.close()
        print(f"\n🔌 驱动器连接已关闭（串口：{self.port}）")

# ===================== 手柄控制（最终适配：左摇杆控左轮、右摇杆控右轮 | 上拨前进、下拨后退） =====================
def init_joystick():
    """初始化手柄"""
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("❌ 未检测到手柄，请连接后重试")
        pygame.quit()
        sys.exit(1)
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"✅ 手柄连接成功：{joystick.get_name()}")
    print("操作说明：")
    print("  🔴 左摇杆Y轴 → 控制左轮速度（上=前进，下=后退）")
    print("  🔵 右摇杆Y轴 → 控制右轮速度（上=前进，下=后退）")
    print("  🟢 摇杆幅度 → 速度大小（精准调速，支持差速转向）")
    print("  🚨 按键1B → 急停（任意时刻按下）")
    print("  🚨 按键0A → 退出程序（等效Ctrl+C）")
    return joystick

def get_joystick_speed(joystick):
    """读取摇杆速度（最终适配：左摇杆控左轮(无负号)、右摇杆控右轮(加负号) | 上拨前进、下拨后退）"""
    pygame.event.pump()
    # 左摇杆Y轴 → 控制左车轮速度（上=前进，下=后退）→ 无负号，直接映射
    left_stick_y = joystick.get_axis(1)  
    if abs(left_stick_y) < DEAD_ZONE:
        left_stick_y = 0.0
    left_wheel_speed = left_stick_y * MAX_SPEED  # 左摇杆：无负号（核心适配）

    # 右摇杆Y轴 → 控制右车轮速度（上=前进，下=后退）→ 保留负号，适配硬件轴方向
    right_stick_y = joystick.get_axis(3)  
    if abs(right_stick_y) < DEAD_ZONE:
        right_stick_y = 0.0
    right_wheel_speed = -right_stick_y * MAX_SPEED  # 右摇杆：加负号（核心适配，按你的要求修正）

    # 按键检测（保持不变）
    is_estop = joystick.get_button(1)
    is_exit = joystick.get_button(0)
    return left_wheel_speed, right_wheel_speed, is_estop, is_exit

# ===================== 主程序 =====================
if __name__ == "__main__":
    # 初始化驱动器
    driver = ZLAC8015D_Driver(port=SERIAL_PORT, baudrate=BAUDRATE, addr=DRIVER_ADDR)
    if not driver.connect():
        sys.exit(1)
    # 初始化低速模式
    if not driver.init_speed_mode():
        driver.close()
        sys.exit(1)
    # 初始化手柄
    joystick = init_joystick()

    try:
        print("\n🚀 小车低速控制启动（MAX_SPEED=10RPM | 轮胎5.5×2）")
        while True:
            # 读取手柄速度指令
            left_wheel_speed, right_wheel_speed, is_estop, is_exit = get_joystick_speed(joystick)
            
            # 急停处理
            if is_estop:
                driver.emergency_stop()
            else:
                # 发送速度指令（精准调速）
                driver.set_wheel_speed(left_wheel_speed, right_wheel_speed)

            # 读取实时状态并打印（包含转速、线速度、电压）
            feedback = driver.read_feedback()
            if feedback["is_ok"]:
                status_str = (f"\r实时状态：左轮={feedback['left_wheel_speed']:4.1f}RPM（{feedback['left_line_speed_m/s']:4.2f}m/s） | "
                             f"右轮={feedback['right_wheel_speed']:4.1f}RPM（{feedback['right_line_speed_m/s']:4.2f}m/s） | "
                             f"电压={feedback['bus_voltage']:4.2f}V")
                print(status_str, end="")

            # 手柄退出按键处理
            if is_exit:
                raise KeyboardInterrupt

            # 检测ESC退出
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    raise KeyboardInterrupt

            time.sleep(0.05)  # 20Hz刷新，兼顾响应速度和稳定性

    except KeyboardInterrupt:
        print("\n\n👋 用户退出程序")
    finally:
        # 安全停机
        driver.stop()
        driver.close()
        joystick.quit()
        pygame.quit()
        print("✅ 程序正常退出")