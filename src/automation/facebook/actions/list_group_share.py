# src/automation/facebook/actions/list_group_share.py
import os
import re
import sys
import time
import json
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from random import randint
from typing import Dict, Set, Any, Optional, TYPE_CHECKING
from src.entities import Job
from src.automation.core.base_automator import BaseAutomator
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.controllers._manager_controllers import ControllerManager
    from PySide6.QtCore import SignalInstance


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def _extract_group_id(raw_input: str) -> str:
    """
    Trích xuất Group ID từ URL hoặc chuỗi UID.
    Ví dụ:
    - 'https://www.facebook.com/groups/5857815244230418' -> '5857815244230418'
    - 'https://facebook.com/groups/muabannhadatdalat/?ref=share' -> 'muabannhadatdalat'
    - '5857815244230418' -> '5857815244230418'
    """
    raw_input = str(raw_input).strip()
    match = re.search(r'groups/([^/?]+)', raw_input)
    if match:
        return match.group(1)
    return raw_input


def _parse_member_count(desc: str) -> int:
    """
    Parses group member count from contentDescription or text strings.
    Supports both Vietnamese and English patterns:
    - "Nhóm Công khai • 81.3K thành viên" -> 81300
    - "Private group • 1.2M members" -> 1200000
    - "Nhóm công khai · 500 thành viên" -> 500
    """
    if not desc:
        return 0
    match = re.search(r'([\d\.,]+)\s*([KMkmTrtrTt]?)\s*(?:members|thành viên|người tham gia)', desc, re.IGNORECASE)
    if not match:
        return 0
        
    num_str, multiplier = match.groups()
    num_str = num_str.replace(',', '.')
    try:
        num = float(num_str)
        multiplier_upper = multiplier.upper()
        if multiplier_upper == 'K':
            num *= 1_000
        elif multiplier_upper in ('M', 'TR', 'T'):
            num *= 1_000_000
        return int(num)
    except Exception:
        return 0


# ==============================================================================
# BƯỚC 1: MỞ ỨNG DỤNG VÀ TRUY CẬP NHÓM (STEP 1)
# ==============================================================================

def open_facebook_group(bot: BaseAutomator, raw_group: str, timeout: int = 15) -> bool:
    """
    STEP 1:
    - Refresh state: Return to Home and close Facebook if already open.
    - Extract Group ID from URL/UID.
    - Launch Facebook app and navigate directly via Deep Link fb://group/<id>.
    - Wait logic: Wait for group page UI to finish loading.
    """
    group_id = _extract_group_id(raw_group)
    if not group_id:
        raise ValueError(f"Unable to extract Group ID from: '{raw_group}'")

    # 1. Reset to home screen and refresh Facebook state before run
    bot.log("🏠 [Init] Resetting device to Home screen and refreshing Facebook state...")
    try:
        bot.d.app_stop("com.facebook.katana")
        bot.d.press("home")
        bot.smart_sleep(1.0)
    except Exception as e:
        logger.debug(f"Failed to stop app or press home: {e}")

    # 2. Open app via Deep Link
    bot.log(f"🚀 [Step 1] Opening Facebook and navigating to Group: {group_id}...")
    deeplink = f"fb://group/{group_id}"
    bot.launch_app("com.facebook.katana", deeplink)

    # 3. Wait for group page data to load
    bot.log("⏳ Waiting for group page to load...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        current_app = bot.d.app_current()
        if current_app.get("package") == "com.facebook.katana":
            # Check indicators that group page has loaded
            selling_btn = bot.get_button_by_text("what are you selling", timeout=1)
            item_btn = bot.get_button_by_text("item", timeout=1)
            ban_btn = bot.get_button_by_text("bạn đang bán gì", timeout=1)
            public_badge = bot.get_button_by_text("public group", timeout=1)
            joined_btn = bot.get_button_by_text("joined", timeout=1)
            
            if selling_btn.exists or item_btn.exists or ban_btn.exists or public_badge.exists or joined_btn.exists:
                bot.log(f"✔️ Successfully accessed Group {group_id}!")
                bot.smart_sleep(1.5)
                return True
                
        bot.smart_sleep(1.0)

    bot.log(f"✔️ Opened Group {group_id}.")
    return True


# ==============================================================================
# BƯỚC 2: CLICK VÀO 'WHAT ARE YOU SELLING?' / 'BẠN ĐANG BÁN GÌ?' (STEP 2)
# ==============================================================================

def click_what_are_you_selling(bot: BaseAutomator, timeout: int = 15) -> bool:
    """
    STEP 2:
    - Search and click 'What are you selling?' (or 'Bạn đang bán gì?', 'Sell something', 'Item').
    - Wait logic: Wait for Listing Composer form to load.
    """
    bot.log("🔍 [Step 2] Searching for 'What are you selling?' button...")
    
    sell_keywords = [
        "what are you selling",
        "bạn đang bán gì",
        "sell something",
        "bán gì đó",
        "item"
    ]

    clicked = False
    for kw in sell_keywords:
        btn = bot.get_button_by_text(kw, timeout=2)
        if btn.exists:
            bot.log(f"👆 Found and clicking '{kw}' button...")
            btn.click_exists(timeout=3)
            clicked = True
            break
        
        wg = bot.get_widget_by_text("android.view.ViewGroup", kw, timeout=1)
        if wg.exists:
            bot.log(f"👆 Found ViewGroup '{kw}', clicking...")
            wg.click()
            clicked = True
            break

    if not clicked:
        # Fallback: Scroll slightly if button is obscured
        bot.log("🔄 Scrolling slightly to find 'What are you selling?' button...")
        bot.swipe_down(scale=0.3)
        bot.smart_sleep(1.0)
        for kw in sell_keywords:
            btn = bot.get_button_by_text(kw, timeout=2)
            if btn.exists:
                btn.click_exists(timeout=3)
                clicked = True
                break

    if not clicked:
        raise Exception("❌ Could not find 'What are you selling?' button on group page.")

    # Wait logic for listing form to open
    bot.log("⏳ Waiting for listing form to open...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        add_photos = bot.get_button_by_text("add photos", timeout=1)
        them_anh = bot.get_button_by_text("thêm ảnh", timeout=1)
        title_field = bot.get_widget_by_text("android.view.ViewGroup", "composer_v3_title", timeout=1)
        next_btn = bot.get_button_by_text("next", timeout=1)

        if add_photos.exists or them_anh.exists or title_field.exists or next_btn.exists:
            bot.log("✔️ Successfully opened Listing Form!")
            bot.smart_sleep(1.5)
            return True

        bot.smart_sleep(1.0)

    bot.log("✔️ Completed Step 2 (Clicked sell button).")
    return True


# ==============================================================================
# STEP 3: CLICK 'ADD PHOTOS' AND SELECT PHOTOS
# ==============================================================================

def click_add_photos(bot: BaseAutomator, photo_num: int = 1, timeout: int = 15, max_retries: int = 2) -> bool:
    """
    STEP 3:
    - Search and click 'Add photos' (or 'Thêm ảnh').
    - If not found, try pressing 'back' (handling discard draft popup if any) and calling click_what_are_you_selling again.
    - Wait logic: Wait for Camera Roll / Photo Gallery to appear.
    - Identify photo checkboxes/grid items.
    - Select corresponding number of photos (photo_num) in reverse order.
    - Click 'Next' / 'Done' to confirm photo selection.
    """
    bot.log("🖼️ [Step 3] Finding and clicking 'Add photos' button...")
    
    add_photo_keywords = ["add photos", "thêm ảnh", "add photo"]
    clicked = False

    for attempt in range(max_retries):
        for kw in add_photo_keywords:
            btn = bot.get_button_by_text(kw, timeout=3)
            if btn.exists:
                bot.log(f"👆 Clicking '{kw}' button...")
                btn.click_exists(timeout=3)
                clicked = True
                break
            wg = bot.get_widget_by_text("android.view.ViewGroup", kw, timeout=2)
            if wg.exists:
                bot.log(f"👆 Clicking ViewGroup '{kw}'...")
                wg.click()
                clicked = True
                break

        if clicked:
            break

        if attempt < max_retries - 1:
            bot.log(f"⚠️ Could not find 'Add photos' button (Attempt {attempt + 1}/{max_retries}). Backing up and re-trying 'What are you selling?'...")
            bot.d.press("back")
            bot.smart_sleep(1.5)

            # Handle discard draft popup if shown
            discard_btn = bot.get_button_by_text("discard", timeout=1)
            if not discard_btn.exists:
                discard_btn = bot.get_button_by_text("bỏ bài viết", timeout=1)
            if not discard_btn.exists:
                discard_btn = bot.get_button_by_text("bỏ", timeout=1)
            if discard_btn.exists:
                bot.log("👆 Found discard draft confirmation, clicking...")
                discard_btn.click_exists(timeout=2)
                bot.smart_sleep(1.0)

            # Re-call click_what_are_you_selling
            try:
                click_what_are_you_selling(bot)
            except Exception as e:
                bot.log(f"⚠️ Error re-clicking 'What are you selling?': {e}")
            bot.smart_sleep(1.5)

    if not clicked:
        raise Exception("❌ Could not find 'Add photos' button on UI.")

    bot.log("⏳ Waiting for Camera Roll to appear...")
    start_time = time.time()
    photos_found = False
    selected_count = 0

    while time.time() - start_time < timeout:
        # 1. Try detecting standard Katana camera roll checkboxes
        camera_images = bot.d(resourceIdMatches=".*camera_roll_image.*")
        if not camera_images.exists:
            camera_images = bot.d(className="android.widget.CheckBox", descriptionMatches="(?i).*Photo taken on.*")
        if not camera_images.exists:
            camera_images = bot.d(className="android.widget.CheckBox")

        if camera_images.exists and camera_images.count > 0:
            count = camera_images.count
            actual_num = min(count, photo_num)
            bot.log(f"📸 Found {count} photos in Camera Roll. Selecting {actual_num} photos from bottom up...")
            
            for i in reversed(range(actual_num)):
                try:
                    img = camera_images[i]
                    img.click_exists(timeout=3)
                    selected_count += 1
                    bot.log(f"   ✔️ Selected photo {i + 1}/{actual_num} (bottom up)")
                    bot.smart_sleep(0.5)
                except Exception as ce:
                    logger.debug(f"Error clicking photo {i}: {ce}")
            
            photos_found = True
            break

        # 2. Try legacy GridView
        grid_view = bot.get_elements_by_widget("android.widget.GridView", timeout=1)
        if grid_view.exists:
            photo_widgets = bot.get_interactable_from_parent(
                grid_view[0], 
                "android.view.ViewGroup", 
                text="photo", 
                timeout=5
            )
            if photo_widgets.count > 0:
                count = photo_widgets.count
                actual_num = min(count, photo_num)
                bot.log(f"📸 Found {count} photos in GridView. Selecting {actual_num} photos...")
                for i in reversed(range(actual_num)):
                    photo_widgets[i].click_exists(timeout=3)
                    selected_count += 1
                    bot.smart_sleep(0.5)
                photos_found = True
                break

        bot.smart_sleep(1.0)

    if not photos_found:
        bot.log("⚠️ No photos detected in Camera Roll/Gallery after timeout.")

    # 3. Click Next / Done / Add to confirm photos
    bot.smart_sleep(1.0)
    next_keywords = ["next", "tiếp", "done", "xong", "add", "thêm"]
    confirmed = False
    for kw in next_keywords:
        btn = bot.get_button_by_text(kw, timeout=3)
        if btn.exists:
            bot.log(f"👆 Clicking '{kw}' button to confirm adding {selected_count} photo(s) to listing...")
            btn.click_exists(timeout=5)
            confirmed = True
            bot.smart_sleep(2.0)
            break

    bot.log(f"✔️ Completed Step 3 (Selected {selected_count} photo(s)).")
    return True


# ==============================================================================
# STEP 4: FILL LISTING DETAILS (TITLE, PRICE, CATEGORY, LOCATION, DESCRIPTION)
# ==============================================================================

def fill_listing_details(bot: BaseAutomator, payload: Dict[str, Any], max_scroll_cycles: int = 5):
    """
    STEP 4 (Adaptive Form Filling - Flexible with UI order):
    Automatically scans fields visible on screen from top to bottom (Y coordinate).
    Fills visible fields first, then scrolls down to find and fill remaining fields.
    """
    bot.log("📝 [Step 4] Filling listing details (adaptive field order)...")
    
    title = payload.get("title", "")
    price = payload.get("price")
    category = payload.get("category") or "Miscellaneous"
    condition = payload.get("condition") or "New"
    location = payload.get("location", "Da Lat")
    description = payload.get("description", "")

    field_handlers = {
        "title": lambda: _set_title(bot, title),
        "price": lambda: _set_price(bot, price),
        "category": lambda: _set_category(bot, category),
        "condition": lambda: _set_condition(bot, condition),
        "location": lambda: _set_location(bot, location),
        "description": lambda: _set_description(bot, description),
    }

    def detect_field_position(field_name: str) -> Optional[int]:
        el = None
        if field_name == "title":
            el = bot.d(resourceId="composer_v3_title")
            if not el.exists:
                el = bot.d(descriptionMatches="(?i)^Title.*")
            if not el.exists:
                el = bot.d(text="Title")
        elif field_name == "price":
            el = bot.d(resourceId="composer_v3_price")
            if not el.exists:
                el = bot.d(descriptionMatches="(?i)^Price.*")
            if not el.exists:
                el = bot.d(text="Price")
        elif field_name == "category":
            el = bot.d(descriptionMatches="(?i)^Category.*")
            if not el.exists:
                el = bot.get_button_by_text("category", timeout=0.2)
            if not el.exists:
                el = bot.d(text="Category")
        elif field_name == "condition":
            el = bot.d(descriptionMatches="(?i)^Condition.*")
            if not el.exists:
                el = bot.get_button_by_text("condition", timeout=0.2)
            if not el.exists:
                el = bot.d(text="Condition")
        elif field_name == "location":
            el = bot.d(descriptionMatches="(?i).*Location.*")
            if not el.exists:
                el = bot.get_button_by_text("location", timeout=0.2)
            if not el.exists:
                el = bot.d(text="Location")
        elif field_name == "description":
            el = bot.d(resourceId="composer_v3_description")
            if not el.exists:
                el = bot.d(descriptionMatches="(?i).*Description.*")
            if not el.exists:
                el = bot.d(text="Description")
            if not el.exists:
                el = bot.get_widget_by_text("android.view.ViewGroup", "description", timeout=0.2)
            if not el.exists:
                el = bot.get_widget_by_text("android.view.ViewGroup", "mô tả", timeout=0.2)

        if el and el.exists:
            try:
                bounds = el.info.get('bounds', {})
                if isinstance(bounds, dict) and 'top' in bounds:
                    top_y = bounds['top']
                    if 180 <= top_y <= 1850:
                        return top_y
            except Exception:
                pass
        return None

    completed_fields = set()
    all_fields = set(field_handlers.keys())

    for cycle in range(max_scroll_cycles):
        remaining_fields = all_fields - completed_fields
        if not remaining_fields:
            bot.log("🎉 All fields completed!")
            break

        # 1. Scan visible fields and record Y coordinates
        visible_fields = []
        for field in remaining_fields:
            top_y = detect_field_position(field)
            if top_y is not None:
                visible_fields.append((top_y, field))

        # 2. Sort fields by top_y ascending
        visible_fields.sort(key=lambda item: item[0])

        if visible_fields:
            field_names_in_order = [f[1] for f in visible_fields]
            bot.log(f"📋 [Scan {cycle + 1}] Detected {len(visible_fields)} field(s) in order: {field_names_in_order}")
            
            for top_y, field in visible_fields:
                if field in completed_fields:
                    continue
                bot.log(f"👉 Filling field: [{field}]...")
                try:
                    field_handlers[field]()
                    completed_fields.add(field)
                    bot.smart_sleep(1.0)
                except Exception as fe:
                    bot.log(f"⚠️ Error handling field [{field}]: {fe}")
                    completed_fields.add(field)

        # 3. Check if all completed
        remaining_fields = all_fields - completed_fields
        if not remaining_fields:
            bot.log("🎉 All fields completed!")
            break

        # 4. Scroll down for remaining fields
        bot.log(f"🔄 Remaining fields: {list(remaining_fields)}. Scrolling down...")
        sig1 = bot._get_screen_signature()
        bot.swipe_up(scale=0.5)
        bot.smart_sleep(1.5)
        sig2 = bot._get_screen_signature()

        if sig1 == sig2 and sig1 != 0:
            bot.log("🏁 Reached the bottom of listing form.")
            break

    bot.log(f"✔️ [Step 4] Completed listing details ({len(completed_fields)}/{len(all_fields)} fields)!")


def _set_title(bot: BaseAutomator, title: str):
    """
    Enters listing title (in UPPERCASE).
    """
    title_text = str(title).strip().upper() if title else "REAL ESTATE DALAT BEST PRICE"
    bot.log(f"✏️ Entering Title: '{title_text[:35]}...'")

    title_elem = bot.d(resourceId="composer_v3_title")
    if not title_elem.exists:
        title_elem = bot.d(descriptionMatches="(?i)^Title.*")
    if not title_elem.exists:
        title_elem = bot.get_widget_by_text("android.view.ViewGroup", "title", timeout=5)

    if not title_elem.exists:
        raise Exception("❌ Could not find Title input field.")

    bot.swipe_widget_to_center(title_elem)
    title_elem.click()
    bot.smart_sleep(0.5)

    title_input = bot.d(className="android.widget.EditText", descriptionMatches="(?i)^Title.*")
    if not title_input.exists:
        title_input = bot.get_interactable_from_parent(title_elem, "android.widget.EditText", timeout=3)
    if not title_input.exists:
        title_input = bot.d(focused=True, className="android.widget.EditText")

    if title_input.exists:
        title_input.send_keys(title_text)
    else:
        bot.d.send_keys(title_text)

    bot.smart_sleep(0.5)
    bot.log("   ✔️ Title entered successfully.")


def _set_price(bot: BaseAutomator, price: Optional[Any] = None):
    """
    Enters listing price.
    """
    if price is not None and str(price).strip() != "":
        price_val = re.sub(r'[^\d]', '', str(price))
        if not price_val:
            price_val = str(price)
    else:
        price_val = str(randint(1, 1000))

    bot.log(f"💰 Entering Price: {price_val}...")

    price_elem = bot.d(resourceId="composer_v3_price")
    if not price_elem.exists:
        price_elem = bot.d(descriptionMatches="(?i)^Price.*")
    if not price_elem.exists:
        price_elem = bot.get_widget_by_text("android.view.ViewGroup", "price", timeout=5)

    if not price_elem.exists:
        raise Exception("❌ Could not find Price input field.")

    bot.swipe_widget_to_center(price_elem)
    price_elem.click()
    bot.smart_sleep(0.5)

    price_input = bot.d(className="android.widget.EditText", descriptionMatches="(?i)^Price.*")
    if not price_input.exists:
        price_input = bot.get_interactable_from_parent(price_elem, "android.widget.EditText", timeout=3)
    if not price_input.exists:
        price_input = bot.d(focused=True, className="android.widget.EditText")

    if price_input.exists:
        price_input.send_keys(price_val)
    else:
        bot.d.send_keys(price_val)

    bot.smart_sleep(0.5)
    bot.log("   ✔️ Price entered successfully.")


def _set_category(bot: BaseAutomator, category_name: str = "Miscellaneous", max_swipes: int = 10):
    """
    Selects listing category if Category field is present on UI.
    """
    category_btn = bot.get_button_by_text("category", timeout=2)
    if not category_btn.exists:
        category_btn = bot.d(descriptionMatches="(?i)^Category.*")
    if not category_btn.exists:
        category_btn = bot.get_widget_by_text("android.view.ViewGroup", "category", timeout=1)

    if not category_btn.exists:
        bot.log("⏩ 'Category' field not found or already set, skipping.")
        return

    target_category = category_name or "Miscellaneous"
    bot.log(f"🏷️ Category field found. Opening list and searching for '{target_category}'...")
    bot.swipe_widget_to_center(category_btn)
    category_btn.click()
    bot.smart_sleep(1.5)

    # Wait for 'Select Category' screen or ViewGroup 'mp_categories_list'
    start_time = time.time()
    while time.time() - start_time < 5:
        if bot.d(resourceId="mp_categories_list").exists or bot.d(text="Select Category").exists:
            break
        bot.smart_sleep(0.5)

    found = False
    for swipe_idx in range(max_swipes):
        # 1. Search node with text or description matching target_category
        cat_node = bot.d(textMatches=f"(?i).*{target_category}.*")
        if not cat_node.exists:
            cat_node = bot.d(descriptionMatches=f"(?i).*{target_category}.*")
        if not cat_node.exists:
            cat_node = bot.get_button_by_text(target_category, timeout=1)

        if cat_node.exists:
            bot.log(f"✔️ Found category '{target_category}' (Swipe {swipe_idx})! Selecting...")
            cat_node.click_exists(timeout=3)
            found = True
            bot.smart_sleep(1.5)
            break

        # 2. Scroll down if not found
        sig1 = bot._get_screen_signature()
        bot.swipe_up(scale=0.7)
        bot.smart_sleep(0.8)
        sig2 = bot._get_screen_signature()

        if sig1 == sig2 and sig1 != 0:
            bot.log("🏁 Reached end of Category list.")
            break

    if not found:
        bot.log(f"⚠️ Could not find category '{target_category}' after {max_swipes} swipes.")
        if bot.d(text="Select Category").exists or bot.d(resourceId="mp_categories_list").exists:
            back_btn = bot.d(description="Back")
            if back_btn.exists:
                back_btn.click_exists(timeout=3)
    else:
        bot.log(f"   ✔️ Category '{target_category}' selected.")


def _set_condition(bot: BaseAutomator, condition_name: str = "New", timeout: int = 5):
    """
    Selects Condition if field is visible on UI.
    """
    cond_btn = bot.d(descriptionMatches="(?i)^Condition.*")
    if not cond_btn.exists:
        cond_btn = bot.get_button_by_text("condition", timeout=2)
    if not cond_btn.exists:
        cond_btn = bot.get_widget_by_text("android.view.ViewGroup", "condition", timeout=1)

    if not cond_btn.exists:
        bot.log("⏩ 'Condition' field not found, skipping.")
        return

    target_cond = condition_name or "New"
    bot.log(f"🏷️ Condition field found. Opening and selecting '{target_cond}'...")
    bot.swipe_widget_to_center(cond_btn)
    cond_btn.click()
    bot.smart_sleep(1.0)

    # Wait for node containing target_cond
    new_option = bot.d(className="android.widget.RadioButton", descriptionMatches=f"(?i)^{target_cond}.*")
    if not new_option.exists:
        new_option = bot.d(text=target_cond)
    if not new_option.exists:
        new_option = bot.d(descriptionMatches=f"(?i)^{target_cond}.*")
    if not new_option.exists:
        new_option = bot.get_button_by_text(target_cond, exact=False, timeout=timeout)

    if new_option.exists:
        bot.log(f"👆 Found option '{target_cond}'. Clicking...")
        new_option.click_exists(timeout=3)
        bot.smart_sleep(1.0)
        bot.log(f"   ✔️ Condition '{target_cond}' selected.")
    else:
        bot.log(f"⚠️ Option '{target_cond}' not found in Condition list.")


def _set_location(bot: BaseAutomator, city_name: str = "Da Lat"):
    """
    Updates Location if needed.
    """
    target_city = city_name or "Da Lat"
    bot.log(f"📍 Checking location: target '{target_city}'...")

    loc_btn = bot.d(descriptionMatches="(?i).*Location.*")
    if not loc_btn.exists:
        loc_btn = bot.get_button_by_text("location", timeout=3)

    if not loc_btn.exists:
        bot.log("⏩ 'Location' button not found, skipping.")
        return

    bot.swipe_widget_to_center(loc_btn)
    desc = ""
    try:
        desc = loc_btn.info.get('contentDescription', '') or loc_btn.info.get('text', '')
    except Exception:
        pass

    # If current location already contains city name, keep it
    if target_city.lower() in desc.lower():
        bot.log(f"   ✔️ Current location already matches ('{desc}'). Keeping as is.")
        return

    bot.log(f"👆 Opening location picker for '{target_city}'...")
    loc_btn.click()
    bot.smart_sleep(1.5)

    search_input = bot.d(className="android.widget.EditText")
    if not search_input.exists:
        search_input = bot.get_widget_by_text("android.widget.EditText", "Search", timeout=3)

    if search_input.exists:
        search_input.click()
        search_input.send_keys(target_city)
        bot.smart_sleep(1.5)

        city_suggestion = bot.get_button_by_text(target_city, timeout=5)
        if city_suggestion.exists:
            city_suggestion.click()
            bot.smart_sleep(1.0)

        apply_btn = bot.get_button_by_text("apply", timeout=5)
        if not apply_btn.exists:
            apply_btn = bot.get_button_by_text("áp dụng", timeout=3)
        if apply_btn.exists:
            apply_btn.click()
            bot.smart_sleep(1.0)
            bot.log(f"   ✔️ Applied location '{target_city}'.")
    else:
        bot.log("⚠️ Could not find location search field.")


def _set_description(bot: BaseAutomator, description: str):
    """
    Inputs listing description.
    """
    desc_text = str(description).strip() if description else "Great real estate deal with direct owner. Contact for viewing."
    bot.log(f"📝 Finding and entering Description ({len(desc_text)} chars)...")

    desc_elem = bot.d(descriptionMatches="(?i).*Description.*")
    if not desc_elem.exists:
        desc_elem = bot.get_widget_by_text("android.view.ViewGroup", "description", timeout=2)
    if not desc_elem.exists:
        desc_elem = bot.get_widget_by_text("android.view.ViewGroup", "mô tả", timeout=2)

    if not desc_elem.exists:
        # Scroll up slightly to reveal description field
        bot.log("🔄 Scrolling down to locate Description field...")
        bot.swipe_up(scale=0.5)
        bot.smart_sleep(1.0)
        desc_elem = bot.d(descriptionMatches="(?i).*Description.*")
        if not desc_elem.exists:
            desc_elem = bot.get_widget_by_text("android.view.ViewGroup", "description", timeout=3)

    if desc_elem.exists:
        bot.swipe_widget_to_center(desc_elem)
        desc_elem.click()
        bot.smart_sleep(0.5)

        desc_input = bot.d(className="android.widget.EditText", descriptionMatches="(?i).*Description.*")
        if not desc_input.exists:
            desc_input = bot.get_interactable_from_parent(desc_elem, "android.widget.EditText", timeout=3)
        if not desc_input.exists:
            desc_input = bot.d(focused=True, className="android.widget.EditText")

        if desc_input.exists:
            desc_input.send_keys(desc_text)
        else:
            bot.d.send_keys(desc_text)

        bot.smart_sleep(0.5)
        bot.log("   ✔️ Description entered successfully.")
    else:
        bot.log("⚠️ Description field not found, skipping.")


def click_next_button(bot: BaseAutomator, timeout: int = 15) -> bool:
    """
    STEP 5: Click 'Next' on listing form to proceed to group selection.
    """
    bot.log("👉 [Step 5] Finding and clicking 'Next' button...")
    next_btn = bot.d(text="Next")
    if not next_btn.exists:
        next_btn = bot.d(descriptionMatches="(?i)^Next.*")
    if not next_btn.exists:
        next_btn = bot.get_button_by_text("next", timeout=5)
    if not next_btn.exists:
        next_btn = bot.get_button_by_text("tiếp", timeout=3)

    if not next_btn.exists:
        raise Exception("❌ Could not find 'Next' button on listing form.")

    next_btn.click_exists(timeout=5)
    bot.smart_sleep(2.5)
    bot.log("✔️ Clicked 'Next', transitioning to group & Marketplace selection.")
    return True


def select_marketplace_checkbox(bot: BaseAutomator) -> bool:
    """
    Checks the Marketplace checkbox if not checked.
    """
    try:
        mp_box = bot.d(className="android.widget.CheckBox", descriptionMatches="(?i).*Marketplace.*")
        if not mp_box.exists:
            mp_box = bot.d(className="android.widget.CheckBox", textMatches="(?i).*Marketplace.*")

        if mp_box.exists:
            is_checked = mp_box.info.get('checked', False)
            if not is_checked:
                bot.log("🛒 Marketplace is unchecked. Selecting...")
                mp_box.click_exists(timeout=3)
                bot.smart_sleep(0.8)
                bot.log("   ✔️ Marketplace selected for cross-posting!")
                return True
            else:
                bot.log("ℹ️ Marketplace is already checked.")
                return True
    except Exception as e:
        logger.debug(f"Error selecting Marketplace: {e}")
    return False


def wait_for_group_list(bot: BaseAutomator, timeout: int = 15) -> bool:
    """
    Waits for the group selection list ('List in more places') to load.
    """
    bot.log("⏳ Waiting for group list to load from server...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        checkboxes = bot.get_elements_by_widget("android.widget.CheckBox", timeout=1)
        if checkboxes.exists and checkboxes.count > 0:
            bot.log(f"✔️ Detected {checkboxes.count} checkbox(es) on screen!")
            bot.smart_sleep(1.0)
            return True
        
        loading = bot.get_elements_by_widget("android.widget.ProgressBar", timeout=1)
        if loading.exists:
            bot.log("🔄 Loading more groups...")
        
        bot.smart_sleep(1.0)

    bot.log("⚠️ Timeout waiting for group checkboxes.")
    return False


def collect_available_groups(
    bot: BaseAutomator, 
    max_swipes: int = 5, 
    swipe_delay: float = 1.5
) -> Dict[str, int]:
    """
    Scrolls down and collects available groups and their member counts.
    """
    collected_groups: Dict[str, int] = {}
    bot.log(f"📋 Scanning group list (Max {max_swipes} swipes)...")

    for swipe_idx in range(max_swipes):
        checkboxes = bot.get_elements_by_widget("android.widget.CheckBox", timeout=2)
        found_in_screen = 0

        if checkboxes.exists:
            for i in range(checkboxes.count):
                try:
                    box = checkboxes[i]
                    desc = box.info.get('contentDescription', '') or box.info.get('text', '')
                    # Skip Marketplace entry
                    if "Marketplace" in desc:
                        continue
                    if desc and desc not in collected_groups:
                        members = _parse_member_count(desc)
                        collected_groups[desc] = members
                        found_in_screen += 1
                except Exception:
                    pass

        bot.log(f"🔍 Swipe {swipe_idx + 1}/{max_swipes}: Collected {found_in_screen} new group(s). Total: {len(collected_groups)} group(s).")

        sig1 = bot._get_screen_signature()
        bot.swipe_up(scale=0.8)
        bot.smart_sleep(swipe_delay)
        sig2 = bot._get_screen_signature()

        if sig1 == sig2 and sig1 != 0:
            bot.log("🏁 Reached the end of group list.")
            break

    return collected_groups


def select_target_groups(
    bot: BaseAutomator, 
    target_descs: Set[str], 
    max_swipes: int = 10, 
    click_delay: float = 0.8
) -> int:
    """
    Scrolls back up and checks target group checkboxes.
    """
    clicked_groups: Set[str] = set()
    total_target = len(target_descs)
    bot.log(f"🎯 Selecting {total_target} target group(s)...")

    for swipe_idx in range(max_swipes):
        checkboxes = bot.get_elements_by_widget("android.widget.CheckBox", timeout=2)

        if checkboxes.exists:
            for i in range(checkboxes.count):
                try:
                    box = checkboxes[i]
                    desc = box.info.get('contentDescription', '') or box.info.get('text', '')
                    is_checked = box.info.get('checked', False)

                    if desc in target_descs and desc not in clicked_groups:
                        if not is_checked:
                            box.click_exists(timeout=3)
                            bot.smart_sleep(click_delay)
                        
                        clicked_groups.add(desc)
                        bot.log(f"✔️ Selected group ({len(clicked_groups)}/{total_target}): {desc[:40]}...")
                except Exception as e:
                    logger.debug(f"Error interacting with checkbox: {e}")

        if len(clicked_groups) >= total_target:
            bot.log("🎉 All target groups selected!")
            break

        sig1 = bot._get_screen_signature()
        bot.swipe_down(scale=0.8)
        bot.smart_sleep(1.0)
        sig2 = bot._get_screen_signature()

        if sig1 == sig2 and sig1 != 0:
            bot.log("🏁 Scrolled back to top of group list.")
            break

    return len(clicked_groups)


def list_in_more_places(
    bot: BaseAutomator, 
    share_groups_count: int = 20, 
    max_swipes: int = 5,
    min_members: int = 0
) -> int:
    """
    STEP 6:
    Selects Marketplace and high-member groups.
    """
    bot.log(f"📋 [Step 6] Starting Marketplace and up to {share_groups_count} groups selection...")

    if not wait_for_group_list(bot, timeout=12):
        bot.log("⚠️ Group list screen not fully recognized, continuing with available elements...")

    # 1. Select Marketplace if present
    select_marketplace_checkbox(bot)

    if share_groups_count <= 0:
        bot.log("ℹ️ Target share group count is 0. Skipping group selection.")
        return 0

    target_count = min(share_groups_count, 20)

    # 2. Collect groups with member counts
    collected_groups = collect_available_groups(bot, max_swipes=max_swipes, swipe_delay=1.5)
    if not collected_groups:
        bot.log("⚠️ No groups found in the list.")
        return 0

    filtered_groups = {
        name: count for name, count in collected_groups.items() 
        if count >= min_members
    }
    if not filtered_groups:
        filtered_groups = collected_groups

    sorted_groups = sorted(filtered_groups.items(), key=lambda item: item[1], reverse=True)
    top_groups = dict(sorted_groups[:target_count])
    target_descs = set(top_groups.keys())

    bot.log(f"📋 Selected Top {len(target_descs)} group(s) with highest member count:")
    for idx, (name, count) in enumerate(top_groups.items(), start=1):
        bot.log(f"   {idx}. {name[:45]} ({count:,} members)")

    # 3. Check target groups
    selected_count = select_target_groups(bot, target_descs, max_swipes=max_swipes, click_delay=0.8)
    bot.log(f"✔️ Completed selecting {selected_count} group(s).")
    return selected_count


def click_publish_or_done(bot: BaseAutomator, timeout: int = 20) -> bool:
    """
    STEP 7: Clicks 'Publish' button and waits for completion.
    """
    bot.log("🚀 [Step 7] Finding and clicking 'Publish' button...")

    publish_btn = bot.d(text="Publish")
    if not publish_btn.exists:
        publish_btn = bot.d(descriptionMatches="(?i)^Publish.*")
    if not publish_btn.exists:
        publish_btn = bot.d(resourceId="mp_composer_post")
    if not publish_btn.exists:
        publish_btn = bot.get_button_by_text("publish", timeout=5)
    if not publish_btn.exists:
        publish_btn = bot.get_button_by_text("đăng", timeout=3)

    if not publish_btn.exists:
        raise Exception("❌ Could not find 'Publish' button.")

    bot.log("👆 Clicking 'Publish' button...")
    publish_btn.click_exists(timeout=5)

    bot.log("⏳ Waiting for system to process listing publication...")
    bot.smart_sleep(8.0)
    bot.log("✔️ Successfully published listing to Group and selected groups!")
    return True


def dump_error_view(bot: BaseAutomator, account_uid: str, step_name: str):
    """
    Automatically dumps UI hierarchy (XML, JSON, Screenshot) on error.
    Saved to: tests/dumps/errors/{account_uid}_{step_name}/
    """
    try:
        from tests.dump_view import parse_hierarchy_node
        
        safe_uid = re.sub(r'[^\w\-_\.]', '_', str(account_uid))
        safe_step = re.sub(r'[^\w\-_\.]', '_', str(step_name))
        
        output_dir = Path("tests/dumps/errors") / f"{safe_uid}_{safe_step}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        bot.log(f"📸 [ERROR REPORT] Auto-dumping UI hierarchy to {output_dir}...")
        
        xml_dump = bot.d.dump_hierarchy()
        xml_file = output_dir / "dumped_view.xml"
        json_file = output_dir / "dumped_view.json"
        png_file = output_dir / "dumped_screen.png"
        
        with open(xml_file, "w", encoding="utf-8") as f:
            f.write(xml_dump)
            
        root = ET.fromstring(xml_dump)
        elements = parse_hierarchy_node(root)
        
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "device_id": bot.device_id,
                "account_uid": account_uid,
                "failed_step": step_name,
                "current_app": bot.d.app_current(),
                "total_elements": len(elements),
                "elements": elements
            }, f, ensure_ascii=False, indent=2)
            
        bot.d.screenshot(str(png_file))
        bot.log(f"💾 Successfully saved error diagnostics to: {output_dir}")
    except Exception as dump_err:
        logger.error(f"Error dumping diagnostics ({account_uid} - {step_name}): {dump_err}")


def dump_step_view(bot: BaseAutomator, tag: str = "after_step_3"):
    """
    Dumps UI hierarchy (XML, JSON, Screenshot) to tests/dumps/ for step analysis.
    """
    try:
        from tests.dump_view import dump_current_screen
        bot.log(f"📸 Auto-saving UI hierarchy ({tag}) to tests/dumps/...")
        dump_current_screen(bot.device_id, take_screenshot=True, output_dir_name="dumps")
        bot.log(f"💾 Successfully saved UI hierarchy '{tag}' to tests/dumps/dumped_view.json!")
    except Exception as e:
        bot.log(f"⚠️ Error dumping UI: {e}")


# ==============================================================================
# ACTION ENTRY POINT
# ==============================================================================

def run_list_group_share(
    device_id: str, 
    job: Job, 
    logger_signal: "SignalInstance", 
    controllers: Optional["ControllerManager"] = None
):
    """
    Main execution entry point for action list_group_share.
    7-step workflow:
    1. Launch Facebook and navigate to Group via Deep Link
    2. Click 'What are you selling?'
    3. Upload photos (Add photos) in reverse order
    4. Fill listing details (Title, Price, Category 'Miscellaneous', Condition 'New', Location, Description)
    5. Click 'Next'
    6. Select Marketplace and Top N groups
    7. Click 'Publish'
    """
    bot = BaseAutomator(device_id, logger_signal)

    account_uid = device_id
    if controllers and getattr(job, 'user_uuid', None):
        user_info = controllers.user_controller.get_by_id(job.user_uuid)
        user_id = user_info.user_id if user_info else 0
        account_uid = getattr(user_info, 'uid', None) or getattr(user_info, 'username', None) or str(job.user_uuid)
    else:
        user_id = int(job.parameters.get("user_id", 0))
        account_uid = job.parameters.get("account_uid") or job.parameters.get("uid") or device_id

    current_step = "step_0_init"

    try:
        # 0. Push media to user storage
        current_step = "step_0_push_media"
        image_paths = job.parameters.get("image_paths", [])
        if image_paths:
            bot.log(f"📤 Pushing {len(image_paths)} image(s) to device (User {user_id})...")
            bot.push_media(image_paths, user_id)
            bot.smart_sleep(2.0)

        raw_group = job.parameters.get("group_url") or job.parameters.get("group_uid") or "5857815244230418"
        share_groups_count = int(job.parameters.get("share_groups_count", 20))

        # STEP 1: Open Facebook and navigate to group
        current_step = "step_1_open_facebook_group"
        open_facebook_group(bot, raw_group)

        # STEP 2: Click 'What are you selling?'
        current_step = "step_2_click_what_are_you_selling"
        click_what_are_you_selling(bot)

        # STEP 3: Click 'Add photos' and select photos
        current_step = "step_3_click_add_photos"
        photo_count = len(image_paths) if image_paths else int(job.parameters.get("photo_num", 1))
        click_add_photos(bot, photo_num=photo_count)

        bot.smart_sleep(2.0)

        # STEP 4: Fill listing details
        current_step = "step_4_fill_listing_details"
        fill_listing_details(bot, job.parameters)

        bot.smart_sleep(2.0)

        # STEP 5: Click Next
        current_step = "step_5_click_next_button"
        click_next_button(bot)

        # STEP 6: Select Marketplace and share groups
        current_step = "step_6_list_in_more_places"
        list_in_more_places(bot, share_groups_count=share_groups_count)

        # STEP 7: Click Publish
        current_step = "step_7_click_publish_or_done"
        click_publish_or_done(bot)

        bot.smart_sleep(3.0)
        bot.log("🎉 Complete Listing & Cross-Posting workflow finished successfully!")
        return True

    except Exception as e:
        dump_error_view(bot, account_uid=account_uid, step_name=current_step)

        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
        full_traceback = "".join(tb_details)

        logger.error(f"Full Traceback for {device_id} ({account_uid}) at {current_step} in list_group_share:\n{full_traceback}")
        bot.log(f"❌ Error occurred at [{current_step}]: {e}")
        raise e

    finally:
        bot.log("🧹 Cleaning up environment (clearing media, stopping Facebook, returning home)...")
        bot.cleanup_media()
        bot.d.app_stop("com.facebook.katana")
        try:
            bot.d.press("home")
        except Exception:
            pass
        bot.teardown()

