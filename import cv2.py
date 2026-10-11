import cv2
import numpy as np
import yaml
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, TextBox, Button
import matplotlib.patches as patches

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'WenQuanYi Micro Hei', 'Noto Sans CJK JP', 'Droid Sans Fallback']
plt.rcParams['axes.unicode_minus'] = False

def load_map():
    yaml_path = '/home/ycy/YCY/my_map.yaml'
    pgm_path = '/home/ycy/YCY/my_map.pgm'
    try:
        with open(yaml_path, 'r') as f:
            meta = yaml.safe_load(f)
            res = meta['resolution']
        img = cv2.imread(pgm_path, cv2.IMREAD_GRAYSCALE)
        if img is None: raise FileNotFoundError
        _, mask = cv2.threshold(img, 205, 255, cv2.THRESH_BINARY_INV)
        coords = cv2.findNonZero(mask)
        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            img = img[y:y+h, x:x+w]
        return img, res
    except:
        print("错误：无法加载地图文件，请检查路径。")
        return None, None

class AdvancedMapTool:
    def __init__(self, img, res):
        if img is None: return
        self.base_img, self.res = img, res
        self.current_img = self.base_img.copy()
        
        # 物理参数
        self.placing_mode = None  
        self.measure_active = False # 测距开关
        self.snap_threshold_m = 0.5
        
        # 线宽换算
        self.outer_lw_m = 0.60
        self.inner_lw_m = 0.15
        self.outer_lw_px = max(1, int(self.outer_lw_m / self.res))
        self.inner_lw_px = max(1, int(self.inner_lw_m / self.res))
        
        # 存储对象
        self.placed_shapes = [] # 存储 (outer_patch, inner_patch) 元组
        self.measure_points = []
        self.temp_plots = [] 
        
        # 界面布局
        self.fig = plt.figure(num='地图高级规划工具', figsize=(15, 9))
        self.ax_panel = self.fig.add_axes([0.02, 0.05, 0.15, 0.9])
        self.ax_panel.axis('off')
        
        self.ax = self.fig.add_axes([0.2, 0.12, 0.75, 0.85])
        self.ax.set_axis_off()
        self.im_display = self.ax.imshow(self.current_img, cmap='gray', interpolation='nearest')
        
        self.ax_slider = self.fig.add_axes([0.2, 0.04, 0.75, 0.03])
        self.slider = Slider(self.ax_slider, '地图旋转 ', 0, 360, valinit=0)
        self.slider.on_changed(self.update_transform)

        # --- UI 控件 ---
        # 矩形
        self.ax_box_w = self.fig.add_axes([0.08, 0.88, 0.08, 0.03])
        self.box_w = TextBox(self.ax_box_w, '宽(m): ', initial='2.0')
        self.ax_box_h = self.fig.add_axes([0.08, 0.84, 0.08, 0.03])
        self.box_h = TextBox(self.ax_box_h, '高(m): ', initial='1.5')
        self.ax_btn_rect = self.fig.add_axes([0.03, 0.79, 0.13, 0.04])
        self.btn_rect = Button(self.ax_btn_rect, '放置双层矩形')
        self.btn_rect.on_clicked(lambda e: self.set_mode('rect'))

        # 圆形
        self.ax_box_r = self.fig.add_axes([0.08, 0.72, 0.08, 0.03])
        self.box_r = TextBox(self.ax_box_r, '半径(m): ', initial='1.0')
        self.ax_btn_circ = self.fig.add_axes([0.03, 0.67, 0.13, 0.04])
        self.btn_circ = Button(self.ax_btn_circ, '放置双层圆形')
        self.btn_circ.on_clicked(lambda e: self.set_mode('circle'))

        # 测距模块
        self.ax_btn_measure = self.fig.add_axes([0.03, 0.58, 0.13, 0.05])
        self.btn_measure = Button(self.ax_btn_measure, '开启测距', color='#ffcc00')
        self.btn_measure.on_clicked(self.toggle_measure)

        self.dynamic_outer = None
        self.dynamic_inner = None
        self.snap_lines = []
        self.update_physics_data()

        self.fig.canvas.mpl_connect('motion_notify_event', self.on_hover)
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)

        print(f"\n配置成功：外宽 {self.outer_lw_m}m, 内宽 {self.inner_lw_m}m")

    def toggle_measure(self, event):
        self.measure_active = not self.measure_active
        self.btn_measure.label.set_text('测距运行中...' if self.measure_active else '开启测距')
        self.btn_measure.color = '#00ff00' if self.measure_active else '#ffcc00'
        if not self.measure_active:
            self.measure_points = [] # 清除待定点
        self.placing_mode = None # 互斥
        self.fig.canvas.draw_idle()

    def set_mode(self, mode):
        self.placing_mode = mode
        self.measure_active = False # 互斥
        self.btn_measure.label.set_text('开启测距')
        self.btn_measure.color = '#ffcc00'
        
        if self.dynamic_outer: 
            self.dynamic_outer.remove(); self.dynamic_inner.remove()
        
        try:
            if mode == 'rect':
                w, h = float(self.box_w.text)/self.res, float(self.box_h.text)/self.res
                self.dynamic_outer = patches.Rectangle((0,0), w, h, lw=self.outer_lw_px, edgecolor='g', facecolor='none', alpha=0.6)
                self.dynamic_inner = patches.Rectangle((0,0), w, h, lw=self.inner_lw_px, edgecolor='yellow', facecolor='none', alpha=1.0)
            elif mode == 'circle':
                r = float(self.box_r.text)/self.res
                self.dynamic_outer = patches.Circle((0,0), r, lw=self.outer_lw_px, edgecolor='g', facecolor='none', alpha=0.6)
                self.dynamic_inner = patches.Circle((0,0), r, lw=self.inner_lw_px, edgecolor='yellow', facecolor='none', alpha=1.0)
            
            self.ax.add_patch(self.dynamic_outer)
            self.ax.add_patch(self.dynamic_inner)
        except: self.placing_mode = None

    def on_hover(self, event):
        if event.inaxes != self.ax or not self.placing_mode or not self.dynamic_outer: return
        tx, ty = event.xdata, event.ydata
        snap_px = self.snap_threshold_m/self.res
        
        # 磁吸
        if len(self.wall_x)>0:
            nx = self.wall_x[np.abs(self.wall_x-tx).argmin()]
            if abs(nx-tx)<snap_px: tx = nx
        if len(self.wall_y)>0:
            ny = self.wall_y[np.abs(self.wall_y-ty).argmin()]
            if abs(ny-ty)<snap_px: ty = ny

        mask = np.zeros_like(self.wall_mask)
        if self.placing_mode == 'rect':
            w, h = self.dynamic_outer.get_width(), self.dynamic_outer.get_height()
            px, py = tx-w/2, ty-h/2
            self.dynamic_outer.set_xy((px, py)); self.dynamic_inner.set_xy((px, py))
            cv2.rectangle(mask, (int(px), int(py)), (int(px+w), int(py+h)), 255, self.outer_lw_px)
        elif self.placing_mode == 'circle':
            self.dynamic_outer.set_center((tx, ty)); self.dynamic_inner.set_center((tx, ty))
            cv2.circle(mask, (int(tx), int(ty)), int(self.dynamic_outer.radius), 255, self.outer_lw_px)
        
        hit = np.any(cv2.bitwise_and(self.wall_mask, mask) > 0)
        self.dynamic_outer.set_edgecolor('red' if hit else 'green')
        self.fig.canvas.draw_idle()

    def on_click(self, event):
        if event.inaxes != self.ax: return
        
        # 右键撤销 (依次删除图形或测量结果)
        if event.button == 3:
            if self.placed_shapes:
                o, i = self.placed_shapes.pop()
                o.remove(); i.remove()
            elif self.temp_plots:
                for _ in range(3): 
                    if self.temp_plots: self.temp_plots.pop().remove()
            self.fig.canvas.draw_idle()
            return

        if event.button == 1:
            # 图形放置
            if self.placing_mode:
                if self.placing_mode == 'rect':
                    o = patches.Rectangle(self.dynamic_outer.get_xy(), self.dynamic_outer.get_width(), self.dynamic_outer.get_height(), edgecolor=self.dynamic_outer.get_edgecolor(), facecolor='none', lw=self.outer_lw_px, alpha=0.7)
                    i = patches.Rectangle(self.dynamic_inner.get_xy(), self.dynamic_inner.get_width(), self.dynamic_inner.get_height(), edgecolor='yellow', facecolor='none', lw=self.inner_lw_px)
                else:
                    o = patches.Circle(self.dynamic_outer.center, self.dynamic_outer.radius, edgecolor=self.dynamic_outer.get_edgecolor(), facecolor='none', lw=self.outer_lw_px, alpha=0.7)
                    i = patches.Circle(self.dynamic_inner.center, self.dynamic_inner.radius, edgecolor='yellow', facecolor='none', lw=self.inner_lw_px)
                
                self.ax.add_patch(o); self.ax.add_patch(i)
                self.placed_shapes.append((o, i))
                self.dynamic_outer.remove(); self.dynamic_inner.remove()
                self.placing_mode, self.dynamic_outer, self.dynamic_inner = None, None, None
            
            # 测距模块 (显式启用后生效)
            elif self.measure_active:
                self.measure_points.append((event.xdata, event.ydata))
                dot, = self.ax.plot(event.xdata, event.ydata, 'ro', ms=4)
                self.temp_plots.append(dot)
                if len(self.measure_points) == 2:
                    p1, p2 = self.measure_points
                    dist = np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2) * self.res
                    line, = self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], 'r--', lw=1)
                    txt = self.ax.text((p1[0]+p2[0])/2, (p1[1]+p2[1])/2, f"{dist:.2f}m", color='white', fontsize=10, fontweight='bold', bbox=dict(facecolor='red', alpha=0.5, edgecolor='none'))
                    self.temp_plots.extend([line, txt])
                    self.measure_points = []
            
            self.fig.canvas.draw_idle()

    def update_transform(self, val):
        angle = self.slider.val
        h, w = self.base_img.shape[:2]
        M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
        cos, sin = np.abs(M[0,0]), np.abs(M[0,1])
        nW, nH = int((h*sin)+(w*cos)), int((h*cos)+(w*sin))
        M[0,2] += (nW/2)-(w//2); M[1,2] += (nH/2)-(h//2)
        self.current_img = cv2.warpAffine(self.base_img, M, (nW, nH), flags=cv2.INTER_NEAREST, borderValue=205)
        self.im_display.set_data(self.current_img)
        self.im_display.set_extent([0, nW, nH, 0])
        self.ax.set_xlim(0, nW); self.ax.set_ylim(nH, 0)
        self.update_physics_data()
        self.fig.canvas.draw_idle()

    def update_physics_data(self):
        _, self.wall_mask = cv2.threshold(self.current_img, 50, 255, cv2.THRESH_BINARY_INV)
        coords = np.column_stack(np.where(self.wall_mask > 0))
        self.wall_y, self.wall_x = (np.unique(coords[:,0]), np.unique(coords[:,1])) if len(coords)>0 else ([], [])

    def on_scroll(self, event):
        if event.inaxes != self.ax: return
        scale = (1/1.2) if event.button == 'up' else 1.2
        cur_xlim, cur_ylim = self.ax.get_xlim(), self.ax.get_ylim()
        new_w, new_h = (cur_xlim[1]-cur_xlim[0])*scale, (cur_ylim[1]-cur_ylim[0])*scale
        self.ax.set_xlim([event.xdata - new_w*((cur_xlim[1]-event.xdata)/(cur_xlim[1]-cur_xlim[0])), event.xdata + new_w*((event.xdata-cur_xlim[0])/(cur_xlim[1]-cur_xlim[0]))])
        self.ax.set_ylim([event.ydata - new_h*((cur_ylim[1]-event.ydata)/(cur_ylim[1]-cur_ylim[0])), event.ydata + new_h*((event.ydata-cur_ylim[0])/(cur_ylim[1]-cur_ylim[0]))])
        self.fig.canvas.draw_idle()

if __name__ == "__main__":
    img, res = load_map()
    if img is not None:
        tool = AdvancedMapTool(img, res)
        plt.show()