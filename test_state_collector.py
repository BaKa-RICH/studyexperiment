import os
import sys
import traci

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from ramp.runtime.state_collector import StateCollector
from ramp.policies.hierarchical.state_collector_ext import HierarchicalStateCollector

def run_test():
    sumo_cmd = ["sumo", "-c", "ramp/scenarios/ramp__mlane_v2_mixed/ramp__mlane_v2_mixed.sumocfg", "--no-step-log", "true"]
    traci.start(sumo_cmd)
    
    base_collector = StateCollector(
        control_zone_length_m=300.0,
        merge_edge="main_h3",
        policy="fifo",
        main_vmax_mps=30.0,
        ramp_vmax_mps=20.0,
        fifo_gap_s=2.0,
        control_mode="E-ctrl-1"
    )
    
    collector = HierarchicalStateCollector(base_collector=base_collector, traci=traci)
    
    print("Running simulation for 60s...")
    for step in range(600):  # 60s at 0.1s step
        traci.simulationStep()
        
        if step == 599:
            state = collector.collect(sim_time=step * 0.1, traci=traci)
            
            print("\n--- Test Results at t=60.0s ---")
            
            # 1. Check vehicle types
            cav_count = sum(1 for v in state.vehicle_types.values() if v == 'cav')
            hdv_count = sum(1 for v in state.vehicle_types.values() if v == 'hdv')
            print(f"Vehicle types: {cav_count} CAVs, {hdv_count} HDVs")
            
            # 2. Check Zone A info
            if state.zone_a_info:
                print(f"Zone A (main_h2) edge length: {state.zone_a_info.edge_length_m:.1f}m")
                for lane_idx in range(4):
                    count = state.zone_a_info.lane_vehicle_counts.get(lane_idx, 0)
                    density = state.zone_a_info.lane_densities.get(lane_idx, 0.0)
                    speed = state.zone_a_info.lane_avg_speeds.get(lane_idx, 0.0)
                    print(f"  Lane {lane_idx}: {count} vehicles, {density:.1f} veh/km, {speed:.1f} m/s avg speed")
            else:
                print("Zone A info missing!")
                
            # 3. Check Zone C info
            print(f"Zone C (main_h3_1) vehicles: {len(state.zone_c_lane1_vehicles)}")
            for vid, pos, speed in state.zone_c_lane1_vehicles[:3]:
                print(f"  - {vid}: pos={pos:.1f}m, speed={speed:.1f}m/s")
            if len(state.zone_c_lane1_vehicles) > 3:
                print("  ...")
                
    traci.close()

if __name__ == "__main__":
    run_test()
