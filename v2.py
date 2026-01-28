import threading
import time
import ctypes
import gc
import os
from pynput import mouse

# --- Configuration Area ---
CLICK_INTERVAL_MS = 44  # 신호 주입 주기 (ms)
# --------------------------

# Win32 API Constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0
REALTIME_PRIORITY_CLASS = 0x00000100

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
winmm = ctypes.windll.winmm

class UltraHighPerformanceHold:
    def __init__(self):
        self.enabled = False
        self.running = True
        self.interval_sec = CLICK_INTERVAL_MS / 1000.0
        
        # [Option 3] 메모리 고정: 구조체 상주 및 포인터 사전 계산
        self._extra = ctypes.c_ulong(0)
        self._p_extra = ctypes.pointer(self._extra)
        
        self.inp_down = INPUT(INPUT_MOUSE, MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, self._p_extra))
        self.inp_up = INPUT(INPUT_MOUSE, MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, self._p_extra))
        
        # 포인터 주소 고정 (Byref 오버헤드 제거)
        self._p_down = ctypes.byref(self.inp_down)
        self._p_up = ctypes.byref(self.inp_up)
        self._input_size = ctypes.sizeof(INPUT)

    def set_realtime(self):
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), REALTIME_PRIORITY_CLASS)

    def click_logic(self):
        self.set_realtime()
        winmm.timeBeginPeriod(1)
        gc.disable()
        
        try:
            while self.running:
                if self.enabled:
                    # [Down Only] 신호 주입
                    user32.SendInput(1, self._p_down, self._input_size)
                    
                    # [Option 2] Hybrid Busy-Wait
                    target = time.perf_counter() + self.interval_sec
                    
                    # 1.5ms 전까지는 OS에 제어권을 넘겨 CPU 과부하 완화 (Precision Sleep)
                    sleep_time = self.interval_sec - 0.0015
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    
                    # 2. 남은 시간은 Spin-lock으로 마이크로초 단위 정밀 대기
                    while time.perf_counter() < target:
                        pass
                else:
                    # 비활성 시 가상 Up 신호로 상태 해제 및 GC 허용
                    user32.SendInput(1, self._p_up, self._input_size)
                    gc.enable()
                    time.sleep(0.01)
                    gc.disable()
        finally:
            winmm.timeEndPeriod(1)
            gc.enable()

    def on_click(self, x, y, button, pressed):
        if button == mouse.Button.right and pressed:
            self.enabled = not self.enabled
            return False

    def run(self):
        threading.Thread(target=self.click_logic, daemon=True).start()
        while self.running:
            with mouse.Listener(on_click=self.on_click, suppress=False) as listener:
                listener.join()

if __name__ == "__main__":
    app = UltraHighPerformanceHold()
    try:
        app.run()
    except KeyboardInterrupt:
        app.running = False