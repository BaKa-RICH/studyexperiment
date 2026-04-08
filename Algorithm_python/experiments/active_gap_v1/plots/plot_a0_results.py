import sys
import os
import numpy as np
import matplotlib.pyplot as plt

# Add src and tests to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tests")))

from active_gap_v1.test_a0_rolling_simulation import run_a0_rolling_simulation


def _first_event_time(trace: list[dict], decision: str) -> float | None:
    for item in trace:
        if item["decision"] == decision:
            return item["time_s"]
    return None


def _annotate_events(ax, first_coord_t: float | None, first_merge_t: float | None) -> None:
    if first_coord_t is not None:
        ax.axvline(first_coord_t, color="gray", linestyle="--", alpha=0.5, label="coordination start")
    if first_merge_t is not None:
        ax.axvline(first_merge_t, color="black", linestyle="-.", alpha=0.6, label="merge start")


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
    gap_pm = np.array([d["gap_pm"] for d in trace])
    gap_ms = np.array([d["gap_ms"] for d in trace])
    virt_e_pm = np.array([d["virt_e_pm"] for d in trace])
    virt_e_ms = np.array([d["virt_e_ms"] for d in trace])

    dt = t[1] - t[0] if len(t) > 1 else 0.1
    p_a = np.gradient(p_v, dt)
    m_a = np.gradient(m_v, dt)
    s_a = np.gradient(s_v, dt)

    first_coord_t = _first_event_time(trace, "coordination")
    first_merge_t = _first_event_time(trace, "merge")

    out_dir = os.path.dirname(__file__)

    plt.rcParams["figure.figsize"] = (11, 6)
    plt.rcParams["font.size"] = 12
    plt.rcParams["lines.linewidth"] = 2

    fig, ax = plt.subplots()
    ax.plot(t, p_x, label="p (Lead)", color="blue")
    ax.plot(t, m_x, label="m (Merge)", color="green")
    ax.plot(t, s_x, label="s (Lag)", color="red")
    _annotate_events(ax, first_coord_t, first_merge_t)
    ax.set_title("Position vs Time (A0 Flexible, Pairwise Virtual Gap)")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Position (m)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.7)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "p_t.png"), dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.plot(t, p_v, label="p (Lead)", color="blue")
    ax.plot(t, m_v, label="m (Merge)", color="green")
    ax.plot(t, s_v, label="s (Lag)", color="red")
    ax.axhline(16.7, color="gray", linestyle=":", alpha=0.5, label="v0 = 16.7")
    ax.axhline(25.0, color="orange", linestyle=":", alpha=0.5, label="mainline vmax")
    ax.axhline(16.7, color="purple", linestyle="--", alpha=0.2)
    _annotate_events(ax, first_coord_t, first_merge_t)
    ax.set_title("Velocity vs Time (A0 Flexible, Pairwise Virtual Gap)")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Velocity (m/s)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.7)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "v_t.png"), dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.plot(t, p_a, label="p (Lead)", color="blue")
    ax.plot(t, m_a, label="m (Merge)", color="green")
    ax.plot(t, s_a, label="s (Lag)", color="red")
    ax.axhline(0.0, color="gray", linestyle="-", alpha=0.3)
    ax.axhline(2.6, color="orange", linestyle=":", alpha=0.5, label="a_max")
    ax.axhline(-2.0, color="orange", linestyle="--", alpha=0.5, label="comfortable brake")
    _annotate_events(ax, first_coord_t, first_merge_t)
    ax.set_title("Acceleration vs Time (A0 Flexible, Pairwise Virtual Gap)")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Acceleration (m/s^2)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.7)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "a_t.png"), dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.plot(t, gap_ps, label="gap p-s", color="purple")
    ax.plot(t, gap_pm, label="gap p-m", color="blue")
    ax.plot(t, gap_ms, label="gap m-s", color="red")
    _annotate_events(ax, first_coord_t, first_merge_t)
    ax.set_title("Pairwise Gaps vs Time (A0 Flexible, Pairwise Virtual Gap)")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Gap Distance (m)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.7)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "gap_t.png"), dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.plot(t, virt_e_pm, label="e_pm^virt", color="blue")
    ax.plot(t, virt_e_ms, label="e_ms^virt", color="red")
    ax.axhline(0.0, color="gray", linestyle="-", alpha=0.3)
    _annotate_events(ax, first_coord_t, first_merge_t)
    ax.set_title("Virtual Gap Errors vs Time (A0 Flexible)")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Virtual Gap Error (m)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.7)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "virt_gap_error_t.png"), dpi=300)
    plt.close(fig)

    print(f"Plots saved to {out_dir}:")
    print(" - p_t.png")
    print(" - v_t.png")
    print(" - a_t.png")
    print(" - gap_t.png")
    print(" - virt_gap_error_t.png")

if __name__ == "__main__":
    main()
