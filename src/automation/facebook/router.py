# src/automation/facebook/router.py
from typing import TYPE_CHECKING, Optional
from src.entities import Job
from src.constants import JobAction
from src.automation.facebook.actions.launch import run_launch_app
from src.automation.facebook.actions.list_marketplace_share import run_list_marketplace_share
from src.automation.facebook.actions.list_group_share import run_list_group_share
from src.automation.facebook.actions.scroll_feed import run_scroll_feed
from src.automation.facebook.actions.join_group import run_join_group
from src.automation.facebook.actions.post_group import run_post_group
from src.automation.facebook.actions.discussion_group import run_discussion_group
from src.automation.facebook.actions.single_listing import run_single_listing
from src.utils.logger import logger

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance
    from src.controllers._manager_controllers import ControllerManager


def resolve_job_content(job: Job, controllers: Optional["ControllerManager"] = None, logger_signal: Optional["SignalInstance"] = None) -> None:
    """
    Dynamically generates product content and triggers AI rewrite at execution time (Just-In-Time)
    instead of generating all jobs upfront at configuration save time.
    Enforces social_note constraints (sale -> only sale, rent -> only rental, with recent days filtering).
    """
    if not job or not job.parameters:
        return
        
    params = job.parameters
    source_type = params.get("source_type")
    
    # If custom content, ensure fields are mapped to standard keys
    if source_type == "custom_content":
        if "custom_title" in params:
            params["title"] = params.pop("custom_title", "")
        if "custom_desc" in params:
            params["description"] = params.pop("custom_desc", "")
        if "custom_images" in params:
            params["image_paths"] = params.pop("custom_images", [])
        return

    # If based on product_id or random_product
    if source_type in ["product_id", "random_product"]:
        if not controllers or not getattr(controllers, 'external_db_controller', None):
            logger.warning("Controllers or external_db_controller not available for content resolution.")
            return

        ext_ctrl = controllers.external_db_controller
        use_ai = params.get("use_ai", True)
        days = int(params.get("days", 7))
        pid = params.get("product_id")

        # ----------------------------------------------------
        # 📌 SOCIAL NOTE CONSTRAINT CHECKING
        # ----------------------------------------------------
        social = None
        if controllers and getattr(controllers, 'social_controller', None) and job.social_uuid:
            social = controllers.social_controller.get_by_id(job.social_uuid)

        social_note = ""
        if social and getattr(social, "social_note", None):
            social_note = str(social.social_note).strip().lower()
        elif params.get("social_note"):
            social_note = str(params.get("social_note")).strip().lower()

        # Constraints:
        # social_note == 'sale' -> ONLY sale products, NO fallback, filter by recent days
        # social_note == 'rent' / 'rental' -> ONLY rental products, NO fallback, filter by recent days
        if social_note in ["sale", "bán", "ban"] or "sale" in social_note:
            trans_type = "sale"
            allow_fallback = False
            if logger_signal:
                logger_signal.emit(f"📌 [Constraint: social_note='{social_note}'] Strictly selecting SALE products (last {days} days, no fallback).")
        elif social_note in ["rent", "rental", "thuê", "thue", "cho thuê"] or "rent" in social_note:
            trans_type = "rental"
            allow_fallback = False
            if logger_signal:
                logger_signal.emit(f"📌 [Constraint: social_note='{social_note}'] Strictly selecting RENTAL products (last {days} days, no fallback).")
        else:
            trans_type = params.get("transaction_type", "sale")
            allow_fallback = True

        if source_type == "product_id" and pid:
            existing_prod = ext_ctrl.get_by_pid(str(pid))
            if existing_prod:
                prod_trans_type = str(existing_prod.get("transaction_type", "")).lower()
                # If constrained by social_note and specified pid does not match
                if not allow_fallback and prod_trans_type != trans_type:
                    if logger_signal:
                        logger_signal.emit(f"⚠️ PID {pid} is '{prod_trans_type}', mismatch with social_note '{social_note}' ({trans_type}). Picking matching recent product...")
                    pid = ext_ctrl.get_random_pid(transaction_type=trans_type, days=days, allow_fallback=False)
            else:
                if logger_signal:
                    logger_signal.emit(f"⚠️ PID {pid} does not exist in DB. Selecting a random recent product ({trans_type})...")
                pid = ext_ctrl.get_random_pid(transaction_type=trans_type, days=days, allow_fallback=allow_fallback)
        else:
            pid = ext_ctrl.get_random_pid(transaction_type=trans_type, days=days, allow_fallback=allow_fallback)

        if not pid:
            msg = f"⚠️ No suitable recent product (within last {days} days) found for transaction type '{trans_type}' (allow_fallback={allow_fallback})."
            if logger_signal:
                logger_signal.emit(msg)
            logger.warning(msg)
            return

        if logger_signal:
            logger_signal.emit(f"🤖 [AI Just-In-Time] Generating content & rewriting with AI for PID {pid} ({trans_type})...")

        content = ext_ctrl.generate_content_by_pid(pid, use_ai=use_ai)
        if content:
            params["title"] = content.get("title", "")
            params["description"] = content.get("description", "")
            params["image_paths"] = content.get("image_paths", [])
            params["product_id"] = pid
            params["transaction_type"] = trans_type
            
            title_preview = params["title"][:40] if params.get("title") else "N/A"
            if logger_signal:
                logger_signal.emit(f"✨ Content successfully prepared for PID {pid}: '{title_preview}...'")
        else:
            msg = f"⚠️ Failed to generate content from PID {pid}."
            if logger_signal:
                logger_signal.emit(msg)
            logger.warning(msg)


def route_facebook_job(device_id: str, job: Job, logger_signal: "SignalInstance", controllers: "ControllerManager"):
    """
    Routes Facebook-specific automation tasks to their respective action handlers.
    
    This function acts as a dispatcher within the Facebook automation module, 
    identifying the required 'action' from the job entity and executing the 
    corresponding logic.
    
    Args:
        device_id (str): The identifier for the target Android device.
        job (Job): The job entity containing the action type and execution parameters.
        logger_signal (Optional[Signal]): Signal used to relay execution logs to the UI.
        
    Raises:
        ValueError: If the requested Facebook action is not recognized or implemented.
    """
    action = getattr(job, 'action', '')

    # Resolve dynamic content & AI rewrite just-in-time before execution
    if action in [
        JobAction.FB__POST_GROUP, 
        JobAction.FB__LIST_MARKETPLACE_AND_SHARE, 
        JobAction.FB__LIST_GROUP_SHARE, 
        "fb_list_group_share",
        JobAction.FB__DISCUSSION_GROUP,
        "fb_discussion_group",
        "discussion_group",
        JobAction.FB__SINGLE_LISTING,
        "fb_single_listing",
        "single_listing"
    ]:
        resolve_job_content(job, controllers, logger_signal)

    if action == JobAction.FB__LAUNCH_APP:
        run_launch_app(device_id, job, logger_signal)
        
    elif action == JobAction.FB__SCROLL_FEED:
        run_scroll_feed(device_id, job, logger_signal, controllers)
    elif action == JobAction.FB__INTERACT_FEED:
        logger.debug(job)
    elif action == JobAction.FB__JOIN_GROUP:
        run_join_group(device_id, job, logger_signal, controllers)
    elif action == JobAction.FB__POST_GROUP:
        run_post_group(device_id, job, logger_signal, controllers)
    elif action == JobAction.FB__INTERACT_TARGET:
        logger.debug(job)
    elif action == JobAction.FB__LIST_MARKETPLACE_AND_SHARE:
        run_list_marketplace_share(device_id, job, logger_signal, controllers)
    elif action == JobAction.FB__LIST_GROUP_SHARE or action == "fb_list_group_share":
        run_list_group_share(device_id, job, logger_signal, controllers)
    elif action == JobAction.FB__DISCUSSION_GROUP or action in ["fb_discussion_group", "discussion_group"]:
        run_discussion_group(device_id, job, logger_signal, controllers)
    elif action == JobAction.FB__SINGLE_LISTING or action in ["fb_single_listing", "single_listing"]:
        run_single_listing(device_id, job, logger_signal, controllers)
        
    else:
        raise ValueError(f"Facebook action '{action}' is not currently supported.")