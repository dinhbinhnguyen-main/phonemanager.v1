# tests/dump_view.py
import os
import sys
import json
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional

# Thêm đường dẫn project vào sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

import uiautomator2 as u2
from adbutils import adb


def select_device(preferred_device: Optional[str] = None) -> Optional[str]:
    """Lấy thiết bị theo chỉ định hoặc cho phép chọn từ danh sách đang kết nối."""
    try:
        devices = [d.serial for d in adb.device_list()]
        if not devices:
            return None
        
        if preferred_device:
            if preferred_device in devices:
                return preferred_device
            else:
                print(f"⚠️ Thiết bị '{preferred_device}' không có trong danh sách kết nối.")
                print(f"📋 Các thiết bị hiện có: {devices}")
                return preferred_device

        if len(devices) == 1:
            return devices[0]

        print("\n📱 PHÁT HIỆN NHIỀU THIẾT BỊ ĐANG KẾT NỐI:")
        for idx, serial in enumerate(devices, start=1):
            print(f"   [{idx}] {serial}")
        
        # Nếu đang chạy không tương tác (hoặc nhập từ terminal)
        try:
            choice = input(f"👉 Chọn thiết bị (1-{len(devices)}, mặc định 1): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(devices):
                return devices[int(choice) - 1]
        except Exception:
            pass
            
        return devices[0]
    except Exception as e:
        print(f"⚠️ Lỗi khi đọc danh sách ADB: {e}")
    return None


def parse_hierarchy_node(node: ET.Element, depth: int = 0) -> List[Dict[str, Any]]:
    """Phân tích cây XML node thành danh sách element chi tiết."""
    elements = []
    
    attrib = node.attrib
    class_name = attrib.get("class", "")
    package = attrib.get("package", "")
    
    resource_id = attrib.get("resource-id", "")
    text = attrib.get("text", "")
    desc = attrib.get("content-desc", "")
    clickable = attrib.get("clickable", "false") == "true"
    enabled = attrib.get("enabled", "true") == "true"
    checked = attrib.get("checked", "false") == "true"
    scrollable = attrib.get("scrollable", "false") == "true"
    bounds = attrib.get("bounds", "")
    
    # Giữ các node có ý nghĩa tương tác hoặc chứa nội dung
    has_info = bool(text or desc or resource_id or (clickable and class_name not in ["android.view.View", "android.widget.FrameLayout"]))
    
    if has_info:
        short_class = class_name.split(".")[-1] if class_name else ""
        
        # Gợi ý code uiautomator2 để tương tác nhanh
        u2_code = ""
        if resource_id:
            u2_code = f'd(resourceId="{resource_id}")'
        elif text and desc:
            u2_code = f'd(text="{text}")'
        elif text:
            u2_code = f'd(text="{text}")'
        elif desc:
            u2_code = f'd(description="{desc}")'
        elif short_class:
            u2_code = f'd(className="{class_name}")'

        elements.append({
            "class": class_name,
            "short_class": short_class,
            "resource_id": resource_id,
            "text": text,
            "content_desc": desc,
            "clickable": clickable,
            "enabled": enabled,
            "checked": checked,
            "scrollable": scrollable,
            "bounds": bounds,
            "suggested_selector": u2_code
        })
        
    for child in node:
        elements.extend(parse_hierarchy_node(child, depth + 1))
        
    return elements


def dump_current_screen(device_id: str, take_screenshot: bool = True, output_dir_name: str = "dumps"):
    # Tạo thư mục lưu kết quả chuyên biệt: tests/dumps/
    output_dir = Path(__file__).resolve().parent / output_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=======================================================")
    print(f"📱 ĐANG PHÂN TÍCH GIAO DIỆN THIẾT BỊ: {device_id}")
    print(f"📂 Thư mục lưu kết quả: {output_dir}")
    print(f"=======================================================\n")
    
    try:
        d = u2.connect(device_id)
        current_app = d.app_current()
        print(f"📦 Ứng dụng hiện tại: {current_app.get('package')} ({current_app.get('activity')})")
        
        # 1. Dump XML Hierarchy
        xml_dump = d.dump_hierarchy()
        
        xml_file = output_dir / "dumped_view.xml"
        json_file = output_dir / "dumped_view.json"
        
        with open(xml_file, "w", encoding="utf-8") as f:
            f.write(xml_dump)
        print(f"💾 Đã lưu file XML gốc: {xml_file}")
        
        # 2. Parse XML thành danh sách phần tử
        root = ET.fromstring(xml_dump)
        elements = parse_hierarchy_node(root)
        
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "device_id": device_id,
                "current_app": current_app,
                "total_elements": len(elements),
                "elements": elements
            }, f, ensure_ascii=False, indent=2)
        print(f"💾 Đã lưu file JSON chi tiết: {json_file}")

        # 3. Chụp ảnh màn hình (nếu được yêu cầu)
        if take_screenshot:
            png_file = output_dir / "dumped_screen.png"
            d.screenshot(str(png_file))
            print(f"📸 Đã lưu ảnh chụp màn hình: {png_file}")

        # 4. In bảng danh sách các phần tử tương tác quan trọng lên Terminal
        print("\n" + "=" * 110)
        print(f"{'STT':<4} | {'LOẠI WIDGET':<22} | {'TEXT / CONTENT-DESC':<40} | {'RESOURCE-ID':<25} | {'CLICK':<5}")
        print("=" * 110)
        
        for idx, el in enumerate(elements, start=1):
            widget = el['short_class']
            content = el['text'] or el['content_desc'] or ""
            if len(content) > 38:
                content = content[:35] + "..."
                
            res_id = el['resource_id']
            if len(res_id) > 23:
                res_id = "..." + res_id[-20:]
                
            clickable_str = "YES" if el['clickable'] else "NO"
            
            print(f"{idx:<4} | {widget:<22} | {content:<40} | {res_id:<25} | {clickable_str:<5}")

        print("=" * 110)
        print(f"\n🎉 Đã phân tích xong {len(elements)} phần tử trên thiết bị {device_id}!")
        print(f"📁 Toàn bộ file đã được lưu trong: {output_dir}/")
        print(f"   • JSON: {json_file}")
        print(f"   • XML : {xml_file}")
        if take_screenshot:
            print(f"   • Ảnh : {png_file}")

    except Exception as e:
        print(f"❌ Xảy ra lỗi khi dump màn hình: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tool dump UI Hierarchy từ màn hình điện thoại thực tế")
    parser.add_argument("--device", type=str, default=None, help="ADB Serial của thiết bị")
    parser.add_argument("--dir", type=str, default="dumps", help="Tên thư mục lưu kết quả bên trong tests/ (mặc định: dumps)")
    parser.add_argument("--no-photo", action="store_true", help="Không chụp ảnh màn hình")
    
    args = parser.parse_args()
    
    target_device = select_device(args.device)
    if not target_device:
        print("❌ Không tìm thấy thiết bị Android nào đang kết nối qua ADB.")
        sys.exit(1)
        
    dump_current_screen(target_device, take_screenshot=not args.no_photo, output_dir_name=args.dir)
