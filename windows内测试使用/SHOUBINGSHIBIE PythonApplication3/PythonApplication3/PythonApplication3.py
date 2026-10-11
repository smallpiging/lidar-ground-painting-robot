# -*- coding: utf-8 -*-
import pygame
import sys
import time

def init_gamepad():
    """初始化手柄，检查连接状态"""
    # 初始化pygame
    pygame.init()
    pygame.joystick.init()

    # 检查是否有手柄连接
    joystick_count = pygame.joystick.get_count()
    if joystick_count == 0:
        print("❌ 未检测到任何手柄，请连接手柄后重新运行程序！")
        pygame.quit()
        sys.exit(1)

    # 初始化第一个手柄（多手柄可修改索引）
    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    # 打印手柄基础信息
    print("="*60)
    print(f"✅ 检测到手柄：{joystick.get_name()}")
    print(f"🎮 手柄ID：{joystick.get_id()}")
    print(f"🔢 按键总数：{joystick.get_numbuttons()}")
    print(f"🕹️  摇杆总数：{joystick.get_numaxes()}")
    print(f"🎚️  方向键（Hats）总数：{joystick.get_numhats()}")
    print("="*60)
    print("操作说明：")
    print("1. 按下任意按键/拨动摇杆/操作方向键，实时显示对应编号和数值")
    print("2. 摇杆数值范围：-1.0 ~ 1.0（0为中立位）")
    print("3. 方向键数值：(0,1)=上、(0,-1)=下、(1,0)=右、(-1,0)=左、(0,0)=中立")
    print("4. 按键盘【ESC】键退出程序")
    print("="*60)

    return joystick

def monitor_gamepad(joystick):
    """实时监控手柄输入并打印对应信息"""
    # 初始化状态缓存，避免重复打印
    last_button_state = [False] * joystick.get_numbuttons()
    last_axis_state = [0.0] * joystick.get_numaxes()
    last_hat_state = [(0, 0)] * joystick.get_numhats()

    print("\n📌 开始监控手柄输入（按ESC退出）...\n")

    while True:
        # 处理pygame事件
        for event in pygame.event.get():
            # 按ESC退出
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                print("\n👋 程序已退出！")
                joystick.quit()
                pygame.quit()
                sys.exit(0)

        # 1. 检测按键（按下/松开）
        for button_idx in range(joystick.get_numbuttons()):
            current_state = joystick.get_button(button_idx)
            if current_state != last_button_state[button_idx]:
                last_button_state[button_idx] = current_state
                if current_state:
                    print(f"🔘 按键 {button_idx} → 按下")
                else:
                    print(f"🔘 按键 {button_idx} → 松开")

        # 2. 检测摇杆（数值变化）
        for axis_idx in range(joystick.get_numaxes()):
            current_value = round(joystick.get_axis(axis_idx), 3)  # 保留3位小数，减少抖动
            # 摇杆中立位可能有微小偏移，设置阈值0.05过滤
            if abs(current_value - last_axis_state[axis_idx]) > 0.05:
                last_axis_state[axis_idx] = current_value
                print(f"🕹️  摇杆 {axis_idx} → 数值：{current_value}")

        # 3. 检测方向键（Hat）
        for hat_idx in range(joystick.get_numhats()):
            current_value = joystick.get_hat(hat_idx)
            if current_value != last_hat_state[hat_idx]:
                last_hat_state[hat_idx] = current_value
                direction = ""
                if current_value == (0, 1):
                    direction = "上"
                elif current_value == (0, -1):
                    direction = "下"
                elif current_value == (1, 0):
                    direction = "右"
                elif current_value == (-1, 0):
                    direction = "左"
                elif current_value == (0, 0):
                    direction = "中立"
                print(f"🎛️  方向键 {hat_idx} → 数值：{current_value}（{direction}）")

        # 降低刷新频率，减少终端刷屏（可调整）
        time.sleep(0.05)

if __name__ == "__main__":
    try:
        gamepad = init_gamepad()
        monitor_gamepad(gamepad)
    except Exception as e:
        print(f"\n❌ 程序运行出错：{str(e)}")
        pygame.quit()
        sys.exit(1)
