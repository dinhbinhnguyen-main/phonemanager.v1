# tests/test_group_actions.py
import re
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from src.entities import Job
from src.constants import Platform, JobAction, JobStatus
from src.automation.facebook.actions.join_group import run_join_group
from src.automation.facebook.actions.post_group import run_post_group
from src.automation.facebook.actions.list_group_share import run_list_group_share


class MockLoggerSignal:
    def emit(self, message: str):
        print(f">>> [LOG] {message}")


def test_join_group(device_id: str, group_uids: str, delay: int = 5):
    uids = [u.strip() for u in re.split(r'[\n,]+', group_uids) if u.strip()]
    print(f"\n================ TEST JOIN GROUP TRÊN {device_id} ({len(uids)} nhóm) ================")
    job = Job(
        name="Test Join Group",
        platform=Platform.FACEBOOK,
        action=JobAction.FB__JOIN_GROUP,
        status=JobStatus.PENDING,
        parameters={
            "group_uids": uids,
            "group_uid": uids[0] if uids else "",
            "auto_rules": True,
            "answer_text": "Em xin phép tham gia nhóm ạ",
            "delay_s": delay
        }
    )
    mock_signal = MockLoggerSignal()
    run_join_group(device_id, job, mock_signal) # type: ignore
    print("================ KẾT THÚC TEST JOIN GROUP ================\n")


def test_post_group(device_id: str, group_uid: str, post_mode: str = "auto"):
    print(f"\n================ TEST POST GROUP TRÊN {device_id} (Mode: {post_mode}) ================")
    job = Job(
        name="Test Post Group",
        platform=Platform.FACEBOOK,
        action=JobAction.FB__POST_GROUP,
        status=JobStatus.PENDING,
        parameters={
            "group_uid": group_uid,
            "post_mode": post_mode,
            "title": "BÁN ĐẤT NỀN NGHỈ DƯỠNG ĐÀ LẠT VIEW ĐẸP",
            "description": "BÁN ĐẤT NỀN NGHỈ DƯỠNG ĐÀ LẠT VIEW ĐẸP\n- Diện tích: 200m2\n- Đường ô tô tới nơi\n- Liên hệ: 0375 155 525",
            "image_paths": []
        }
    )
    mock_signal = MockLoggerSignal()
    run_post_group(device_id, job, mock_signal) # type: ignore
    print("================ KẾT THÚC TEST POST GROUP ================\n")


def test_list_group_share(device_id: str, group_url: str = "", share_count: int = 20):
    print(f"\n================ TEST LIST GROUP SHARE TRÊN {device_id} ({group_url}) ================")
    job = Job(
        name="Test List Group Share",
        platform=Platform.FACEBOOK,
        action=JobAction.FB__LIST_GROUP_SHARE,
        status=JobStatus.PENDING,
        parameters={
            "group_url": group_url,
            "share_groups_count": share_count,
            "title": "BÁN ĐẤT NGHỈ DƯỠNG VIEW ĐẸP ĐÀ LẠT",
            "price": "1500000000",
            "location": "Da Lat",
            "transaction_type": "sale",
            "description": "Bán đất nghỉ dưỡng view thung lũng cực đẹp tại Đà Lạt. Sổ hồng riêng chính chủ, đường ô tô vào tận nơi.",
            "max_swipes": 10
        }
    )
    mock_signal = MockLoggerSignal()
    run_list_group_share(device_id, job, mock_signal) # type: ignore
    print("================ KẾT THÚC TEST LIST GROUP SHARE ================\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test Facebook Group Automation Actions")
    parser.add_argument("--device", type=str, default="330089d86bd75431", help="ADB Serial of target device")
    parser.add_argument("--group", type=str, default="https://www.facebook.com/groups/5857815244230418", help="Target Group ID or URL")
    parser.add_argument("--action", choices=["join", "post", "share"], default="share", help="Action to test (join, post, or share)")
    parser.add_argument("--mode", choices=["auto", "discussion", "sell"], default="auto", help="Post mode (for post action)")
    parser.add_argument("--count", type=int, default=20, help="Number of groups to share to (for share action)")

    args = parser.parse_args()

    if args.action == "join":
        test_join_group(args.device, args.group)
    elif args.action == "post":
        test_post_group(args.device, args.group, args.mode)
    elif args.action == "share":
        test_list_group_share(args.device, args.group, args.count)


