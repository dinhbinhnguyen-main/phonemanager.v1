# src/automation/facebook/actions/join_group.py
import re
import sys
import traceback
from random import uniform
from typing import List, Optional, Union, TYPE_CHECKING
from src.entities import Job
from src.automation.core.base_automator import BaseAutomator
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.controllers._manager_controllers import ControllerManager
    from PySide6.QtCore import SignalInstance


def _extract_group_id(raw_input: str) -> str:
    """
    Extracts group ID from URL or returns clean numeric/alphanumeric string.
    e.g. 'https://www.facebook.com/groups/12345678/' -> '12345678'
    """
    raw_input = str(raw_input).strip()
    match = re.search(r'groups/([^/?]+)', raw_input)
    if match:
        return match.group(1)
    return raw_input


def run_join_group(
    device_id: str, 
    job: Job, 
    logger_signal: "SignalInstance", 
    controllers: Optional["ControllerManager"] = None
):
    """
    Automates joining one or multiple Facebook groups by ID/URL.
    
    Accepts:
    - job.parameters["group_uids"]: List[str] or multiline string.
    - job.parameters["group_uid"]: Single string fallback.
    - job.parameters["auto_rules"]: bool (auto tick rules agreement).
    - job.parameters["answer_text"]: str (default answer for admission questions).
    - job.parameters["delay_s"]: int (delay between multiple joins).
    """
    bot = BaseAutomator(device_id, logger_signal)
    
    try:
        raw_targets = job.parameters.get("group_uids") or job.parameters.get("group_uid", [])
        if isinstance(raw_targets, str):
            targets = [u.strip() for u in re.split(r'[\n,]+', raw_targets) if u.strip()]
        elif isinstance(raw_targets, (list, tuple)):
            targets = [str(u).strip() for u in raw_targets if str(u).strip()]
        else:
            targets = []

        if not targets:
            raise ValueError("No group UID or URL provided in job parameters.")

        auto_rules = job.parameters.get("auto_rules", True)
        answer_text = job.parameters.get("answer_text", "Em xin phép tham gia nhóm ạ")
        delay_s = int(job.parameters.get("delay_s", 10))

        total = len(targets)
        bot.log(f"📋 Starting Join Group sequence for {total} target group(s)...")

        success_count = 0
        for i, raw_target in enumerate(targets, start=1):
            group_id = _extract_group_id(raw_target)
            bot.log(f"[{i}/{total}] 🔗 Processing Group: {group_id} ({raw_target})...")

            try:
                joined = _join_single_group(bot, group_id, auto_rules, answer_text)
                if joined:
                    success_count += 1
            except Exception as ge:
                bot.log(f"⚠️ Error while joining group {group_id}: {ge}")

            # Sleep between consecutive groups to avoid spam flags
            if i < total:
                pause = delay_s + uniform(1.0, 3.0)
                bot.log(f"⏳ Waiting {pause:.1f}s before moving to next group...")
                bot.smart_sleep(pause)

        bot.log(f"🎉 Finished Join Group tasks: {success_count}/{total} groups processed successfully!")
        return True

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
        full_traceback = "".join(tb_details)
        logger.error(f"Error joining groups on {device_id}:\n{full_traceback}")
        raise e

    finally:
        bot.d.app_stop("com.facebook.katana")
        bot.teardown()


def _join_single_group(
    bot: BaseAutomator, 
    group_id: str, 
    auto_rules: bool, 
    answer_text: str
) -> bool:
    """
    Navigates to a single Facebook group and clicks join / handles questionnaire.
    """
    deeplink = f"fb://group/{group_id}"
    bot.launch_app("com.facebook.katana", deeplink)
    bot.smart_sleep(4)

    # 1. Check if already a member or pending request
    joined_btn = bot.get_button_by_text("đã tham gia", timeout=3)
    if not joined_btn.exists:
        joined_btn = bot.get_button_by_text("joined", timeout=2)
        
    if joined_btn.exists:
        bot.log(f"✔️ Already a member of group {group_id}. Skipping.")
        return True

    requested_btn = bot.get_button_by_text("đã gửi yêu cầu", timeout=2)
    if not requested_btn.exists:
        requested_btn = bot.get_button_by_text("requested", timeout=2)
    if not requested_btn.exists:
        requested_btn = bot.get_button_by_text("hủy yêu cầu", timeout=2)

    if requested_btn.exists:
        bot.log(f"ℹ️ Membership request already pending for group {group_id}. Skipping.")
        return True

    # 2. Find and click 'Join' button
    bot.log("🔍 Looking for 'Join' button...")
    join_btn = bot.get_button_by_text("tham gia nhóm", timeout=5)
    if not join_btn.exists:
        join_btn = bot.get_button_by_text("tham gia", timeout=3)
    if not join_btn.exists:
        join_btn = bot.get_button_by_text("join group", timeout=3)
    if not join_btn.exists:
        join_btn = bot.get_button_by_text("join", timeout=3)

    if not join_btn.exists:
        bot.log(f"⚠️ Could not find 'Join' button for {group_id}. Group might be private or restricted.")
        return False

    join_btn.click_exists(timeout=5)
    bot.log(f"👆 Clicked 'Join' button for group {group_id}. Checking for rules/questions...")
    bot.smart_sleep(3)

    # 3. Handle Rules agreement and Membership questions
    _handle_group_rules_and_questions(bot, auto_rules, answer_text)

    bot.smart_sleep(2)
    bot.log(f"✔️ Successfully submitted join request for group {group_id}!")
    return True


def _handle_group_rules_and_questions(bot: BaseAutomator, auto_rules: bool, answer_text: str):
    """
    Detects and handles membership admission dialogs:
    - Checks checkboxes for group rules.
    - Fills in EditText fields for required questions.
    - Clicks Submit/Gửi button.
    """
    # 1. Tick all rule checkboxes if enabled
    if auto_rules:
        checkboxes = bot.get_elements_by_widget("android.widget.CheckBox", timeout=3)
        if checkboxes.exists:
            bot.log(f"📋 Found {checkboxes.count} checkbox(es), agreeing to rules...")
            for i in range(checkboxes.count):
                cb = checkboxes[i]
                try:
                    if not cb.info.get("checked", False):
                        cb.click_exists(timeout=2)
                        bot.smart_sleep(0.5)
                except Exception:
                    pass

    # 2. Fill question edit fields if present
    edit_texts = bot.get_elements_by_widget("android.widget.EditText", timeout=2)
    if edit_texts.exists:
        bot.log(f"✍️ Found {edit_texts.count} question field(s). Filling answers...")
        for i in range(edit_texts.count):
            et = edit_texts[i]
            try:
                et.click_exists(timeout=2)
                et.send_keys(answer_text)
                bot.smart_sleep(0.5)
            except Exception:
                pass

    # 3. Look for Submit/Confirm buttons
    submit_keywords = ["gửi", "submit", "xác nhận", "hoàn tất", "xong", "done"]
    for kw in submit_keywords:
        btn = bot.get_button_by_text(kw, exact=False, timeout=2)
        if btn.exists:
            bot.log(f"📤 Submitting answers via '{kw}' button...")
            btn.click_exists(timeout=3)
            bot.smart_sleep(2)
            break
