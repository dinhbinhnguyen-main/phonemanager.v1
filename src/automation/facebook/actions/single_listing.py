# src/automation/facebook/actions/single_listing.py
"""
Facebook Single Listing Action (single_listing).
Iterates over N groups (default: 3 groups):
- Step 1: Opens Facebook Groups Tab List via deeplink ('fb://groups/tab/list').
- Step 2: Selects random group matching transaction_type (excluding already posted groups).
- Step 3: Analyzes group interface (Buy & Sell vs Discussion):
    - If Buy & Sell group ('What are you selling?' / 'Bạn đang bán gì?'):
        Executes listing flow with forward anchor verification:
        (Click sell -> Add photos -> Fill Adaptive Form -> Next -> Direct Publish).
    - If Discussion group ('Write something...' / 'Bạn viết gì đi...'):
        Executes discussion post flow with forward anchor verification:
        (Write text -> Add photos -> Next -> Post).
If any step fails anchor verification, dumps UI diagnostics (dumped_screen.png, dumped_view.json, dumped_view.xml)
saved in directory <uid>_<step>.
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

# Import steps from discussion_group
from src.automation.facebook.actions.discussion_group import (
    open_groups_tab_list,
    is_group_matching_transaction_type,
    _is_system_button,
    click_write_something_button,
    click_create_post_input_field,
    paste_discussion_content,
    click_done_or_next_button,
    click_gallery_button,
    select_pushed_images,
    click_next_after_photos,
    click_post_button,
)

# Import steps from list_group_share
from src.automation.facebook.actions.list_group_share import (
    click_what_are_you_selling,
    click_add_photos as click_add_photos_listing,
    fill_listing_details,
    click_next_button as click_next_listing,
    click_publish_or_done
)

if TYPE_CHECKING:
    from src.controllers._manager_controllers import ControllerManager
    from PySide6.QtCore import SignalInstance


# ==============================================================================
# UI DIAGNOSTIC DUMP HELPERS (<uid>_<step>)
# ==============================================================================

def dump_error_view(bot: BaseAutomator, account_uid: Optional[str] = None, step_name: str = "unknown_step"):
    """
    Automatically dumps UI hierarchy (XML, JSON, Screenshot) on error or missing anchor elements.
    Saved to: tests/dumps/errors/{safe_uid}_{safe_step}/
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

        bot.log(f"📸 [ERROR DUMP] Missing anchor / error at [{step_name}]. Auto-dumping UI to {output_dir}...")

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
                "timestamp": time.strftime("%Y%m%d_%H%M%S"),
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
# GROUP SELECTION WITH EXCLUSION SET
# ==============================================================================

def select_random_group_with_exclusion(
    bot: BaseAutomator,
    transaction_type: Optional[str] = "rental",
    excluded_groups: Optional[Set[str]] = None,
    max_scrolls: int = 2,
    timeout: int = 15
) -> str:
    """
    Scans groups in 'Your groups' tab and selects a random group matching transaction_type,
    excluding groups that were already posted to in this session.
    Anchor verification: Confirms navigation to group feed.
    """
    bot.log(f"🔍 Selecting random group matching transaction_type '{transaction_type}'...")

    if not bot.d:
        raise Exception("Device is not connected.")

    excluded = excluded_groups or set()

    # 1. Perform random scrolling to discover more groups
    actual_scrolls = random.randint(1, max(1, max_scrolls))
    bot.log(f"📜 Scrolling down {actual_scrolls} time(s) to discover groups...")
    for _ in range(actual_scrolls):
        bot.swipe_up(scale=random.uniform(0.4, 0.7))
        bot.smart_sleep(1.5)

    seen_titles: Set[str] = set()
    priority_candidates: List[Tuple[Any, str]] = []
    secondary_candidates: List[Tuple[Any, str]] = []

    def _collect_groups():
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

                # Skip already posted groups
                if group_title in excluded:
                    bot.log(f"   ⏩ Skipping already posted group: '{group_title}'")
                    continue

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

    _collect_groups()

    if not priority_candidates and not secondary_candidates:
        bot.log("ℹ️ No available groups on current view, scrolling slightly up to re-check...")
        bot.swipe_down(scale=0.3)
        bot.smart_sleep(1.5)
        _collect_groups()

    pool = priority_candidates if priority_candidates else secondary_candidates
    if not pool:
        bot.log(f"❌ No suitable new group found for transaction_type '{transaction_type}' (Excluded {len(excluded)} groups).")
        raise Exception(f"❌ [Anchor Failed] No matching unvisited groups found in Groups list tab for '{transaction_type}'.")

    chosen_elem, chosen_name = random.choice(pool)
    bot.log(f"🎯 Selected target Group: '{chosen_name}' (from {len(pool)} eligible candidates). Clicking...")
    chosen_elem.click()
    bot.smart_sleep(3.0)

    # Anchor verification: Wait for group feed page to load
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not bot.d:
            break
        write_box = bot.d(textMatches=r"(?i).*Write something.*|.*Viết gì đó.*|.*Bạn đang nghĩ gì.*|.*Bạn đang bán gì.*|.*What are you selling.*")
        write_desc = bot.d(descriptionMatches=r"(?i).*Write something.*|.*Viết gì đó.*|.*Bạn đang nghĩ gì.*|.*Bạn đang bán gì.*|.*What are you selling.*")
        group_feed = bot.d(textMatches=r"(?i).*Joined.*|.*Đã tham gia.*|.*Invite.*|.*Mời.*|.*Featured.*|.*Đáng chú ý.*")

        if write_box.exists or write_desc.exists or group_feed.exists:
            bot.log(f"✔️ [Anchor Verified] Successfully opened Group '{chosen_name}'!")
            return chosen_name
        bot.smart_sleep(1.0)

    bot.log(f"ℹ️ Proceeding with group '{chosen_name}'...")
    return chosen_name


# ==============================================================================
# GROUP MODE DETECTION (BUY & SELL VS DISCUSSION)
# ==============================================================================

def detect_group_post_mode(bot: BaseAutomator, timeout: int = 10) -> str:
    """
    Detects whether the current group feed supports 'SELL' (Buy & Sell listing) or 'DISCUSSION' (Discussion post).
    Returns 'SELL' or 'DISCUSSION'.
    """
    bot.log("🔍 Analyzing group interface (Buy & Sell vs Discussion, with up to 3 scroll attempts)...")

    sell_patterns = [
        r"(?i).*What are you selling.*",
        r"(?i).*Bạn đang bán gì.*",
        r"(?i).*Sell something.*",
        r"(?i).*Bán gì đó.*",
        r"(?i).*Tạo bài niêm yết.*"
    ]

    discussion_patterns = [
        r"(?i).*Write something.*",
        r"(?i).*Bạn viết gì đi.*",
        r"(?i).*Viết gì đó.*",
        r"(?i).*Bạn đang nghĩ gì.*",
        r"(?i).*Tạo bài viết.*",
        r"(?i).*Hãy viết gì đó.*"
    ]

    def _check_current_mode() -> Optional[str]:
        if not bot.d:
            return None

        # 1. Check for Buy & Sell indicators
        for p in sell_patterns:
            if bot.d(textMatches=p).exists or bot.d(descriptionMatches=p).exists:
                bot.log(f"🛒 Detected BUY & SELL group interface (matched '{p}').")
                return "SELL"

        # Check for Item button / ViewGroup
        if bot.d(textMatches=r"(?i)^Item$|^Mặt hàng$").exists:
            bot.log("🛒 Detected BUY & SELL group interface (found 'Item' button).")
            return "SELL"

        # 2. Check for Discussion indicators
        for p in discussion_patterns:
            if bot.d(textMatches=p).exists or bot.d(descriptionMatches=p).exists:
                bot.log(f"📝 Detected DISCUSSION group interface (matched '{p}').")
                return "DISCUSSION"

        return None

    # Check initial view
    detected = _check_current_mode()
    if detected:
        return detected

    # If not found, scroll down (swipe up) up to 3 times to find buttons
    for scroll_idx in range(3):
        bot.log(f"📜 [Scroll {scroll_idx + 1}/3] Scrolling down to find group post buttons...")
        bot.swipe_up(scale=0.35)
        bot.smart_sleep(1.2)
        detected = _check_current_mode()
        if detected:
            return detected

    bot.log("⚠️ Could not definitively detect mode after 3 scrolls. Defaulting to DISCUSSION.")
    return "DISCUSSION"


# ==============================================================================
# PIPELINE EXECUTION FOR SINGLE GROUP
# ==============================================================================

def execute_single_group_post(
    bot: BaseAutomator,
    params: Dict[str, Any],
    group_name: str,
    user_id: int = 0
) -> bool:
    """
    Executes posting flow to a single group, dynamically adapting between SELL and DISCUSSION.
    Verifies forward anchor point at each step.
    """
    bot.log(f"\n🚀 ===== POSTING TO GROUP: '{group_name}' =====")

    title = params.get("title", "")
    description = params.get("description", "")
    image_paths = params.get("image_paths", [])
    photo_count = len(image_paths) if image_paths else int(params.get("photo_num", 1))

    # Detect interface mode
    mode = detect_group_post_mode(bot, timeout=10)

    if mode == "SELL":
        bot.log("🛒 [Mode: SELL] Executing Buy & Sell Listing Flow...")

        # Step S1: Click 'What are you selling?' (Anchor: form or category picker opens)
        bot.log("👉 [Step S1] Clicking 'What are you selling?'...")
        click_what_are_you_selling(bot, timeout=20)

        # Step S2: Add photos (Anchor: photos attached, returned to listing form)
        bot.log(f"👉 [Step S2] Adding {photo_count} photo(s)...")
        click_add_photos_listing(bot, photo_num=photo_count, timeout=15, max_retries=20)

        # Step S3: Fill listing details (Adaptive form: Title, Price, Category, Condition, Location, Description)
        bot.log("👉 [Step S3] Filling listing details...")
        fill_listing_details(bot, params, max_scroll_cycles=5)

        # Step S4: Click Next (Anchor: transitions to publish screen)
        bot.log("👉 [Step S4] Clicking Next button...")
        click_next_listing(bot, timeout=15)

        # Step S5: Direct Publish
        bot.log("👉 [Step S5] Publishing listing to group...")
        click_publish_or_done(bot, timeout=30)
        bot.log("⏳ Waiting 10s after publishing before next step...")
        bot.smart_sleep(10.0, 10.5)

    else:
        bot.log("📝 [Mode: DISCUSSION] Executing Discussion Post Flow...")

        if title and description:
            full_content = f"{title}\n\n{description}"
        elif description:
            full_content = description
        elif title:
            full_content = title
        else:
            full_content = "Thảo luận chia sẻ thông tin bất động sản chính chủ Đà Lạt."

        # Step D1: Click 'Write something...' button (Anchor: composer opens)
        bot.log("👉 [Step D1] Clicking 'Write something...' button...")
        click_write_something_button(bot, timeout=15)

        # Step D2: Focus 'Create your post...' field (Anchor: field focused)
        bot.log("👉 [Step D2] Focusing 'Create your post...' field...")
        click_create_post_input_field(bot, timeout=15)

        # Step D3: Paste discussion content
        bot.log("👉 [Step D3] Pasting discussion content...")
        paste_discussion_content(bot, content=full_content, timeout=15)

        # Step D4: Click Done / Next (Anchor: returns to composer main view)
        bot.log("👉 [Step D4] Clicking Done / Next...")
        click_done_or_next_button(bot, timeout=10)

        # Step D5: Attach photos if available
        if image_paths:
            bot.log("👉 [Step D5] Opening Gallery & selecting photos...")
            click_gallery_button(bot, timeout=15)
            select_pushed_images(bot, photo_count=min(len(image_paths), 5), timeout=15)
            click_next_after_photos(bot, timeout=15)

        # Step D6: Click Post / Đăng (Anchor: post published and composer closed)
        bot.log("👉 [Step D6] Clicking 'Post' / 'Đăng' button...")
        click_post_button(bot, timeout=25)
        bot.log("⏳ Waiting 10s after posting before next step...")
        bot.smart_sleep(10.0, 10.5)

    bot.log(f"✔️ Successfully posted to group '{group_name}'!")
    return True


# ==============================================================================
# MAIN ENTRY POINT: run_single_listing
# ==============================================================================

def run_single_listing(
    device_id: str, 
    job: Job, 
    logger_signal: "SignalInstance", 
    controllers: Optional["ControllerManager"] = None
) -> bool:
    """
    Main execution entry point for action 'single_listing' (or 'fb_single_listing').
    Executes posting to N groups (default: 3 groups):
    - For each group:
      1. Opens Facebook Groups Tab List ('fb://groups/tab/list')
      2. Selects a random group matching transaction_type (avoiding already posted groups)
      3. Analyzes group UI (SELL vs DISCUSSION) and posts with forward anchor verification.
    Dumps UI diagnostics (dumped_screen.png, dumped_view.json, dumped_view.xml) in directory <uid>_<step> on error.
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

    total_groups_target = int(job.parameters.get("group_count") or job.parameters.get("target_groups_count") or 3)
    transaction_type = job.parameters.get("transaction_type", "rental")
    max_scrolls = int(job.parameters.get("max_scrolls", 2))
    image_paths = job.parameters.get("image_paths", [])

    bot.log(f"🎯 Starting 'single_listing' action on {device_id} (Target: {total_groups_target} groups, Trans: '{transaction_type}')...")

    posted_groups: Set[str] = set()
    current_step = "step_0_init"
    is_success = False

    try:
        # Step 0: Deploy media to user storage if provided
        current_step = "step_0_push_media"
        if image_paths:
            bot.log(f"📤 Pushing {len(image_paths)} image(s) to device (User {user_id})...")
            bot.push_media(image_paths, user_id)
            bot.smart_sleep(1.5)

        for group_idx in range(total_groups_target):
            bot.log(f"\n=======================================================")
            bot.log(f"📍 PROCESSING GROUP {group_idx + 1}/{total_groups_target} (Posted so far: {len(posted_groups)})")
            bot.log(f"=======================================================")

            # Step 1: Open Groups tab list
            current_step = f"step_1_open_groups_tab_g{group_idx + 1}"
            open_groups_tab_list(bot, timeout=20)

            # Step 2: Select random group matching transaction_type (excluding already posted)
            current_step = f"step_2_select_group_g{group_idx + 1}"
            chosen_group = select_random_group_with_exclusion(
                bot,
                transaction_type=transaction_type,
                excluded_groups=posted_groups,
                max_scrolls=max_scrolls,
                timeout=15
            )

            # Step 3: Detect mode and post
            current_step = f"step_3_post_to_group_g{group_idx + 1}"
            execute_single_group_post(
                bot=bot,
                params=job.parameters,
                group_name=chosen_group,
                user_id=user_id
            )

            posted_groups.add(chosen_group)
            bot.log(f"✅ Group {group_idx + 1}/{total_groups_target} ('{chosen_group}') completed successfully!")

            # Interval pause between groups
            if group_idx < total_groups_target - 1:
                pause_s = random.randint(3, 6)
                bot.log(f"⏳ Pausing {pause_s}s before next group...")
                bot.smart_sleep(pause_s)

        is_success = True
        bot.log(f"🎉 Successfully completed 'single_listing' on all {len(posted_groups)} groups!")
        return True

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
        full_traceback = "".join(tb_details)
        logger.error(f"Full Traceback for {device_id} ({account_uid}) at {current_step} in single_listing:\n{full_traceback}")
        raise e

    finally:
        if not is_success:
            dump_error_view(bot, account_uid=account_uid, step_name=f"error_{current_step}")
        bot.cleanup_media()
        if bot.d:
            bot.d.app_stop("com.facebook.katana")
        bot.teardown()
