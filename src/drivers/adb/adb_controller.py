# src/drivers/adb/controller.py
import os
import re
from time import sleep
from datetime import datetime
from typing import List, Dict, Optional
from adbutils import adb
from adbutils.errors import AdbError
from src.constants import UserStatus
from src.entities import User
from src.drivers.adb.exceptions import ADBConnectionError, ADBCommandError, DeviceNotFoundError
from src.utils.yaml_handler import settings

DEFAULT_APP_PERMISSIONS = [
    "android.permission.CAMERA",
    "android.permission.RECORD_AUDIO",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
    "android.permission.READ_CONTACTS",
    "android.permission.ACCESS_NETWORK_STATE"
]

class ADBController:
    def __init__(self, device_id: str):
        self.device_id = device_id
        try:
            self.device = adb.device(device_id)
        except AdbError as e:
            raise ADBConnectionError(f"Failed to connect to device: {e}")
    
    def _shell(self, command: str) -> str:
        try:
            return self.device.shell(command)
        except AdbError as e:
            raise ADBCommandError(f"Failed to execute command: {e}")
    
    def get_screen_size(self) -> Dict[str, int]:
        output = self._shell("wm size")
        match = re.search(r"(\d+)x(\d+)", output)
        if match:
            return {"width": int(match.group(1)), "height": int(match.group(2))}
        else:
            raise ADBCommandError("Failed to parse screen size output")
    
    def get_users(self) -> List[Dict[str, str]]:
        output = self._shell("pm list users")
        pattern = re.compile(r"UserInfo\{(\d+):([^:]+):")
        users = []
        for line in output.splitlines():
            match = pattern.search(line)
            if match:
                is_running = "running" in line
                users.append({
                    "user_id": int(match.group(1)),
                    "user_name": "root" if match.group(2).lower() == "owner" else match.group(2),
                    "user_status": UserStatus.ACTIVE if is_running else UserStatus.INACTIVE
                })
        return users
    
    def check_root(self) -> bool:
        try:
            su_check = self._shell("su -c 'echo is_rooted'").strip()
            if "is_rooted" in su_check:
                return True
            return False
        except ADBCommandError:
            return False
    
    def create_user(self, username: str) -> Optional[User]:
        output = self._shell(f"pm create-user {username}")
        match = re.search(r"id\s+(\d+)", output)
        if match:
            return User(
                user_id=int(match.group(1)),
                user_name=username,
                user_status=UserStatus.INACTIVE
            )
        return None
    
    def get_current_user(self) -> int:
        """Gets the ID of the user currently displayed on the screen"""
        try:
            output = self._shell("am get-current-user").strip()
            return int(output)
        except (ADBCommandError, ValueError):
            return 0
    
    def switch_user(self, user_id: int) -> bool:
        """
        Switches the User, stops all other background users (except root 0), 
        and performs a deep RAM cleanup.
        """
        try:
            current_user = self.get_current_user()
            if current_user != user_id:                
                output = self._shell(f"am switch-user {user_id}")
                if "error" in output.lower():
                    return False
                success = False
                for _ in range(15):
                    sleep(1)
                    current_user = self.get_current_user()
                    if int(current_user) == int(user_id):
                        success = True
                        break
                if not success:
                    return False
            all_users = self.get_users()

            for u in all_users:
                uid = int(u["user_id"])
                if uid != 0 and uid != user_id:
                    self._shell(f"am stop-user -f {uid}")
            self._shell("am kill-all") 
            self._shell("su -c 'pm trim-caches 999G'") 
            self._shell("su -c 'echo 3 > /proc/sys/vm/drop_caches'")

            return True
        except ADBCommandError:
            return False
        
    def remove_user(self, user_id: int) -> bool:
        try:
            self.switch_user(0)
            sleep(3)
            self._shell(f"pm remove-user {user_id}")
            return True
        except ADBCommandError:
            return False

    def set_max_user(self, max_users: int = 10) -> bool:
        """
        Configures the maximum number of user profiles allowed on the device.

        This method modifies the system property 'fw.max_users'. It requires 
        Root privileges to execute the 'setprop' command. This is essential 
        for environments managing multiple Android user profiles for automation.

        Args:
            max_users (int): The maximum limit of user profiles to allow. 
                             Defaults to 10.

        Returns:
            bool: True if the property was set successfully, False if the 
                  command failed or permissions were denied.
        """
        try:
            script = f"setprop fw.max_users {max_users}"
            out = self._shell(f"su -c '{script}'")
            
            if any(err in out.lower() for err in ["error", "denied", "not found"]):
                from src.utils.logger import logger
                logger.error(f"[{self.device_id}] Failed to set max users: {out}")
                return False
                
            return True
        except ADBCommandError:
            return False

    def install_app_for_users(self, app_name: str, user_ids: List[int]) -> bool:
        apk_name = ""
        apk_path =""
        if "tiktok" in app_name.lower():
            apk_name = "com.zhiliaoapp.musically"
            apk_path = settings.repositories.tiktok_path # type: ignore
        elif "facebook" in app_name.lower():
            apk_name = "com.facebook.katana"
            apk_path = settings.repositories.facebook_path # type: ignore
        else:
            return False
        
            
        if not self.is_apk_installed(0, apk_name):
            self.install_new_apk(0, apk_path)
        for user_id in user_ids:
            self.install_existed_apk(user_id, apk_name)
        return True

    def is_apk_installed(self, user_id: int, package_name: str) -> bool:
        output = self._shell(f"pm list packages --user {user_id} {package_name}")
        return package_name in output
    
    def install_new_apk(self, user_id: int, apk_path: str) -> bool: 
        """
        Pushes an APK file from the host PC to the mobile device and installs it 
        for a specific Android user profile.

        The process involves three stages: 
        1. Synchronizing the local file to the device's temporary directory.
        2. Executing the Package Manager (pm) install command with the --user flag.
        3. Cleaning up the temporary APK file from the device to save storage.

        Args:
            user_id (int): The target Android user profile ID (e.g., 0 for Owner, 10+ for others).
            apk_path (str): The absolute local path to the APK file on the PC.

        Returns:
            bool: True if the installation was successful, False otherwise.
        """
        import os
        from src.utils.logger import logger
        
        if not os.path.exists(apk_path):
            logger.error(f"[{self.device_id}] APK file not found on PC: {apk_path}")
            return False
            
        try:
            remote_tmp = "/data/local/tmp/temp_install.apk"
            self.device.sync.push(apk_path, remote_tmp)
            
            output = self._shell(f"pm install -r --user {user_id} {remote_tmp}")
            
            self._shell(f"rm {remote_tmp}")
            
            return "success" in output.lower()
            
        except Exception as e:
            logger.error(f"[{self.device_id}] Error pushing or installing APK: {e}")
            return False
    
    def install_existed_apk(self, user_id: int, package_name: str) -> bool: 
        output = self._shell(f"pm install-existing --user {user_id} {package_name}")
        return "installed" in output.lower()

    def uninstall_apk(self, user_id: int, package_name: str) -> bool: 
        output = self._shell(f"pm uninstall --user {user_id} {package_name}")
        return "success" in output.lower()
    
    def block_app_notifications(self, user_id: int, package_name: str) -> bool:
        """
        Disables all visual and system notifications for a specific application.

        This method uses a two-layered approach to ensure compatibility across 
        different Android versions:
        1. Utilizes 'appops' to set the POST_NOTIFICATION operation to 'ignore'. 
           This is effective for the majority of Android versions.
        2. Attempts to revoke the 'POST_NOTIFICATIONS' permission specifically 
           introduced in Android 13 (API 33).

        Args:
            user_id (int): The target Android user profile ID.
            package_name (str): The unique package identifier (e.g., 'com.facebook.katana').

        Returns:
            bool: True if the primary restriction (appops) was applied successfully, 
                  False if an error or exception occurred.
        """
        success = True
        
        appops_cmd = f"appops set --user {user_id} {package_name} POST_NOTIFICATION ignore"
        output_appops = self._shell(appops_cmd)
        
        if "error" in output_appops.lower() or "exception" in output_appops.lower():
            success = False

        revoke_cmd = f"pm revoke --user {user_id} {package_name} android.permission.POST_NOTIFICATIONS"
        self._shell(revoke_cmd) 

        return success

    def disable_keyboard(self, user_id: Optional[int] = None) -> bool:
        """
        Completely disables the soft keyboard for single/multi-user space on Android.
        1. Suppresses on-screen virtual keyboard popup via secure settings (show_ime_with_hard_keyboard 0).
        2. Ensures FastInputIME / AdbKeyboard package is installed and enabled for target user.
        3. Sets default IME to FastInputIME.
        """
        try:
            target_user = user_id if user_id is not None else self.get_current_user()
            
            # 1. Disable on-screen virtual keyboard popup globally & for user
            self._shell(f"settings put secure --user {target_user} show_ime_with_hard_keyboard 0")
            self._shell("settings put secure show_ime_with_hard_keyboard 0")
            
            # 2. Ensure uiautomator package exists in secondary user profile
            if target_user != 0:
                self._shell(f"pm install-existing --user {target_user} com.github.uiautomator")
                self._shell(f"pm install-existing --user {target_user} com.github.uiautomator.test")
                self._shell(f"pm install-existing --user {target_user} com.android.adbkeyboard")
            
            # 3. Detect available fast input IME
            ime_list = self._shell(f"ime list -s --user {target_user}")
            if not ime_list or "error" in ime_list.lower() or "unknown" in ime_list.lower():
                ime_list = self._shell("ime list -s -a")
                
            fast_ime = None
            for candidate in [
                "com.github.uiautomator/.FastInputIME",
                "com.github.uiautomator.test/com.github.uiautomator.fastinput.FastInputIME",
                "com.android.adbkeyboard/.AdbIME"
            ]:
                if candidate in ime_list or candidate.split("/")[0] in ime_list:
                    fast_ime = candidate
                    break
                    
            if not fast_ime:
                fast_ime = "com.github.uiautomator/.FastInputIME"
                
            # 4. Enable and set IME
            self._shell(f"ime enable --user {target_user} {fast_ime}")
            self._shell(f"ime set --user {target_user} {fast_ime}")
            self._shell(f"settings put --user {target_user} secure default_input_method {fast_ime}")
            
            if target_user != 0:
                self._shell(f"ime enable --user 0 {fast_ime}")
                self._shell(f"ime set --user 0 {fast_ime}")
                self._shell(f"settings put --user 0 secure default_input_method {fast_ime}")
                
            return True
        except Exception as e:
            from src.utils.logger import logger
            logger.error(f"[{self.device_id}] Error disabling keyboard for user {user_id}: {e}")
            return False

    def enable_keyboard(self, user_id: Optional[int] = None) -> bool:
        """
        Restores stock soft keyboard.
        """
        try:
            target_user = user_id if user_id is not None else self.get_current_user()
            self._shell(f"settings put secure --user {target_user} show_ime_with_hard_keyboard 1")
            self._shell("settings put secure show_ime_with_hard_keyboard 1")
            
            ime_list = self._shell(f"ime list -s --user {target_user}")
            if not ime_list or "error" in ime_list.lower():
                ime_list = self._shell("ime list -s -a")
                
            stock_ime = None
            for line in ime_list.splitlines():
                line = line.strip()
                if not line or "uiautomator" in line or "adbkeyboard" in line:
                    continue
                if any(k in line for k in ["latin", "gboard", "honeyboard", "samsung", "inputmethod", "pinyin", "touchtype"]):
                    stock_ime = line
                    break
                    
            if stock_ime:
                self._shell(f"ime enable --user {target_user} {stock_ime}")
                self._shell(f"ime set --user {target_user} {stock_ime}")
                self._shell(f"settings put --user {target_user} secure default_input_method {stock_ime}")
            return True
        except Exception as e:
            from src.utils.logger import logger
            logger.error(f"[{self.device_id}] Error restoring keyboard for user {user_id}: {e}")
            return False

    def is_keyboard_shown(self) -> bool:
        """Checks if soft keyboard is currently visible on screen."""
        try:
            dumpsys = self._shell("dumpsys input_method")
            if "mInputShown=true" in dumpsys or "mIsInputViewShown=true" in dumpsys:
                return True
            return False
        except Exception:
            return False

    def hide_keyboard(self) -> bool:
        """Actively dismisses soft keyboard if currently open."""
        try:
            if self.is_keyboard_shown():
                self._shell("input keyevent 111")  # KEYCODE_ESCAPE
                sleep(0.3)
                return True
            return False
        except Exception:
            return False

    def grand_apk_permission(self, user_id: int, package_name: str, permissions: List[str] = DEFAULT_APP_PERMISSIONS) -> bool:
        success = True
        self.block_app_notifications(user_id, package_name)
        for perm in permissions:
            output = self._shell(f"pm grant --user {user_id} {package_name} {perm}")
            if "error" in output.lower():
                success = False
        return success

    def get_public_ip(self) -> str:
        return self._shell("curl ifconfig.me")

    def disable_internet(self) -> bool:
        """
        Chặn toàn bộ mạng (IPv4). An toàn không dính lỗi dội rule.
        """
        try:
            # Gộp thành 1 chuỗi script, dùng 2>/dev/null để giấu đi các lỗi lặt vặt (như chain đã tồn tại)
            script = (
                "iptables -N FARM_BLOCK 2>/dev/null; "
                "iptables -F FARM_BLOCK; "
                "iptables -A FARM_BLOCK -p tcp --sport 5555 -j RETURN; "
                "iptables -A FARM_BLOCK -j DROP; "
                "iptables -D OUTPUT -j FARM_BLOCK 2>/dev/null; " # Xóa cũ
                "iptables -D OUTPUT -j FARM_BLOCK 2>/dev/null; " # Xóa dự phòng
                "iptables -I OUTPUT 1 -j FARM_BLOCK"            # Chèn mới vào Top 1
            )
            out = self._shell(f"su -c \"{script}\"")
            
            # Catch actual error in output
            if "error" in out.lower() or "denied" in out.lower():
                from src.utils.logger import logger
                logger.error(f"[{self.device_id}] Error blocking internet: {out}")
                return False
                
            return True
        except ADBCommandError:
            return False

    def enable_internet(self) -> bool:
        """
        Unblocks internet access by flushing iptables chain.
        """
        try:
            script = (
                "iptables -F FARM_BLOCK; "
                "iptables -D OUTPUT -j FARM_BLOCK 2>/dev/null; "
                "iptables -D OUTPUT -j FARM_BLOCK 2>/dev/null; "
                "iptables -D OUTPUT -j FARM_BLOCK 2>/dev/null; "
                "iptables -X FARM_BLOCK 2>/dev/null"
            )
            out = self._shell(f"su -c \"{script}\"")
            
            if "error" in out.lower() or "denied" in out.lower():
                from src.utils.logger import logger
                logger.error(f"[{self.device_id}] Error enabling internet: {out}")
                return False
                
            return True
        except ADBCommandError:
            return False

    def disable_wifi(self) -> bool:
        try:
            self._shell("svc wifi disable")
            return True
        except ADBCommandError:
            return False

    def enanble_wifi(self) -> bool:
        try:
            self._shell("svc wifi enable")
            return True
        except ADBCommandError:
            return False

    def take_screenshot(self, output_dir: str) -> Optional[str]:
        """
        Captures a device screenshot and transfers it directly to the computer.
        
        This method bypasses temporary storage on the mobile device by using 
        adbutils to read the framebuffer directly, ensuring high performance.
        
        Args:
            output_dir (str): The local directory path where the image will be saved.
            
        Returns:
            Optional[str]: The absolute local file path of the saved screenshot, 
                          or None if the capture fails.
        """
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_device_id = self.device_id.replace(":", "_").replace(".", "_")
            file_name = f"{safe_device_id}_{timestamp}.png"
            local_path = os.path.join(output_dir, file_name)

            image = self.device.screenshot()
            
            image.save(local_path)

            return local_path
        except Exception as e:
            from src.utils.logger import logger
            logger.error(f"[{self.device_id}] Error capturing direct screenshot: {e}")
            return None

    def clear_all_users_photos(self) -> List[str]:
        """
        Switches to each user profile on the device and clears all photos/media.
        Returns a list of status messages/logs.
        """
        logs = []
        try:
            # 1. Get current user
            original_user = self.get_current_user()
            logs.append(f"Original user identified: ID {original_user}")
            
            # 2. Get list of all users from the device
            users = self.get_users()
            if not users:
                logs.append("No user profiles detected.")
                return logs
                
            logs.append(f"Found {len(users)} user profile(s) on device.")
            
            for u in users:
                user_id = u["user_id"]
                user_name = u["user_name"]
                
                logs.append(f"Switching to user profile: {user_name} (ID: {user_id})")
                success = self.switch_user(user_id)
                if not success:
                    logs.append(f"❌ Failed to switch to user {user_name} (ID: {user_id}). Skipping photo deletion.")
                    continue
                
                # Give Android a short sleep to handle the switch
                sleep(2)
                
                logs.append(f"🗑️ Clearing photos for user profile {user_name}...")
                
                for folder in ["DCIM", "Pictures"]:
                    # Virtual paths
                    self._shell(f"rm -rf /storage/emulated/{user_id}/{folder}/*")
                    # Physical paths (via root/su)
                    self._shell(f"su -c 'rm -rf /data/media/{user_id}/{folder}/*'")
                    self._shell(f"su -c 'rm -rf /storage/emulated/{user_id}/{folder}/*'")
                    
                    # Update MediaStore so the gallery doesn't show ghost thumbnails
                    self._shell(f"am broadcast --user {user_id} -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///storage/emulated/{user_id}/{folder}")
                
                # Full scan of external volume
                self._shell("media scan-volume external")
                logs.append(f"✔️ Finished clearing photos for user {user_name}.")
                
            # 3. Restore the original user profile
            if original_user is not None:
                logs.append(f"Restoring screen to original user profile (ID: {original_user})...")
                self.switch_user(original_user)
                
            logs.append("🎉 Photo clearing process completed successfully.")
        except Exception as e:
            logs.append(f"❌ Error during photo clearing: {str(e)}")
            
        return logs

    def scan_media_file(self, virtual_path: str, user_id: int = 0):
        """
        Triggers Android MediaStore to scan and index a media file for Gallery apps.
        Uses both modern ContentProvider scan (Android 10+) and legacy Broadcast (Android 4-9).
        """
        try:
            # 1. Modern method for Android 10+ (API 29+)
            self._shell(
                f'content call --user {user_id} --uri content://media/external/file '
                f'--method scan_file --extra path:s:"{virtual_path}"'
            )
        except Exception:
            pass

        try:
            # 2. Legacy broadcast for Android 4-9
            self._shell(
                f'am broadcast --user {user_id} '
                f'-a android.intent.action.MEDIA_SCANNER_SCAN_FILE '
                f'-d "file://{virtual_path}"'
            )
        except Exception:
            pass