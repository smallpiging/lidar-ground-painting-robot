import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import os

# 物理参数 (单位: cm)
AXLE_WIDTH = 50      # 车轴长度
PEN_OFFSET = 20     # 喷笔距车轴距离
SIDE_LEN = 30       # 正方形边长

def generate_robot_gif():
    # 获取 Ubuntu 桌面路径
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "robot_painting.gif")
    
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(-10, 60)
    ax.set_ylim(-30, 60)
    ax.set_aspect('equal')
    ax.grid(True, linestyle=':', alpha=0.5)
    ax.set_facecolor('#1c1c1c')
    
    # 绘制 30x30 参考框
    ax.add_patch(plt.Rectangle((0, 0), SIDE_LEN, SIDE_LEN, fill=False, color='white', alpha=0.2, ls='--'))

    path_line, = ax.plot([], [], lw=2.5, zorder=3)
    car_axle, = ax.plot([], [], '#f1c40f', lw=4, label='车轴 (50cm)')
    car_arm, = ax.plot([], [], '#f1c40f', lw=2)  # T字形竖杆
    pen_dot, = ax.plot([], [], 'ro', markersize=6, zorder=5)

    history_x, history_y = [], []

    def get_motion(t):
        """核心逻辑：t从0到5对应5个阶段"""
        if t <= 1:    # 1. 前进 30cm
            return (20 + 30 * t, 0), 0, 'white'
        elif t <= 2:  # 2. 后退 20cm (使车轴重合顶点)
            return (50 - 20 * (t - 1), 0), 0, 'red'
        elif t <= 3:  # 3. 原地旋转 90度 (圆心在30,0)
            return (30, 0), 90 * (t - 2), 'blue'
        elif t <= 4:  # 4. 前进 20cm (喷笔复位至30,0)
            return (30, 20 * (t - 3)), 90, 'green'
        else:         # 5. 喷绘 30cm
            return (30, 20 + 30 * (t - 4)), 90, 'yellow'

    def update(frame):
        t = frame / 20.0
        (cx, cy), angle, col = get_motion(t)
        rad = np.radians(angle)
        
        # 计算喷笔(P)位置: 始终在车轴(C)后方 20cm
        px = cx - PEN_OFFSET * np.cos(rad)
        py = cy - PEN_OFFSET * np.sin(rad)
        
        history_x.append(px)
        history_y.append(py)
        path_line.set_data(history_x, history_y)
        path_line.set_color(col)
        
        # 更新车体 T 字形
        dx, dy = -np.sin(rad)*(AXLE_WIDTH/2), np.cos(rad)*(AXLE_WIDTH/2)
        car_axle.set_data([cx-dx, cx+dx], [cy-dy, cy+dy])
        car_arm.set_data([cx, px], [cy, py])
        pen_dot.set_data([px], [py])
        
        return path_line, car_axle, car_arm, pen_dot

    ani = FuncAnimation(fig, update, frames=101, interval=50, blit=True)
    
    try:
        writer = PillowWriter(fps=20)
        ani.save(desktop_path, writer=writer)
        print(f"成功保存动画至: {desktop_path}")
    except Exception as e:
        print(f"保存失败: {e}")
    
    plt.title("喷绘机器人偏置补偿仿真 (修正版)")
    plt.show()

if __name__ == "__main__":
    generate_robot_gif()