import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# 物理参数 (mm)
L = 500       # 轮距
d = 180       # A点到轴心的垂直距离
rpm = 10      # 设定转速
omega = (rpm * 2 * np.pi) / 60  # 转化为 rad/s

# 计算轮子到A点的半径和线速度
R_wheel = np.sqrt(d**2 + (L/2)**2)
v_magnitude = omega * R_wheel # 约 322.5 mm/s

# 仿真设置
duration = 1.5  # 旋转90度约需1.5秒 (10 RPM下)
fps = 30
frames = int(duration * fps)
thetas = np.linspace(0, np.pi/2, frames)

fig, ax = plt.subplots(figsize=(9, 9))
ax.set_aspect('equal')
ax.set_xlim(-400, 400)
ax.set_ylim(-100, 500)
ax.grid(True, linestyle=':', alpha=0.6)

# 绘制元素
robot_axle, = ax.plot([], [], 'k-', lw=3, label='Axle BC')
drawing_point, = ax.plot(0, 0, 'go', markersize=10)
# 速度矢量箭头 (Quiver)
q_b = ax.quiver(0, 0, 0, 0, color='blue', scale=1000, label='Vel B (Left)')
q_c = ax.quiver(0, 0, 0, 0, color='red', scale=1000, label='Vel C (Right)')
# 数值标注
txt_b = ax.text(0, 0, '', color='blue', fontweight='bold')
txt_c = ax.text(0, 0, '', color='red', fontweight='bold')
txt_a = ax.text(10, 10, 'Point A (Fixed)', color='green')

def update(theta):
    # 1. 位置计算 (保持A在原点)
    ox, oy = d * np.cos(theta), d * np.sin(theta)
    half_L = L / 2
    bx, by = ox - half_L * np.sin(theta), oy + half_L * np.cos(theta) # 左轮B
    cx, cy = ox + half_L * np.sin(theta), oy - half_L * np.cos(theta) # 右轮C
    
    robot_axle.set_data([bx, cx], [by, cy])
    
    # 2. 速度矢量计算 (垂直于半径方向)
    # 旋转中心是原点，所以速度方向是 (-y, x)
    vx_b, vy_b = -by * omega, bx * omega
    vx_c, vy_c = -cy * omega, cx * omega
    
    # 更新箭头
    q_b.set_offsets([bx, by])
    q_b.set_UVC(vx_b, vy_b)
    q_c.set_offsets([cx, cy])
    q_c.set_UVC(vx_c, vy_c)
    
    # 3. 更新数值标注
    txt_b.set_position((bx, by + 20))
    txt_b.set_text(f'B: {v_magnitude:.1f} mm/s')
    txt_c.set_position((cx, cy + 20))
    txt_c.set_text(f'C: {v_magnitude:.1f} mm/s')
    
    return robot_axle, q_b, q_c, txt_b, txt_c

ani = FuncAnimation(fig, update, frames=thetas, interval=1000/fps, blit=False)
plt.title(f"Differential Drive Simulation @ {rpm} RPM\nTarget: Point A Stationary")
plt.legend(loc='upper left')
plt.show()