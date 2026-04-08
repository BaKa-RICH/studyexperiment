import sys
import os
import numpy as np
import matplotlib.pyplot as plt

# Add src and tests to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tests")))

from active_gap_v1.test_a0_rolling_simulation import run_a0_rolling_simulation

def main():
    print("Running A0 simulation...")
    result = run_a0_rolling_simulation(max_ticks=200, verbose=False)
    trace = result["trace"]
    
    if not trace:
        print("No trace data generated.")
        return
        
    t = np.array([d["time_s"] for d in trace])
    p_x = np.array([d["p_x"] for d in trace])
    m_x = np.array([d["m_x"] for d in trace])
    s_x = np.array([d["s_x"] for d in trace])
    
    p_v = np.array([d["p_v"] for d in trace])
    m_v = np.array([d["m_v"] for d in trace])
    s_v = np.array([d["s_v"] for d in trace])
    
    gap_ps = np.array([d["gap_ps"] for d in trace])
    
    # Calculate acceleration (simple finite difference)
    dt = t[1] - t[0] if len(t) > 1 else 0.1
    p_a = np.gradient(p_v, dt)
    m_a = np.gradient(m_v, dt)
    s_a = np.gradient(s_v, dt)
    
    out_dir = os.path.dirname(__file__)
    
    # Common plot settings
    plt.rcParams['figure.figsize'] = (10, 6)
    plt.rcParams['font.size'] = 12
    plt.rcParams['lines.linewidth'] = 2
    
    # 1. Position vs Time (p/t)
    plt.figure()
    plt.plot(t, p_x, label='p (Lead)', color='blue')
    plt.plot(t, m_x, label='m (Merge)', color='green')
    plt.plot(t, s_x, label='s (Lag)', color='red')
    plt.title('Position vs Time (A0 Flexible)')
    plt.xlabel('Time (s)')
    plt.ylabel('Position (m)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'p_t.png'), dpi=300)
    plt.close()
    
    # 2. Velocity vs Time (v/t)
    plt.figure()
    plt.plot(t, p_v, label='p (Lead)', color='blue')
    plt.plot(t, m_v, label='m (Merge)', color='green')
    plt.plot(t, s_v, label='s (Lag)', color='red')
    plt.title('Velocity vs Time (A0 Flexible)')
    plt.xlabel('Time (s)')
    plt.ylabel('Velocity (m/s)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'v_t.png'), dpi=300)
    plt.close()
    
    # 3. Acceleration vs Time (a/t)
    plt.figure()
    plt.plot(t, p_a, label='p (Lead)', color='blue')
    plt.plot(t, m_a, label='m (Merge)', color='green')
    plt.plot(t, s_a, label='s (Lag)', color='red')
    plt.title('Acceleration vs Time (A0 Flexible)')
    plt.xlabel('Time (s)')
    plt.ylabel('Acceleration (m/s²)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'a_t.png'), dpi=300)
    plt.close()
    
    # 4. Gap vs Time (gap/t)
    plt.figure()
    plt.plot(t, gap_ps, label='Gap (p-s)', color='purple')
    plt.title('Mainline Gap (p-s) vs Time (A0 Flexible)')
    plt.xlabel('Time (s)')
    plt.ylabel('Gap Distance (m)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'gap_t.png'), dpi=300)
    plt.close()
    
    print(f"Plots saved to {out_dir}:")
    print(" - p_t.png")
    print(" - v_t.png")
    print(" - a_t.png")
    print(" - gap_t.png")

if __name__ == "__main__":
    main()
