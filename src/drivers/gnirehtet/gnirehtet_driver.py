import subprocess
import time
from src.utils.logger import logger
from src.utils.yaml_handler import settings
from src.drivers.adb.adb_controller import ADBController

class GnirehtetDriver:
    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self.adb_controller = ADBController(device_id)
        self.gnirehtet_proc = settings.repositories.gnirehtet_proc # type: ignore
        self.package_name = "com.genymobile.gnirehtet"

    def start(self, user_id: int) -> bool:
        logger.info(f"[{self.device_id}] Connecting USB tethering (Gnirehtet)...")
        try:
            # 1. Check and install base APK
            if not self.adb_controller.is_apk_installed(0, self.package_name):
                apk_path = self.gnirehtet_proc.replace(".exe", ".apk")
                self.adb_controller.install_new_apk(0, apk_path)
            
            # 2. Clone APK to User
            if user_id != 0:
                self.adb_controller.install_existed_apk(user_id, self.package_name)
            
            # 3. Grant permissions
            self._grant_vpn_permission(user_id)
            
            # 4. ⚡ Send "start" instead of "run" (Connect to shared Relay Server)
            cmd = [self.gnirehtet_proc, "start", self.device_id]
            subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            
            time.sleep(2) # Wait 2s for VPN to allocate IP
            return True
        except Exception as e:
            logger.error(f"[{self.device_id}] Gnirehtet connection error: {e}")
            return False
    
    def stop(self) -> bool:
        logger.info(f"[{self.device_id}] Disconnecting Gnirehtet...")
        try:
            cmd = [self.gnirehtet_proc, "stop", self.device_id]
            subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception as e:
            logger.error(f"[{self.device_id}] Gnirehtet disconnection error: {e}")
            return False
    
    def _grant_vpn_permission(self, user_id: int) -> None:
        try:
            cmd = f"su -c 'appops set --user {user_id} {self.package_name} ACTIVATE_VPN allow'"
            self.adb_controller._shell(cmd)
        except Exception as e:
            logger.warning(f"[{self.device_id}] Unable to grant VPN permission via AppOps: {e}")