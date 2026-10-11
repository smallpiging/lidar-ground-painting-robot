# -*- coding: utf-8 -*-
import numpy as np
import open3d as o3d
import os
import time

def preprocess_pcd(pcd, voxel_size):
    """高精度预处理"""
    # 这里的 voxel_size 设置为 0.01 (1cm)
    pcd_down = pcd.voxel_down_sample(voxel_size)
    # 增加法线估计的邻域搜索范围，确保在高密度下的法线平滑
    pcd_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 5, max_nn=50))
    return pcd_down

def main():
    # 1. 配置
    data_path = "data/test_room_35hz.npz"
    voxel_size = 0.01  # 精度提升至 1cm
    
    if not os.path.exists(data_path):
        print("❌ 文件不存在")
        return

    dataset = np.load(data_path, allow_pickle=True)
    points_list = dataset['points']
    
    vis = o3d.visualization.Visualizer()
    vis.create_window(window_name="R2000 1cm高精度SLAM", width=1280, height=720)
    
    # 2. 状态变量
    current_pose = np.eye(4)
    last_pcd = None
    full_map = o3d.geometry.PointCloud()
    
    # 为了 1cm 精度，步长不能太大，建议设为 1 或 2，确保帧间重叠度极高
    step = 1 

    print(f"💎 开启 1cm 高分辨率模式，总帧数: {len(points_list)}")

    for i in range(0, len(points_list), step):
        pts_2d = points_list[i]
        if len(pts_2d) < 50: continue

        # 3. 转换点云
        source_raw = o3d.geometry.PointCloud()
        pts_3d = np.zeros((len(pts_2d), 3))
        pts_3d[:, :2] = pts_2d
        source_raw.points = o3d.utility.Vector3dVector(pts_3d)
        
        # 预处理：1cm 采样
        source_pcd = preprocess_pcd(source_raw, voxel_size)

        if last_pcd is not None:
            # 4. 高精度 ICP 配置
            # 使用 Point-to-Plane (点到面) 算法，这在 1cm 精度下比点到点更准确，不会产生重叠毛刺
            reg_result = o3d.pipelines.registration.registration_icp(
                source_pcd, last_pcd, 
                max_correspondence_distance=voxel_size * 5, # 严格控制搜索半径 5cm
                init=np.eye(4),
                estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(),
                criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
                    max_iteration=50,       # 增加迭代次数确保收敛
                    relative_fitness=1e-7,  # 更严苛的停止条件
                    relative_rmse=1e-7
                )
            )
            
            # 5. 运动过滤
            trans = reg_result.transformation
            dist = np.linalg.norm(trans[:3, 3])
            
            if dist < 0.5: # 1cm 模式下拦截阈值收紧
                current_pose = current_pose @ trans
            else:
                print(f"⚠️ 帧 {i} 匹配不稳，已跳过")

        # 6. 地图融合
        # 关键：为了保持 1cm 精度，我们将每一帧转换到全局坐标后再合并
        target_frame = source_pcd.transform(current_pose)
        full_map += target_frame
        
        # 每 10 帧做一次地图全局降采样，防止内存爆炸
        if i % 10 == 0:
            full_map = full_map.voxel_down_sample(voxel_size=voxel_size)
            x, y = current_pose[0, 3], current_pose[1, 3]
            print(f"正在构建... 帧 {i:04d} | 位置: [{x:.3f}, {y:.3f}]")

        # 实时更新显示
        if i == 0: vis.add_geometry(full_map)
        vis.update_geometry(full_map)
        vis.poll_events()
        vis.update_renderer()
        
        last_pcd = source_pcd

    # 7. 最终保存
    output_file = "high_res_1cm_map.ply"
    o3d.io.write_point_cloud(output_file, full_map)
    print(f"✅ 高精度地图已保存至: {output_file}")
    
    vis.run()
    vis.destroy_window()

if __name__ == "__main__":
    main()