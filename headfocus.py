"""HeadFocus - look toward a monitor and the mouse + focus follow.

Uses the webcam + MediaPipe face landmarks to estimate where you're looking
left/right: head turn plus eye (iris) direction, so an eyes-only glance counts
too. After a one-time calibration (look at each monitor), whenever your gaze
settles on a different monitor, the cursor jumps there (to where you last left
it on that screen) and the window under it gets keyboard focus.

    python headfocus.py --calibrate   # first run, and after moving the camera
    python headfocus.py               # run
    python headfocus.py --preview     # run with a camera window showing the angle

F9 pauses / resumes. Ctrl+C in the terminal quits.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

# Silence MediaPipe / TensorFlow Lite startup chatter; must be set before import.
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

# As a PyInstaller exe, bundled files unpack to sys._MEIPASS and the exe's own
# folder may not be writable, so calibration goes to %APPDATA% instead.
FROZEN = getattr(sys, "frozen", False)
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
MODEL_PATH = HERE / "models" / "face_landmarker.task"
# Official MediaPipe model (Apache 2.0). The exe bundles it; the script
# version fetches it on first run instead of storing it in the repo.
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)
if FROZEN:
    CONFIG_PATH = Path(os.environ.get("APPDATA", Path.home())) / "HeadFocus" / "config.json"
else:
    CONFIG_PATH = HERE / "config.json"

CAMERA_INDEX = 0
CAMERA_FIRST_FRAME_TIMEOUT = 5  # seconds to wait for the first picture
CAMERA_HELP = """
{problem}

Check:
  - A webcam is built in or plugged in (USB webcams work).
  - No other app is using it (Zoom, Teams, Discord, the Camera app).
  - Settings > Privacy & security > Camera: "Camera access" and
    "Let desktop apps access your camera" are both On.
  - Any privacy shutter or camera on/off key on the laptop is open.
  - Several cameras? Change CAMERA_INDEX at the top of headfocus.py (0, 1, 2...).
"""
FRAME_SIZE = (640, 480)
TARGET_FPS = 15  # plenty for head turns, keeps CPU low

DWELL_SECONDS = 0.25  # gaze must stay on the new monitor this long before switching
HYSTERESIS = 0.2  # fraction of the gap between monitors, stops flicker at the boundary
SMOOTHING = 0.4  # 0..1, higher = follows the raw angle faster

# How much the eyes count vs the head. 0 = head only; raise it if eyes-only
# glances don't switch, lower it if it switches when you just glance around.
EYE_GAIN = 1.0
EYE_DEG_PER_UNIT = 150  # iris offset (fraction of eye width) -> rough degrees
BLINK_RATIO = 0.18  # eye openness below this = blink, reuse last eye reading

CONFIG_VERSION = 2  # bump when the gaze signal changes; forces recalibration

# MediaPipe face mesh landmark ids.
NOSE_TIP = 1
FACE_EDGES = (234, 454)
RIGHT_EYE = {"outer": 33, "inner": 133, "top": 159, "bottom": 145, "iris": 468}
LEFT_EYE = {"outer": 263, "inner": 362, "top": 386, "bottom": 374, "iris": 473}

CALIBRATE_COUNTDOWN = 3
CALIBRATE_SAMPLE_SECONDS = 2

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MENU = 0x12
VK_F9 = 0x78
KEYEVENTF_KEYUP = 0x0002
GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
MONITOR_DEFAULTTONULL = 0

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.MonitorFromWindow.restype = wt.HMONITOR
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD


# ---------------------------------------------------------------- Windows side

def enable_dpi_awareness():
    # Without this, scaled monitors (125%, 150%) report wrong coordinates.
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # per-monitor v2
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
    ]


MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM
)
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def get_monitors():
    """Monitors sorted left to right: list of dicts with handle and rect."""
    monitors = []

    def callback(hmon, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        r = info.rcMonitor
        monitors.append({"handle": hmon, "rect": (r.left, r.top, r.right, r.bottom)})
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
    monitors.sort(key=lambda m: (m["rect"][0], m["rect"][1]))
    return monitors


def point_in(rect, x, y):
    left, top, right, bottom = rect
    return left <= x < right and top <= y < bottom


def center_of(rect):
    left, top, right, bottom = rect
    return (left + right) // 2, (top + bottom) // 2


def cursor_pos():
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def window_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def is_app_window(hwnd):
    if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return False
    if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return False
    if window_class(hwnd) in SHELL_CLASSES:
        return False
    return bool(window_title(hwnd))


def topmost_window_on(monitor_handle):
    """First real app window (top of z-order) that lives on this monitor."""
    found = []

    def callback(hwnd, _data):
        if is_app_window(hwnd) and user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONULL) == monitor_handle:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found[0] if found else None


def window_at(x, y):
    hwnd = user32.WindowFromPoint(wt.POINT(x, y))
    if not hwnd:
        return None
    root = user32.GetAncestor(hwnd, GA_ROOT)
    return root if is_app_window(root) else None


def focus_window(hwnd):
    """SetForegroundWindow is normally refused for background apps; borrow the
    foreground thread's input state so Windows allows it."""
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    our_thread = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread) and fg_thread != our_thread and bool(
        user32.AttachThreadInput(our_thread, fg_thread, True)
    )
    try:
        user32.BringWindowToTop(hwnd)
        ok = user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(our_thread, fg_thread, False)
    if not ok:
        # Fallback: a synthetic Alt tap also unlocks SetForegroundWindow.
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)


# ---------------------------------------------------------------- head tracking

def ensure_model():
    if MODEL_PATH.exists():
        return
    print("Downloading face model (~4 MB, one time)...")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    partial = MODEL_PATH.with_suffix(".part")
    try:
        urllib.request.urlretrieve(MODEL_URL, partial)
    except OSError as e:
        partial.unlink(missing_ok=True)
        sys.exit(f"Couldn't download the face model ({e}). Check your internet and retry.")
    partial.replace(MODEL_PATH)
    print("Face model ready.")


def head_angle(lm):
    """Head turn from how far the nose sits off the middle of the face."""
    a, b = lm[FACE_EDGES[0]].x, lm[FACE_EDGES[1]].x
    half = abs(b - a) / 2
    if half < 1e-6:
        return 0.0
    # The nose sticks out, so its offset grows ~tan(angle) and passes 1 on big
    # turns; atan keeps it from saturating.
    offset = (lm[NOSE_TIP].x - (a + b) / 2) / half
    return math.degrees(math.atan(offset))


def eye_angle(lm):
    """Eye direction from where each iris sits between its eye corners.
    None while blinking (iris landmarks are garbage with closed eyes)."""
    offsets = []
    for eye in (RIGHT_EYE, LEFT_EYE):
        x1, x2 = lm[eye["outer"]].x, lm[eye["inner"]].x
        width = abs(x2 - x1)
        if width < 1e-6:
            continue
        if abs(lm[eye["top"]].y - lm[eye["bottom"]].y) / width < BLINK_RATIO:
            continue
        offsets.append((lm[eye["iris"]].x - min(x1, x2)) / width - 0.5)
    if not offsets:
        return None
    return sum(offsets) / len(offsets) * EYE_DEG_PER_UNIT


class HeadTracker:
    def __init__(self):
        ensure_model()
        options = vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)
        self.cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_MSMF)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_SIZE[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_SIZE[1])
        if not self.cap.isOpened():
            self.landmarker.close()
            sys.exit(CAMERA_HELP.format(
                problem=f"No camera found (camera #{CAMERA_INDEX}). HeadFocus needs a webcam to work."
            ))
        # A camera can "open" but deliver nothing (blocked by privacy settings).
        deadline = time.monotonic() + CAMERA_FIRST_FRAME_TIMEOUT
        while not self.cap.read()[0]:
            if time.monotonic() > deadline:
                self.cap.release()
                self.landmarker.close()
                sys.exit(CAMERA_HELP.format(problem="The camera opened but isn't sending any picture."))
            time.sleep(0.1)
        self.started = time.monotonic()
        self.last_ts = -1
        self.frame = None
        self.head = 0.0
        self.eyes = 0.0

    def read_yaw(self):
        """Horizontal gaze (head + eyes) in rough degrees, or None if no face."""
        ok, frame = self.cap.read()
        if not ok:
            return None
        self.frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = int((time.monotonic() - self.started) * 1000)
        if ts <= self.last_ts:  # MediaPipe needs strictly increasing timestamps
            ts = self.last_ts + 1
        self.last_ts = ts
        result = self.landmarker.detect_for_video(image, ts)
        if not result.face_landmarks:
            return None
        lm = result.face_landmarks[0]
        # Both parts are measured along image x, so they always add in the same
        # direction. Absolute sign/scale don't matter: calibration maps them.
        self.head = head_angle(lm)
        eyes = eye_angle(lm)
        if eyes is not None:
            self.eyes = eyes
        return self.head + EYE_GAIN * self.eyes

    def close(self):
        self.cap.release()
        self.landmarker.close()
        cv2.destroyAllWindows()


# ---------------------------------------------------------------- calibration

def calibrate():
    monitors = get_monitors()
    if len(monitors) < 2:
        sys.exit("Only one monitor detected - nothing to switch between.")

    tracker = HeadTracker()
    print(f"Found {len(monitors)} monitors (left to right). Sit how you normally work.\n")
    entries = []
    try:
        for i, mon in enumerate(monitors, 1):
            user32.SetCursorPos(*center_of(mon["rect"]))
            input(f"Monitor {i}/{len(monitors)} (the cursor is in its center). "
                  "Press Enter, then look at the cursor the way you normally would...")
            for s in range(CALIBRATE_COUNTDOWN, 0, -1):
                print(f"  look at monitor {i} ... {s}")
                end = time.monotonic() + 1
                while time.monotonic() < end:
                    tracker.read_yaw()  # keep the camera warm
            samples = []
            end = time.monotonic() + CALIBRATE_SAMPLE_SECONDS
            while time.monotonic() < end:
                yaw = tracker.read_yaw()
                if yaw is not None:
                    samples.append(yaw)
            if len(samples) < 5:
                sys.exit("Couldn't see your face. Check lighting / camera angle and retry.")
            yaw = statistics.median(samples)
            print(f"  monitor {i}: gaze {yaw:+.1f}\n")
            entries.append({"rect": list(mon["rect"]), "yaw": yaw})
    finally:
        tracker.close()

    yaws = sorted(e["yaw"] for e in entries)
    min_gap = min(b - a for a, b in zip(yaws, yaws[1:]))
    if min_gap < 8:
        print(f"Warning: monitors are only {min_gap:.1f} apart - look more clearly at "
              "each one (turn your head a bit), or switching will be unreliable.")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"version": CONFIG_VERSION, "monitors": entries}, indent=2))
    print(f"Saved calibration to {CONFIG_PATH}")


# ---------------------------------------------------------------- main loop

def load_config():
    """Calibrated monitors, or None (with the reason printed) if a fresh
    calibration is needed."""
    if not CONFIG_PATH.exists():
        print("Not calibrated yet.")
        return None
    config = json.loads(CONFIG_PATH.read_text())
    if config.get("version") != CONFIG_VERSION:
        print("Calibration is from an older version.")
        return None
    live = get_monitors()
    # Re-attach calibration to the live monitor handles by matching rects.
    result = []
    for entry in config["monitors"]:
        match = next((m for m in live if list(m["rect"]) == entry["rect"]), None)
        if match is None:
            print("Monitor layout changed since calibration.")
            return None
        result.append({**match, "yaw": entry["yaw"]})
    return result


def pick_monitor(yaw, monitors, current):
    """Nearest calibrated monitor, but only leave `current` when clearly past it."""
    best = min(range(len(monitors)), key=lambda i: abs(monitors[i]["yaw"] - yaw))
    if current is None or best == current:
        return best
    gap = abs(monitors[best]["yaw"] - monitors[current]["yaw"])
    if abs(monitors[current]["yaw"] - yaw) - abs(monitors[best]["yaw"] - yaw) > gap * HYSTERESIS:
        return best
    return current


def switch_to(index, monitors, last_pos):
    mon = monitors[index]
    pos = last_pos.get(index)
    if pos is None or not point_in(mon["rect"], *pos):
        pos = center_of(mon["rect"])
    user32.SetCursorPos(*pos)
    hwnd = window_at(*pos) or topmost_window_on(mon["handle"])
    if hwnd:
        focus_window(hwnd)
    return hwnd


def run(preview):
    monitors = load_config()
    if monitors is None:
        print("Starting calibration first.\n")
        calibrate()
        monitors = load_config()
        if monitors is None:
            sys.exit("Calibration didn't match the current monitors. Try again.")
        print()
    tracker = HeadTracker()
    frame_time = 1 / TARGET_FPS

    smooth = None
    looking = None  # monitor the head is settled on
    candidate, candidate_since = None, 0.0
    last_pos = {}  # where the cursor was last seen on each monitor
    paused = False
    f9_was_down = False

    print("HeadFocus running. F9 = pause/resume, Ctrl+C = quit.")
    try:
        while True:
            tick = time.monotonic()

            f9 = key_down(VK_F9)
            if f9 and not f9_was_down:
                paused = not paused
                print("Paused." if paused else "Resumed.")
            f9_was_down = f9

            cx, cy = cursor_pos()
            for i, mon in enumerate(monitors):
                if point_in(mon["rect"], cx, cy):
                    last_pos[i] = (cx, cy)

            yaw = tracker.read_yaw()
            if yaw is not None:
                smooth = yaw if smooth is None else smooth + SMOOTHING * (yaw - smooth)
                target = pick_monitor(smooth, monitors, looking)

                if looking is None:
                    looking = target
                elif target != looking:
                    if candidate != target:
                        candidate, candidate_since = target, tick
                    elif tick - candidate_since >= DWELL_SECONDS:
                        looking, candidate = target, None
                        dragging = key_down(VK_LBUTTON) or key_down(VK_RBUTTON)
                        cursor_there = point_in(monitors[looking]["rect"], cx, cy)
                        # Only act on the turn itself, never fight a mouse you're using.
                        if not paused and not dragging and not cursor_there:
                            hwnd = switch_to(looking, monitors, last_pos)
                            title = window_title(hwnd) if hwnd else "-"
                            print(f"-> monitor {looking + 1}  ({title[:60]})")
                else:
                    candidate = None

            if preview and tracker.frame is not None:
                view = cv2.flip(tracker.frame, 1)
                if smooth is None or yaw is None:
                    text = "no face"
                else:
                    text = (f"gaze {smooth:+.1f} (head {tracker.head:+.0f} eyes {tracker.eyes:+.0f})"
                            f"  monitor {looking + 1}")
                if paused:
                    text += "  [PAUSED]"
                cv2.putText(view, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow("HeadFocus (q to close preview)", view)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    preview = False
                    cv2.destroyAllWindows()

            spare = frame_time - (time.monotonic() - tick)
            if spare > 0:
                time.sleep(spare)
    except KeyboardInterrupt:
        pass
    finally:
        tracker.close()
        print("HeadFocus stopped.")


def main():
    if sys.platform != "win32":
        sys.exit("HeadFocus only runs on Windows.")
    if not FROZEN:
        return _main()
    # Double-clicked exe: its console window vanishes on exit, so hold it open
    # long enough to read the last message (errors included).
    try:
        _main()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(e.code if isinstance(e.code, str) else f"Exited with code {e.code}")
    except Exception:
        import traceback
        traceback.print_exc()
    try:
        input("\nPress Enter to close...")
    except (EOFError, KeyboardInterrupt):
        pass


def _main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--calibrate", action="store_true", help="look at each monitor to record its gaze angle")
    parser.add_argument("--preview", action="store_true", help="show the camera with the detected angle")
    parser.add_argument("--download-model", action="store_true", help="just fetch the face model and exit")
    args = parser.parse_args()

    if args.download_model:
        ensure_model()
        return
    enable_dpi_awareness()
    if args.calibrate:
        calibrate()
    else:
        run(args.preview)


if __name__ == "__main__":
    main()
