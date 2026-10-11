#!/bin/bash

# --- 1. 环境与路径配置 ---
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="/home/ycy/ros2_ws/install/setup.bash"
TARGET_DIR="/home/ycy/YCY"
MAP_YAML="$TARGET_DIR/my_map.yaml"
AMCL_CONFIG="$TARGET_DIR/amcl_config.yaml"

cd $TARGET_DIR

# 检查地图文件是否存在
if [ ! -f "$MAP_YAML" ]; then
    echo "❌ 错误: 未找到地图文件 $MAP_YAML"
    exit 1
fi

# --- 2. 启动硬件与定位 ---

# 窗口 1: 雷达驱动
gnome-terminal --title="1.雷达驱动" -- bash -c "source $ROS_SETUP; [ -f $WS_SETUP ] && source $WS_SETUP; ros2 launch pf_driver r2000.launch.py; exec bash"
sleep 4

# 窗口 2: 静态坐标变换 (底盘 -> 雷达)
gnome-terminal --title="2.坐标变换TF" -- bash -c "source $ROS_SETUP; ros2 run tf2_ros static_transform_publisher 0.5 0 0.25 0 0 0 base_link scanner_link; exec bash"
sleep 2

# 窗口 3: 底盘里程计控制 (ZLAC8015D)
gnome-terminal --title="3.底盘里程计" -- bash -c "source $ROS_SETUP; python3 /home/ycy/zlac8015d_odom_joy.py; exec bash"
sleep 2

# 窗口 4: 启动定位组件 (但不激活)
gnome-terminal --title="4.定位核心组件" -- bash -c "source $ROS_SETUP; \
    ros2 run nav2_map_server map_server --ros-args -p yaml_filename:=$MAP_YAML -p use_sim_time:=false & \
    ros2 run nav2_amcl amcl --ros-args --params-file $AMCL_CONFIG; \
    exec bash"
sleep 2

# 窗口 5: 统一生命周期管理器 (关键：一键激活所有定位节点)
# 窗口 5: 修正后的节点激活器
gnome-terminal --title="5.节点激活器" -- bash -c "source $ROS_SETUP; \
    ros2 run nav2_lifecycle_manager lifecycle_manager --ros-args \
    -p node_names:=['map_server','amcl'] \
    -p autostart:=true \
    -p bond_timeout:=0.0; \
    exec bash"

echo "✅ AMCL 定位与地图服务已启动。"
echo "💡 请在 RViz2 中确认 Map 话题并进行初始位姿标注。"
