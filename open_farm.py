import subprocess
import math
import time
import tkinter as tk

def get_monitor_resolution():
    """Lấy kích thước màn hình động bằng thư viện tkinter (có sẵn)"""
    root = tk.Tk()
    root.withdraw()  # Ẩn cửa sổ tk đi để không hiện popup rác chớp lên màn hình
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    root.destroy()   # Giải phóng bộ nhớ
    return width, height

def get_connected_devices():
    """Lấy danh sách các thiết bị đang ở trạng thái 'device'"""
    result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
    lines = result.stdout.strip().split('\n')[1:]
    devices = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1] == 'device':
            devices.append(parts[0])
    return devices

def get_device_aspect_ratio(serial):
    """Lấy tỷ lệ khung hình (width/height) của thiết bị qua adb. Mặc định tỷ lệ dọc 9/16 nếu lỗi."""
    try:
        result = subprocess.run(
            ['adb', '-s', serial, 'shell', 'wm', 'size'],
            capture_output=True,
            text=True,
            timeout=2
        )
        for line in result.stdout.splitlines():
            if 'Physical size' in line or 'Override size' in line:
                size_str = line.split(':')[-1].strip()
                w, h = map(int, size_str.split('x'))
                if w > 0 and h > 0:
                    return w / h
    except Exception:
        pass
    return 9 / 16

def calculate_grid(num_devices):
    """Tính lưới vuông nhất có thể"""
    if num_devices == 0:
        return 0, 0
    cols = math.ceil(math.sqrt(num_devices))
    rows = math.ceil(num_devices / cols)
    return rows, cols

def main():
    devices = get_connected_devices()
    num_devices = len(devices)

    if num_devices == 0:
        print("[!] Không có thiết bị nào sẵn sàng (đang cắm cáp và bật Debugging).")
        return

    # Lấy kích thước màn hình động
    monitor_width, monitor_height = get_monitor_resolution()
    
    # Lấy tỉ lệ khung hình của thiết bị đầu tiên để đồng bộ lưới
    aspect_ratio = get_device_aspect_ratio(devices[0])
    
    rows, cols = calculate_grid(num_devices)
    
    # Khoảng cách viền tối thiểu giữa các cửa sổ (pixels)
    gap = 2
    
    # 1. Tính kích thước tối đa cho phép của mỗi cửa sổ dựa theo số hàng/cột và gap
    max_w = (monitor_width - (cols - 1) * gap) // cols
    max_h = (monitor_height - (rows - 1) * gap) // rows
    
    # 2. Tính toán kích thước scrcpy thực tế để giữ nguyên tỉ lệ khung hình
    # Điện thoại dọc: ưu tiên chiều cao tối đa trước
    actual_h = max_h
    actual_w = int(actual_h * aspect_ratio)
    
    # Nếu chiều rộng vượt quá kích thước tối đa cho phép, tính ngược lại theo chiều rộng
    if actual_w > max_w:
        actual_w = max_w
        actual_h = int(actual_w / aspect_ratio)
        
    # 3. Tính toán kích thước của toàn bộ khối cửa sổ (gồm các khoảng gap ở giữa)
    total_block_w = cols * actual_w + (cols - 1) * gap
    total_block_h = rows * actual_h + (rows - 1) * gap
    
    # 4. Tính toán điểm bắt đầu để căn giữa toàn bộ khối cửa sổ trên màn hình PC
    start_x = (monitor_width - total_block_w) // 2
    start_y = (monitor_height - total_block_h) // 2
 
    print(f"[*] Độ phân giải PC hiện tại: {monitor_width}x{monitor_height}")
    print(f"[*] Tỉ lệ màn hình thiết bị: {aspect_ratio:.4f}")
    print(f"[*] Tìm thấy {num_devices} thiết bị. Phân bổ lưới: {rows} hàng x {cols} cột.")
    print(f"[*] Kích thước thực tế mỗi cửa sổ: {actual_w}px x {actual_h}px")
    print(f"[*] Kích thước toàn bộ khối: {total_block_w}px x {total_block_h}px (gap={gap}px)")
    print(f"[*] Căn giữa toàn khối tại: X_start={start_x}px, Y_start={start_y}px")
    print("-" * 50)
 
    processes = []
 
    for i, serial in enumerate(devices):
        row = i // cols
        col = i % cols
 
        # Định vị các cửa sổ sát nhau chỉ cách nhau khoảng gap
        x_pos = start_x + col * (actual_w + gap)
        y_pos = start_y + row * (actual_h + gap)

        cmd = [
            'scrcpy',
            '-s', serial,
            '--window-x', str(x_pos),
            '--window-y', str(y_pos),
            '--window-width', str(actual_w),
            '--window-height', str(actual_h),
            '--window-borderless',  # Ép sát viền
            '-b', '2M',
            '--max-fps', '30',
            '--turn-screen-off'
        ]

        print(f"-> Đang mở [Thiết bị {i+1}/{num_devices}] - ID: {serial}")
        
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(p)

    print("-" * 50)
    print("[*] Đã mở thành công toàn bộ thiết bị!")
    print("[!] ĐANG GIỮ TIẾN TRÌNH. NHẤN TỔ HỢP PHÍM [ CTRL + C ] ĐỂ TẮT TẤT CẢ.")

    try:
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[*] Đã nhận lệnh ngắt. Đang đóng toàn bộ các cửa sổ scrcpy...")
        for p in processes:
            p.terminate()
        
        for p in processes:
            p.wait()
            
        print("[*] Đã tắt sạch toàn bộ. Hẹn gặp lại!")

if __name__ == '__main__':
    main()