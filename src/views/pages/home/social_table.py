# src/views/pages/home/social_table.py
from typing import List
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QTableView, QAbstractItemView, QMenu

from src.entities import Social
from src.models.table_model import SocialTableModel
from src.database.connection import DatabaseManager

class SocialTable(QTableView):
    socials_selected = Signal(list) 
    row_double_clicked = Signal(Social)
    log_msg = Signal(str)

    def __init__(self, controllers, parent=None):
        super().__init__(parent)
        self.controllers = controllers
        self._model = SocialTableModel(DatabaseManager())
        self.setModel(self._model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | 
            QAbstractItemView.EditTrigger.EditKeyPressed
        )

        self._hide_columns(["uuid", "created_at", "updated_at", "social_password"])
        self.doubleClicked.connect(self._on_row_double_clicked)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, pos):
        selected_indexes = self.selectionModel().selectedRows()
        if not selected_indexes:
            return
        
        socials = []
        for idx in selected_indexes:
            if idx.isValid():
                record = self._model.record(idx.row())
                socials.append(self._parse_social_from_record(record))
        
        if not socials:
            return

        menu = QMenu(self)
        
        launch_action = menu.addAction(f"🚀 Launch ({len(socials)} accounts)")
        launch_action.triggered.connect(lambda: self._launch_socials(socials))
        
        menu.addSeparator()
        
        delete_action = menu.addAction(f"🗑 Delete ({len(socials)} accounts)")
        delete_action.triggered.connect(lambda: self._delete_socials(socials))

        menu.exec(self.viewport().mapToGlobal(pos))

    # ==========================================
    # ACTION SLOTS
    # ==========================================
    def _launch_socials(self, socials: List[Social]):
        self.log_msg.emit(f"🚀 Scheduling launch for {len(socials)} social accounts...")
        
        redis_facade = self.controllers.service_manager.redis
        queued_count = 0

        from src.entities import Job
        from src.constants import Platform, JobAction, JobStatus

        for social in socials:
            if not social.user_uuid:
                self.log_msg.emit(f"⚠️ Skipping '{social.social_name}': Not linked to any Profile.")
                continue
                
            user = self.controllers.user_controller.get_by_id(social.user_uuid)
            if not user or not user.device_uuid:
                self.log_msg.emit(f"⚠️ Skipping '{social.social_name}': Target Device not found.")
                continue

            plat_str = str(social.social_platform).lower()
            if "tiktok" in plat_str or "tikok" in plat_str:
                platform = Platform.TIKTOK
                action = JobAction.TT__LAUNCH_APP
                deeplink = "musically://feed"  # Standard deep link for tiktok/musically
            else:
                platform = Platform.FACEBOOK
                action = JobAction.FB__LAUNCH_APP
                deeplink = "fb://feed"

            job = Job(
                name=f"Launch {social.social_platform.upper()} - {social.social_name}",
                social_uuid=social.uuid,
                user_uuid=user.uuid,
                device_uuid=user.device_uuid,
                platform=platform,
                action=action, 
                status=JobStatus.PENDING
            )
            job.parameters = {
                "open_scrcpy": True,
                "deeplink": deeplink,
            }

            try:
                redis_facade.jobs.push_job(job.to_dict())
                queued_count += 1
            except Exception as e:
                self.log_msg.emit(f"❌ Error pushing job for {social.social_name}: {e}")
        
        if queued_count > 0:
            self.log_msg.emit(f"✔️ Successfully queued {queued_count} launch jobs.")

    def _delete_socials(self, socials: List[Social]):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete these {len(socials)} accounts from the system?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        success_count = 0
        for social in socials:
            success = self.controllers.social_controller.delete(social.uuid)
            if success:
                success_count += 1
        
        self.log_msg.emit(f"🗑 Deleted {success_count}/{len(socials)} social accounts.")
        self.refresh_data()

    # Các hàm parse và refresh giữ nguyên
    def _hide_columns(self, column_names: list[str]):
        record = self._model.record()
        for i in range(record.count()):
            field_name = record.fieldName(i)
            self.setColumnHidden(i, field_name in column_names)

    def _parse_social_from_record(self, record) -> Social:
        return Social(
            uuid=record.value("uuid"),
            user_uuid=record.value("user_uuid"),
            social_id=record.value("social_id"),
            social_name=record.value("social_name"),
            social_password=record.value("social_password"),
            social_status=int(record.value("social_status") or 0),
            social_group=int(record.value("social_group") or 0),
            social_platform=record.value("social_platform"),
            social_note=str(record.value("social_note") or ""),
            created_at=record.value("created_at"),
            updated_at=record.value("updated_at")
        )

    def _on_selection_changed(self, selected, deselected):
        selected_socials = []
        for index in self.selectionModel().selectedRows():
            if index.isValid():
                record = self._model.record(index.row())
                social = self._parse_social_from_record(record)
                selected_socials.append(social)
        self.socials_selected.emit(selected_socials)

    def _on_row_double_clicked(self, index):
        if not index.isValid():
            return
        record = self._model.record(index.row())
        selected_social = self._parse_social_from_record(record)
        self.row_double_clicked.emit(selected_social)
        
    def refresh_data(self):
        self._model.select()