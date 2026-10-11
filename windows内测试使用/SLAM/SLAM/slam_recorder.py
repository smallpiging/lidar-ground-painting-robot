import os
import time
import numpy as np
from r2000_driver import R2000Driver

def start_recording(duration_seconds=60, filename="office_scan_01"):
    # 1. 初始化驱动
    # SLAM 调试建议：20Hz 频率，2400点（或1200点），保证数据量适中
    driver = R2000Driver(freq=35, samples=2400)
    driver.start()
    
    print(f"开始录制数据集: {filename}")
    print(f"预计持续时间: {duration_seconds} 秒...")
    
    frames_data = []
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration_seconds:
            if not driver.frame_queue.empty():
                frame = driver.frame_queue.get()
                # 存储 [时间戳, 点云数据]
                frames_data.append(frame)
                
                # 每录制 20 帧打印一次进度
                if len(frames_data) % 20 == 0:
                    elapsed = time.time() - start_time
                    print(f"已录制: {elapsed:.1f}s | 当前帧数: {len(frames_data)}")
            
            time.sleep(0.005) # 稍微休眠，减少 CPU 占用
            
    except KeyboardInterrupt:
        print("\n用户中止录制")
    finally:
        driver.stop()
        
    # 2. 保存数据
# --- 修改后的保存逻辑 ---
    if frames_data:
        save_path = f"{filename}.npz"
        
        # 提取时间戳序列
        timestamps = np.array([f['timestamp'] for f in frames_data])
        
        # 【关键修改】：将点云列表转换为 dtype=object 的 NumPy 数组
        # 这样即使每帧点数不一样也能保存
        points_list = np.array([f['points'] for f in frames_data], dtype=object)
        
        np.savez_compressed(save_path, timestamps=timestamps, points=points_list)
        print(f"--- 录制完成 ---")
        print(f"文件保存在: {os.path.abspath(save_path)}")
        print(f"总计帧数: {len(timestamps)}")
    else:
        print("未采集到数据。")

if __name__ == "__main__":
    # 创建 data 文件夹存放数据
    if not os.path.exists("data"):
        os.makedirs("data")
    
    # 录制 30 秒的数据
    start_recording(duration_seconds=30, filename="data/test_room_35hz")



