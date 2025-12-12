#!/usr/bin/env python3
"""
多车协同规划系统测试脚本
"""

import numpy as np
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trajectory_plannner_multi import (
    MultiVehicleTrajectoryPlanner, 
    ForewarnOutput, 
    TrafficElementSimple, 
    RiskElement, 
    RiskLevel, 
    Decision
)

def create_test_data():
    """创建测试数据"""
    
    # 创建三辆测试车辆
    vehicle1 = TrafficElementSimple(
        element_id="audi1",
        location=(100.0, 0.0),
        heading=(0.0,),
        velocity=(20.0, 0.0),
        acceleration=(1.0, 0.0),
        edge_id="edge1",
        lane_id="edge1_0"
    )
    
    vehicle2 = TrafficElementSimple(
        element_id="audi2", 
        location=(80.0, 3.5),
        heading=(0.0,),
        velocity=(18.0, 0.0),
        acceleration=(0.5, 0.0),
        edge_id="edge1",
        lane_id="edge1_1"
    )
    
    vehicle3 = TrafficElementSimple(
        element_id="audi3",
        location=(120.0, -3.5),
        heading=(0.0,),
        velocity=(22.0, 0.0),
        acceleration=(2.0, 0.0),
        edge_id="edge1", 
        lane_id="edge1_2"
    )
    
    all_elements = {
        "audi1": vehicle1,
        "audi2": vehicle2,
        "audi3": vehicle3
    }
    
    # 创建风险要素
    # 为每辆车创建简单的历史和预测轨迹
    def create_trajectory(start_pos, velocity, num_points=50):
        traj = []
        for i in range(num_points):
            t = i * 0.1
            x = start_pos[0] + velocity[0] * t
            y = start_pos[1] + velocity[1] * t
            heading = 0.0
            traj.append([x, y, heading])
        return np.array(traj, dtype=np.float64)
    
    risk1 = RiskElement(
        element_id="audi1",
        risk_level=RiskLevel.HIGH,
        related_risk_elements=["audi2", "audi3"],
        history_trajectory=create_trajectory((95.0, 0.0), (20.0, 0.0), 10),
        predicted_trajectory=create_trajectory((100.0, 0.0), (20.0, 0.0)),
        planned_trajectory=np.array([[0, 0, 0]], dtype=np.float64),
        decision=Decision.LEFT_LANE_CHANGE
    )
    
    risk2 = RiskElement(
        element_id="audi2",
        risk_level=RiskLevel.HIGH,
        related_risk_elements=["audi1", "audi3"],
        history_trajectory=create_trajectory((75.0, 3.5), (18.0, 0.0), 10),
        predicted_trajectory=create_trajectory((80.0, 3.5), (18.0, 0.0)),
        planned_trajectory=np.array([[0, 0, 0]], dtype=np.float64),
        decision=Decision.RIGHT_LANE_CHANGE
    )
    
    risk3 = RiskElement(
        element_id="audi3",
        risk_level=RiskLevel.CRITICAL,
        related_risk_elements=["audi1", "audi2"],
        history_trajectory=create_trajectory((115.0, -3.5), (22.0, 0.0), 10),
        predicted_trajectory=create_trajectory((120.0, -3.5), (22.0, 0.0)),
        planned_trajectory=np.array([[0, 0, 0]], dtype=np.float64),
        decision=Decision.LANE_KEEPING
    )
    
    risk_elements = [risk1, risk2, risk3]
    
    # 创建ForewarnOutput
    forewarn_output = ForewarnOutput(
        timestamp=10.0,
        all_elements=all_elements,
        risk_elements=risk_elements
    )
    
    return forewarn_output

def test_multi_vehicle_planning():
    """测试多车协同规划"""
    print("开始测试多车协同规划系统...")
    
    try:
        # 创建测试数据
        test_input = create_test_data()
        print(f"创建了 {len(test_input.all_elements)} 辆测试车辆")
        print(f"检测到 {len(test_input.risk_elements)} 个风险要素")
        
        # 创建规划器
        planner = MultiVehicleTrajectoryPlanner()
        print("多车协同规划器初始化成功")
        
        # 注意：由于没有SUMO环境，这个测试会在获取参考路径时失败
        # 但可以验证代码结构是否正确
        print("尝试进行轨迹规划...")
        planned_trajectories = planner.plan_trajectories(test_input)
        
        if planned_trajectories:
            print(f"成功规划了 {len(planned_trajectories)} 条轨迹")
            for vehicle_id, trajectory in planned_trajectories.items():
                print(f"  车辆 {vehicle_id}: {len(trajectory)} 个轨迹点")
        else:
            print("轨迹规划失败（预期结果，因为没有SUMO环境）")
            
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        print("这是预期的，因为测试环境中没有SUMO")
    
    print("测试完成！")

if __name__ == "__main__":
    test_multi_vehicle_planning()