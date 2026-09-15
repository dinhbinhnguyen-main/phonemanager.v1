# src/automation/facebook/actions/scroll_feed.py
import sys
import traceback
import random
from typing import Optional, TYPE_CHECKING
from src.entities import Job
from src.automation.core.base_automator import BaseAutomator
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.controllers._manager_controllers import ControllerManager
    from PySide6.QtCore import SignalInstance

def run_scroll_feed(device_id: str, job: Job, logger_signal: "SignalInstance", controllers: Optional["ControllerManager"] = None):
    """
    Simulates human-like scrolling through Facebook News Feed.
    """
    bot = BaseAutomator(device_id, logger_signal)
    
    try:
        max_swipes = job.parameters.get("max_swipes", 30)
        min_delay = job.parameters.get("min_delay", 3.0)
        max_delay = job.parameters.get("max_delay", 8.0)
        
        bot.log("🔄 Launching Facebook and navigating to News Feed...")
        bot.launch_app("com.facebook.katana", "fb://feed")
        bot.smart_sleep(6)
        
        # Check login status
        login_keywords = ["Log In", "Log in", "Đăng nhập", "Create new account", "Tạo tài khoản mới"]
        is_logged_out = False
        for kw in login_keywords:
            btn = bot.get_button_by_text(kw, timeout=1)
            if btn.exists:
                is_logged_out = True
                break
        if is_logged_out:
            bot.log("⚠️ Cannot scroll Feed: Device is not logged in or at login screen.")
            return

        bot.log(f"🚀 Starting News Feed scroll ({max_swipes} planned swipes)...")
        
        swipes_performed = 0
        while swipes_performed < max_swipes:
            # Ensure Facebook app stays in foreground
            try:
                curr_app = bot.d.app_current()
                if curr_app.get("package") != "com.facebook.katana":
                    bot.log("🔄 Facebook app was minimized or closed, reopening...")
                    bot.launch_app("com.facebook.katana", "fb://feed")
                    bot.smart_sleep(5)
            except Exception as app_err:
                logger.warning(f"Could not check app state: {app_err}")
            
            # Decide scroll behavior
            roll = random.random()
            if roll < 0.75:
                scale = random.uniform(0.4, 0.7)
                bot.log(f"[{swipes_performed + 1}/{max_swipes}] 📜 Scrolling up for new posts (Scale: {scale:.2f})...")
                bot.swipe_up(scale=scale)
            elif roll < 0.90:
                scale = random.uniform(0.25, 0.45)
                bot.log(f"[{swipes_performed + 1}/{max_swipes}] 📜 Scrolling down to re-read previous post (Scale: {scale:.2f})...")
                bot.swipe_down(scale=scale)
            else:
                scale = random.uniform(0.75, 0.9)
                bot.log(f"[{swipes_performed + 1}/{max_swipes}] ⚡ Fast swipe across long post (Scale: {scale:.2f})...")
                bot.swipe_up(scale=scale)

            swipes_performed += 1

            # Pause to simulate reading
            sleep_time = random.uniform(min_delay, max_delay)
            bot.log(f"⏳ Reading post for {sleep_time:.1f}s...")
            bot.smart_sleep(sleep_time)

            # --- RANDOM USER INTERACTIONS ---
            
            # Interaction 1: Click "See more" if found (25% chance)
            if random.random() < 0.25:
                try:
                    see_more_xpaths = [
                        "//*[contains(@text, 'See more') or contains(@text, 'Xem thêm') or contains(@text, 'See More') or contains(@text, 'xem thêm')]",
                        "//*[contains(@description, 'See more') or contains(@description, 'Xem thêm') or contains(@description, 'See More') or contains(@description, 'xem thêm')]"
                    ]
                    for xpath in see_more_xpaths:
                        el = bot.d.xpath(xpath)
                        if el.exists:
                            bot.log("🔍 Clicking 'See more' to read full post...")
                            el.click()
                            bot.smart_sleep(random.uniform(2.0, 4.0))
                            break
                except Exception as e:
                    logger.debug(f"Could not click See more: {e}")

            # Interaction 2: Like / React to post (7% chance)
            if random.random() < 0.07:
                try:
                    like_xpaths = [
                        "//android.widget.Button[contains(@text, 'Like') or contains(@text, 'Thích')]",
                        "//android.widget.TextView[contains(@text, 'Like') or contains(@text, 'Thích')]",
                        "//android.view.ViewGroup[contains(@content-desc, 'Like button') or contains(@content-desc, 'Thích button') or @content-desc='Like' or @content-desc='Thích']"
                    ]
                    for xpath in like_xpaths:
                        el = bot.d.xpath(xpath)
                        if el.exists:
                            bot.log("❤️ Liking random post to increase engagement...")
                            el.click()
                            bot.smart_sleep(random.uniform(1.5, 3.0))
                            break
                except Exception as e:
                    logger.debug(f"Could not like post: {e}")

            # Interaction 3: Open comments (4% chance)
            if random.random() < 0.04:
                try:
                    comment_xpaths = [
                        "//android.widget.Button[contains(@text, 'Comment') or contains(@text, 'Bình luận')]",
                        "//android.widget.TextView[contains(@text, 'Comment') or contains(@text, 'Bình luận')]",
                        "//android.view.ViewGroup[contains(@content-desc, 'Comment') or contains(@content-desc, 'Bình luận')]"
                    ]
                    for xpath in comment_xpaths:
                        el = bot.d.xpath(xpath)
                        if el.exists:
                            bot.log("💬 Opening post comments...")
                            el.click()
                            bot.smart_sleep(random.uniform(4.0, 7.0))
                            if random.random() < 0.5:
                                bot.swipe_up(scale=0.3)
                                bot.smart_sleep(random.uniform(2.0, 4.0))
                            bot.log("↩️ Returning to News Feed...")
                            bot.d.press("back")
                            bot.smart_sleep(2)
                            break
                except Exception as e:
                    logger.debug(f"Could not open comments: {e}")

        bot.log("✔️ News Feed scroll task completed!")

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
        full_traceback = "".join(tb_details)
        
        logger.error(f"Error scrolling feed on device {device_id}:\n{full_traceback}")
        bot.log(f"❌ Error during Feed scroll: {e}")
        raise e
        
    finally:
        bot.teardown()
