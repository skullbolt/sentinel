"""
Humanizer Module
================
Generates human-like touch parameters:
  - Gaussian coordinate offsets (not perfectly centered taps)
  - Pressure bell curves (pressure ramps up then down)
  - Micro-drift during touch (finger moves slightly)
  - Bezier curve swipe paths (curved, not straight lines)
  - Realistic timing between actions
  - Variable tap durations
"""

from __future__ import annotations

import random
import math
import time
from typing import List, Tuple, Dict
from dataclasses import dataclass, field


@dataclass
class TouchPoint:
    """A single point in a touch event sequence"""
    x: int
    y: int
    pressure: int
    touch_major: int
    timestamp_ms: float  # relative to touch start


@dataclass
class TouchSequence:
    """Complete touch event sequence (tap, swipe, etc.)"""
    points: List[TouchPoint] = field(default_factory=list)
    total_duration_ms: float = 0
    action_type: str = "tap"


class Humanizer:
    """Generates human-like touch parameters"""

    def __init__(
        self,
        pressure_max: int = 1024,
        touch_major_max: int = 10,
        seed: int = None
    ):
        self.pressure_max = pressure_max
        self.touch_major_max = touch_major_max if touch_major_max > 0 else 10

        if seed is not None:
            random.seed(seed)

    # ─── COORDINATE HUMANIZATION ─────────────────

    def humanize_coordinates(
        self,
        target_x: int,
        target_y: int,
        element_width: int = 100,
        element_height: int = 60,
    ) -> Tuple[int, int]:
        """
        Offset target coordinates using Gaussian distribution.
        
        Humans don't tap the EXACT center of a button.
        They tap near the center with some natural variance.
        
        Gaussian = most taps near center, fewer taps near edges.
        """
        # Sigma = how spread out the taps are
        # Smaller element = more precise taps (user aims more carefully)
        sigma_x = max(element_width * 0.15, 3)
        sigma_y = max(element_height * 0.15, 3)

        # Generate offset using Gaussian (bell curve) distribution
        offset_x = random.gauss(0, sigma_x)
        offset_y = random.gauss(0, sigma_y)

        # Clamp to stay within element bounds
        max_offset_x = element_width * 0.4
        max_offset_y = element_height * 0.4
        offset_x = max(-max_offset_x, min(max_offset_x, offset_x))
        offset_y = max(-max_offset_y, min(max_offset_y, offset_y))

        final_x = int(target_x + offset_x)
        final_y = int(target_y + offset_y)

        return final_x, final_y

    # ─── PRESSURE CURVE GENERATION ───────────────

    def generate_pressure_curve(
        self,
        duration_ms: float,
        step_ms: float = 8.0,
    ) -> List[int]:
        """
        Generate a realistic pressure curve for a tap.
        
        Real finger pressure follows a bell curve:
          - Starts at 0 (finger approaching)
          - Ramps up quickly
          - Peaks in the middle
          - Ramps down as finger lifts
        
        With slight noise added for realism.
        """
        steps = max(int(duration_ms / step_ms), 3)
        peak_pressure = random.randint(
            int(self.pressure_max * 0.3),
            int(self.pressure_max * 0.7)
        )

        # Peak position — slightly before middle (humans press harder initially)
        peak_pos = random.uniform(0.35, 0.55)

        pressures = []
        for i in range(steps):
            t = i / (steps - 1)  # 0.0 to 1.0

            # Bell curve using sine-based envelope
            if t < peak_pos:
                # Rising phase
                phase = (t / peak_pos) * (math.pi / 2)
                p = math.sin(phase) * peak_pressure
            else:
                # Falling phase
                phase = ((t - peak_pos) / (1 - peak_pos)) * (math.pi / 2)
                p = math.cos(phase) * peak_pressure

            # Add noise (±5% of max)
            noise = random.gauss(0, self.pressure_max * 0.02)
            p = max(1, min(self.pressure_max, int(p + noise)))

            pressures.append(p)

        # Ensure first and last are very low
        pressures[0] = random.randint(1, max(2, int(self.pressure_max * 0.05)))
        pressures[-1] = random.randint(1, max(2, int(self.pressure_max * 0.03)))

        return pressures

    def generate_touch_major_curve(
        self,
        duration_ms: float,
        step_ms: float = 8.0,
    ) -> List[int]:
        """
        Generate touch contact size curve.
        Correlates with pressure — bigger contact when pressing harder.
        """
        steps = max(int(duration_ms / step_ms), 3)
        peak_size = random.randint(
            max(1, int(self.touch_major_max * 0.4)),
            max(2, int(self.touch_major_max * 0.8))
        )

        sizes = []
        for i in range(steps):
            t = i / (steps - 1)
            # Simple bell shape
            size = peak_size * math.sin(t * math.pi)
            size = max(1, min(self.touch_major_max, int(size)))
            sizes.append(size)

        sizes[0] = max(1, int(self.touch_major_max * 0.1))
        sizes[-1] = max(1, int(self.touch_major_max * 0.1))

        return sizes

    # ─── MICRO-DRIFT GENERATION ──────────────────

    def generate_micro_drift(
        self,
        start_x: int,
        start_y: int,
        num_points: int,
    ) -> List[Tuple[int, int]]:
        """
        Generate slight coordinate drift during a touch.
        
        A real finger doesn't stay at exactly one pixel.
        It drifts 1-3 pixels during a tap.
        """
        points = [(start_x, start_y)]

        # Drift direction — finger tends to drift in one direction
        drift_angle = random.uniform(0, 2 * math.pi)
        total_drift = random.uniform(1, 4)  # pixels

        for i in range(1, num_points):
            t = i / (num_points - 1)

            # Cumulative drift in one general direction
            drift_x = total_drift * math.cos(drift_angle) * t
            drift_y = total_drift * math.sin(drift_angle) * t

            # Add micro-jitter
            jitter_x = random.gauss(0, 0.5)
            jitter_y = random.gauss(0, 0.5)

            x = int(start_x + drift_x + jitter_x)
            y = int(start_y + drift_y + jitter_y)

            points.append((x, y))

        return points

    # ─── TAP SEQUENCE GENERATION ─────────────────

    def generate_tap(
        self,
        x: int,
        y: int,
        element_width: int = 100,
        element_height: int = 60,
    ) -> TouchSequence:
        """
        Generate a complete human-like single tap.
        
        Returns a TouchSequence with all the points
        that need to be sent via sendevent.
        """
        # Humanize target coordinates
        hx, hy = self.humanize_coordinates(x, y, element_width, element_height)

        # Random tap duration (quick tap = 50-130ms)
        duration = random.uniform(50, 130)
        step_ms = 8.0  # ~125Hz touch report rate
        num_steps = max(int(duration / step_ms), 3)

        # Generate curves
        pressures = self.generate_pressure_curve(duration, step_ms)
        touch_majors = self.generate_touch_major_curve(duration, step_ms)
        drift_points = self.generate_micro_drift(hx, hy, num_steps)

        # Ensure all lists are same length
        min_len = min(len(pressures), len(touch_majors), len(drift_points))
        pressures = pressures[:min_len]
        touch_majors = touch_majors[:min_len]
        drift_points = drift_points[:min_len]

        # Build touch sequence
        sequence = TouchSequence(action_type="tap", total_duration_ms=duration)

        for i in range(min_len):
            point = TouchPoint(
                x=drift_points[i][0],
                y=drift_points[i][1],
                pressure=pressures[i],
                touch_major=touch_majors[i],
                timestamp_ms=i * step_ms,
            )
            sequence.points.append(point)

        return sequence

    def generate_double_tap(
        self,
        x: int,
        y: int,
        element_width: int = 200,
        element_height: int = 200,
    ) -> Tuple[TouchSequence, TouchSequence]:
        """
        Generate two taps for a double-tap.
        Second tap is slightly offset from first.
        """
        tap1 = self.generate_tap(x, y, element_width, element_height)

        # Second tap slightly offset from first
        offset_x = random.randint(-5, 5)
        offset_y = random.randint(-5, 5)
        tap2 = self.generate_tap(x + offset_x, y + offset_y, element_width, element_height)

        return tap1, tap2

    def generate_long_press(
        self,
        x: int,
        y: int,
        hold_duration_ms: float = 800,
        element_width: int = 100,
        element_height: int = 60,
    ) -> TouchSequence:
        """Generate a long press — same as tap but longer hold."""
        hx, hy = self.humanize_coordinates(x, y, element_width, element_height)

        duration = hold_duration_ms + random.uniform(-100, 200)
        step_ms = 16.0  # Lower frequency for long press
        num_steps = max(int(duration / step_ms), 5)

        # Sustained pressure (not a bell curve — more like a plateau)
        sustained_pressure = random.randint(
            int(self.pressure_max * 0.3),
            int(self.pressure_max * 0.6)
        )

        sequence = TouchSequence(action_type="long_press", total_duration_ms=duration)
        drift_points = self.generate_micro_drift(hx, hy, num_steps)

        for i in range(num_steps):
            t = i / (num_steps - 1)

            # Ramp up, sustain, ramp down
            if t < 0.1:
                pressure = int(sustained_pressure * (t / 0.1))
            elif t > 0.9:
                pressure = int(sustained_pressure * ((1 - t) / 0.1))
            else:
                pressure = sustained_pressure + random.randint(-10, 10)

            pressure = max(1, min(self.pressure_max, pressure))

            dx, dy = drift_points[min(i, len(drift_points) - 1)]

            point = TouchPoint(
                x=dx, y=dy,
                pressure=pressure,
                touch_major=random.randint(
                    max(1, int(self.touch_major_max * 0.4)),
                    max(2, int(self.touch_major_max * 0.7))
                ),
                timestamp_ms=i * step_ms,
            )
            sequence.points.append(point)

        return sequence

    # ─── SWIPE / SCROLL GENERATION ───────────────

    def generate_swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: float = None,
    ) -> TouchSequence:
        """
        Generate a human-like swipe using bezier curves.
        
        Real swipes:
          - Follow a curved path (not straight)
          - Start slow, speed up, slow down at end
          - Have slight wobble
          - Vary in pressure throughout
        """
        if duration_ms is None:
            # Calculate duration based on distance
            distance = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
            duration_ms = max(200, min(800, distance * 0.5 + random.uniform(-50, 100)))

        step_ms = 8.0
        num_steps = max(int(duration_ms / step_ms), 10)

        # Generate bezier control point for curved path
        mid_x = (start_x + end_x) / 2
        mid_y = (start_y + end_y) / 2

        # Perpendicular offset for curve
        dx = end_x - start_x
        dy = end_y - start_y
        perp_x = -dy
        perp_y = dx
        length = math.sqrt(perp_x ** 2 + perp_y ** 2)

        if length > 0:
            perp_x /= length
            perp_y /= length

        # Random curve amount (slight curve, not exaggerated)
        curve_amount = random.uniform(-30, 30)
        control_x = mid_x + perp_x * curve_amount
        control_y = mid_y + perp_y * curve_amount

        # Swipe pressure (lower than tap, more sustained)
        swipe_pressure = random.randint(
            int(self.pressure_max * 0.15),
            int(self.pressure_max * 0.35)
        )

        sequence = TouchSequence(action_type="swipe", total_duration_ms=duration_ms)

        for i in range(num_steps):
            t = i / (num_steps - 1)

            # Ease-in-out timing (slow start, fast middle, slow end)
            eased_t = self._ease_in_out(t)

            # Quadratic bezier curve
            bx = (1 - eased_t) ** 2 * start_x + 2 * (1 - eased_t) * eased_t * control_x + eased_t ** 2 * end_x
            by = (1 - eased_t) ** 2 * start_y + 2 * (1 - eased_t) * eased_t * control_y + eased_t ** 2 * end_y

            # Add micro-wobble
            wobble_x = random.gauss(0, 1.5)
            wobble_y = random.gauss(0, 1.0)

            px = int(bx + wobble_x)
            py = int(by + wobble_y)

            # Pressure: rises at start, sustained, drops at end
            if t < 0.15:
                pressure = int(swipe_pressure * (t / 0.15))
            elif t > 0.85:
                pressure = int(swipe_pressure * ((1 - t) / 0.15))
            else:
                pressure = swipe_pressure + random.randint(-5, 5)

            pressure = max(1, min(self.pressure_max, pressure))

            point = TouchPoint(
                x=px, y=py,
                pressure=pressure,
                touch_major=random.randint(
                    max(1, int(self.touch_major_max * 0.3)),
                    max(2, int(self.touch_major_max * 0.6))
                ),
                timestamp_ms=i * step_ms,
            )
            sequence.points.append(point)

        return sequence

    def generate_scroll(
        self,
        screen_width: int,
        screen_height: int,
        direction: str = "up",
    ) -> TouchSequence:
        """
        Generate a natural scroll gesture.
        
        direction: "up" (scroll content up = swipe finger up)
                   "down" (scroll content down = swipe finger down)
        """
        # Start position — not exactly center, slightly random
        start_x = screen_width // 2 + random.randint(-80, 80)

        if direction == "up":
            start_y = random.randint(int(screen_height * 0.55), int(screen_height * 0.75))
            end_y = random.randint(int(screen_height * 0.2), int(screen_height * 0.35))
        else:
            start_y = random.randint(int(screen_height * 0.25), int(screen_height * 0.4))
            end_y = random.randint(int(screen_height * 0.65), int(screen_height * 0.8))

        # Slight horizontal drift during scroll (humans don't scroll perfectly vertical)
        end_x = start_x + random.randint(-20, 20)

        # Scroll speed varies
        duration = random.uniform(250, 600)

        return self.generate_swipe(start_x, start_y, end_x, end_y, duration)

    # ─── TIMING ──────────────────────────────────

    def get_action_delay(self, action_type: str = "general") -> float:
        """
        Get a human-like delay between actions (in seconds).
        
        Returns seconds to wait before next action.
        """
        delays = {
            "between_taps": (0.3, 1.5),
            "between_likes": (15, 45),
            "between_follows": (30, 90),
            "between_comments": (45, 120),
            "between_dms": (60, 180),
            "between_scrolls": (1.5, 5.0),
            "after_navigation": (1.5, 3.5),
            "reading_post": (2.0, 8.0),
            "reading_profile": (2.0, 6.0),
            "typing_pause": (0.5, 2.0),
            "double_tap_gap": (0.08, 0.2),
            "general": (1.0, 3.0),
        }

        min_d, max_d = delays.get(action_type, delays["general"])

        # 10% chance of longer pause (human distraction)
        if random.random() < 0.10:
            return random.uniform(max_d * 2, max_d * 4)

        # 3% chance of very long pause (checking notification, etc.)
        if random.random() < 0.03:
            return random.uniform(10, 30)

        return random.uniform(min_d, max_d)

    def get_typing_delay(self) -> float:
        """Delay between keystrokes when typing (in seconds)."""
        # Most characters: fast
        base = random.uniform(0.04, 0.15)

        # 15% chance of slightly longer pause (thinking)
        if random.random() < 0.15:
            base = random.uniform(0.2, 0.5)

        # 3% chance of even longer pause
        if random.random() < 0.03:
            base = random.uniform(0.5, 1.5)

        return base

    # ─── UTILITY ─────────────────────────────────

    @staticmethod
    def _ease_in_out(t: float) -> float:
        """Smooth ease-in-out curve (slow start, fast middle, slow end)"""
        if t < 0.5:
            return 2 * t * t
        else:
            return 1 - (-2 * t + 2) ** 2 / 2