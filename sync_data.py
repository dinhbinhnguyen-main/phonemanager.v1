import os
import sqlite3
import getpass
import paramiko
from scp import SCPClient, SCPException
from tqdm import tqdm

# ================= CẤU HÌNH =================
MAC_IP = '192.168.1.11'
MAC_USER = 'dinhbinhnguyen' 

MAC_DB_PATH = '/Users/dinhbinhnguyen/Dev/my-manager.v1/bin/database.db'
MAC_IMAGES_BASE_PATH = '/Volumes/KINGSTON/Ext_dev/python/my-manager.v1.repositories/images'

WIN_DB_DIR = r'C:\Users\dinhb\Desktop\repositories\db'
WIN_DB_PATH = os.path.join(WIN_DB_DIR, 'database.db')
WIN_IMAGES_BASE_PATH = r'C:\Users\dinhb\Desktop\repositories\images_products'
# ============================================

def create_ssh_client(ip, username):
    """Thiết lập kết nối SSH một lần duy nhất"""
    print(f"\n--- Đang kết nối SSH tới {username}@{ip} ---")
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(ip, username=username, timeout=10)
        print("=> Kết nối thành công (Sử dụng SSH Key).\n")
    except paramiko.ssh_exception.AuthenticationException:
        print("=> Không tìm thấy SSH Key. Vui lòng nhập mật khẩu:")
        password = getpass.getpass(f"Mật khẩu cho {username}@{ip}: ")
        ssh.connect(ip, username=username, password=password, timeout=10)
        print("=> Kết nối thành công (Sử dụng Mật khẩu).\n")
    
    return ssh

# Hàm callback để vẽ thanh loading theo dung lượng file tải về (dành cho Database)
def scp_progress():
    pbar = None
    def update_progress(filename, size, sent):
        nonlocal pbar
        if pbar is None:
            # Khởi tạo thanh loading khi bắt đầu tải file
            desc = f"Tải {filename.decode('utf-8')}" if isinstance(filename, bytes) else f"Tải {filename}"
            pbar = tqdm(total=size, unit='B', unit_scale=True, desc=desc, leave=False)
        
        # Cập nhật tiến trình
        pbar.update(sent - pbar.n)
        
        # Đóng thanh loading khi tải xong
        if sent == size:
            pbar.close()
            pbar = None
    return update_progress

def main():
    os.makedirs(WIN_DB_DIR, exist_ok=True)
    os.makedirs(WIN_IMAGES_BASE_PATH, exist_ok=True)

    try:
        ssh = create_ssh_client(MAC_IP, MAC_USER)
    except Exception as e:
        print(f"Không thể kết nối tới Mac: {e}")
        return

    # Gắn hàm scp_progress vào SCPClient để theo dõi dung lượng tải
    with SCPClient(ssh.get_transport(), progress=scp_progress()) as scp:
        
        # 1. Kéo Database
        print("--- BƯỚC 1: Kéo Database từ Mac ---")
        try:
            scp.get(MAC_DB_PATH, WIN_DB_PATH)
            print("=> Kéo Database hoàn tất.\n")
        except Exception as e:
            print(f"Lỗi khi kéo Database: {e}")
            ssh.close()
            return

        # 2. Đọc Database & Phân loại
        print("--- BƯỚC 2: Phân tích dữ liệu ---")
        conn = sqlite3.connect(WIN_DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT id FROM real_estate_products WHERE status = 'selling'")
            products = cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Lỗi truy vấn SQL: {e}")
            conn.close()
            ssh.close()
            return
        
        conn.close()

        if not products:
            print("Không có sản phẩm nào đang bán (status = 'selling').")
            ssh.close()
            return

        # Logic kiểm tra sự tồn tại của thư mục
        products_skipped = []
        products_to_sync = []

        # Dùng tqdm để hiển thị tiến trình đang kiểm tra thư mục (chạy rất nhanh)
        for row in tqdm(products, desc="Kiểm tra trạng thái", unit="sp"):
            product_id = str(row[0])
            win_img_dir = os.path.join(WIN_IMAGES_BASE_PATH, product_id)
            
            if os.path.exists(win_img_dir):
                products_skipped.append(product_id)
            else:
                products_to_sync.append(product_id)

        # In log thống kê
        print("\n[BẢNG THỐNG KÊ]")
        print(f"  * Tổng số sản phẩm đang bán: {len(products)}")
        print(f"  * Đã có sẵn (bỏ qua):        {len(products_skipped)}")
        print(f"  * Cần đồng bộ hình ảnh:      {len(products_to_sync)}\n")

        if not products_to_sync:
            print("=> Tất cả sản phẩm đã được đồng bộ. Kết thúc chương trình.")
            ssh.close()
            return

        # 3. Đồng bộ Hình ảnh
        print("--- BƯỚC 3: Bắt đầu đồng bộ hình ảnh ---")
        
        # Dùng tqdm bọc mảng cần đồng bộ để làm thanh loading đếm tổng số sản phẩm
        for product_id in tqdm(products_to_sync, desc="Đang đồng bộ", unit="sp"):
            mac_img_source = f"{MAC_IMAGES_BASE_PATH}/{product_id}"
            try:
                # Kéo toàn bộ folder ảnh của product_id về
                scp.get(mac_img_source, WIN_IMAGES_BASE_PATH, recursive=True)
            except SCPException:
                # Nếu muốn terminal gọn gàng, dùng tqdm.write thay vì print để không phá vỡ thanh loading
                tqdm.write(f"[Cảnh báo] LỖI ID {product_id}: Không tìm thấy thư mục trên Mac hoặc lỗi quyền truy cập.")
            except Exception as e:
                tqdm.write(f"[Lỗi] KHÔNG XÁC ĐỊNH ở ID {product_id}: {e}")

    ssh.close()
    print("\n--- HOÀN TẤT ĐỒNG BỘ ---")

if __name__ == "__main__":
    main()