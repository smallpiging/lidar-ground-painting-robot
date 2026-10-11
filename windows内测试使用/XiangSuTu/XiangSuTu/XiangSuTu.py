import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

# -----------------------------------------------------------------------------
# 核心功能：自动裁黑边 + 10列分割 + 垂直翻转（适配小车从下往上走）
# -----------------------------------------------------------------------------
def process_image(image_path):
    # 1. 读取图片
    img = cv2.imread(image_path)
    if img is None:
        raise Exception("图片读取失败，请更换路径或图片格式")

    # 2. 转灰度 + 二值化（黑底白块，白色=喷漆）
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)

    # 3. 自动裁剪：去掉左右纯黑边
    coords = cv2.findNonZero(binary)
    x, y, w, h = cv2.boundingRect(coords)
    crop_img = binary[y:y+h, x:x+w]

    # 4. 垂直翻转（上下颠倒）：让图像底部 = 小车起点，顶部 = 小车终点
    crop_img = cv2.flip(crop_img, 0)  # 0 = 垂直翻转

    # 5. 缩放到宽度为10的整数倍，保证10列等宽
    target_width = (crop_img.shape[1] // 10) * 10
    crop_img = cv2.resize(crop_img, (target_width, crop_img.shape[0]), interpolation=cv2.INTER_NEAREST)

    # 6. 分割成10列（每列=1支喷笔）
    hh, ww = crop_img.shape
    col_w = ww // 10
    slices = []
    for i in range(10):
        sl = crop_img[:, i * col_w : (i+1)*col_w]
        slices.append(sl)

    # 7. 拼接回完整图像
    final_img = np.hstack(slices)
    return final_img

# -----------------------------------------------------------------------------
# GUI窗口（导入 + 开始 + 显示 + 自适应窗口大小）
# -----------------------------------------------------------------------------
class SprayPatternGenerator:
    def __init__(self, root):
        self.root = root
        self.root.title("10喷笔图案生成器（无黑边+自适应窗口版）")
        self.root.geometry("800x600")  # 初始窗口大小

        self.img_path = None
        self.processed_img = None

        # 按钮区
        self.frame = tk.Frame(root)
        self.frame.pack(pady=10)
        self.btn_import = tk.Button(self.frame, text="导入图片", font=("黑体",14), command=self.import_img)
        self.btn_import.grid(row=0, column=0, padx=10)

        self.btn_start = tk.Button(self.frame, text="开始处理", font=("黑体",14), command=self.start_proc)
        self.btn_start.grid(row=0, column=1, padx=10)

        # 显示画布
        self.canvas = tk.Canvas(root, bg="black")
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)

        self.label = tk.Label(root, text="请导入图片", font=("黑体",12))
        self.label.pack(pady=5)

    def import_img(self):
        path = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp")])
        if path:
            self.img_path = path
            self.label.config(text=f"已导入：{path.split('/')[-1]}")

    def start_proc(self):
        if not self.img_path:
            messagebox.showwarning("提示", "请先导入图片")
            return

        try:
            self.processed_img = process_image(self.img_path)
            img_pil = Image.fromarray(self.processed_img)
            self.tk_img = ImageTk.PhotoImage(img_pil)

            # ✅ 核心：自动调整窗口大小贴合图像
            img_w, img_h = img_pil.size
            # 窗口总高度 = 图像高度 + 按钮区高度 + 标签区高度
            total_height = img_h + 80  # 80为按钮+标签区域预留高度
            self.root.geometry(f"{img_w}x{total_height}")

            # 更新画布大小并显示图像
            self.canvas.config(width=img_w, height=img_h)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)
            self.label.config(text="✅ 处理完成：无黑边 | 10列等宽 | 窗口自适应 | 小车从下往上扫描")
        except Exception as e:
            messagebox.showerror("错误", str(e))

# -----------------------------------------------------------------------------
# 启动程序
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = SprayPatternGenerator(root)
    root.mainloop()