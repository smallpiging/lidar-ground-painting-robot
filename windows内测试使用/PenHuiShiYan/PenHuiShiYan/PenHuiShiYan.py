# -*- coding: utf-8 -*-
import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import serial
import time
from threading import Thread

# ===================== 核心配置 =====================
CANVAS_WIDTH = 600
NUM_PENS = 10
CELL_WIDTH = 60
THRESHOLD = 127
# 上半圆参数（相切布局，直径60）
CIRCLE_R = 30
# 白色占比阈值（上半圆超过即喷涂）
WHITE_RATIO_THRESH = 0.2

# ===================== 串口配置 =====================
SERIAL_PORT = "COM9"
BAUD_RATE = 115200
DO_COMMANDS = {
    1: {"on": "FE050000FF009835", "off": "FE0500000000D9C5"},
    2: {"on": "FE050001FF00C9F5", "off": "FE05000100008805"},
    3: {"on": "FE050002FF0039F5", "off": "FE05000200007805"},
    4: {"on": "FE050003FF006835", "off": "FE050003000029C5"},
    5: {"on": "FE050004FF00D9F4", "off": "FE05000400009804"},
    6: {"on": "FE050005FF008334", "off": "FE0500050000C9C4"},
    7: {"on": "FE050006FF007834", "off": "FE050006000039C4"},
    8: {"on": "FE050007FF0029F4", "off": "FE05000700006804"},
    9: {"on": "FE050008FF0019F7", "off": "FE05000800005807"},
    10:{"on": "FE050009FF004837", "off": "FE050009000009C7"}
}

# 全局变量
spraying_flag = False
circle_obj_list = []
bin_crop = None  # 二值化图像（黑底白字）
display_img = None

# ===================== 串口控制（稳定下发指令） =====================
def send_cmd(hexstr):
    try:
        s = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.02)
        s.write(bytes.fromhex(hexstr))
        time.sleep(0.01)
        s.close()
    except:
        pass

def pen(n, on):
    send_cmd(DO_COMMANDS[n]["on"] if on else DO_COMMANDS[n]["off"])

def all_pen_open():
    for i in range(1,11): pen(i, True)
    messagebox.showinfo("提示","全部喷笔开启")

def all_pen_close():
    global spraying_flag
    spraying_flag = False
    for i in range(1,11): pen(i, False)

# ===================== 图像处理（修复：黑底白字 + 裁剪多余边框） =====================
def process_image(path):
    global bin_crop, display_img
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # ✅ 关键修复：反色二值化 → 白底黑字 → 黑底白字
    _, binary = cv2.threshold(gray, THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    
    # 找到白色字母的有效区域（裁剪掉周围空白）
    coords = cv2.findNonZero(binary)
    if coords is None:
        x, y, w, h = 0, 0, img.shape[1], img.shape[0]
    else:
        x, y, w, h = cv2.boundingRect(coords)
    
    # 裁剪二值图和原图
    bin_crop = binary[y:y+h, x:x+w]
    crop_rgb = img[y:y+h, x:x+w]
    
    # ✅ 显示图像也反色 → 让用户看到黑底白字
    crop_rgb_inv = cv2.bitwise_not(crop_rgb)
    
    # 等比例缩放
    scale = CANVAS_WIDTH / crop_rgb.shape[1]
    new_h = int(crop_rgb.shape[0] * scale)
    display_img = cv2.resize(crop_rgb_inv, (CANVAS_WIDTH, new_h), interpolation=cv2.INTER_NEAREST)
    bin_crop = cv2.resize(bin_crop, (CANVAS_WIDTH, new_h), interpolation=cv2.INTER_NEAREST)
    return display_img.shape[0]

# ===================== 核心：✅ 只计算【上半圆】白色占比 =====================
def get_upper_half_white_ratio(center_y, pen_idx):
    try:
        h, w = bin_crop.shape
        step = w / NUM_PENS
        center_x = int(step * pen_idx + step/2)
        
        # 采样区域：严格上半圆（红线以上部分）
        x1 = max(0, center_x - CIRCLE_R)
        x2 = min(w, center_x + CIRCLE_R)
        y1 = max(0, center_y - CIRCLE_R)
        y2 = center_y  # 只取上半部分，避免重复计算

        roi = bin_crop[y1:y2, x1:x2]
        total = roi.size
        if total <= 0: return 0.0
        white_count = np.sum(roi == 255)  # 统计上半圆里白色（原黑色字母）的占比
        return white_count / total
    except:
        return 0.0

# ===================== GUI界面 =====================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("上半圆瞄准喷涂系统")
        self.geometry("820x900")
        self.scan_line = None
        self.blocks = []
        self.build_ui()

    def build_ui(self):
        # 顶部按钮
        top = tk.Frame(self)
        top.pack(pady=8)
        tk.Button(top,text="导入图片",command=self.load_img).pack(side=tk.LEFT,padx=5)
        tk.Button(top,text="🔓一键全开",bg="green",fg="white",command=all_pen_open).pack(side=tk.LEFT,padx=5)
        tk.Button(top,text="🔒一键全闭",bg="red",fg="white",command=all_pen_close).pack(side=tk.LEFT,padx=5)
        tk.Button(top,text="开始喷绘",bg="#8f8",command=self.start_spray).pack(side=tk.LEFT,padx=5)

        # 画布
        self.canvas = tk.Canvas(self, bg="black", width=CANVAS_WIDTH)
        self.canvas.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)

        # 喷笔状态灯（修复：正常显示黑白）
        pen_frame = tk.Frame(self)
        pen_frame.pack(side=tk.RIGHT, padx=15)
        for i in range(10):
            self.blocks.append(tk.Canvas(pen_frame,width=60,height=30,bg="black"))
            self.blocks[-1].pack(pady=4)
            tk.Label(pen_frame,text=f"P{i+1}").pack()

    # 清空上半圆（不重叠）
    def clear_semi_circles(self):
        for item in circle_obj_list:
            self.canvas.delete(item)
        circle_obj_list.clear()

    # ✅ 绘制【上半圆】+ 十字准星（圆心在红线上）
    def draw_upper_semi_circles(self, center_y):
        self.clear_semi_circles()
        step = CANVAS_WIDTH / NUM_PENS
        for i in range(NUM_PENS):
            cx = step * i + step/2
            cy = center_y
            # 上半圆（圆弧：start=0, extent=180 → 上半部分）
            arc = self.canvas.create_arc(
                cx-CIRCLE_R, cy-CIRCLE_R,
                cx+CIRCLE_R, cy+CIRCLE_R,
                start=0, extent=180, outline="red", width=2
            )
            # 中心十字准星
            h_line = self.canvas.create_line(cx-10, cy, cx+10, cy, fill="red")
            v_line = self.canvas.create_line(cx, cy-10, cx, cy, fill="red")
            circle_obj_list.extend([arc, h_line, v_line])

    # 绿色竖直分隔线
    def draw_green_grid(self, height):
        for i in range(11):
            x = i * CELL_WIDTH
            self.canvas.create_line(x, 0, x, height, fill="green", dash=(2,2))

    def load_img(self):
        path = filedialog.askopenfilename()
        if not path: return
        img_h = process_image(path)
        self.canvas.config(height=img_h)
        self.canvas.delete("all")
        # 显示黑底白字图像
        img = Image.fromarray(cv2.cvtColor(display_img, cv2.COLOR_BGR2RGB))
        self.canvas.img = ImageTk.PhotoImage(img)
        self.canvas.create_image(0,0,image=self.canvas.img,anchor="nw")
        self.draw_green_grid(img_h)

    def start_spray(self):
        global spraying_flag
        if bin_crop is None or spraying_flag: return
        spraying_flag = True
        Thread(target=self.run_spray, daemon=True).start()

    # ===================== 核心喷涂逻辑 =====================
    def run_spray(self):
        total_h = bin_crop.shape[0]
        # 从下往上扫描（红线+上半圆）
        for y in range(total_h-1, -1, -1):
            if not spraying_flag: break

            # 1. 计算每个喷笔 上半圆白色占比
            states = []
            for i in range(NUM_PENS):
                ratio = get_upper_half_white_ratio(y, i)
                states.append(ratio > WHITE_RATIO_THRESH)

            # 2. ✅ 下发串口指令（精准控制喷笔）
            for i in range(NUM_PENS):
                pen(i+1, states[i])

            # 3. 更新界面
            self.after(0, self.update_ui, y, states)
            time.sleep(0.06)

        # 结束关闭所有喷笔
        all_pen_close()
        self.after(0, lambda: messagebox.showinfo("完成","喷涂结束"))

    # 更新界面：红线 + 上半圆 + 状态灯
    def update_ui(self, y, states):
        # 删除旧红线
        if self.scan_line:
            self.canvas.delete(self.scan_line)
        # 绘制新红线
        self.scan_line = self.canvas.create_line(0, y, CANVAS_WIDTH, y, fill="red", width=2)
        # 绘制上半圆瞄准
        self.draw_upper_semi_circles(y)
        # ✅ 修复状态灯：正常显示黑白（开=白，关=黑）
        for i in range(NUM_PENS):
            self.blocks[i].config(bg="white" if states[i] else "black")

if __name__ == "__main__":
    App().mainloop()