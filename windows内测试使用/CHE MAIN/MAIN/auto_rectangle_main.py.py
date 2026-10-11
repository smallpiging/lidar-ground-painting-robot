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

def calculate_turn_time(wheelbase_mm=500, tire_circumference_mm=439.8, speed_rpm=30, angle_deg=90):
    """
    精准计算：以右轮为圆心转指定角度的转弯时间（基于轮距和轮胎尺寸）
    :param wheelbase_mm: 两轮轴线距离（默认500mm，你的实际参数）
    :param tire_circumference_mm: 轮胎周长（默认439.8mm，5.5英寸轮胎）
    :param speed_rpm: 左轮转速（默认30RPM）
    :param angle_deg: 转向角度（默认90°）
    :return: 精准转弯时间（秒）
    """
    if speed_rpm <= 0:
        return 0.0
    # 1. 计算左轮需要走的弧长（以右轮为圆心的圆弧）
    arc_length = (angle_deg / 360) * 2 * 3.14159 * wheelbase_mm
    # 2. 计算左轮需要的转数：弧长 ÷ 轮胎周长
    wheel_turns = arc_length / tire_circumference_mm
    # 3. 计算转弯时间（秒）：转数 ÷ 转速（转/秒）
    turn_time = wheel_turns / (speed_rpm / 60)
    return round(turn_time, 2)  # 保留2位小数，精准到0.01秒

def move_straight(driver, distance_mm, speed_rpm, direction=1):
    """
    控制小车直线行驶指定距离（修正：两轮同向同速，避免原地转圈）
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
    
    # 核心修正：直线行驶需两轮同向同速（适配你的右轮硬件负号需求）
    # 左轮：直接赋值（与direction一致），右轮：加负号（适配硬件，保证与左轮同向）
    base_speed = -direction * speed_rpm
    left_speed = base_speed  # 左轮：无负号（保持你的硬件适配）
    right_speed = -base_speed  # 右轮：加负号（关键！保证与左轮同向，避免反向转圈）
    
    # 2. 设置车轮同速（直线行驶核心）
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

def turn_90_degree_clockwise(driver, speed_rpm=30):
    """
    精准顺时针转90°：右轮停止，左轮以指定速度转动（自动计算转弯时间）
    :param driver: 驱动器实例
    :param speed_rpm: 左轮转速（默认30RPM，可自定义）
    :return: 无
    """
    if speed_rpm <= 0:
        print("⚠️  转向速度无效，使用默认30RPM")
        speed_rpm = 30
    
    # 自动计算精准转弯时间（基于500mm轮距+5.5英寸轮胎+90°）
    turn_time = calculate_turn_time(
        wheelbase_mm=500,          # 你的两轮轴线距离
        tire_circumference_mm=439.8, # 5.5英寸轮胎周长
        speed_rpm=speed_rpm,       # 传入的左轮转速
        angle_deg=90               # 转向90°
    )
    print(f"\n📌 开始顺时针转90度 | 左轮速度={speed_rpm}RPM | 右轮停止 | 精准时间={turn_time}s")
    
    # 适配你的起始方向（保留整体负号，与直线方向一致）
    left_speed = -speed_rpm  # 左轮转动（负号适配起始方向，反了就去掉）
    right_speed = 0          # 右轮停止（核心！）
    
    # 设置转向速度：右轮停，左轮转
    driver.set_wheel_speed(left_speed, right_speed)
    
    # 保持转向精准时间
    start_time = time.time()
    while (time.time() - start_time) < turn_time:
        # 实时监测故障，确保转向安全
        feedback = driver.read_feedback()
        if not feedback["is_ok"]:
            print("❌ 转向中出现故障，停止转向")
            driver.emergency_stop()
            return
        time.sleep(0.05)
    
    # 转向完成，停止所有车轮
    driver.set_wheel_speed(0, 0)
    print("✅ 顺时针转90度完成（精准时间控制）")

def calculate_circle_speed_ratio(target_diameter_mm, wheelbase_mm=500):
    """
    根据目标圆直径，计算差动转向的左右轮速度比
    :param target_diameter_mm: 目标圆直径（必须>500mm）
    :param wheelbase_mm: 轮距
    :return: (v_L_ratio, v_R_ratio) 速度比例，None表示参数无效
    """
    L = wheelbase_mm
    R = target_diameter_mm / 2  # 目标半径
    if R <= L/2:
        print(f"❌ 目标直径必须大于{L}mm（半径>{L/2}mm）")
        return None, None
    # 计算速度比
    v_L_ratio = R + L/2
    v_R_ratio = R - L/2
    return v_L_ratio, v_R_ratio

def draw_clockwise_circle(driver, target_diameter_mm, max_speed_rpm=30):
    """
    控制小车顺时针画完整圆（差动转向，任意直径）
    :param driver: 驱动器实例
    :param target_diameter_mm: 目标圆直径（>500mm）
    :param max_speed_rpm: 左轮最大速度（默认30RPM）
    """
    # 1. 计算速度比
    v_L_ratio, v_R_ratio = calculate_circle_speed_ratio(target_diameter_mm)
    if v_L_ratio is None:
        return
    # 2. 确定左右轮实际速度（左轮取max_speed_rpm）
    v_L = max_speed_rpm
    v_R = int(v_L * v_R_ratio / v_L_ratio)
    if v_R <= 0:
        print("❌ 右轮速度为0或负数，无法画圆")
        return
    # 3. 计算画完整圆的时间
    R = target_diameter_mm / 2
    tire_circum = 439.8  # 5.5英寸轮胎周长
    # 喷漆点一圈的周长 / 左轮线速度（mm/秒）-
    left_line_speed = tire_circum * (v_L / 60)  # mm/秒
    draw_time = circle_circum / left_line_speed
    draw_time = round(draw_time, 2)

    print(f"\n🎯 开始顺时针画圆 | 直径={target_diameter_mm}mm | 半径={R}mm")
    print(f"⚡ 速度配置：左轮{v_L}RPM | 右轮{v_R}RPM | 预计时间{draw_time}s")

    # 4. 硬件适配：右轮加负号，保证同向（和直线行驶逻辑一致）
    left_speed = -v_L  # 适配起始方向负号
    right_speed = v_R  # 右轮加负号，和左轮同向

    # 5. 开始画圆
    driver.set_wheel_speed(left_speed, right_speed)
    start_time = time.time()
    while (time.time() - start_time) < draw_time:
        feedback = driver.read_feedback()
        if not feedback["is_ok"]:
            print("❌ 画圆中出现故障，停止")
            driver.emergency_stop()
            return
        time.sleep(0.05)
    
    # 6. 画圆完成，停止
    driver.set_wheel_speed(0, 0)
    print(f"✅ 顺时针画圆完成！实际耗时{round(time.time()-start_time,2)}s")

def run_rectangle_track(driver, rect_width, rect_length, speed_rpm):
    """
    执行矩形轨迹行驶（宽=rect_width，长=rect_length）
    轨迹逻辑：前进长→顺时针转90°→前进宽→顺时针转90°→前进长→顺时针转90°→前进宽→顺时针转90°（回到原点）
    """
    print(f"\n🚀 开始执行矩形轨迹：宽={rect_width}mm | 长={rect_length}mm | 行驶速度={speed_rpm}RPM")
    print(f"📌 转弯参数：顺时针转90° | 左轮30RPM | 右轮停止 | 转动4秒")
    time.sleep(1)
    
    # 矩形4条边+4次顺时针转弯（循环执行）
    for i in range(2):
        # 第1段：前进长
        move_straight(driver, rect_length, speed_rpm, direction=1)
        time.sleep(0.5)
        
        # 顺时针转90度（使用新的转弯函数，默认30RPM+4秒）
        turn_90_degree_clockwise(driver)
        time.sleep(0.5)
        
        # 第2段：前进宽
        move_straight(driver, rect_width, speed_rpm, direction=1)
        time.sleep(0.5)
        
        # 顺时针转90度
        turn_90_degree_clockwise(driver)
        time.sleep(0.5)
    
    print("\n🎉 矩形轨迹行驶完成！")
# ===================== 用户输入交互 + 主程序 =====================
if __name__ == "__main__":
    # 1. 功能选择
    print("==================== 小车轨迹控制程序 ====================")
    print("请选择功能：")
    print("1. 画矩形（200mm×300mm）")
    print("2. 顺时针画圆（自定义直径）")
    choice = input("输入1或2：")

    # 2. 初始化驱动器
    driver = ZLAC8015D_Driver()
    if not driver.connect():
        exit(1)
    if not driver.init_speed_mode():
        driver.close()
        exit(1)

    try:
        if choice == "1":
            # 原有矩形轨迹逻辑
            rect_width = float(input("请输入矩形宽度（毫米，默认200）：") or 200)
            rect_length = float(input("请输入矩形长度（毫米，默认300）：") or 300)
            speed_rpm = float(input(f"请输入行驶速度（RPM，1~20，默认5）：") or 5)
            if rect_width <= 0 or rect_length <= 0 or not (1 <= speed_rpm <= 50):
                raise ValueError("参数无效")
            run_rectangle_track(driver, int(rect_width), int(rect_length), int(speed_rpm))
        elif choice == "2":
            # 新增画圆逻辑
            target_dia = float(input(f"请输入圆直径（毫米，必须>500，默认1000）：") or 1000)
            max_speed = float(input(f"请输入左轮最大速度（RPM，默认30）：") or 30)
            if max_speed <= 0:
                raise ValueError("速度无效")
            draw_clockwise_circle(driver, int(target_dia), int(max_speed))
        else:
            print("❌ 选择无效")
    except KeyboardInterrupt:
        print("\n\n👋 用户手动终止")
    except ValueError as e:
        print(f"❌ 参数错误：{e}")
    finally:
        driver.stop()
        driver.close()
        print("✅ 程序正常退出")
