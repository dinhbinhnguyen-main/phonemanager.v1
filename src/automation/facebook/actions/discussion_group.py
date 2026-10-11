# src/automation/facebook/actions/discussion_group.py
"""
Facebook Group Discussion Post Action (discussion_group).
Posts real estate discussion content with rewritten AI/template text and attached gallery images.
Supports 100% Vietnamese and English Facebook UI on Android devices / Redroid.
"""

import re
import sys
import json
import time
import shutil
import random
import logging
import traceback
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Set, Tuple, TYPE_CHECKING

from src.entities import Job
from src.automation.core.base_automator import BaseAutomator
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.controllers._manager_controllers import ControllerManager
    from PySide6.QtCore import SignalInstance


# ==============================================================================
# UI DIAGNOSTIC DUMP HELPERS
# ==============================================================================

def dump_error_view(bot: BaseAutomator, account_uid: Optional[str] = None, step_name: str = "unknown_step"):
    """
    Automatically dumps UI hierarchy (XML, JSON, Screenshot) on error or missing elements.
    Saved to: tests/dumps/errors/{safe_uid}_{safe_step}_{timestamp}/
    Also mirrors latest error dump to tests/dumps/latest/
    """
    try:
        from tests.dump_view import parse_hierarchy_node

        uid = str(account_uid or getattr(bot, "account_uid", None) or getattr(bot, "device_id", "device"))
        safe_uid = re.sub(r'[^\w\-_\.]', '_', uid)
        safe_step = re.sub(r'[^\w\-_\.]', '_', str(step_name))
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        output_dir = Path("tests/dumps/errors") / f"{safe_uid}_{safe_step}"
        output_dir.mkdir(parents=True, exist_ok=True)

        latest_dir = Path("tests/dumps/latest")
        latest_dir.mkdir(parents=True, exist_ok=True)

        bot.log(f"📸 [ERROR DUMP] Missing element / error at [{step_name}]. Auto-dumping UI to {output_dir}...")

        if not bot.d:
            bot.log("⚠️ UIAutomator2 device is not connected, cannot dump screen.")
            return

        xml_dump = bot.d.dump_hierarchy()
        xml_file = output_dir / "dumped_view.xml"
        json_file = output_dir / "dumped_view.json"
        png_file = output_dir / "dumped_screen.png"

        with open(xml_file, "w", encoding="utf-8") as f:
            f.write(xml_dump)

        root = ET.fromstring(xml_dump)
        elements = parse_hierarchy_node(root)

        app_info = {}
        try:
            app_info = bot.d.app_current()
        except Exception:
            pass

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "device_id": getattr(bot, "device_id", None),
                "account_uid": uid,
                "failed_step": step_name,
                "timestamp": timestamp,
                "current_app": app_info,
                "total_elements": len(elements),
                "elements": elements
            }, f, ensure_ascii=False, indent=2)

        try:
            bot.d.screenshot(str(png_file))
        except Exception as se:
            bot.log(f"⚠️ Could not capture screenshot: {se}")

        # Mirror to latest/
        try:
            shutil.copy2(xml_file, latest_dir / "dumped_view.xml")
            shutil.copy2(json_file, latest_dir / "dumped_view.json")
            if png_file.exists():
                shutil.copy2(png_file, latest_dir / "dumped_screen.png")
        except Exception:
            pass

        bot.log(f"💾 Successfully saved UI error diagnostics to: {output_dir}")
    except Exception as dump_err:
        logger.error(f"Error dumping diagnostics ({account_uid} - {step_name}): {dump_err}")


# ==============================================================================
# STEP 1: OPEN FACEBOOK GROUPS TAB LIST VIA DEEPLINK
# ==============================================================================

def open_groups_tab_list(bot: BaseAutomator, timeout: int = 20) -> bool:
    """
    STEP 1:
    - Stop com.facebook.katana and reset to Home screen.
    - Open Facebook app using deeplink: 'fb://groups/tab/list'.
    - Wait logic: Wait for the Groups list tab UI ('Your groups' / 'Nhóm của bạn') to load.
    """
    bot.log("🏠 [Step 1] Resetting Facebook app state and navigating to Groups Tab List...")
    try:
        if bot.d:
            bot.d.app_stop("com.facebook.katana")
            bot.d.press("home")
        bot.smart_sleep(1.0)
    except Exception as e:
        logger.debug(f"Failed to reset app state: {e}")

    deeplink = "fb://groups/tab/list"
    bot.log(f"🚀 [Step 1] Launching deeplink: '{deeplink}'...")
    bot.launch_app("com.facebook.katana", deeplink)

    bot.log("⏳ Waiting for Groups Tab List page to finish loading...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not bot.d:
            break

        # Check for indicators of groups tab
        your_groups = bot.d(textMatches=r"(?i).*Your groups.*|.*Nhóm của bạn.*|.*Nhóm bạn đã tham gia.*")
        pinned_hdr = bot.d(textMatches=r"(?i).*Pinned.*|.*Đã ghim.*|.*Other.*|.*Khác.*|.*Groups you manage.*|.*Nhóm do bạn quản lý.*")
        create_btn = bot.d(descriptionMatches=r"(?i).*Create group.*|.*Tạo nhóm.*")

        if your_groups.exists or pinned_hdr.exists or create_btn.exists:
            bot.log("✔️ Groups tab list page loaded successfully!")
            bot.smart_sleep(1.5)
            return True

        bot.smart_sleep(1.0)

    bot.log("⚠️ Timed out waiting for Groups Tab list page indicator. Checking if any group buttons are visible...")
    if bot.d and (bot.d(className="androidx.recyclerview.widget.RecyclerView").exists or bot.d(className="android.widget.Button").exists):
        return True

    raise Exception("❌ Failed to open Groups Tab List via deeplink 'fb://groups/tab/list'")


# ==============================================================================
# STEP 2: SELECT RANDOM GROUP MATCHING TRANSACTION TYPE
# ==============================================================================

SYSTEM_GROUP_BUTTON_KEYWORDS = [
    "pinned", "đã ghim", "edit", "chỉnh sửa", "groups you manage", "nhóm do bạn quản lý",
    "create group", "tạo nhóm", "create", "tạo", "other", "khác", "sort your other groups",
    "sắp xếp nhóm khác của bạn", "back", "quay lại", "search", "tìm kiếm", "your groups", "nhóm của bạn"
]

def _is_system_button(text: str, desc: str) -> bool:
    """Checks if a UI element is a system navigation/header button rather than a group item."""
    combined = f"{text} {desc}".strip().lower()
    if not combined:
        return True
    for kw in SYSTEM_GROUP_BUTTON_KEYWORDS:
        if combined == kw or combined.startswith(kw + " button") or combined == f"{kw}":
            return True
    return False


def is_group_matching_transaction_type(group_title: str, transaction_type: str = "rental") -> Tuple[bool, bool]:
    """
    Strictly evaluates if a group title matches the target transaction type.
    Returns: (is_priority_match, is_conflicting)
    - is_priority_match: True if title directly matches transaction type (e.g. 'bán' for sale, 'cho thuê' for rental).
    - is_conflicting: True if group is exclusively for the opposite transaction type (e.g. pure rental group when trans_type='sale').
    """
    title = group_title.lower()
    t_type = str(transaction_type or "rental").lower().strip()

    rental_exclusive_terms = [
        "cho thuê", "cho thue", "for rent", "nhà trọ", "phòng trọ", "nha tro",
        "phong tro", "apartment for rent", "house for rent", "căn hộ cho thuê",
        "can ho cho thue", "nhà cho thuê", "nha cho thue"
    ]
    rental_terms = rental_exclusive_terms + [
        "thuê", "thue", "rent", "rental", "căn hộ", "can ho", "sang nhượng", "sang nhuong"
    ]

    sale_terms = [
        "bán", "ban", "mua bán", "mua ban", "sale", "mua", "đất", "dat",
        "nhà đất", "nha dat", "bất động sản", "bat dong san", "bds", "đất nền",
        "dat nen", "nhà đẹp", "nha dep", "chính chủ", "chinh chu"
    ]

    is_pure_rental = any(r in title for r in rental_exclusive_terms)
    has_rental = any(r in title for r in rental_terms) or bool(re.search(r'\b(thue|rent|rental)\b', title))
    has_sale = any(s in title for s in sale_terms) or bool(re.search(r'\b(ban|sale|mua)\b', title))

    if t_type in ("sale", "ban", "mua_ban", "0"):
        # For SALE:
        # If group is explicitly a rental-only group (e.g. 'Căn hộ cho thuê Đà Lạt', 'House for rent'), reject it!
        if is_pure_rental:
            return False, True
        if has_rental and not ("mua bán" in title or "mua ban" in title or "bán" in title or "bds" in title or "bất động sản" in title):
            return False, True

        # Matches sale terms
        if has_sale:
            return True, False
        return False, False

    elif t_type in ("rental", "rent", "thue", "cho_thue", "1"):
        # For RENTAL:
        if has_rental:
            return True, False
        # If group title is purely buy/sell without rental
        if ("chuyên bán" in title or "mua bán đất" in title) and not has_rental:
            return False, True
        if has_sale:
            return False, False
        return False, False

    return True, False


def select_random_group_by_transaction_type(
    bot: BaseAutomator,
    transaction_type: Optional[str] = "rental",
    max_scrolls: int = 2,
    timeout: int = 15
) -> str:
    """
    STEP 2:
    - Scans groups listed in 'Your groups' tab.
    - Performs random scrolls down to discover more groups and pick randomly.
    - Filters groups matching transaction_type (rental / sale / real estate).
    - Strictly avoids conflicting groups (e.g. rental groups for sale transactions).
    - Randomly clicks an eligible group item.
    - Waits for the group main page to load.
    Returns the selected group name/title.
    """
    bot.log(f"🔍 [Step 2] Selecting random group matching transaction_type '{transaction_type}'...")

    if not bot.d:
        raise Exception("Device is not connected.")

    # 1. Perform random scrolling to get deeper into the group list
    actual_scrolls = random.randint(1, max(1, max_scrolls))
    bot.log(f"📜 Scrolling down {actual_scrolls} time(s) to discover groups in the list...")
    for s_idx in range(actual_scrolls):
        bot.swipe_up(scale=random.uniform(0.4, 0.7))
        bot.smart_sleep(1.5)

    # 2. Extract group candidate buttons from current view
    seen_titles: Set[str] = set()
    priority_candidates: List[Tuple[Any, str]] = []
    secondary_candidates: List[Tuple[Any, str]] = []

    def _collect_groups_from_view():
        buttons = bot.d(className="android.widget.Button")
        for btn in buttons:
            try:
                if not btn.exists:
                    continue
                info = btn.info
                desc = info.get("contentDescription", "") or ""
                text = info.get("text", "") or ""

                if not text and not desc:
                    child_tv = btn.child(className="android.widget.TextView")
                    if child_tv.exists:
                        text = child_tv.info.get("text", "") or ""

                raw_label = f"{text} {desc}".strip()
                if _is_system_button(text, desc):
                    continue

                group_title = text or desc.split("Button")[0].strip() or raw_label
                if not group_title or len(group_title) < 4 or group_title in seen_titles:
                    continue
                seen_titles.add(group_title)

                is_priority, is_conflicting = is_group_matching_transaction_type(group_title, transaction_type)
                if is_conflicting:
                    bot.log(f"   ⛔ Excluding conflicting group for '{transaction_type}': '{group_title}'")
                    continue

                if is_priority:
                    priority_candidates.append((btn, group_title))
                else:
                    secondary_candidates.append((btn, group_title))
            except Exception:
                continue

    _collect_groups_from_view()

    # If no priority candidates, try one slight swipe down or up to scan more
    if not priority_candidates:
        bot.log("ℹ️ No priority group on current view, scrolling slightly up to re-check...")
        bot.swipe_down(scale=0.3)
        bot.smart_sleep(1.5)
        _collect_groups_from_view()

    bot.log(f"📊 Found {len(priority_candidates)} priority group(s) and {len(secondary_candidates)} secondary group(s) for transaction_type '{transaction_type}'.")

    pool = priority_candidates if priority_candidates else secondary_candidates
    if not pool:
        bot.log("❌ Failed to find any suitable group to click in group list tab.")
        raise Exception(f"❌ No matching groups found in Groups list tab for transaction_type '{transaction_type}'.")

    chosen_elem, chosen_name = random.choice(pool)
    bot.log(f"🎯 [Step 2] Selected target Group: '{chosen_name}' (from {len(pool)} candidates). Clicking...")
    chosen_elem.click()
    bot.smart_sleep(3.0)

    # 3. Wait for group feed page to load
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not bot.d:
            break
        write_box = bot.d(textMatches=r"(?i).*Write something.*|.*Viết gì đó.*|.*Bạn đang nghĩ gì.*|.*Tạo bài viết.*|.*Bạn viết gì đi.*")
        write_desc = bot.d(descriptionMatches=r"(?i).*Write something.*|.*Viết gì đó.*|.*Bạn đang nghĩ gì.*|.*Tạo bài viết.*|.*Bạn viết gì đi.*")
        group_feed = bot.d(textMatches=r"(?i).*Joined.*|.*Đã tham gia.*|.*Invite.*|.*Mời.*|.*Featured.*|.*Đáng chú ý.*")

        if write_box.exists or write_desc.exists or group_feed.exists:
            bot.log(f"✔️ Successfully opened Group '{chosen_name}'!")
            return chosen_name
        bot.smart_sleep(1.0)

    bot.log(f"ℹ️ Proceeding with group '{chosen_name}'...")
    return chosen_name


# ==============================================================================
# STEP 3: CLICK 'WRITE SOMETHING...' BUTTON
# ==============================================================================

def click_write_something_button(bot: BaseAutomator, timeout: int = 15) -> bool:
    """
    STEP 3:
    - Finds and clicks 'Write something...' / 'Bạn viết gì đi...' / 'Viết gì đó...' in group feed.
    """
    bot.log("✍️ [Step 3] Finding and clicking 'Write something...' button (with up to 3 scroll attempts)...")

    write_patterns = [
        r"(?i)^Write something\.\.\.$",
        r"(?i)^Bạn viết gì đi\.\.\.$",
        r"(?i)^Viết gì đó\.\.\.$",
        r"(?i)^Bạn đang nghĩ gì\?*$",
        r"(?i)^Tạo bài viết.*",
        r"(?i)^Hãy viết gì đó\.\.\.$",
        r"(?i).*write something.*",
        r"(?i).*viết gì đó.*",
        r"(?i).*bạn đang nghĩ gì.*"
    ]

    def _try_click_write() -> bool:
        if not bot.d:
            return False

        # 1. By exact / pattern text
        for p in write_patterns:
            btn = bot.d(textMatches=p)
            if btn.exists:
                bot.log(f"👆 Clicking 'Write something...' button (via text: {p})...")
                btn.click()
                bot.smart_sleep(2.0)
                return True

            desc_btn = bot.d(descriptionMatches=p)
            if desc_btn.exists:
                bot.log(f"👆 Clicking 'Write something...' button (via description: {p})...")
                desc_btn.click()
                bot.smart_sleep(2.0)
                return True

        # 2. Via widget helpers
        for kw in ["write something", "viết gì đó", "bạn đang nghĩ gì", "bạn viết gì đi", "tạo bài viết"]:
            w_btn = bot.get_button_by_text(kw, timeout=1)
            if w_btn and w_btn.exists:
                bot.log(f"👆 Clicking button '{kw}'...")
                w_btn.click()
                bot.smart_sleep(2.0)
                return True

        # 3. Fallback: Check if composer is already opened
        create_post_field = bot.d(className="android.widget.AutoCompleteTextView") or bot.d(className="android.widget.EditText")
        if create_post_field.exists:
            bot.log("ℹ️ Composer form is already open.")
            return True

        return False

    # Check initial view
    if _try_click_write():
        return True

    # If not found, scroll down (swipe up) up to 3 times
    for scroll_idx in range(3):
        bot.log(f"📜 [Scroll {scroll_idx + 1}/3] Scrolling down to find 'Write something...' button...")
        bot.swipe_up(scale=0.35)
        bot.smart_sleep(1.2)
        if _try_click_write():
            return True

    bot.log("❌ Could not find 'Write something...' button in group feed after 3 scrolls.")
    raise Exception("❌ Could not find 'Write something...' button.")


# ==============================================================================
# STEP 4: CLICK 'CREATE YOUR POST...' INPUT FIELD
# ==============================================================================

def click_create_post_input_field(bot: BaseAutomator, timeout: int = 15) -> Any:
    """
    STEP 4:
    - Finds and clicks 'Create your post...' / 'Tạo bài viết công khai...' text field.
    """
    bot.log("📝 [Step 4] Finding and focusing 'Create your post...' input field...")

    input_patterns = [
        r"(?i).*Create your post.*",
        r"(?i).*Tạo bài viết.*",
        r"(?i).*Bạn đang nghĩ gì.*",
        r"(?i).*Viết gì đó.*",
        r"(?i).*Hãy viết gì đó.*",
        r"(?i).*What's on your mind.*"
    ]

    start_time = time.time()
    while time.time() - start_time < timeout:
        if not bot.d:
            break

        # 1. By AutoCompleteTextView (Standard Facebook Composer text box)
        actv = bot.d(className="android.widget.AutoCompleteTextView")
        if actv.exists:
            bot.log("👆 Focusing AutoCompleteTextView composer field...")
            actv.click()
            bot.smart_sleep(1.5)
            return actv

        # 2. By EditText
        edit_tv = bot.d(className="android.widget.EditText")
        if edit_tv.exists:
            bot.log("👆 Focusing EditText composer field...")
            edit_tv.click()
            bot.smart_sleep(1.5)
            return edit_tv

        # 3. By text/description matching
        for p in input_patterns:
            field = bot.d(textMatches=p)
            if field.exists:
                bot.log(f"👆 Focusing composer field matching text: '{p}'...")
                field.click()
                bot.smart_sleep(1.5)
                return field

            field_desc = bot.d(descriptionMatches=p)
            if field_desc.exists:
                bot.log(f"👆 Focusing composer field matching desc: '{p}'...")
                field_desc.click()
                bot.smart_sleep(1.5)
                return field_desc

        bot.smart_sleep(1.0)

    bot.log("❌ Could not find 'Create your post...' field in composer.")
    raise Exception("❌ Could not find 'Create your post...' input field.")


# ==============================================================================
# STEP 5: PASTE REWRITTEN AI CONTENT OR DEFAULT TEMPLATE
# ==============================================================================

def paste_discussion_content(bot: BaseAutomator, content: str, timeout: int = 15) -> bool:
    """
    STEP 5:
    - Inputs post text content into the active composer field.
    """
    bot.log("💬 [Step 5] Inputting post content into composer text field...")

    if not content or not content.strip():
        content = "Thảo luận bài viết bất động sản chính chủ."

    # Try setting text on focused AutoCompleteTextView or EditText
    actv = bot.d(className="android.widget.AutoCompleteTextView") if bot.d else None
    edit_tv = bot.d(className="android.widget.EditText") if bot.d else None

    target_field = None
    if actv and actv.exists:
        target_field = actv
    elif edit_tv and edit_tv.exists:
        target_field = edit_tv

    if target_field:
        try:
            bot.log(f"📋 Setting text into input field ({len(content)} chars)...")
            target_field.set_text(content)
            bot.smart_sleep(1.5)
            return True
        except Exception as e:
            bot.log(f"⚠️ set_text failed ({e}), attempting fallback input_text...")

    # Fallback to bot.input_text
    bot.input_text(content)
    bot.smart_sleep(1.5)
    return True


# ==============================================================================
# STEP 6: CLICK 'DONE' / 'NEXT' BUTTON
# ==============================================================================

def click_done_or_next_button(bot: BaseAutomator, timeout: int = 10) -> bool:
    """
    STEP 6:
    - Clicks 'Done' / 'Next' / 'Xong' / 'Tiếp' button to complete text input mode.
    """
    bot.log("👌 [Step 6] Clicking 'Done' / 'Next' button after text input...")

    done_keywords = ["done", "xong", "next", "tiếp", "tiếp tục", "hoàn tất"]

    start_time = time.time()
    while time.time() - start_time < timeout:
        if not bot.d:
            break

        # 1. Check exact button by text or content-desc
        for kw in done_keywords:
            btn = bot.d(textMatches=f"(?i)^{kw}$")
            if btn.exists:
                bot.log(f"👆 Clicking '{kw}' button (via text)...")
                btn.click()
                bot.smart_sleep(1.5)
                return True

            btn_desc = bot.d(descriptionMatches=f"(?i)^{kw}$")
            if btn_desc.exists:
                bot.log(f"👆 Clicking '{kw}' button (via desc)...")
                btn_desc.click()
                bot.smart_sleep(1.5)
                return True

            w_btn = bot.get_button_by_text(kw, timeout=1)
            if w_btn and w_btn.exists:
                bot.log(f"👆 Clicking widget '{kw}'...")
                w_btn.click()
                bot.smart_sleep(1.5)
                return True

        # 2. Check if already back on the main composer view (e.g. Gallery button visible)
        gallery_btn = bot.d(textMatches=r"(?i).*Gallery.*|.*Ảnh.*|.*Ảnh/video.*") or bot.d(descriptionMatches=r"(?i).*Gallery.*|.*Ảnh.*|.*Ảnh/video.*")
        if gallery_btn.exists:
            bot.log("ℹ️ Already on main composer view with Gallery button visible.")
            return True

        bot.smart_sleep(1.0)

    bot.log("⚠️ 'Done' button not found or already dismissed. Hiding soft keyboard if needed...")
    try:
        bot.hide_keyboard()
        bot.smart_sleep(1.0)
    except Exception:
        pass
    return True


# ==============================================================================
# STEP 7: CLICK 'GALLERY' / 'PHOTO/VIDEO' BUTTON
# ==============================================================================

def click_gallery_button(bot: BaseAutomator, timeout: int = 15) -> bool:
    """
    STEP 7:
    - Finds and clicks 'Gallery' / 'Ảnh/video' / 'Ảnh' button to open media picker.
    """
    bot.log("🖼️ [Step 7] Finding and clicking 'Gallery' / 'Ảnh/video' button...")

    gallery_patterns = [
        r"(?i)^Gallery$",
        r"(?i)^Ảnh/video$",
        r"(?i)^Ảnh$",
        r"(?i)^Photo/video$",
        r"(?i)^Photo/Video$",
        r"(?i)^Thư viện ảnh$",
        r"(?i)^Bộ sưu tập$",
        r"(?i).*gallery.*",
        r"(?i).*ảnh/video.*",
        r"(?i).*photo/video.*"
    ]

    start_time = time.time()
    while time.time() - start_time < timeout:
        if not bot.d:
            break

        for p in gallery_patterns:
            btn_desc = bot.d(descriptionMatches=p)
            if btn_desc.exists:
                bot.log(f"👆 Clicking Gallery button (via desc: {p})...")
                btn_desc.click()
                bot.smart_sleep(2.0)
                return True

            btn_text = bot.d(textMatches=p)
            if btn_text.exists:
                bot.log(f"👆 Clicking Gallery button (via text: {p})...")
                btn_text.click()
                bot.smart_sleep(2.0)
                return True

        # Check if photo grid is already open
        photo_item = bot.d(descriptionMatches=r"(?i).*Photo, item \d+.*|.*Ảnh, mục \d+.*|.*Photo.*taken on.*")
        if photo_item.exists:
            bot.log("ℹ️ Media picker / Gallery is already open.")
            return True

        bot.smart_sleep(1.0)

    bot.log("❌ Could not find 'Gallery' / 'Ảnh/video' button.")
    raise Exception("❌ Could not find 'Gallery' / 'Ảnh/video' button.")


# ==============================================================================
# STEP 8: SELECT IMAGES (REVERSE 5-4-3-2-1 ORDER WITH DEDUPLICATION)
# ==============================================================================

def _has_selected_photos(bot: BaseAutomator) -> bool:
    """Checks if any photo is already selected in the gallery picker to prevent double clicking/deselection."""
    if not bot.d:
        return False
    try:
        if bot.d(className="android.widget.CompoundButton", checked=True).exists:
            return True
        if bot.d(className="android.widget.CompoundButton", selected=True).exists:
            return True
        if bot.d(className="android.widget.CheckBox", checked=True).exists:
            return True
        if bot.d(className="android.widget.CheckBox", selected=True).exists:
            return True
        if bot.d(className="android.widget.TextView", textMatches=r"^[1-9]\d*$").exists:
            return True
    except Exception:
        pass
    return False


def ensure_select_multiple_mode(bot: BaseAutomator) -> bool:
    """
    Checks if Facebook gallery picker has a 'Select multiple' / 'Chọn nhiều' button.
    If present and not already active, clicks it to enable multi-photo selection.
    """
    if not bot.d:
        return False
        
    try:
        # 1. Check text-based matches
        multi_text = bot.d(textMatches=r"(?i).*(select multiple|chọn nhiều|chọn nhiều ảnh|chọn nhiều mục).*")
        if multi_text.exists:
            info = multi_text.info
            if not info.get("selected") and not info.get("checked"):
                bot.log(f"👆 Found 'Select multiple' button (text='{info.get('text', '')}'). Clicking to enable multi-selection...")
                multi_text.click_exists(timeout=2)
                bot.smart_sleep(1.0)
                return True
            else:
                bot.log("ℹ️ 'Select multiple' mode is already active.")
                return True

        # 2. Check description-based matches
        multi_desc = bot.d(descriptionMatches=r"(?i).*(select multiple|chọn nhiều|chọn nhiều ảnh|chọn nhiều mục).*")
        if multi_desc.exists:
            info = multi_desc.info
            if not info.get("selected") and not info.get("checked"):
                bot.log(f"👆 Found 'Select multiple' button (desc='{info.get('contentDescription', '')}'). Clicking to enable multi-selection...")
                multi_desc.click_exists(timeout=2)
                bot.smart_sleep(1.0)
                return True
            else:
                bot.log("ℹ️ 'Select multiple' mode is already active.")
                return True

        # 3. Check resource-id based matches
        multi_id = bot.d(resourceIdMatches=r"(?i).*(select_multiple|multi_select|multiple_selection).*")
        if multi_id.exists:
            bot.log("👆 Found 'Select multiple' button by resourceId. Clicking to enable multi-selection...")
            multi_id.click_exists(timeout=2)
            bot.smart_sleep(1.0)
            return True

        # 4. Check buttons by text via helper
        for kw in ["select multiple", "chọn nhiều", "chọn nhiều ảnh", "chọn nhiều mục"]:
            b = bot.get_button_by_text(kw, timeout=1)
            if b and b.exists:
                bot.log(f"👆 Clicking '{kw}' button...")
                b.click_exists(timeout=2)
                bot.smart_sleep(1.0)
                return True

    except Exception as ex:
        logger.debug(f"Error checking 'Select multiple' mode: {ex}")

    return False


def select_pushed_images(bot: BaseAutomator, photo_count: int = 1, timeout: int = 15) -> int:
    """
    STEP 8:
    - Checks and enables 'Select multiple' mode if available.
    - Selects the pushed images from the gallery / Camera Roll picker.
    - STRICTLY selects in reverse order (5-4-3-2-1) so the first pushed photo (oldest) becomes Photo 1.
    - De-duplicates UI elements by bounds to prevent double-click deselection.
    Returns the number of selected photos.
    """
    bot.log(f"📸 [Step 8] Selecting {photo_count} image(s) from Gallery in reverse order...")

    start_time = time.time()
    photos_ready = False
    while time.time() - start_time < timeout:
        if not bot.d:
            break

        photo_elem = bot.d(descriptionMatches=r"(?i).*Photo, item \d+.*|.*Ảnh, mục \d+.*|.*Photo.*taken on.*|.*Ảnh.*chụp.*")
        grid = bot.d(className="android.widget.GridView")
        comp_btn = bot.d(className="android.widget.CompoundButton")

        if photo_elem.exists or grid.exists or comp_btn.exists:
            photos_ready = True
            break
        bot.smart_sleep(1.0)

    if not photos_ready:
        bot.log("⚠️ Photo grid not immediately detected, waiting a moment...")
        bot.smart_sleep(1.5)

    # 1. Check if photos are already selected: if so, skip to avoid deselecting
    if _has_selected_photos(bot):
        bot.log("📸 Photo(s) ALREADY selected in Gallery. Skipping re-selection to avoid deselecting!")
        return photo_count

    # 2. Enable multi-selection mode if 'Select multiple' button is present
    ensure_select_multiple_mode(bot)

    target_num = max(1, photo_count)
    selected_count = 0

    # 2. Collect unique photo clickable items (Primary: ViewGroup clickable / CompoundButton / Button with photo description)
    camera_images = bot.d(className="android.view.ViewGroup", clickable=True, descriptionMatches=r"(?i).*Photo.*taken on.*|.*Photo, item \d+.*|.*Ảnh.*chụp.*|.*Ảnh, mục \d+.*")
    if not camera_images.exists or camera_images.count == 0:
        camera_images = bot.d(className="android.widget.CompoundButton", descriptionMatches=r"(?i).*Photo.*taken on.*|.*Photo, item \d+.*|.*Ảnh.*chụp.*|.*Ảnh, mục \d+.*")
    if not camera_images.exists or camera_images.count == 0:
        camera_images = bot.d(className="android.widget.Button", descriptionMatches=r"(?i).*Photo.*taken on.*|.*Photo, item \d+.*|.*Ảnh.*chụp.*|.*Ảnh, mục \d+.*")
    if not camera_images.exists or camera_images.count == 0:
        camera_images = bot.d(descriptionMatches=r"(?i)^Photo, item \d+.*|^Ảnh, mục \d+.*")
    if not camera_images.exists or camera_images.count == 0:
        camera_images = bot.d(descriptionMatches=r"(?i).*Photo.*taken on.*|.*Ảnh.*chụp.*")
    if not camera_images.exists or camera_images.count == 0:
        camera_images = bot.d(className="android.widget.CheckBox")

    if camera_images.exists and camera_images.count > 0:
        # Deduplicate elements by bounds to ensure exactly 1 click per physical photo
        unique_items = []
        seen_bounds = set()
        for idx in range(camera_images.count):
            try:
                img = camera_images[idx]
                info = img.info
                b = info.get("bounds")
                if b:
                    key = (b.get("left") // 10, b.get("top") // 10, b.get("right") // 10, b.get("bottom") // 10)
                    if key not in seen_bounds:
                        seen_bounds.add(key)
                        unique_items.append((img, info))
            except Exception as ex:
                logger.debug(f"Error inspecting photo item {idx}: {ex}")

        if unique_items:
            unique_items.sort(key=lambda x: (x[1].get('bounds', {}).get('top', 0), x[1].get('bounds', {}).get('left', 0)))
            total_avail = len(unique_items)
            actual_num = min(total_avail, max(1, target_num))
            target_indices = list(range(total_avail - 1, total_avail - 1 - actual_num, -1))
            bot.log(f"📸 Gallery has {total_avail} photo(s). Selecting {actual_num} photo(s) from bottom up (indices: {target_indices})...")

            # Deselect any checked photo that is NOT in target_indices
            for i in range(total_avail):
                if i not in target_indices:
                    try:
                        img_widget, info = unique_items[i]
                        if info.get("checked") or info.get("selected"):
                            bot.log(f"   🧹 Deselecting stale photo at index {i}...")
                            img_widget.click_exists(timeout=2)
                            bot.smart_sleep(0.3)
                    except Exception:
                        pass

            # Select target photos from bottom up
            for order, idx in enumerate(target_indices, start=1):
                try:
                    img_widget, info = unique_items[idx]
                    img_widget.click_exists(timeout=2)
                    selected_count += 1
                    bot.log(f"   ✔️ Selected photo item {order}/{actual_num} (index {idx}, bottom-up)")
                    bot.smart_sleep(0.6)
                except Exception as ce:
                    logger.debug(f"Error selecting photo index {idx}: {ce}")

            return selected_count

    bot.log("⚠️ Could not locate photo elements in Gallery.")
    return selected_count


# ==============================================================================
# STEP 9: CLICK 'NEXT' BUTTON AFTER PHOTO SELECTION
# ==============================================================================

def click_next_after_photos(bot: BaseAutomator, timeout: int = 15) -> bool:
    """
    STEP 9:
    - Clicks 'Next' / 'Tiếp' button to confirm selected photos and return to composer.
    """
    bot.log("➡️ [Step 9] Clicking 'Next' / 'Tiếp' button to confirm selected photos...")

    next_keywords = ["next", "tiếp", "tiếp tục", "xong", "done", "chọn", "thêm"]

    start_time = time.time()
    while time.time() - start_time < timeout:
        if not bot.d:
            break

        # Check if already back on composer view with Post button visible
        post_btn = bot.d(textMatches=r"(?i)^Post$|^Đăng$") or bot.d(descriptionMatches=r"(?i)^Post$|^Đăng$")
        if post_btn.exists:
            bot.log("ℹ️ Returned to composer form. Post button is visible.")
            return True

        # 1. By text
        for kw in next_keywords:
            btn = bot.d(textMatches=f"(?i)^{kw}$")
            if btn.exists:
                bot.log(f"👆 Clicking '{kw}' button (via text)...")
                btn.click()
                bot.smart_sleep(2.0)
                return True

            desc_btn = bot.d(descriptionMatches=f"(?i)^{kw}$")
            if desc_btn.exists:
                bot.log(f"👆 Clicking '{kw}' button (via desc)...")
                desc_btn.click()
                bot.smart_sleep(2.0)
                return True

            w_btn = bot.get_button_by_text(kw, timeout=1)
            if w_btn and w_btn.exists:
                bot.log(f"👆 Clicking widget '{kw}'...")
                w_btn.click()
                bot.smart_sleep(2.0)
                return True

        bot.smart_sleep(1.0)

    bot.log("⚠️ Could not find Next button or already on composer form.")
    return True


# ==============================================================================
# STEP 10: CLICK 'POST' / 'ĐĂNG' BUTTON
# ==============================================================================

def click_post_button(bot: BaseAutomator, timeout: int = 25) -> bool:
    """
    STEP 10:
    - Finds and clicks 'Post' / 'Đăng' button in the top right of the composer.
    - Waits for post publication confirmation.
    """
    bot.log("🚀 [Step 10] Finding and clicking 'Post' / 'Đăng' button...")

    post_keywords = ["post", "đăng", "đăng bài", "publish", "chia sẻ"]

    start_time = time.time()
    clicked = False

    while time.time() - start_time < timeout:
        if not bot.d:
            break

        # 1. By exact text
        for kw in post_keywords:
            btn = bot.d(textMatches=f"(?i)^{kw}$")
            if btn.exists:
                bot.log(f"👆 Clicking '{kw}' button (via text)...")
                btn.click()
                clicked = True
                break

            desc_btn = bot.d(descriptionMatches=f"(?i)^{kw}$")
            if desc_btn.exists:
                bot.log(f"👆 Clicking '{kw}' button (via desc)...")
                desc_btn.click()
                clicked = True
                break

            w_btn = bot.get_button_by_text(kw, timeout=1)
            if w_btn and w_btn.exists:
                bot.log(f"👆 Clicking widget '{kw}'...")
                w_btn.click()
                clicked = True
                break

        if clicked:
            bot.log("⏳ Waiting for post to finish publishing (10s)...")
            bot.smart_sleep(10.0, 10.5)

            # Check if composer closed and returned to group feed
            write_box = bot.d(textMatches=r"(?i).*Write something.*|.*Viết gì đó.*|.*Bạn đang nghĩ gì.*")
            if write_box.exists or not bot.d(textMatches=r"(?i)^Post$|^Đăng$").exists:
                bot.log("🎉 Post successfully published!")
                return True
            else:
                bot.smart_sleep(2.0)
                return True

        bot.smart_sleep(1.0)

    if not clicked:
        bot.log("❌ Could not find or click 'Post' / 'Đăng' button.")
        raise Exception("❌ Could not find 'Post' / 'Đăng' button.")

    return True


# ==============================================================================
# MAIN ENTRY POINT: run_discussion_group
# ==============================================================================

def run_discussion_group(
    device_id: str, 
    job: Job, 
    logger_signal: "SignalInstance", 
    controllers: Optional["ControllerManager"] = None
) -> bool:
    """
    Main execution entry point for action 'discussion_group' (or 'fb_discussion_group').
    10-step Discussion Group Posting workflow:
    1. Navigate to Groups Tab List (or target group URL/ID) via Deep Link
    2. Select random group matching transaction_type (or load target group)
    3. Click 'Write something...' button
    4. Click 'Create your post...' input field
    5. Input discussion content (AI rewritten or template)
    6. Click 'Done' / 'Next'
    7. Click 'Gallery' / 'Ảnh/video' button (if images provided)
    8. Select pushed images in reverse (5-4-3-2-1) order with deduplication
    9. Click 'Next' to confirm photos
    10. Click 'Post' / 'Đăng' button and confirm publication
    """
    bot = BaseAutomator(device_id, logger_signal)

    user_id = 0
    if controllers and getattr(job, 'user_uuid', None) and getattr(controllers, 'user_controller', None):
        user_info = controllers.user_controller.get_by_id(job.user_uuid)
        user_id = user_info.user_id if user_info else 0
    else:
        user_id = int(job.parameters.get("user_id", 0))

    social_id = None
    if controllers and getattr(job, 'social_uuid', None) and getattr(controllers, 'social_controller', None):
        social_info = controllers.social_controller.get_by_id(job.social_uuid)
        if social_info and getattr(social_info, 'social_id', None):
            social_id = str(social_info.social_id).strip()

    if not social_id:
        social_id = job.parameters.get("social_id") or job.parameters.get("account_uid") or job.parameters.get("uid")

    account_uid = social_id or device_id

    if hasattr(bot, "__dict__"):
        bot.account_uid = account_uid

    current_step = "step_0_init"
    is_success = False

    try:
        # Extract parameters
        title = job.parameters.get("title", "")
        description = job.parameters.get("description", "")
        image_paths = job.parameters.get("image_paths", [])
        group_id = job.parameters.get("group_uid") or job.parameters.get("group_url") or ""
        transaction_type = job.parameters.get("transaction_type", "rental")
        max_scrolls = int(job.parameters.get("max_scrolls", 2))

        # Compose full post text content
        if title and description:
            full_content = f"{title}\n\n{description}"
        elif description:
            full_content = description
        elif title:
            full_content = title
        else:
            full_content = "Thảo luận chia sẻ thông tin bất động sản chính chủ Đà Lạt."

        # Step 0: Deploy media to user storage if provided
        current_step = "step_0_push_media"
        if image_paths:
            bot.log(f"📤 Pushing {len(image_paths)} image(s) to device (User {user_id})...")
            bot.push_media(image_paths, user_id)
            bot.smart_sleep(1.5)

        # Step 1: Open Groups tab list (or specific group if provided)
        current_step = "step_1_open_groups_tab_list"
        if group_id:
            clean_gid = str(group_id).strip().replace("https://www.facebook.com/groups/", "").strip("/")
            bot.log(f"🔗 [Step 1] Navigating directly to group {clean_gid}...")
            deeplink = f"fb://group/{clean_gid}"
            bot.launch_app("com.facebook.katana", deeplink)
            bot.smart_sleep(3.0)
        else:
            open_groups_tab_list(bot, timeout=20)

            # Step 2: Select random group matching transaction_type
            current_step = "step_2_select_random_group"
            select_random_group_by_transaction_type(
                bot, 
                transaction_type=transaction_type, 
                max_scrolls=max_scrolls, 
                timeout=15
            )

        # Step 3: Click 'Write something...' button
        current_step = "step_3_click_write_something"
        click_write_something_button(bot, timeout=15)

        # Step 4: Click 'Create your post...' input field
        current_step = "step_4_click_create_post_field"
        click_create_post_input_field(bot, timeout=15)

        # Step 5: Input rewritten AI / template content
        current_step = "step_5_paste_content"
        paste_discussion_content(bot, content=full_content, timeout=15)

        # Step 6: Click 'Done' / 'Next'
        current_step = "step_6_click_done_or_next"
        click_done_or_next_button(bot, timeout=10)

        # Step 7, 8, 9: If images available, open Gallery and select photos
        if image_paths:
            current_step = "step_7_click_gallery_button"
            click_gallery_button(bot, timeout=15)

            current_step = "step_8_select_pushed_images"
            photo_count = min(len(image_paths), 5)
            select_pushed_images(bot, photo_count=photo_count, timeout=15)

            current_step = "step_9_click_next_after_photos"
            click_next_after_photos(bot, timeout=15)

        # Step 10: Click 'Post' / 'Đăng' button
        current_step = "step_10_click_post_button"
        click_post_button(bot, timeout=25)

        is_success = True
        bot.log(f"🎉 Successfully completed Discussion Group action on {device_id}!")
        return True

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
        full_traceback = "".join(tb_details)
        logger.error(f"Full Traceback for {device_id} ({account_uid}) at {current_step} in discussion_group:\n{full_traceback}")
        raise e

    finally:
        if not is_success:
            dump_error_view(bot, account_uid=account_uid, step_name=f"error_{current_step}")
        bot.cleanup_media()
        if bot.d:
            bot.d.app_stop("com.facebook.katana")
        bot.teardown()
