import serial
import time

# ==================== 串口配置 ====================
try:
    ser = serial.Serial(
        port="COM9",
        baudrate=115200,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=8,
        timeout=1
    )
    print("✅ 串口 COM9 打开成功")
    time.sleep(0.2)
except Exception as e:
    print(f"❌ 打开失败：{e}")
    exit()

# ==================== 发送指令 ====================
def send(hex_str, name):
    try:
        cmd = bytes.fromhex(hex_str)
        print(f"→ {name}")
        ser.write(cmd)
        time.sleep(0.2)
        resp = ser.read(64)
        print(f"← {resp.hex()}\n")
        return resp
    except Exception as e:
        print(f"❌ 失败：{e}")
        return None

# ==================== 真正原地旋转流程 ====================
# 1. 独立双电机模式（必须！否则永远一起往前走）
send("01 06 20 0C 00 01 83 C8", "设置独立双轮模式")

# 2. 相对位置模式
send("01 06 20 0D 00 01 D2 09", "相对位置模式")

# 3. 同步控制
send("01 06 20 0F 00 01 73 C9", "同步模式")

# 4. 电机使能
send("01 06 20 0E 00 08 E2 0F", "电机使能")
time.sleep(0.3)

# ==================== ✅ 核心：原地旋转指令（一轮正、一轮反） ====================
send("01 10 208A 0004 08 00003000 FFFFd000 88C1", "设置：左轮正转 右轮反转 → 原地转")

# 启动
send("01 06 20 0E 00 10 E2 05", "启动旋转")

print("⏳ 旋转中...")
time.sleep(4)

# 停止
send("01 06 20 0E 00 07 A2 0B", "停止")

ser.close()
print("\n🎉 动作完成：A点不动，原地旋转90°")