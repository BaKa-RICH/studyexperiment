import numpy as np
from typing import List, Tuple
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d, UnivariateSpline
from scipy.optimize import minimize_scalar

#横向距离：右侧为正，左侧为负

class CartesianFrenetConverter:
    """
    Cartesian坐标系和Frenet坐标系转换器
    """

    def __init__(self, waypoints, smooth: bool = True):
        """
        初始化转换器

        Args:
            waypoints: 路径点列表 [(x, y), ...]
            smooth: 是否使用样条插值平滑路径
        """
        self.waypoints = np.array(waypoints)
        self.smooth = smooth
        self.s_values = None  # 累积弧长
        self.x_func = None  # x关于s的函数
        self.y_func = None  # y关于s的函数
        self.dx_ds_func = None  # dx/ds函数
        self.dy_ds_func = None  # dy/ds函数
        self.d2x_ds2_func = None  # d²x/ds²函数
        self.d2y_ds2_func = None  # d²y/ds²函数

        self._build_reference_line()

    def _build_reference_line(self):
        """建立参考线坐标系"""
        # 计算累积弧长
        x, y = self.waypoints[:, 0], self.waypoints[:, 1]
        dx = np.diff(x)
        dy = np.diff(y)
        ds = np.sqrt(dx ** 2 + dy ** 2)
        self.s_values = np.concatenate([[0], np.cumsum(ds)])

        if self.smooth and len(self.waypoints) > 3:
            # 使用样条插值平滑路径
            # 设置平滑参数，避免过度平滑
            smoothing_factor = len(self.waypoints) * 0.1
            self.x_func = UnivariateSpline(self.s_values, x, s=smoothing_factor)
            self.y_func = UnivariateSpline(self.s_values, y, s=smoothing_factor)

            # 计算一阶和二阶导数函数
            self.dx_ds_func = self.x_func.derivative(n=1)
            self.dy_ds_func = self.y_func.derivative(n=1)
            self.d2x_ds2_func = self.x_func.derivative(n=2)
            self.d2y_ds2_func = self.y_func.derivative(n=2)
        else:
            # 使用线性插值
            self.x_func = interp1d(self.s_values, x, kind='linear',
                                   bounds_error=False, fill_value='extrapolate')
            self.y_func = interp1d(self.s_values, y, kind='linear',
                                   bounds_error=False, fill_value='extrapolate')

            # 对于线性插值，导数是常数
            def dx_ds_linear(s):
                idx = np.searchsorted(self.s_values[1:], s)
                idx = np.clip(idx, 0, len(dx) - 1)
                return dx[idx] / ds[idx]

            def dy_ds_linear(s):
                idx = np.searchsorted(self.s_values[1:], s)
                idx = np.clip(idx, 0, len(dy) - 1)
                return dy[idx] / ds[idx]

            self.dx_ds_func = dx_ds_linear
            self.dy_ds_func = dy_ds_linear
            # 线性插值的二阶导数为0
            self.d2x_ds2_func = lambda s: np.zeros_like(s) if hasattr(s, '__iter__') else 0.0
            self.d2y_ds2_func = lambda s: np.zeros_like(s) if hasattr(s, '__iter__') else 0.0

    def _find_closest_point_on_path(self, x: float, y: float) -> float:
        """找到路径上距离给定点最近的点对应的弧长s"""

        def distance_squared(s):
            x_path = self.x_func(s)
            y_path = self.y_func(s)
            return (x - x_path) ** 2 + (y - y_path) ** 2

        # 在整个路径范围内搜索最小距离点
        result = minimize_scalar(distance_squared, bounds=(0, self.s_values[-1]), method='bounded')
        return result.x

    def cartesian_to_frenet(self, x: float, y: float) -> Tuple[float, float]:
        """
        Cartesian坐标转换为Frenet坐标

        Args:
            x, y: Cartesian坐标

        Returns:
            (s, d): Frenet坐标，s为弧长坐标，d为横向距离
        """
        # 找到最近点的弧长
        s = self._find_closest_point_on_path(x, y)

        # 计算参考线上该点的坐标和切线方向
        x_ref = self.x_func(s)
        y_ref = self.y_func(s)

        # 计算切线方向（单位切向量）
        dx_ds = self.dx_ds_func(s)
        dy_ds = self.dy_ds_func(s)
        norm = np.sqrt(dx_ds ** 2 + dy_ds ** 2)
        if norm > 1e-10:
            tx = dx_ds / norm  # 切向量x分量
            ty = dy_ds / norm  # 切向量y分量
        else:
            tx, ty = 1.0, 0.0

        # 法向量（顺时针旋转90度）
        nx = ty
        ny = -tx

        # 计算横向距离d（带符号）
        dx = x - x_ref
        dy = y - y_ref
        d = dx * nx + dy * ny

        return s, d

    def frenet_to_cartesian(self, s: float, d: float) -> Tuple[float, float]:
        """
        Frenet坐标转换为Cartesian坐标

        Args:
            s: 弧长坐标
            d: 横向距离

        Returns:
            (x, y): Cartesian坐标
        """
        # 限制s在有效范围内
        s = np.clip(s, 0, self.s_values[-1])

        # 获取参考线上的点
        x_ref = self.x_func(s)
        y_ref = self.y_func(s)

        # 计算切线方向
        dx_ds = self.dx_ds_func(s)
        dy_ds = self.dy_ds_func(s)
        norm = np.sqrt(dx_ds ** 2 + dy_ds ** 2)
        if norm > 1e-10:
            tx = dx_ds / norm
            ty = dy_ds / norm
        else:
            tx, ty = 1.0, 0.0

        # 法向量（顺时针旋转90度）
        nx = ty
        ny = -tx

        # 计算实际坐标
        x = x_ref + d * nx
        y = y_ref + d * ny

        return x, y

    def velocity_cartesian_to_frenet(self, x: float, y: float, vx: float, vy: float) -> Tuple[float, float]:
        """
        速度从Cartesian坐标系转换到Frenet坐标系

        Args:
            x, y: 位置
            vx, vy: Cartesian坐标系下的速度

        Returns:
            (vs, vd): Frenet坐标系下的速度
        """
        # 获取当前位置对应的弧长
        s, d = self.cartesian_to_frenet(x, y)

        # 计算切线和法线方向
        dx_ds = self.dx_ds_func(s)
        dy_ds = self.dy_ds_func(s)
        norm = np.sqrt(dx_ds ** 2 + dy_ds ** 2)
        if norm > 1e-10:
            tx = dx_ds / norm
            ty = dy_ds / norm
        else:
            tx, ty = 1.0, 0.0

        nx = ty
        ny = -tx

        # 计算曲率
        d2x_ds2 = self.d2x_ds2_func(s)
        d2y_ds2 = self.d2y_ds2_func(s)
        kappa = (dx_ds * d2y_ds2 - dy_ds * d2x_ds2) / (norm ** 3) if norm > 1e-10 else 0.0

        # 速度转换公式
        vs = (vx * tx + vy * ty) / (1 - kappa * d)
        vd = vx * nx + vy * ny

        return vs, vd

    def velocity_frenet_to_cartesian(self, s: float, d: float, vs: float, vd: float) -> Tuple[float, float]:
        """
        速度从Frenet坐标系转换到Cartesian坐标系

        Args:
            s, d: Frenet位置
            vs, vd: Frenet坐标系下的速度

        Returns:
            (vx, vy): Cartesian坐标系下的速度
        """
        # 计算切线和法线方向
        dx_ds = self.dx_ds_func(s)
        dy_ds = self.dy_ds_func(s)
        norm = np.sqrt(dx_ds ** 2 + dy_ds ** 2)
        if norm > 1e-10:
            tx = dx_ds / norm
            ty = dy_ds / norm
        else:
            tx, ty = 1.0, 0.0

        nx = ty
        ny = -tx

        # 计算曲率
        d2x_ds2 = self.d2x_ds2_func(s)
        d2y_ds2 = self.d2y_ds2_func(s)
        kappa = (dx_ds * d2y_ds2 - dy_ds * d2x_ds2) / (norm ** 3) if norm > 1e-10 else 0.0

        # 速度转换公式
        vx = vs * (1 - kappa * d) * tx + vd * nx
        vy = vs * (1 - kappa * d) * ty + vd * ny

        return vx, vy

    def acceleration_cartesian_to_frenet(self, x: float, y: float, vx: float, vy: float,
                                         ax: float, ay: float) -> Tuple[float, float]:
        """
        加速度从Cartesian坐标系转换到Frenet坐标系

        Args:
            x, y: 位置
            vx, vy: 速度
            ax, ay: Cartesian坐标系下的加速度

        Returns:
            (as_, ad): Frenet坐标系下的加速度
        """
        # 获取Frenet坐标和速度
        s, d = self.cartesian_to_frenet(x, y)
        vs, vd = self.velocity_cartesian_to_frenet(x, y, vx, vy)

        # 计算切线和法线方向
        dx_ds = self.dx_ds_func(s)
        dy_ds = self.dy_ds_func(s)
        norm = np.sqrt(dx_ds ** 2 + dy_ds ** 2)
        if norm > 1e-10:
            tx = dx_ds / norm
            ty = dy_ds / norm
        else:
            tx, ty = 1.0, 0.0

        nx = ty
        ny = -tx

        # 计算曲率和曲率导数
        d2x_ds2 = self.d2x_ds2_func(s)
        d2y_ds2 = self.d2y_ds2_func(s)
        kappa = (dx_ds * d2y_ds2 - dy_ds * d2x_ds2) / (norm ** 3) if norm > 1e-10 else 0.0

        # 计算曲率导数（简化处理）
        delta_s = 1e-6
        s_plus = min(s + delta_s, self.s_values[-1])
        s_minus = max(s - delta_s, 0)

        dx_ds_plus = self.dx_ds_func(s_plus)
        dy_ds_plus = self.dy_ds_func(s_plus)
        norm_plus = np.sqrt(dx_ds_plus ** 2 + dy_ds_plus ** 2)
        d2x_ds2_plus = self.d2x_ds2_func(s_plus)
        d2y_ds2_plus = self.d2y_ds2_func(s_plus)
        kappa_plus = (dx_ds_plus * d2y_ds2_plus - dy_ds_plus * d2x_ds2_plus) / (
                    norm_plus ** 3) if norm_plus > 1e-10 else 0.0

        dx_ds_minus = self.dx_ds_func(s_minus)
        dy_ds_minus = self.dy_ds_func(s_minus)
        norm_minus = np.sqrt(dx_ds_minus ** 2 + dy_ds_minus ** 2)
        d2x_ds2_minus = self.d2x_ds2_func(s_minus)
        d2y_ds2_minus = self.d2y_ds2_func(s_minus)
        kappa_minus = (dx_ds_minus * d2y_ds2_minus - dy_ds_minus * d2x_ds2_minus) / (
                    norm_minus ** 3) if norm_minus > 1e-10 else 0.0

        dkappa_ds = (kappa_plus - kappa_minus) / (2 * delta_s) if abs(s_plus - s_minus) > 1e-10 else 0.0

        # 加速度转换公式
        as_ = (ax * tx + ay * ty - kappa * (1 - kappa * d) * vs ** 2 - 2 * kappa * vs * vd) / (1 - kappa * d)
        ad = ax * nx + ay * ny + (1 - kappa * d) * vs ** 2 * kappa - dkappa_ds * d * vs ** 2

        return as_, ad

    def acceleration_frenet_to_cartesian(self, s: float, d: float, vs: float, vd: float,
                                         as_: float, ad: float) -> Tuple[float, float]:
        """
        加速度从Frenet坐标系转换到Cartesian坐标系

        Args:
            s, d: Frenet位置
            vs, vd: Frenet速度
            as_, ad: Frenet坐标系下的加速度

        Returns:
            (ax, ay): Cartesian坐标系下的加速度
        """
        # 计算切线和法线方向
        dx_ds = self.dx_ds_func(s)
        dy_ds = self.dy_ds_func(s)
        norm = np.sqrt(dx_ds ** 2 + dy_ds ** 2)
        if norm > 1e-10:
            tx = dx_ds / norm
            ty = dy_ds / norm
        else:
            tx, ty = 1.0, 0.0

        nx = ty
        ny = -tx

        # 计算曲率和曲率导数
        d2x_ds2 = self.d2x_ds2_func(s)
        d2y_ds2 = self.d2y_ds2_func(s)
        kappa = (dx_ds * d2y_ds2 - dy_ds * d2x_ds2) / (norm ** 3) if norm > 1e-10 else 0.0

        # 计算曲率导数
        delta_s = 1e-6
        s_plus = min(s + delta_s, self.s_values[-1])
        s_minus = max(s - delta_s, 0)

        dx_ds_plus = self.dx_ds_func(s_plus)
        dy_ds_plus = self.dy_ds_func(s_plus)
        norm_plus = np.sqrt(dx_ds_plus ** 2 + dy_ds_plus ** 2)
        d2x_ds2_plus = self.d2x_ds2_func(s_plus)
        d2y_ds2_plus = self.d2y_ds2_func(s_plus)
        kappa_plus = (dx_ds_plus * d2y_ds2_plus - dy_ds_plus * d2x_ds2_plus) / (
                    norm_plus ** 3) if norm_plus > 1e-10 else 0.0

        dx_ds_minus = self.dx_ds_func(s_minus)
        dy_ds_minus = self.dy_ds_func(s_minus)
        norm_minus = np.sqrt(dx_ds_minus ** 2 + dy_ds_minus ** 2)
        d2x_ds2_minus = self.d2x_ds2_func(s_minus)
        d2y_ds2_minus = self.d2y_ds2_func(s_minus)
        kappa_minus = (dx_ds_minus * d2y_ds2_minus - dy_ds_minus * d2x_ds2_minus) / (
                    norm_minus ** 3) if norm_minus > 1e-10 else 0.0

        dkappa_ds = (kappa_plus - kappa_minus) / (2 * delta_s) if abs(s_plus - s_minus) > 1e-10 else 0.0

        # 加速度转换公式
        ax = ((1 - kappa * d) * as_ + kappa * (1 - kappa * d) * vs ** 2 + 2 * kappa * vs * vd) * tx + \
             (ad - (1 - kappa * d) * vs ** 2 * kappa + dkappa_ds * d * vs ** 2) * nx

        ay = ((1 - kappa * d) * as_ + kappa * (1 - kappa * d) * vs ** 2 + 2 * kappa * vs * vd) * ty + \
             (ad - (1 - kappa * d) * vs ** 2 * kappa + dkappa_ds * d * vs ** 2) * ny

        return ax, ay

    def heading_cartesian_to_frenet(self, x: float, y: float, heading_cartesian: float) -> float:
            """
            航向角从Cartesian坐标系转换到Frenet坐标系
            
            Args:
                x, y: 位置坐标
                heading_cartesian: Cartesian坐标系下的航向角（弧度），以X轴正方向为0，逆时针为正
                
            Returns:
                heading_frenet: Frenet坐标系下的航向角（弧度），相对于参考线切线方向的夹角
            """
            # 获取当前位置对应的弧长
            s, d = self.cartesian_to_frenet(x, y)
            
            # 计算参考线在该点的切线方向角
            dx_ds = self.dx_ds_func(s)
            dy_ds = self.dy_ds_func(s)
            norm = np.sqrt(dx_ds ** 2 + dy_ds ** 2)
            
            if norm > 1e-10:
                # 参考线切线方向角
                reference_heading = np.arctan2(dy_ds, dx_ds)
            else:
                reference_heading = 0.0
            
            # Frenet坐标系下的航向角 = Cartesian航向角 - 参考线切线方向角
            heading_frenet = heading_cartesian - reference_heading
            
            # 将角度归一化到 [-π, π] 范围
            heading_frenet = np.arctan2(np.sin(heading_frenet), np.cos(heading_frenet))
            
            return heading_frenet

    def heading_frenet_to_cartesian(self, s: float, heading_frenet: float) -> float:
        """
        航向角从Frenet坐标系转换到Cartesian坐标系
        
        Args:
            s: 弧长坐标
            heading_frenet: Frenet坐标系下的航向角（弧度），相对于参考线切线方向的夹角
            
        Returns:
            heading_cartesian: Cartesian坐标系下的航向角（弧度），以X轴正方向为0，逆时针为正
        """
        # 限制s在有效范围内
        s = np.clip(s, 0, self.s_values[-1])
        
        # 计算参考线在该点的切线方向角
        dx_ds = self.dx_ds_func(s)
        dy_ds = self.dy_ds_func(s)
        norm = np.sqrt(dx_ds ** 2 + dy_ds ** 2)
        
        if norm > 1e-10:
            # 参考线切线方向角
            reference_heading = np.arctan2(dy_ds, dx_ds)
        else:
            reference_heading = 0.0
        
        # Cartesian坐标系下的航向角 = Frenet航向角 + 参考线切线方向角
        heading_cartesian = heading_frenet + reference_heading
        
        # 将角度归一化到 [-π, π] 范围
        heading_cartesian = np.arctan2(np.sin(heading_cartesian), np.cos(heading_cartesian))
        
        return heading_cartesian

    def get_reference_heading(self, s: float) -> float:
        """
        获取参考线在给定弧长位置的航向角
        
        Args:
            s: 弧长坐标
            
        Returns:
            reference_heading: 参考线在该位置的航向角（弧度）
        """
        # 限制s在有效范围内
        s = np.clip(s, 0, self.s_values[-1])
        
        # 计算参考线切线方向
        dx_ds = self.dx_ds_func(s)
        dy_ds = self.dy_ds_func(s)
        
        # 计算航向角
        reference_heading = np.arctan2(dy_ds, dx_ds)
        
        return reference_heading



    def get_reference_path(self, num_points: int = 100) -> Tuple[np.ndarray, np.ndarray]:
        """获取参考路径点用于可视化"""
        s_interp = np.linspace(0, self.s_values[-1], num_points)
        x_interp = self.x_func(s_interp)
        y_interp = self.y_func(s_interp)
        return x_interp, y_interp

    def visualize_path(self, title: str = "Reference Path"):
        """可视化参考路径"""
        plt.figure(figsize=(10, 8))

        # 绘制原始路径点
        plt.plot(self.waypoints[:, 0], self.waypoints[:, 1], 'ro-',
                 label='Original Waypoints', markersize=8)

        # 绘制插值后的平滑路径
        x_smooth, y_smooth = self.get_reference_path(200)
        plt.plot(x_smooth, y_smooth, 'b-', label='Reference Path', linewidth=2)

        plt.xlabel('X (m)')
        plt.ylabel('Y (m)')
        plt.title(title)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.axis('equal')
        plt.show()


# 使用示例
if __name__ == "__main__":
    # 定义路径点
    waypoints = [
        (0, 0),
        (10, 5),
        (20, 8),
        (30, 10),
        (40, 8),
        (50, 5),
        (60, 0),
        (70, -5),
        (80, -8),
        (90, -5),
        (100, 0)
    ]

    # 创建转换器
    converter = CartesianFrenetConverter(waypoints, smooth=True)

    # 可视化路径
    converter.visualize_path("Cartesian-Frenet Coordinate Converter")

    # 测试坐标转换
    print("=== 坐标转换测试 ===")
    test_x, test_y = 25, 12
    s, d = converter.cartesian_to_frenet(test_x, test_y)
    x_back, y_back = converter.frenet_to_cartesian(s, d)

    print(f"原始Cartesian坐标: ({test_x}, {test_y})")
    print(f"转换为Frenet坐标: s={s:.3f}, d={d:.3f}")
    print(f"转换回Cartesian坐标: ({x_back:.3f}, {y_back:.3f})")
    print(f"误差: dx={abs(test_x - x_back):.6f}, dy={abs(test_y - y_back):.6f}")

    # 测试速度转换
    print("\n=== 速度转换测试 ===")
    vx, vy = 15, 2  # Cartesian速度
    vs, vd = converter.velocity_cartesian_to_frenet(test_x, test_y, vx, vy)
    vx_back, vy_back = converter.velocity_frenet_to_cartesian(s, d, vs, vd)

    print(f"原始Cartesian速度: vx={vx}, vy={vy}")
    print(f"转换为Frenet速度: vs={vs:.3f}, vd={vd:.3f}")
    print(f"转换回Cartesian速度: vx={vx_back:.3f}, vy={vy_back:.3f}")
    print(f"速度误差: dvx={abs(vx - vx_back):.6f}, dvy={abs(vy - vy_back):.6f}")

    # 测试加速度转换
    print("\n=== 加速度转换测试 ===")
    ax, ay = 1, 0.5  # Cartesian加速度
    as_, ad = converter.acceleration_cartesian_to_frenet(test_x, test_y, vx, vy, ax, ay)
    ax_back, ay_back = converter.acceleration_frenet_to_cartesian(s, d, vs, vd, as_, ad)

    print(f"原始Cartesian加速度: ax={ax}, ay={ay}")
    print(f"转换为Frenet加速度: as={as_:.3f}, ad={ad:.3f}")
    print(f"转换回Cartesian加速度: ax={ax_back:.3f}, ay={ay_back:.3f}")
    print(f"加速度误差: dax={abs(ax - ax_back):.6f}, day={abs(ay - ay_back):.6f}")

    # 测试航向角转换
    print("\n=== 航向角转换测试 ===")
    test_heading_cart = np.pi / 4  # 45度
    heading_frenet = converter.heading_cartesian_to_frenet(test_x, test_y, test_heading_cart)
    heading_cart_back = converter.heading_frenet_to_cartesian(s, heading_frenet)
    ref_heading = converter.get_reference_heading(s)

    print(f"原始Cartesian航向角: {np.degrees(test_heading_cart):.3f}°")
    print(f"参考线方向角: {np.degrees(ref_heading):.3f}°")
    print(f"转换为Frenet航向角: {np.degrees(heading_frenet):.3f}°")
    print(f"转换回Cartesian航向角: {np.degrees(heading_cart_back):.3f}°")
    print(f"航向角误差: {np.degrees(abs(test_heading_cart - heading_cart_back)):.6f}°")