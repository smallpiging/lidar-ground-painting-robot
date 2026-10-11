# -*- coding: utf-8 -*-
import pygame
import sys
import serial
import time
import math

# ===================== 全局配置 =====================
SERIAL_PORT = "COM9"
BAUDRATE = 115200
DRIVER_ADDR = 1

CELL_SIZE = 90
GRID_ROWS = 5
INIT_WINDOW_WIDTH = 1400
WINDOW_HEIGHT = GRID_ROWS * CELL_SIZE + 100
RELAY_MAP = [1, 3, 5, 7, 9]

# ===================== 电磁阀指令 =====================
DO_COMMANDS = {
    1: {"on": bytes.fromhex("FE050000FF009835"), "off": bytes.fromhex("FE0500000000D9C5")},
    3: {"on": bytes.fromhex("FE050002FF0039F5"), "off": bytes.fromhex("FE05000200007805")},
    5: {"on": bytes.fromhex("FE050004FF00D9F4"), "off": bytes.fromhex("FE05000400009804")},
    7: {"on": bytes.fromhex("FE050006FF007834"), "off": bytes.fromhex("FE050006000039C4")},
    9: {"on": bytes.fromhex("FE050008FF0019F7"), "off": bytes.fromhex("FE05000800005807")},
}

# ===================== 小车寄存器（ZLAC8015D 手册） =====================
REG = {
    "RUN_MODE": 0x200D,
    "CONTROL_WORD": 0x200E,
    "LEFT_ACCEL": 0x2080,
    "RIGHT_ACCEL": 0x2081,
    "LEFT_DECEL": 0x2082,
    "RIGHT_DECEL": 0x2083,
    "LEFT_TARGET_SPEED": 0x2088,
    "RIGHT_TARGET_SPEED": 0x2089,
}

CONTROL_WORD = {
    "ESTOP": 0x05,
    "CLEAR_FAULT": 0x06,
    "STOP": 0x07,
    "ENABLE": 0x08,
}

CAR_INIT_CMDS = [
    (REG["RUN_MODE"], 3),
    (REG["LEFT_ACCEL"], 500),
    (REG["RIGHT_ACCEL"], 500),
    (REG["LEFT_DECEL"], 500),
    (REG["RIGHT_DECEL"], 500),
    (REG["CONTROL_WORD"], CONTROL_WORD["CLEAR_FAULT"]),
    (REG["CONTROL_WORD"], CONTROL_WORD["ENABLE"]),
]

# ===================== 5x5 字库 =====================
FONT_5X5 = {
    '0': [0b11111,0b10001,0b10001,0b10001,0b11111],
    '1': [0b00100,0b01100,0b00100,0b00100,0b01110],
    '2': [0b11111,0b00001,0b01111,0b10000,0b11111],
    '3': [0b11111,0b00001,0b01111,0b00001,0b11111],
    '4': [0b10001,0b10001,0b11111,0b00001,0b00001],
    '5': [0b11111,0b10000,0b11111,0b00001,0b11111],
    '6': [0b11111,0b10000,0b11111,0b10001,0b11111],
    '7': [0b11111,0b00001,0b00100,0b00100,0b00100],
    '8': [0b11111,0b10001,0b11111,0b10001,0b11111],
    '9': [0b11111,0b10001,0b11111,0b00001,0b11111],
    'A': [0b01110,0b10001,0b11111,0b10001,0b10001],
    'B': [0b11110,0b10001,0b11110,0b10001,0b11110],
    'C': [0b01111,0b10000,0b10000,0b10000,0b01111],
    'D': [0b11110,0b10001,0b10001,0b10001,0b11110],
    'E': [0b11111,0b10000,0b11110,0b10000,0b11111],
    'F': [0b11111,0b10000,0b11110,0b10000,0b10000],
}

# ===================== 共用串口控制器 =====================
class UnifiedController:
    def __init__(self):
        self.ser = None
        self.spray_state = {1:0,3:0,5:0,7:0,9:0}
        self.car_enabled = False

    def connect(self):
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUDRATE, parity='N', stopbits=1, bytesize=8, timeout=0.1)
            print("✅ COM9 连接成功")
            return True
        except Exception as e:
            print("❌ 串口失败", e)
            return False

    def crc16(self, data):
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc.to_bytes(2, 'little')

    def car_write_reg(self, reg, val):
        try:
            val = max(-32768, min(32767, val))
            frame = bytearray([DRIVER_ADDR, 0x06])
            frame.extend(reg.to_bytes(2, 'big'))
            frame.extend(val.to_bytes(2, 'big', signed=True))
            frame.extend(self.crc16(frame))
            self.ser.write(frame)
            time.sleep(0.01)
            return True
        except:
            return False

    def car_init(self):
        print("🔧 小车初始化...")
        for r, v in CAR_INIT_CMDS:
            self.car_write_reg(r, v)
        self.car_enabled = True
        print("✅ 小车已锁轴使能")

    def car_set_speed(self, rpm):
        if not self.car_enabled:
            self.car_init()
        rpm = max(-3000, min(3000, int(rpm)))
        self.car_write_reg(REG["LEFT_TARGET_SPEED"], -rpm)
        self.car_write_reg(REG["RIGHT_TARGET_SPEED"], rpm)
        print(f"📌 速度: {rpm} RPM")

    def car_stop(self):
        self.car_write_reg(REG["LEFT_TARGET_SPEED"], 0)
        self.car_write_reg(REG["RIGHT_TARGET_SPEED"], 0)
        self.car_write_reg(REG["CONTROL_WORD"], CONTROL_WORD["STOP"])
        self.car_enabled = False
        print("🛑 小车停机解轴")

    def car_emergency_stop(self):
        self.car_write_reg(REG["CONTROL_WORD"], CONTROL_WORD["ESTOP"])
        self.car_write_reg(REG["LEFT_TARGET_SPEED"], 0)
        self.car_write_reg(REG["RIGHT_TARGET_SPEED"], 0)
        self.car_enabled = False
        print("🚨 急停")

    def spray_set(self, ch, enable):
        if self.spray_state[ch] == enable:
            return
        self.spray_state[ch] = enable
        self.ser.write(DO_COMMANDS[ch]["on"] if enable else DO_COMMANDS[ch]["off"])
        time.sleep(0.005)

    def spray_all_off(self):
        for ch in RELAY_MAP:
            self.spray_set(ch, False)

# ===================== 工具函数 =====================
def render_text_to_canvas(text, start=0):
    c = start
    for ch in text:
        if ch not in FONT_5X5: continue
        d = FONT_5X5[ch]
        for y in range(5):
            b = d[y]
            for x in range(5):
                if (b >> (4-x)) & 1:
                    canvas[(c+x, y)] = True
                else:
                    canvas.pop((c+x, y), None)
        c +=6
    return c

def clear_area(ec, sc=0):
    for x in range(sc, ec):
        for y in range(5):
            canvas.pop((x,y), None)

def max_content_col():
    return max([x for x,y in canvas.keys()]) if canvas else -1

# ===================== 初始化 =====================
pygame.init()
screen = pygame.display.set_mode((INIT_WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
clock = pygame.time.Clock()
ui_font = pygame.font.SysFont("simhei", 18)

canvas = {}
text_input = ""
text_active = False
last_text_col = 0

speed_input = "10"
speed_active = False

scanning = False
scan_x = 0
is_drawing = False
is_erasing = False

ctl = UnifiedController()
if ctl.connect():
    ctl.car_init()

# 按钮
start_btn  = pygame.Rect(250, WINDOW_HEIGHT-35, 120, 30)
stop_btn   = pygame.Rect(400, WINDOW_HEIGHT-35, 120, 30)
resume_btn = pygame.Rect(550, WINDOW_HEIGHT-35, 120, 30)
estop_btn  = pygame.Rect(700, WINDOW_HEIGHT-35, 120, 30)

text_rect   = pygame.Rect(50, WINDOW_HEIGHT-35, 180, 30)
speed_rect  = pygame.Rect(850, WINDOW_HEIGHT-35, 120, 30)

# ===================== 主循环 =====================
while True:
    win_w, win_h = screen.get_size()
    max_col = win_w // CELL_SIZE

    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            ctl.spray_all_off()
            ctl.car_stop()
            pygame.quit()
            sys.exit()

        # 鼠标画图
        if e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 1:
                is_drawing, is_erasing = True, False
            elif e.button == 3:
                is_drawing, is_erasing = True, True
        if e.type == pygame.MOUSEBUTTONUP:
            is_drawing = False

        # 点击
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            text_active = text_rect.collidepoint(e.pos)
            speed_active = speed_rect.collidepoint(e.pos)
            if not (text_active or speed_active):
                text_active = speed_active = False

            if start_btn.collidepoint(e.pos):
                scanning = True
                scan_x = 0
                ctl.spray_all_off()
                ctl.car_set_speed(int(speed_input))

            elif stop_btn.collidepoint(e.pos):
                scanning = False
                ctl.spray_all_off()
                ctl.car_stop()

            elif resume_btn.collidepoint(e.pos):
                scanning = True
                ctl.car_set_speed(int(speed_input))

            elif estop_btn.collidepoint(e.pos):
                scanning = False
                ctl.spray_all_off()
                ctl.car_emergency_stop()

        # 字母输入
        if e.type == pygame.KEYDOWN and text_active:
            if e.key == pygame.K_BACKSPACE:
                text_input = text_input[:-1]
            else:
                c = e.unicode.upper()
                if c in FONT_5X5:
                    text_input += c
            clear_area(last_text_col)
            last_text_col = render_text_to_canvas(text_input)

        # 速度输入
        if e.type == pygame.KEYDOWN and speed_active:
            if e.key == pygame.K_BACKSPACE:
                speed_input = speed_input[:-1]
            elif e.unicode.isdigit():
                speed_input += e.unicode

    # 实时画图
    if is_drawing:
        mx, my = pygame.mouse.get_pos()
        if my < 5*CELL_SIZE:
            x = mx // CELL_SIZE
            y = my // CELL_SIZE
            if 0 <= y < 5:
                if is_erasing:
                    canvas.pop((x,y), None)
                else:
                    canvas[(x,y)] = True

    # 扫描喷涂
    if scanning:
        c = scan_x // CELL_SIZE
        for row in range(5):
            ch = RELAY_MAP[row]
            need = canvas.get((c, row), False)
            ctl.spray_set(ch, need)
        scan_x += 4
        if c > max_content_col():
            scanning = False
            ctl.spray_all_off()
            ctl.car_stop()

    # 绘制
    screen.fill((0,0,0))

    # 点阵
    for x in range(max_col):
        for y in range(5):
            rect = (x*CELL_SIZE+1, y*CELL_SIZE+1, CELL_SIZE-2, CELL_SIZE-2)
            pygame.draw.rect(screen, (255,255,255) if (x,y) in canvas else (0,0,0), rect)

    # 扫描线
    if scanning or scan_x > 0:
        pygame.draw.line(screen, (255,0,0), (scan_x,0), (scan_x,5*CELL_SIZE),3)
        for y in range(5):
            cx, cy = scan_x, y*CELL_SIZE + CELL_SIZE//2
            r = CELL_SIZE//2
            pygame.draw.arc(screen, (255,0,0), (cx-r, cy-r, 2*r, 2*r), -math.pi/2, math.pi/2,3)

    # 输入框
    pygame.draw.rect(screen, (40,40,60), text_rect)
    pygame.draw.rect(screen, (255,255,255), text_rect,2)
    screen.blit(ui_font.render(f"字母: {text_input}", True, (255,255,255)), (text_rect.x+5, text_rect.y+4))

    pygame.draw.rect(screen, (40,40,60), speed_rect)
    pygame.draw.rect(screen, (255,255,255), speed_rect,2)
    screen.blit(ui_font.render(f"速度(RPM):{speed_input}", True, (255,255,255)), (speed_rect.x+5, speed_rect.y+4))

    # 按钮
    pygame.draw.rect(screen, (0,180,0), start_btn)
    pygame.draw.rect(screen, (180,0,0), stop_btn)
    pygame.draw.rect(screen, (0,0,180), resume_btn)
    pygame.draw.rect(screen, (255,100,0), estop_btn)

    t1 = ui_font.render("重新开始",True,(255,255,255))
    t2 = ui_font.render("停止",True,(255,255,255))
    t3 = ui_font.render("继续",True,(255,255,255))
    t4 = ui_font.render("急停",True,(255,255,255))

    screen.blit(t1, (start_btn.centerx - t1.get_width()//2, start_btn.y+5))
    screen.blit(t2, (stop_btn.centerx - t2.get_width()//2, stop_btn.y+5))
    screen.blit(t3, (resume_btn.centerx - t3.get_width()//2, resume_btn.y+5))
    screen.blit(t4, (estop_btn.centerx - t4.get_width()//2, estop_btn.y+5))

    pygame.display.flip()
    clock.tick(60)