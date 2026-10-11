#!/bin/bash

# --- 环境配置 ---
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="/home/ycy/ros2_ws/install/setup.bash"
TARGET_DIR="/home/ycy/YCY"
NAV_CONFIG="$TARGET_DIR/nav2_params.yaml"

cd $TARGET_DIR

# 检查配置文件是否存在
if [ ! -f "$NAV_CONFIG" ]; then
    echo "❌ 错误: 未找到导航配置文件 $NAV_CONFIG"
    exit 1
fi

# --- 启动完整Nav2导航 ---
gnome-terminal --title="NAV2导航核心" -- bash -c "source $ROS_SETUP; [ -f $WS_SETUP ] && source $WS_SETUP; cd $TARGET_DIR; ros2 launch nav2_bringup navigation_launch.py use_sim_time:=False params_file:=$NAV_CONFIG; exec bash"
sleep 3


echo "✅ Nav2导航启动完成！已加载配置文件，启动速度平滑节点"

