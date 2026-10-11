#!/bin/bash

# --- 1. 环境与路径配置 ---
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="/home/ycy/ros2_ws/install/setup.bash"
TARGET_DIR="/home/ycy/YCY"
MAP_FILE="$TARGET_DIR/my_map.pbstream"

mkdir -p $TARGET_DIR
cd $TARGET_DIR

# 检查地图文件是否存在
if [ ! -f "$MAP_FILE" ]; then
    echo "❌ 错误: 未在 $TARGET_DIR 中找到 $MAP_FILE"
    exit 1
fi

# --- 2. 自动生成【原始版】定位配置文件 ---
cat << 'LUA_EOF' > localization.lua
include "map_builder.lua"
include "trajectory_builder.lua"

options = {
  map_builder = MAP_BUILDER,
  trajectory_builder = TRAJECTORY_BUILDER,
  map_frame = "map",
  tracking_frame = "base_link", 
  published_frame = "odom",
  odom_frame = "odom",
  provide_odom_frame = false,
  publish_frame_projected_to_2d = true,
  use_odometry = true,
  use_nav_sat = false,
  use_landmarks = false,
  num_laser_scans = 1,
  num_multi_echo_laser_scans = 0,
  num_subdivisions_per_laser_scan = 1,
  num_point_clouds = 0,
  lookup_transform_timeout_sec = 0.2,
  submap_publish_period_sec = 0.3,
  pose_publish_period_sec = 5e-3,
  trajectory_publish_period_sec = 30e-3,
  rangefinder_sampling_ratio = 1.,
  odometry_sampling_ratio = 1.,
  fixed_frame_pose_sampling_ratio = 1.,
  imu_sampling_ratio = 1.,
  landmarks_sampling_ratio = 1.,
}

MAP_BUILDER.use_trajectory_builder_2d = true
TRAJECTORY_BUILDER_2D.use_imu_data = false
TRAJECTORY_BUILDER_2D.min_range = 0.3
TRAJECTORY_BUILDER_2D.max_range = 30.0

-- 【精进】前端匹配：扩大搜索范围，增强纠偏能力
TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching = true
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.2
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.angular_search_window = math.rad(30.)

-- 【精进】锁死特征：解决“回到原点漂移”的核心权重
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.occupied_space_weight = 50.0
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 0.1
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.rotation_weight = 0.1

-- 【精进】回环优化：提高回到起点时的闭合频率
POSE_GRAPH.optimize_every_n_nodes = 10
POSE_GRAPH.constraint_builder.min_score = 0.45
POSE_GRAPH.constraint_builder.global_localization_min_score = 0.55

-- 【精进】纯定位模式：保留更多子图历史
TRAJECTORY_BUILDER.pure_localization_trimmer = {
  max_submaps_to_keep = 10,
}

return options
LUA_EOF

# --- 3. 启动硬件与定位 ---

# 窗口 1: 雷达驱动
gnome-terminal --title="1.雷达驱动" -- bash -c "source $ROS_SETUP; [ -f $WS_SETUP ] && source $WS_SETUP; ros2 launch pf_driver r2000.launch.py; exec bash"
sleep 4

# 窗口 2: 坐标变换 (根据实际安装位置微调 0.5 0 0.25)
gnome-terminal --title="2.坐标变换TF" -- bash -c "source $ROS_SETUP; ros2 run tf2_ros static_transform_publisher 0.5 0 0.25 0 0 0 base_link scanner_link; exec bash"
sleep 2

# 窗口 3: 底盘里程计控制
gnome-terminal --title="3.底盘里程计控制" -- bash -c "source $ROS_SETUP; python3 /home/ycy/zlac8015d_odom_joy.py; exec bash"
sleep 2

# 窗口 4: Cartographer 定位核心
gnome-terminal --title="4.Cartographer定位" -- bash -c "source $ROS_SETUP; cd $TARGET_DIR; ros2 run cartographer_ros cartographer_node -configuration_directory . -configuration_basename localization.lua -load_state_filename $MAP_FILE --remap scan:=/pf/scan --remap odom:=/odom; exec bash"
sleep 2

# 窗口 5: 栅格地图发布
gnome-terminal --title="5.栅格地图输出" -- bash -c "source $ROS_SETUP; ros2 run cartographer_ros cartographer_occupancy_grid_node -resolution 0.05; exec bash"

echo "✅ 定位模式（精进版）启动完成！已强化原点稳定性。"

