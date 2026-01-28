import threading
import time
import ctypes
import gc
import sys
from pynput import mouse

# --- Configuration Area ---
CLICK_INTERVAL_MS = 74   # Total period (Target: 18.18 clicks/sec)
DUTY_CYCLE_PERCENT = 12.154  # 50% Down / 50% Up
# --------------------------

# Win32 API Constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0
REALTIME_PRIORITY_CLASS = 0x00000100

# Win32 API Function Bindings
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
winmm = ctypes.windll.winmm

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("mi", MOUSEINPUT)
    ]

class UltimateExpertClicker:
    def __init__(self):
        self.enabled = False
        self.running = True
        
        # 1. Pre-calculate timings in seconds
        self.on_time = (CLICK_INTERVAL_MS * (DUTY_CYCLE_PERCENT / 100.0)) / 1000.0
        self.off_time = (CLICK_INTERVAL_MS * (1 - (DUTY_CYCLE_PERCENT / 100.0))) / 1000.0
        
        # 2. Memory Pinning (Option 3 & 4)
        # We pre-allocate structures and cache their pointers/sizes to minimize 
        # Python interpreter overhead during the high-speed loop.
        self._extra = ctypes.c_ulong(0)
        self._p_extra = ctypes.pointer(self._extra)
        
        # Pre-build Down and Up INPUT structures
        self.inp_down = INPUT(INPUT_MOUSE, MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, self._p_extra))
        self.inp_up = INPUT(INPUT_MOUSE, MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, self._p_extra))
        
        # Cache references for SendInput (Zero allocation during loop)
        self._p_down = ctypes.byref(self.inp_down)
        self._p_up = ctypes.byref(self.inp_up)
        self._input_size = ctypes.sizeof(INPUT)

    def _precise_wait(self, duration):
        """
        Hybrid Spin-Lock Mechanism:
        Combines OS sleep for CPU efficiency and Spin-lock for microsecond precision.
        """
        if duration <= 0:
            return
        
        target = time.perf_counter() + duration
        
        # If duration is long enough, let the OS handle the bulk of it (~1.2ms margin)
        if duration > 0.0015:
            time.sleep(duration - 0.0012)
            
        # Spin-lock for the final stretch to bypass OS scheduler jitter
        while time.perf_counter() < target:
            pass

    def click_loop(self):
        # Set Process Priority to Real-time to prevent CPU starvation
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), REALTIME_PRIORITY_CLASS)
        # Force Windows system timer to 1ms resolution
        winmm.timeBeginPeriod(1)
        
        print(f"[LOG] Logic Thread Started. Target: {CLICK_INTERVAL_MS}ms")
        
        try:
            while self.running:
                if self.enabled:
                    # Disable GC to prevent "Stop-the-World" pauses
                    gc.disable()
                    
                    # Action: Mouse Down
                    user32.SendInput(1, self._p_down, self._input_size)
                    self._precise_wait(self.on_time)
                    
                    # Action: Mouse Up
                    user32.SendInput(1, self._p_up, self._input_size)
                    self._precise_wait(self.off_time)
                else:
                    # Enable GC and yield CPU when IDLE
                    gc.enable()
                    time.sleep(0.01)
                    gc.disable()
        finally:
            # Critical Clean-up: Restore system timer and GC
            winmm.timeEndPeriod(1)
            gc.enable()
            print("[LOG] Logic Thread Terminated Safely.")

    def on_click(self, x, y, button, pressed):
        if button == mouse.Button.right and pressed:
            self.enabled = not self.enabled
            status = "ACTIVE" if self.enabled else "IDLE"
            sys.stdout.write(f"\r[STATUS] Clicker is {status}   ")
            sys.stdout.flush()
            # Return False is not used here to keep the listener alive
            
    def run(self):
        # Start high-priority logic thread
        logic_thread = threading.Thread(target=self.click_loop, daemon=True)
        logic_thread.start()

        print("[SYSTEM] Clicker Ready. Right-click to toggle.")
        # Start Mouse Listener (Non-suppressed to allow cursor movement)
        with mouse.Listener(on_click=self.on_click, suppress=False) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                self.running = False
                print("\n[SYSTEM] Stopping...")

if __name__ == "__main__":
    app = UltimateExpertClicker()
    app.run()
