# auto_rectangle_main.py
# -*- coding: utf-8 -*-
from zlac8015d_core import ZLAC8015D_Driver, TIRE_CIRCUMFERENCE_MM, MAX_SPEED
import time

# ===================== 矩形轨迹辅助计算函数 =====================
def calculate_running_time(distance_mm, speed_rpm):
    """
    计算小车行驶指定距离所需的时间（秒）
    :param distance_mm: 行驶距离（毫米）
    :param speed_rpm: 车轮转速（RPM）
    :return: 行驶时间（秒）
    """
    if speed_rpm <= 0:
        return 0.0
    # 1. 计算需要的车轮转数：距离 ÷ 车轮周长
    wheel_turns = distance_mm / TIRE_CIRCUMFERENCE_MM
    # 2. 计算行驶时间（分钟）：转数 ÷ 转速（RPM）
    time_minutes = wheel_turns / speed_rpm
    # 3. 转换为秒
    time_seconds = time_minutes * 60
    return round(time_seconds, 2)

def move_straight(driver, distance_mm, speed_rpm, direction=1):
    """
    控制小车直线行驶指定距离
    :param driver: 驱动器实例
    :param distance_mm: 行驶距离（毫米）
    :param speed_rpm: 行驶速度（RPM）
    :param direction: 行驶方向（1=前进，-1=后退）
    :return: 无
    """
    if distance_mm <= 0 or speed_rpm <= 0:
        print("⚠️  距离或速度无效，跳过本次行驶")
        return
    
    # 1. 计算行驶时间
    run_time = calculate_running_time(distance_mm, speed_rpm)
    print(f"\n📌 开始直线行驶：距离={distance_mm}mm | 速度={speed_rpm}RPM | 预计时间={run_time}s")
    
    # 2. 设置车轮同速（直线行驶），方向一致
    left_speed = direction * speed_rpm
    right_speed = direction * speed_rpm
    driver.set_wheel_speed(left_speed, right_speed)
    
    # 3. 保持速度行驶指定时间
    start_time = time.time()
    while (time.time() - start_time) < run_time:
        # 实时读取反馈，监测故障
        feedback = driver.read_feedback()
        if not feedback["is_ok"]:
            print("❌ 行驶中出现故障，停止行驶")
            driver.emergency_stop()
            return
        time.sleep(0.05)
    
    # 4. 行驶完成，停止车轮
    driver.set_wheel_speed(0, 0)
    print("✅ 直线行驶完成")

def turn_90_degree(driver, speed_rpm, turn_direction="left"):
    """
    控制小车差动转向90度（简化版，基于时间）
    :param driver: 驱动器实例
    :param speed_rpm: 转向速度（RPM，建议小于MAX_SPEED/2）
    :param turn_direction: 转向方向（left=左转，right=右转）
    :return: 无
    """
    print(f"\n📌 开始{turn_direction}转90度 | 转向速度={speed_rpm}RPM")
    
    # 差动转向：左右轮反向转动
    if turn_direction == "left":
        # 左转：左轮后退，右轮前进
        left_speed = -speed_rpm
        right_speed = speed_rpm
    else:
        # 右转：左轮前进，右轮后退
        left_speed = speed_rpm
        right_speed = -speed_rpm
    
    # 设置转向速度（转向时间可根据实际小车微调，这里默认0.8秒）
    driver.set_wheel_speed(left_speed, right_speed)
    time.sleep(0.8)
    
    # 转向完成，停止车轮
    driver.set_wheel_speed(0, 0)
    print(f"✅ {turn_direction}转90度完成")

def run_rectangle_track(driver, rect_width, rect_length, speed_rpm):
    """
    执行矩形轨迹行驶（宽=rect_width，长=rect_length）
    轨迹逻辑：前进长→右转→前进宽→右转→前进长→右转→前进宽→右转（回到原点）
    """
    print(f"\n🚀 开始执行矩形轨迹：宽={rect_width}mm | 长={rect_length}mm | 速度={speed_rpm}RPM")
    time.sleep(1)
    
    # 矩形4条边+4次转向（循环执行）
    for i in range(2):
        # 第1段：前进长
        move_straight(driver, rect_length, speed_rpm, direction=1)
        time.sleep(0.5)
        
        # 右转90度
        turn_90_degree(driver, speed_rpm//2, turn_direction="right")
        time.sleep(0.5)
        
        # 第2段：前进宽
        move_straight(driver, rect_width, speed_rpm, direction=1)
        time.sleep(0.5)
        
        # 右转90度
        turn_90_degree(driver, speed_rpm//2, turn_direction="right")
        time.sleep(0.5)
    
    print("\n🎉 矩形轨迹行驶完成！")

# ===================== 用户输入交互 + 主程序 =====================
if __name__ == "__main__":
    # 1. 用户输入参数（带验证）
    print("==================== 小车矩形轨迹行驶程序 ====================")
    try:
        # 输入矩形尺寸
        rect_width = float(input("请输入矩形宽度（毫米，默认200）：") or 200)
        rect_length = float(input("请输入矩形长度（毫米，默认300）：") or 300)
        # 输入行驶速度
        speed_rpm = float(input(f"请输入行驶速度（RPM，1~{MAX_SPEED}，默认5）：") or 5)
        
        # 输入验证
        if rect_width <= 0 or rect_length <= 0:
            raise ValueError("矩形尺寸必须大于0")
        if not (1 <= speed_rpm <= MAX_SPEED):
            raise ValueError(f"速度必须在1~{MAX_SPEED}之间")
        
        # 转换为整数（方便显示，不影响计算）
        rect_width = int(rect_width)
        rect_length = int(rect_length)
        speed_rpm = int(speed_rpm)
        
    except ValueError as e:
        print(f"❌ 输入参数错误：{e}")
        exit(1)
    
    # 2. 初始化驱动器（复用核心模块的ZLAC8015D_Driver类）
    driver = ZLAC8015D_Driver()
    if not driver.connect():
        exit(1)
    if not driver.init_speed_mode():
        driver.close()
        exit(1)
    
    # 3. 执行矩形轨迹（核心：调用自定义函数，内部复用driver的方法）
    try:
        run_rectangle_track(driver, rect_width, rect_length, speed_rpm)
    except KeyboardInterrupt:
        print("\n\n👋 用户手动终止程序")
    finally:
        # 4. 安全停机，关闭连接（复用driver的方法）
        driver.stop()
        driver.close()
        print("✅ 程序正常退出")
