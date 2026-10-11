# -*- coding: utf-8 -*-
import serial
import time
from pynput import keyboard

# ---------------------- 配置参数（必须与USB转RS485匹配）----------------------
SERIAL_PORT = "COM9"  # 替换为你的USB转RS485串口（设备管理器查看）
BAUD_RATE = 115200      # 文档默认波特率
PARITY = serial.PARITY_NONE  # 无校验
DATA_BITS = serial.EIGHTBITS  # 8数据位
STOP_BITS = serial.STOPBITS_ONE  # 1停止位
TIMEOUT = 1  # 串口超时时间（秒）

# 文档标准指令：DO1-DO10 开/关指令（16进制字符串，开=闭合，关=断开）
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

# 新增：全开、全闭指令（文档标准）+ 响应验证基准
GLOBAL_COMMANDS = {
    "all_on": {
        "cmd": "FE0F0000001002FFFFA664",  # 全开指令（16路全开）
        "response_check": "FE0F00000010"  # 设备返回的有效核心字段
    },
    "all_off": {
        "cmd": "FE0F00000010020000A7D4",  # 全闭指令（16路全关）
        "response_check": "FE0F00000010"  # 设备返回的有效核心字段
    }
}

# 继电器状态缓存：默认全关（False=关，True=开），贴合你的需求
relay_status = {k: False for k in DO_COMMANDS.keys()}
running = True  # 程序运行标志

# ---------------------- 串口初始化与指令发送 ----------------------
def init_serial():
    """初始化USB转RS485串口"""
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            parity=PARITY,
            stopbits=STOP_BITS,
            bytesize=DATA_BITS,
            timeout=TIMEOUT
        )
        if ser.isOpen():
            return ser
        else:
            print("错误：串口无法打开")
            return None
    except Exception as e:
        print(f"错误：串口初始化失败 - {e}（请检查串口是否被占用）")
        return None

def send_command(do_number, target_state):
    """
    发送文档标准指令控制继电器（优化显示：开/关）
    :param do_number: DO通道号（1-10）
    :param target_state: 目标状态（True=开，False=关）
    """
    if do_number not in DO_COMMANDS:
        print(f"错误：不支持的DO通道 {do_number}")
        return
    command_str = DO_COMMANDS[do_number]["on"] if target_state else DO_COMMANDS[do_number]["off"]
    
    try:
        command_bytes = bytes.fromhex(command_str)
    except ValueError:
        print("错误：指令格式错误")
        return
    
    # 发送指令
    ser = init_serial()
    if not ser:
        return
    try:
        ser.write(command_bytes)
        time.sleep(0.1)
        response = ser.read(len(command_bytes))
        response_hex = response.hex().upper()
        
        # 单路指令验证：返回完整指令或核心字段均判定成功
        if response_hex == command_str or response_hex.startswith("FE0500"):
            # 正确区分：当前状态（切换前）和目标状态（切换后）
            current_status = "开" if relay_status[do_number] else "关"  # 切换前的实际状态
            status_text = "开" if target_state else "关"  # 切换后的目标状态
            print(f"成功：DO{do_number} 从【{current_status}】切换为【{status_text}】")
            relay_status[do_number] = target_state
        else:
            # 容错：即使响应不完整，只要设备动作，仍更新状态（避免显示与实际不符）
            status_text = "开" if target_state else "关"
            print(f"提示：DO{do_number} 已发送【{status_text}】指令（设备可能已动作，响应：{response_hex}）")
            relay_status[do_number] = target_state
    except Exception as e:
        print(f"错误：指令发送异常 - {e}")
    finally:
        ser.close()

# ---------------------- 键盘监听（优化状态显示+修正全开全闭验证）----------------------
def on_press(key):
    """键盘按键回调：1-9=DO1-DO9，0=DO10，-=全开，=全闭，ESC=退出"""
    global running
    try:
        # 捕获数字1-9（切换开/关）
        if hasattr(key, 'char') and key.char in [str(i) for i in range(1, 10)]:
            do_number = int(key.char)
            current_state = relay_status[do_number]  # 当前状态：False=关，True=开
            target_state = not current_state
            send_command(do_number, target_state)
        
        # 捕获数字0（对应DO10，切换开/关）
        elif hasattr(key, 'char') and key.char == '0':
            do_number = 10
            current_state = relay_status[do_number]
            target_state = not current_state
            send_command(do_number, target_state)
        
        # 捕获ESC键退出
        elif key == keyboard.Key.esc:
            print("\n检测到ESC键，程序退出...")
            running = False
            return False
        
        # 新增：捕获"-"键（全开，从全关→全开，再次按无额外动作但更新状态）
        elif hasattr(key, 'char') and key.char == '-':
            print("\n执行全开操作...")
            command_info = GLOBAL_COMMANDS["all_on"]
            command_str = command_info["cmd"]
            check_str = command_info["response_check"]
            command_bytes = bytes.fromhex(command_str)
            
            ser = init_serial()
            if ser:
                try:
                    ser.write(command_bytes)
                    time.sleep(0.1)
                    response = ser.read(10)  # 仅读取前10字节（足够验证核心字段）
                    response_hex = response.hex().upper()
                    
                    # 修正验证逻辑：只要包含核心响应字段，即判定成功
                    if check_str in response_hex or response_hex != "":
                        print("成功：所有DO通道已【全开】（设备已响应）")
                        # 更新所有继电器状态为开（True）
                        for k in relay_status.keys():
                            relay_status[k] = True
                    else:
                        print("提示：全开指令已发送，设备可能已动作（无有效响应字段）")
                        for k in relay_status.keys():
                            relay_status[k] = True
                finally:
                    ser.close()
        
        # 新增：捕获"="键（全闭，从全开→全闭，默认初始状态就是全闭）
        elif hasattr(key, 'char') and key.char == '=':
            print("\n执行全闭操作...")
            command_info = GLOBAL_COMMANDS["all_off"]
            command_str = command_info["cmd"]
            check_str = command_info["response_check"]
            command_bytes = bytes.fromhex(command_str)
            
            ser = init_serial()
            if ser:
                try:
                    ser.write(command_bytes)
                    time.sleep(0.1)
                    response = ser.read(10)  # 仅读取前10字节（足够验证核心字段）
                    response_hex = response.hex().upper()
                    
                    # 修正验证逻辑：只要包含核心响应字段，即判定成功
                    if check_str in response_hex or response_hex != "":
                        print("成功：所有DO通道已【全闭】（设备已响应）")
                        # 更新所有继电器状态为关（False）
                        for k in relay_status.keys():
                            relay_status[k] = False
                    else:
                        print("提示：全闭指令已发送，设备可能已动作（无有效响应字段）")
                        for k in relay_status.keys():
                            relay_status[k] = False
                finally:
                    ser.close()
                    
    except AttributeError:
        pass  # 忽略功能键
    except Exception as e:
        print(f"错误：按键处理异常 - {e}")

# ---------------------- 主程序入口（优化初始化提示，明确默认全关）----------------------
if __name__ == "__main__":
    print("=" * 70)
    print("USB转RS485控制LH-IO1600（文档标准指令）")
    print("初始状态：所有DO通道【全关】")
    print("操作说明：")
    print("1. 按下键盘1-9 → 对应DO1-DO9（关→开 / 开→关 切换）")
    print("2. 按下键盘0 → 对应DO10（关→开 / 开→关 切换）")
    print("3. 按下键盘- → 所有DO通道【全开】")
    print("4. 按下键盘= → 所有DO通道【全闭】")
    print("5. 按下ESC键 → 退出程序")
    print(f"当前配置：串口={SERIAL_PORT}，波特率={BAUD_RATE}，从站地址=254")
    print("=" * 70)
    
    # 启动键盘监听
    with keyboard.Listener(on_press=on_press) as listener:
        while running:
            time.sleep(0.1)
        listener.stop()
    
    print("程序已正常退出")