# src/automation/facebook/actions/post_group.py
import re
import sys
import traceback
from random import randint
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from src.entities import Job
from src.automation.core.base_automator import BaseAutomator
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.controllers._manager_controllers import ControllerManager
    from PySide6.QtCore import SignalInstance


def _extract_group_id(raw_input: str) -> str:
    """Extracts group ID from URL or returns clean string."""
    raw_input = str(raw_input).strip()
    match = re.search(r'groups/([^/?]+)', raw_input)
    if match:
        return match.group(1)
    return raw_input


def run_post_group(
    device_id: str, 
    job: Job, 
    logger_signal: "SignalInstance", 
    controllers: Optional["ControllerManager"] = None
):
    """
    Automates posting to a Facebook group, dynamically handling:
    1. Discussion groups (Nhóm trao đổi/thảo luận): Text + Images compose.
    2. Buy and Sell groups (Nhóm mua bán):
       - If post_mode == 'sell' or 'auto': Uses Buy & Sell listing format (Marketplace-style form).
       - If post_mode == 'discussion': Switches to 'Thảo luận' tab and posts discussion-style.
    """
    bot = BaseAutomator(device_id, logger_signal)
    
    if controllers:
        user_info = controllers.user_controller.get_by_id(job.user_uuid)
        user_id = user_info.user_id if user_info else 0
    else:
        user_id = 0

    try:
        raw_uid = job.parameters.get("group_uid", "")
        if not raw_uid:
            raise ValueError("Group UID is missing in job parameters.")

        group_id = _extract_group_id(raw_uid)
        post_mode = str(job.parameters.get("post_mode", "auto")).lower()
        title = job.parameters.get("title", "")
        description = job.parameters.get("description", "")
        image_paths = job.parameters.get("image_paths", [])

        # 1. Media deployment to device user storage
        if image_paths:
            bot.push_media(image_paths, user_id)

        # 2. Open group via deep link
        bot.log(f"🔗 Navigating to Facebook Group {group_id}...")
        deeplink = f"fb://group/{group_id}"
        bot.launch_app("com.facebook.katana", deeplink)
        bot.smart_sleep(5)

        # 3. Detect group type
        is_buy_sell = _check_is_buy_sell_group(bot)
        bot.log(f"📊 Group category detected: {'BUY & SELL' if is_buy_sell else 'DISCUSSION'}")

        # 4. Route posting strategy
        if is_buy_sell and post_mode != "discussion":
            bot.log("🛒 Executing Buy & Sell Listing Flow...")
            _post_buy_sell_listing(bot, job.parameters, len(image_paths))
        else:
            if is_buy_sell and post_mode == "discussion":
                bot.log("🔄 Switching to 'Discussion' tab in Buy & Sell group...")
                _switch_to_discussion_tab(bot)

            bot.log("📝 Executing Discussion Post Flow...")
            _post_discussion(bot, title, description, len(image_paths))

        bot.smart_sleep(5)
        bot.log(f"🎉 Successfully posted to group {group_id}!")
        return True

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
        full_traceback = "".join(tb_details)
        logger.error(f"Error posting to group on {device_id}:\n{full_traceback}")
        raise e

    finally:
        bot.cleanup_media()
        bot.d.app_stop("com.facebook.katana")
        bot.teardown()


# ==============================================================================
# GROUP TYPE DETECTION & TAB SWITCHING
# ==============================================================================

def _check_is_buy_sell_group(bot: BaseAutomator) -> bool:
    """
    Checks whether the current group interface is configured for Buy & Sell.
    Looks for keywords like 'Bán gì đó', 'Bạn đang bán gì?', 'Sell something',
    or a dedicated 'Bán' / 'Sell' tab.
    """
    buy_sell_keywords = [
        "bạn đang bán gì",
        "bán gì đó",
        "what are you selling",
        "sell something",
        "tạo bài niêm yết",
    ]
    for kw in buy_sell_keywords:
        el = bot.get_widget_by_text("android.view.ViewGroup", kw, timeout=2)
        if el.exists:
            return True
        btn = bot.get_button_by_text(kw, timeout=2)
        if btn.exists:
            return True

    # Check for 'Bán' or 'Sell' tab
    sell_tab = bot.get_button_by_text("bán", exact=True, timeout=1)
    if not sell_tab.exists:
        sell_tab = bot.get_button_by_text("sell", exact=True, timeout=1)
    if sell_tab.exists:
        return True

    return False


def _switch_to_discussion_tab(bot: BaseAutomator) -> bool:
    """
    Switches to the 'Thảo luận' / 'Discussion' tab in a Buy & Sell group.
    """
    disc_tab = bot.get_button_by_text("thảo luận", exact=False, timeout=3)
    if not disc_tab.exists:
        disc_tab = bot.get_button_by_text("discussion", exact=False, timeout=2)
    if disc_tab.exists:
        disc_tab.click_exists(timeout=3)
        bot.smart_sleep(2)
        return True
    return False


# ==============================================================================
# STRATEGY 1: DISCUSSION POSTING (Nhóm Thảo luận / Trao đổi)
# ==============================================================================

def _post_discussion(bot: BaseAutomator, title: str, description: str, photo_num: int):
    """
    Handles standard Facebook group discussion post.
    """
    # 1. Click 'Bạn viết gì đi...' / 'Write something...'
    prompt_keywords = [
        "bạn viết gì đi",
        "tạo bài viết công khai",
        "bạn đang nghĩ gì",
        "write something",
        "create a public post",
        "viết bài",
    ]
    box_clicked = False
    for kw in prompt_keywords:
        prompt_box = bot.get_widget_by_text("android.view.ViewGroup", kw, timeout=3)
        if prompt_box.exists:
            prompt_box.click()
            box_clicked = True
            break
        prompt_tv = bot.get_widget_by_text("android.widget.TextView", kw, timeout=2)
        if prompt_tv.exists:
            prompt_tv.click()
            box_clicked = True
            break

    if not box_clicked:
        # Fallback: swipe down slightly and try again
        bot.swipe_down(scale=0.3)
        bot.smart_sleep(1)
        for kw in prompt_keywords:
            prompt_box = bot.get_widget_by_text("android.view.ViewGroup", kw, timeout=3)
            if prompt_box.exists:
                prompt_box.click()
                box_clicked = True
                break

    if not box_clicked:
        raise Exception("Could not find discussion post input prompt ('Write something...')")

    bot.smart_sleep(3)

    # 2. Enter Content in EditText
    full_text = f"{title}\n\n{description}".strip() if title else description
    edit_input = bot.get_elements_by_widget("android.widget.EditText", timeout=10)
    if not edit_input.exists:
        raise Exception("Could not locate post compose EditText field.")

    bot.log("✏️ Typing post content...")
    edit_input[0].click()
    edit_input[0].send_keys(full_text)
    bot.smart_sleep(2)

    # 3. Add Photos if available
    if photo_num > 0:
        bot.log(f"🖼️ Adding {photo_num} photos to discussion post...")
        _attach_photos_discussion(bot, photo_num)

    # 4. Click 'POST'
    bot.log("🚀 Clicking 'POST' button...")
    post_btn = bot.get_button_by_text("đăng", exact=False, timeout=10)
    if not post_btn.exists:
        post_btn = bot.get_button_by_text("post", exact=False, timeout=5)

    if not post_btn.exists:
        raise Exception("Could not find 'POST' button.")

    post_btn.click_exists(timeout=5)
    
    # Wait for compose window to finish/upload
    if post_btn.wait_gone(timeout=20):
        bot.log("✔️ Discussion post published successfully!")
    else:
        bot.log("⚠️ Post button clicked, waiting for network upload...")
        bot.smart_sleep(5)


def _attach_photos_discussion(bot: BaseAutomator, photo_num: int):
    """
    Attaches media to the discussion post compose screen.
    """
    # Look for 'Ảnh/video' button
    photo_btn = bot.get_button_by_text("ảnh/video", exact=False, timeout=5)
    if not photo_btn.exists:
        photo_btn = bot.get_button_by_text("photo/video", exact=False, timeout=3)
    if not photo_btn.exists:
        photo_btn = bot.get_widget_by_text("android.view.ViewGroup", "ảnh/video", timeout=3)

    if photo_btn.exists:
        photo_btn.click_exists(timeout=5)
        bot.smart_sleep(2)

        # Select photos from GridView
        grid_view = bot.get_elements_by_widget("android.widget.GridView", timeout=10)
        if grid_view.exists:
            photo_widgets = bot.get_interactable_from_parent(
                grid_view[0], "android.view.ViewGroup", text="photo", timeout=15
            )
            count = photo_widgets.count
            if count > 0:
                actual_num = min(count, photo_num)
                for i in reversed(range(actual_num)):
                    photo_widgets[i].click_exists(timeout=5)
                    bot.smart_sleep(0.5)

        # Click 'Tiếp' / 'Next'
        next_btn = bot.get_button_by_text("tiếp", timeout=5)
        if not next_btn.exists:
            next_btn = bot.get_button_by_text("next", timeout=3)
        if next_btn.exists:
            next_btn.click_exists(timeout=5)
            bot.smart_sleep(2)


# ==============================================================================
# STRATEGY 2: BUY AND SELL LISTING (Nhóm Mua Bán)
# ==============================================================================

def _post_buy_sell_listing(bot: BaseAutomator, payload: Dict[str, Any], photo_num: int):
    """
    Handles posting to a Buy & Sell group using the listing creation form.
    """
    # 1. Click 'Bán gì đó' / 'Bạn đang bán gì?'
    sell_prompt_keywords = [
        "bạn đang bán gì",
        "bán gì đó",
        "what are you selling",
        "sell something",
        "bán",
    ]
    sell_clicked = False
    for kw in sell_prompt_keywords:
        btn = bot.get_button_by_text(kw, timeout=3)
        if btn.exists:
            btn.click_exists(timeout=3)
            sell_clicked = True
            break
        wg = bot.get_widget_by_text("android.view.ViewGroup", kw, timeout=2)
        if wg.exists:
            wg.click()
            sell_clicked = True
            break

    if not sell_clicked:
        raise Exception("Could not find 'What are you selling?' (Sell) entry point.")

    bot.smart_sleep(3)

    # 2. Fill Photos if available
    if photo_num > 0:
        bot.log(f"🖼️ Selecting {photo_num} photos for listing...")
        add_photo_btn = bot.get_button_by_text("thêm ảnh", timeout=5)
        if not add_photo_btn.exists:
            add_photo_btn = bot.get_button_by_text("add photos", timeout=3)
        if add_photo_btn.exists:
            add_photo_btn.click_exists(timeout=5)
            bot.smart_sleep(2)
            grid_view = bot.get_elements_by_widget("android.widget.GridView", timeout=10)
            if grid_view.exists:
                photo_widgets = bot.get_interactable_from_parent(
                    grid_view[0], "android.view.ViewGroup", text="photo", timeout=15
                )
                count = photo_widgets.count
                if count > 0:
                    actual_num = min(count, photo_num)
                    for i in reversed(range(actual_num)):
                        photo_widgets[i].click_exists(timeout=5)
                        bot.smart_sleep(0.5)

            next_btn = bot.get_button_by_text("tiếp", timeout=5)
            if not next_btn.exists:
                next_btn = bot.get_button_by_text("next", timeout=3)
            if next_btn.exists:
                next_btn.click_exists(timeout=5)
                bot.smart_sleep(2)

    # 3. Set Title
    title = payload.get("title", "")
    if title:
        title_group = bot.get_widget_by_text("android.view.ViewGroup", "title", timeout=5)
        if not title_group.exists:
            title_group = bot.get_widget_by_text("android.view.ViewGroup", "tiêu đề", timeout=3)
        if title_group.exists:
            bot.swipe_widget_to_center(title_group)
            title_group.click()
            title_input = bot.get_interactable_from_parent(title_group, "android.widget.EditText", timeout=10)
            if title_input.exists:
                title_input.send_keys(title.upper())

    # 4. Set Price
    price_group = bot.get_widget_by_text("android.view.ViewGroup", "price", timeout=5)
    if not price_group.exists:
        price_group = bot.get_widget_by_text("android.view.ViewGroup", "giá", timeout=3)
    if price_group.exists:
        bot.swipe_widget_to_center(price_group)
        price_group.click()
        price_input = bot.get_interactable_from_parent(price_group, "android.widget.EditText", timeout=10)
        if price_input.exists:
            price_input.send_keys(str(randint(1, 1000)))

    # 5. Set Description
    description = payload.get("description", "")
    if description:
        desc_group = bot.get_widget_by_text("android.view.ViewGroup", "description", timeout=5)
        if not desc_group.exists:
            desc_group = bot.get_widget_by_text("android.view.ViewGroup", "mô tả", timeout=3)
        if desc_group.exists:
            bot.swipe_widget_to_center(desc_group)
            desc_group.click()
            desc_input = bot.get_interactable_from_parent(desc_group, "android.widget.EditText", timeout=10)
            if desc_input.exists:
                desc_input.send_keys(description)

    bot.smart_sleep(2)

    # 6. Click Publish / Đăng / Tiếp
    publish_btn = bot.get_button_by_text("đăng", exact=False, timeout=5)
    if not publish_btn.exists:
        publish_btn = bot.get_button_by_text("publish", exact=False, timeout=5)
    if not publish_btn.exists:
        publish_btn = bot.get_button_by_text("tiếp", exact=False, timeout=5)

    if publish_btn.exists:
        bot.log("🚀 Submitting Buy & Sell listing...")
        publish_btn.click_exists(timeout=5)
        publish_btn.wait_gone(timeout=15)
        bot.log("✔️ Listing published to group successfully!")
    else:
        bot.log("⚠️ Could not find explicit publish button, checking 'Next'...")
