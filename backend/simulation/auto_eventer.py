import time
import math
from typing import Dict, Any, Optional
from api.schemas import AutoEventDetection, EventType, Coordinates, BallTelemetry

class AutoEventVisionPipeline:
    """
    Simulates real-time Azure Vision / YOLO pitch-tracking inference pipeline.
    Transforms raw continuous video coordinates into classified discrete football events,
    calculating pass speeds, trajectories, and player tagging automatically.
    """
    def __init__(self, model_version: str = "Azure-ComputerVision-Football-v4.2"):
        self.model_version = model_version
        self.frame_count = 0

    def process_frame(
        self,
        event_type: EventType,
        start_coord: Coordinates,
        end_coord: Coordinates,
        delta_seconds: float
    ) -> Dict[str, Any]:
        """
        Runs automated feature extraction over spatial displacement to infer speed,
        distance, and detection confidence.
        """
        self.frame_count += 1
        t0 = time.perf_counter()

        dx = end_coord.x - start_coord.x
        dy = end_coord.y - start_coord.y
        distance_m = math.sqrt(dx * dx + dy * dy)
        
        # Calculate speed in km/h: (distance_m / delta_seconds) * 3.6
        if delta_seconds > 0:
            speed_kmh = (distance_m / max(0.2, delta_seconds)) * 3.6
        else:
            speed_kmh = 0.0

        # Bound realistic speeds
        if event_type == EventType.SHOT:
            speed_kmh = max(82.0, min(128.0, speed_kmh * 1.5))
        elif event_type == EventType.PASS:
            speed_kmh = max(25.0, min(88.0, speed_kmh))
        else:
            speed_kmh = max(0.0, min(36.0, speed_kmh))

        # Vision model inference timing simulation (typically 12 - 25 ms)
        inference_latency_ms = round((time.perf_counter() - t0) * 1000.0 + 15.4, 2)
        confidence = 0.97 if event_type in [EventType.PASS, EventType.SHOT] else 0.89

        detection = AutoEventDetection(
            model_name=self.model_version,
            confidence_score=confidence,
            inference_latency_ms=inference_latency_ms,
            auto_detected=True
        )

        telemetry = BallTelemetry(
            speed_kmh=round(speed_kmh, 1),
            airborne=(distance_m > 18.0),
            distance_meters=round(distance_m, 1)
        )

        return {
            "telemetry": telemetry,
            "detection": detection
        }
