#!/bin/bash

# --- 1. 路径配置 ---
ROS_SETUP="/opt/ros/humble/setup.bash"
# 请确保此路径指向包含 pf_driver 的工作空间
WS_SETUP="/home/ycy/ros2_ws/install/setup.bash"
TARGET_DIR="/home/ycy/YCY"

mkdir -p $TARGET_DIR
cd $TARGET_DIR

# --- 2. 自动生成配置文件 (针对 ycy 机器人的 0.5m 偏移优化) ---
cat << 'LUA_EOF' > simple_carto.lua
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
  use_odometry = false,
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
TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching = true
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.resolution = 0.03

return options
LUA_EOF

# --- 3. 弹出独立终端执行各环节 ---

# 窗口 1: 雷达驱动 (自带 RViz2)
gnome-terminal --title="1.雷达驱动与RViz" -- bash -c "source $ROS_SETUP; [ -f $WS_SETUP ] && source $WS_SETUP; ros2 launch pf_driver r2000.launch.py; exec bash"
sleep 4
# 窗口 2: 坐标变换 (base_link -> scanner_link 偏移 0.5m)
gnome-terminal --title="2.坐标变换TF" -- bash -c "source $ROS_SETUP; ros2 run tf2_ros static_transform_publisher 0.5 0 0.25 0 0 0 base_link scanner_link; exec bash"
sleep 4
# 窗口 3: 手柄控制底盘
gnome-terminal --title="3.手柄底盘控制" -- bash -c "source $ROS_SETUP; python3 /home/ycy/zlac8015d_odom_joy.py; exec bash"
sleep 4
# 窗口 4: Cartographer SLAM 核心
gnome-terminal --title="4.Cartographer核心" -- bash -c "source $ROS_SETUP; sleep 5; cd $TARGET_DIR; ros2 run cartographer_ros cartographer_node -configuration_directory . -configuration_basename simple_carto.lua --ros-args --remap scan:=/pf/scan; exec bash"
sleep 4
# 窗口 5: 栅格地图生成
gnome-terminal --title="5.栅格地图输出" -- bash -c "source $ROS_SETUP; sleep 6; ros2 run cartographer_ros cartographer_occupancy_grid_node -resolution 0.03; exec bash"
sleep 4
echo "------------------------------------------------"
echo "🚀 所有进程已在独立终端启动！"
echo "1. 请在自动开启的 RViz 中，将 Fixed Frame 改为 'map'。"
echo "2. 添加 'Map' 插件，话题选 '/map'。"
echo "3. 控制小车向前直行，进行建图。"
echo "------------------------------------------------"

