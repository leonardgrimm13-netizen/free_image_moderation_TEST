#!/usr/bin/env python3
"""Monitor screen 1 for a target image and save full screenshots while visible."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import cv2
import mss
import numpy as np

# ------------------------- Configuration constants -------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "target.png"
SAVE_DIR = BASE_DIR / "screenshots"
MONITOR_INDEX = 1  # MSS monitor index (1 = first physical monitor)
CHECK_EVERY = 0.45  # seconds between visibility checks
SCREENSHOT_EVERY = 3.0  # seconds between saved screenshots while visible
MATCH_THRESHOLD = 0.74
SCALES = (0.85, 0.92, 1.0, 1.08, 1.16)
DEBUG = False
IMMEDIATE_FIRST_SHOT = True


@dataclass
class TemplateData:
    gray: np.ndarray
    mask: Optional[np.ndarray]
    width: int
    height: int


def log(msg: str) -> None:
    print(msg, flush=True)


def log_debug(enabled: bool, msg: str) -> None:
    if enabled:
        log(f"[DEBUG] {msg}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Watches monitor 1 for target.png and saves full screenshots every "
            "3 seconds only while the target is visible."
        )
    )
    parser.add_argument("--threshold", type=float, default=MATCH_THRESHOLD)
    parser.add_argument("--check-every", type=float, default=CHECK_EVERY)
    parser.add_argument("--screenshot-every", type=float, default=SCREENSHOT_EVERY)
    parser.add_argument(
        "--scales",
        type=str,
        default=",".join(str(v) for v in SCALES),
        help="Comma separated scales, e.g. 0.9,1.0,1.1",
    )
    parser.add_argument("--monitor", type=int, default=MONITOR_INDEX)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--self-test", action="store_true", help="Run internal checks")
    parser.add_argument(
        "--no-immediate-first-shot",
        action="store_true",
        help="When target becomes visible, wait for normal interval before first shot.",
    )
    return parser.parse_args()


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise RuntimeError(f"Screenshot directory not available: {path}")


def parse_scales(raw: str) -> list[float]:
    scales = []
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        value = float(text)
        if value <= 0:
            raise ValueError(f"Scale must be > 0, got {value}")
        scales.append(value)
    if not scales:
        raise ValueError("At least one scale is required")
    return scales


def load_template(template_path: Path) -> TemplateData:
    if not template_path.exists():
        raise FileNotFoundError(f"target image not found: {template_path}")

    image = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Failed to read target image: {template_path}")

    # Handle grayscale, BGR, BGRA robustly.
    if image.ndim == 2:
        gray = image
        mask = None
    elif image.ndim == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mask = None
    elif image.ndim == 3 and image.shape[2] == 4:
        bgr = image[:, :, :3]
        alpha = image[:, :, 3]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        mask = alpha
    else:
        raise ValueError(f"Unsupported template image format: shape={image.shape}")

    h, w = gray.shape[:2]
    if h < 2 or w < 2:
        raise ValueError("target.png is too small (minimum 2x2)")

    return TemplateData(gray=gray, mask=mask, width=w, height=h)


def capture_monitor_bgr(sct: mss.mss, monitor_index: int) -> np.ndarray:
    monitors = sct.monitors
    if monitor_index < 1 or monitor_index >= len(monitors):
        raise IndexError(
            f"Monitor index {monitor_index} is invalid. Available physical monitors: "
            f"1..{len(monitors) - 1}"
        )
    raw = np.array(sct.grab(monitors[monitor_index]))
    if raw.size == 0:
        raise RuntimeError("Empty frame captured from monitor")
    return raw[:, :, :3]  # BGRA -> BGR


def scaled_template(template: TemplateData, scale: float) -> Optional[TemplateData]:
    new_w = max(1, int(round(template.width * scale)))
    new_h = max(1, int(round(template.height * scale)))
    if new_w < 2 or new_h < 2:
        return None

    gray = cv2.resize(template.gray, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    mask = None
    if template.mask is not None:
        mask = cv2.resize(template.mask, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
    return TemplateData(gray=gray, mask=mask, width=new_w, height=new_h)


def best_match_score(
    frame_gray: np.ndarray,
    template: TemplateData,
    scales: Iterable[float],
    debug: bool = False,
) -> float:
    frame_h, frame_w = frame_gray.shape[:2]
    best = -1.0

    for scale in scales:
        candidate = scaled_template(template, scale)
        if candidate is None:
            continue
        if candidate.width > frame_w or candidate.height > frame_h:
            log_debug(debug, f"skip scale={scale:.3f} (template larger than frame)")
            continue

        try:
            if candidate.mask is not None:
                result = cv2.matchTemplate(
                    frame_gray,
                    candidate.gray,
                    cv2.TM_CCOEFF_NORMED,
                    mask=candidate.mask,
                )
            else:
                result = cv2.matchTemplate(frame_gray, candidate.gray, cv2.TM_CCOEFF_NORMED)
        except cv2.error:
            # Some OpenCV builds/method combinations can reject masks.
            result = cv2.matchTemplate(frame_gray, candidate.gray, cv2.TM_CCOEFF_NORMED)

        score = float(cv2.minMaxLoc(result)[1])
        if score > best:
            best = score
        log_debug(debug, f"scale={scale:.3f}, score={score:.4f}")

    return best


def screenshot_filename(now: Optional[datetime] = None) -> str:
    ts = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    return f"screen1_{ts}.png"


def save_screenshot(frame_bgr: np.ndarray, save_dir: Path) -> Path:
    ensure_output_dir(save_dir)
    path = save_dir / screenshot_filename()

    ok = cv2.imwrite(str(path), frame_bgr)
    if not ok:
        raise RuntimeError(f"cv2.imwrite reported failure for file: {path}")
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"Screenshot file was not created correctly: {path}")

    return path


def run_self_test() -> int:
    log("Running self-test...")
    ensure_output_dir(SAVE_DIR)

    # 1) Path and save validation
    dummy = np.zeros((80, 120, 3), dtype=np.uint8)
    dummy[:, :] = (0, 120, 255)
    saved = save_screenshot(dummy, SAVE_DIR)
    log(f"Self-test screenshot written: {saved}")

    # 2) Basic template matching sanity check with synthetic data
    frame = np.full((120, 160), 20, dtype=np.uint8)
    template_arr = np.full((16, 20), 180, dtype=np.uint8)
    frame[50:66, 70:90] = template_arr
    td = TemplateData(gray=template_arr, mask=None, width=20, height=16)
    score = best_match_score(frame, td, [1.0], debug=False)
    if score < 0.95:
        raise RuntimeError(f"Self-test matching score unexpectedly low: {score:.4f}")

    log(f"Self-test matching score: {score:.4f}")
    log("Self-test passed.")
    return 0


def main() -> int:
    args = parse_args()
    debug = bool(DEBUG or args.debug)

    if args.self_test:
        return run_self_test()

    try:
        scales = parse_scales(args.scales)
        template = load_template(TEMPLATE_PATH)
        ensure_output_dir(SAVE_DIR)
    except Exception as exc:
        log(f"[ERROR] Startup failed: {exc}")
        return 1

    immediate_first_shot = not args.no_immediate_first_shot and IMMEDIATE_FIRST_SHOT

    log("Starting monitor watcher...")
    log(f"Script path: {BASE_DIR}")
    log(f"Target path: {TEMPLATE_PATH}")
    log(f"Screenshot folder: {SAVE_DIR}")
    log(f"Monitor index: {args.monitor}")
    log(f"Threshold: {args.threshold:.3f}, scales: {scales}")

    was_visible = False
    next_shot_at = 0.0

    try:
        with mss.mss() as sct:
            while True:
                loop_started = time.monotonic()
                try:
                    frame_bgr = capture_monitor_bgr(sct, args.monitor)
                    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                    score = best_match_score(frame_gray, template, scales, debug=debug)
                    visible = score >= args.threshold
                except Exception as exc:
                    log(f"[ERROR] Capture/match failed: {exc}")
                    time.sleep(max(0.2, args.check_every))
                    continue

                now = time.monotonic()
                if visible != was_visible:
                    if visible:
                        log(f"[STATE] erkannt (score={score:.4f})")
                        next_shot_at = now if immediate_first_shot else now + args.screenshot_every
                    else:
                        log(f"[STATE] nicht erkannt (score={score:.4f})")
                    was_visible = visible

                if visible and now >= next_shot_at:
                    try:
                        saved_path = save_screenshot(frame_bgr, SAVE_DIR)
                        log(f"[SAVE] {saved_path}")
                    except Exception as exc:
                        log(f"[ERROR] Save failed: {exc}")
                    finally:
                        next_shot_at = now + args.screenshot_every

                elapsed = time.monotonic() - loop_started
                sleep_for = max(0.05, args.check_every - elapsed)
                time.sleep(sleep_for)
    except KeyboardInterrupt:
        log("Stopped by user (Ctrl+C).")
        return 0
    except Exception as exc:
        log(f"[ERROR] Fatal error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
