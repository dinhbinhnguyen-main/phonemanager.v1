# src/views/pages/facebook/facebook_action.py
import re
import os
from typing import Optional, List, Dict, Any, Tuple
from PySide6.QtWidgets import (
    QGroupBox, 
    QVBoxLayout, 
    QHBoxLayout, 
    QGridLayout, 
    QLabel, 
    QLineEdit, 
    QTextEdit, 
    QRadioButton, 
    QButtonGroup, 
    QSpinBox,
    QComboBox,
    QCheckBox,
    QWidget,
    QListWidget,
    QFileDialog,
    QAbstractItemView,
    QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence
from src.ui.facebook_action_ui import Ui_action
from src.constants import JobAction, FacebookReaction

class ImageDropWidget(QListWidget):
    """
    Custom QListWidget supporting Drag & Drop, Double-click, and Paste (Cmd+V / Ctrl+V) for multiple image selection.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setToolTip("Double-click to open file explorer.\nDrag and drop images here.\nPaste (Cmd+V / Ctrl+V) file paths.\nSelect and press Delete to remove.")
        self.setMaximumHeight(80) 

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                    self._add_image(path)

    def mouseDoubleClickEvent(self, event) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "", 
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        for f in files:
            self._add_image(f)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
        elif event.matches(QKeySequence.StandardKey.Paste) or (
            event.key() == Qt.Key.Key_V and (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        ):
            self._handle_paste()
        else:
            super().keyPressEvent(event)

    def _handle_paste(self) -> None:
        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()
        
        # 1. Kiểm tra URLs từ clipboard (copy file trực tiếp từ Finder/File Explorer)
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                        self._add_image(path)
            return

        # 2. Kiểm tra text path (paste chuỗi đường dẫn)
        if mime_data.hasText():
            text = mime_data.text().strip()
            lines = [line.strip().strip('"\'') for line in text.splitlines()]
            for line in lines:
                if os.path.exists(line) and line.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                    self._add_image(line)

    def _add_image(self, path: str) -> None:
        existing = [self.item(i).text() for i in range(self.count())]
        if path not in existing:
            self.addItem(path)

    def get_paths(self) -> List[str]:
        """Returns a list of all stored file paths."""
        return [self.item(i).text() for i in range(self.count())]


class FacebookAction(QGroupBox, Ui_action):
    """
    Component for configuring individual Facebook automation actions.
    Handles dynamic UI generation based on the selected action type.
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        self.action__content.setVisible(False)
        
        self.action__content_join_group_container = QWidget()
        self.action__content_join_group_layout = QVBoxLayout(self.action__content_join_group_container)
        self.action__content.addWidget(self.action__content_join_group_container)

        self.action__content_list_group_container = QWidget()
        self.action__content_list_group_layout = QVBoxLayout(self.action__content_list_group_container)
        self.action__content.addWidget(self.action__content_list_group_container)

        self.action__content_discussion_group_container = QWidget()
        self.action__content_discussion_group_layout = QVBoxLayout(self.action__content_discussion_group_container)
        self.action__content.addWidget(self.action__content_discussion_group_container)

        self.action__content_single_listing_container = QWidget()
        self.action__content_single_listing_layout = QVBoxLayout(self.action__content_single_listing_container)
        self.action__content.addWidget(self.action__content_single_listing_container)

        self.page_mapping = {
            JobAction.FB__SCROLL_FEED: self.action__content_scroll_feed_container,
            JobAction.FB__INTERACT_FEED: self.action__content_interact_feed_container,
            JobAction.FB__JOIN_GROUP: self.action__content_join_group_container,
            JobAction.FB__POST_GROUP: self.action__content_post_group_container,
            JobAction.FB__INTERACT_TARGET: self.action__content_interact_target_container,
            JobAction.FB__LIST_MARKETPLACE_AND_SHARE: self.action__content_list_marketplace_container,
            JobAction.FB__LIST_GROUP_SHARE: self.action__content_list_group_container,
            JobAction.FB__DISCUSSION_GROUP: self.action__content_discussion_group_container,
            JobAction.FB__SINGLE_LISTING: self.action__content_single_listing_container
        }

        self._setup_combobox()
        self._build_scroll_feed_ui()
        self._build_interact_feed_ui()
        self._build_interact_target_ui()
        self._build_join_group_ui()
        self._build_post_group_ui()
        self._build_list_marketplace_ui()
        self._build_list_group_ui()
        self._build_discussion_group_ui()
        self._build_single_listing_ui()
        
        self.action__actions_option.currentIndexChanged.connect(self._on_action_changed)
        self.action__delete_btn.clicked.connect(self.deleteLater)

    def _setup_combobox(self) -> None:
        options: List[Tuple[str, JobAction]] = [
            ("Scroll Feed", JobAction.FB__SCROLL_FEED),
            ("Interact Feed", JobAction.FB__INTERACT_FEED),
            ("Join Group", JobAction.FB__JOIN_GROUP),
            ("Post to Group", JobAction.FB__POST_GROUP),
            ("Interact with Target", JobAction.FB__INTERACT_TARGET),
            ("List Marketplace & Share", JobAction.FB__LIST_MARKETPLACE_AND_SHARE),
            ("List Group & Share", JobAction.FB__LIST_GROUP_SHARE),
            ("Discussion Group", JobAction.FB__DISCUSSION_GROUP),
            ("Single Listing (Auto 3 Groups)", JobAction.FB__SINGLE_LISTING),
        ]
        for label, enum_val in options:
            self.action__actions_option.addItem(label, userData=enum_val)


    def _on_action_changed(self, index: int) -> None:
        action_enum: Optional[JobAction] = self.action__actions_option.itemData(index)
        
        for i in range(self.action__content.count()):
            widget = self.action__content.widget(i)
            if not widget: continue
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        
        if not action_enum: 
            self.action__content.setVisible(False)
        else:
            self.action__content.setVisible(True)
            page = self.page_mapping.get(action_enum)
            if page:
                self.action__content.setCurrentWidget(page)
                page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                page.adjustSize()
                
        self.action__content.adjustSize()
        self.adjustSize()

    def _build_scroll_feed_ui(self) -> None:
        layout = self.action__content_scroll_feed_layout
        row = QHBoxLayout()
        row.addWidget(QLabel("Time (s):"))
        self.sf_time = QLineEdit()
        self.sf_time.setPlaceholderText("e.g. 60")
        row.addWidget(self.sf_time)
        layout.addLayout(row)
        layout.addStretch()

    def _build_interact_feed_ui(self) -> None:
        layout = self.action__content_interact_feed_layout
        row_time = QHBoxLayout()
        row_time.addWidget(QLabel("Time (s):"))
        self.if_time = QLineEdit()
        self.if_time.setPlaceholderText("e.g. 120")
        row_time.addWidget(self.if_time)
        layout.addLayout(row_time)

        layout.addWidget(QLabel("Reaction:"))
        self.if_react_group = QButtonGroup(self)
        
        react_grid = QGridLayout()
        react_grid.setSpacing(5)
        
        rb_none = QRadioButton("None")
        rb_none.setChecked(True)
        rb_none.setProperty("reaction_enum", None)
        self.if_react_group.addButton(rb_none, 0)
        react_grid.addWidget(rb_none, 0, 0)
        
        row, col = 0, 1
        for i, reaction in enumerate(FacebookReaction, start=1):
            rb = QRadioButton(reaction.value.capitalize())
            rb.setProperty("reaction_enum", reaction)
            self.if_react_group.addButton(rb, i)
            
            react_grid.addWidget(rb, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1
                
        layout.addLayout(react_grid)
        layout.addStretch()

    def _build_interact_target_ui(self) -> None:
        layout = self.action__content_interact_target_layout
        row_id = QHBoxLayout()
        row_id.addWidget(QLabel("Target Post/Page ID:"))
        self.it_target_id = QLineEdit()
        row_id.addWidget(self.it_target_id)
        layout.addLayout(row_id)
        
        row_time = QHBoxLayout()
        row_time.addWidget(QLabel("Time (s):"))
        self.it_time = QLineEdit()
        row_time.addWidget(self.it_time)
        layout.addLayout(row_time)
        
        layout.addWidget(QLabel("Comment:"))
        self.it_comment = QTextEdit()
        self.it_comment.setMaximumHeight(60)
        layout.addWidget(self.it_comment)
        
        layout.addWidget(QLabel("Reaction:"))
        self.it_react_group = QButtonGroup(self)
        
        react_grid = QGridLayout()
        react_grid.setSpacing(5)
        
        rb_none = QRadioButton("None")
        rb_none.setChecked(True)
        rb_none.setProperty("reaction_enum", None)
        self.it_react_group.addButton(rb_none, 0)
        react_grid.addWidget(rb_none, 0, 0)
        
        row, col = 0, 1
        for i, reaction in enumerate(FacebookReaction, start=1):
            rb = QRadioButton(reaction.value.capitalize())
            rb.setProperty("reaction_enum", reaction)
            self.it_react_group.addButton(rb, i)
            
            react_grid.addWidget(rb, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1
                
        layout.addLayout(react_grid)
        layout.addStretch()

    def _build_join_group_ui(self) -> None:
        layout = self.action__content_join_group_layout
        layout.addWidget(QLabel("Group UIDs / Links (Mỗi dòng 1 nhóm hoặc cách nhau dấu phẩy):"))
        self.jg_group_uids = QTextEdit()
        self.jg_group_uids.setPlaceholderText("e.g.\n123456789\nhttps://facebook.com/groups/987654321")
        self.jg_group_uids.setMaximumHeight(65)
        layout.addWidget(self.jg_group_uids)

        row_settings = QHBoxLayout()
        self.jg_auto_rules = QCheckBox("Auto accept rules (Đồng ý quy tắc nhóm)")
        self.jg_auto_rules.setChecked(True)
        row_settings.addWidget(self.jg_auto_rules)

        row_settings.addWidget(QLabel("Delay (s):"))
        self.jg_delay_s = QSpinBox()
        self.jg_delay_s.setRange(2, 300)
        self.jg_delay_s.setValue(10)
        row_settings.addWidget(self.jg_delay_s)
        layout.addLayout(row_settings)

        row_answer = QHBoxLayout()
        row_answer.addWidget(QLabel("Question Answer:"))
        self.jg_answer = QLineEdit()
        self.jg_answer.setPlaceholderText("e.g. Em xin phép tham gia nhóm ạ")
        row_answer.addWidget(self.jg_answer)
        layout.addLayout(row_answer)
        layout.addStretch()

    def _build_post_group_ui(self) -> None:
        layout = self.action__content_post_group_layout
        row_uid = QHBoxLayout()
        row_uid.addWidget(QLabel("Group UID / Link:"))
        self.pg_group_uid = QLineEdit()
        self.pg_group_uid.setPlaceholderText("e.g. 123456789 or group link")
        row_uid.addWidget(self.pg_group_uid)
        layout.addLayout(row_uid)

        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Post Mode:"))
        self.pg_mode_combo = QComboBox()
        self.pg_mode_combo.addItem("Auto (Tự động nhận diện)", "auto")
        self.pg_mode_combo.addItem("Discussion Post (Bài viết thảo luận)", "discussion")
        self.pg_mode_combo.addItem("Buy & Sell Listing (Tin bán hàng)", "sell")
        row_mode.addWidget(self.pg_mode_combo)
        layout.addLayout(row_mode)
        
        layout.addWidget(QLabel("Content Source:"))
        self.pg_source_group = QButtonGroup(self)
        
        source_grid = QGridLayout()
        source_grid.setSpacing(5)
        sources = ["Product ID", "Random Product", "Custom Content"]
        
        row, col = 0, 0
        for i, s in enumerate(sources):
            rb = QRadioButton(s)
            if i == 0: rb.setChecked(True)
            self.pg_source_group.addButton(rb, i)
            
            source_grid.addWidget(rb, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
                
        layout.addLayout(source_grid)

        self.pg_use_ai = QCheckBox("Sử dụng AI viết lại nội dung (Gemini AI)")
        self.pg_use_ai.setChecked(True)
        layout.addWidget(self.pg_use_ai)
        
        self.pg_pid_container = QWidget()
        pg_pid_layout = QVBoxLayout(self.pg_pid_container)
        pg_pid_layout.setContentsMargins(0, 0, 0, 0)
        row_pid = QHBoxLayout()
        row_pid.addWidget(QLabel("Product ID:"))
        self.pg_product_id = QLineEdit()
        row_pid.addWidget(self.pg_product_id)
        pg_pid_layout.addLayout(row_pid)
        
        self.pg_custom_container = QWidget()
        pg_custom_layout = QVBoxLayout(self.pg_custom_container)
        pg_custom_layout.setContentsMargins(0, 0, 0, 0)
        pg_custom_layout.addWidget(QLabel("Custom Title:"))
        self.pg_custom_title = QLineEdit()
        pg_custom_layout.addWidget(self.pg_custom_title)
        pg_custom_layout.addWidget(QLabel("Custom Description:"))
        self.pg_custom_desc = QTextEdit()
        self.pg_custom_desc.setMaximumHeight(50)
        pg_custom_layout.addWidget(self.pg_custom_desc)
        pg_custom_layout.addWidget(QLabel("Custom Images (Drag & Drop or Double-click):"))
        self.pg_custom_images = ImageDropWidget()
        pg_custom_layout.addWidget(self.pg_custom_images)
        
        layout.addWidget(self.pg_pid_container)
        layout.addWidget(self.pg_custom_container)
        self.pg_custom_container.setVisible(False)
        self.pg_source_group.idToggled.connect(self._on_pg_source_toggled)
        layout.addStretch()

    def _on_pg_source_toggled(self, btn_id: int, checked: bool) -> None:
        if checked:
            self.pg_pid_container.setVisible(btn_id == 0)
            self.pg_custom_container.setVisible(btn_id == 2)
            self.pg_use_ai.setVisible(btn_id != 2)

    def _build_list_marketplace_ui(self) -> None:
        layout = self.action__content_list_marketplace_layout
        row_share = QHBoxLayout()
        row_share.addWidget(QLabel("Number of Groups to Share:"))
        self.mp_share_count = QSpinBox()
        self.mp_share_count.setRange(0, 100)
        row_share.addWidget(self.mp_share_count)
        layout.addLayout(row_share)

        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Transaction Type:"))
        self.mp_transaction_type = QComboBox()
        self.mp_transaction_type.addItem("Rental", "rental")
        self.mp_transaction_type.addItem("Sale", "sale")
        row_type.addWidget(self.mp_transaction_type)
        layout.addLayout(row_type)
        
        layout.addWidget(QLabel("Content Source:"))
        self.mp_source_group = QButtonGroup(self)
        
        source_grid = QGridLayout()
        source_grid.setSpacing(5)
        sources = ["Product ID", "Random Product", "Custom Content"]
        
        row, col = 0, 0
        for i, s in enumerate(sources):
            rb = QRadioButton(s)
            if i == 0: rb.setChecked(True)
            self.mp_source_group.addButton(rb, i)
            
            source_grid.addWidget(rb, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
                
        layout.addLayout(source_grid)

        self.mp_use_ai = QCheckBox("Sử dụng AI viết lại nội dung (Gemini AI)")
        self.mp_use_ai.setChecked(True)
        layout.addWidget(self.mp_use_ai)
        
        self.mp_pid_container = QWidget()
        mp_pid_layout = QVBoxLayout(self.mp_pid_container)
        mp_pid_layout.setContentsMargins(0, 0, 0, 0)
        row_pid = QHBoxLayout()
        row_pid.addWidget(QLabel("Product ID:"))
        self.mp_product_id = QLineEdit()
        row_pid.addWidget(self.mp_product_id)
        mp_pid_layout.addLayout(row_pid)
        
        self.mp_custom_container = QWidget()
        mp_custom_layout = QVBoxLayout(self.mp_custom_container)
        mp_custom_layout.setContentsMargins(0, 0, 0, 0)
        mp_custom_layout.addWidget(QLabel("Custom Title:"))
        self.mp_custom_title = QLineEdit()
        mp_custom_layout.addWidget(self.mp_custom_title)
        mp_custom_layout.addWidget(QLabel("Custom Description:"))
        self.mp_custom_desc = QTextEdit()
        self.mp_custom_desc.setMaximumHeight(50)
        mp_custom_layout.addWidget(self.mp_custom_desc)
        mp_custom_layout.addWidget(QLabel("Custom Images (Drag & Drop or Double-click):"))
        self.mp_custom_images = ImageDropWidget()
        mp_custom_layout.addWidget(self.mp_custom_images)
        
        layout.addWidget(self.mp_pid_container)
        layout.addWidget(self.mp_custom_container)
        self.mp_custom_container.setVisible(False)
        self.mp_source_group.idToggled.connect(self._on_mp_source_toggled)
        layout.addStretch()

    def _on_mp_source_toggled(self, btn_id: int, checked: bool) -> None:
        if checked:
            self.mp_pid_container.setVisible(btn_id == 0)
            self.mp_custom_container.setVisible(btn_id == 2)
            self.mp_use_ai.setVisible(btn_id != 2)

    def _build_list_group_ui(self) -> None:
        layout = self.action__content_list_group_layout
        
        row_target = QHBoxLayout()
        row_target.addWidget(QLabel("Target Group (UID / URL):"))
        self.lg_group_uid = QLineEdit()
        self.lg_group_uid.setPlaceholderText("e.g. 5857815244230418 or https://facebook.com/groups/...")
        row_target.addWidget(self.lg_group_uid)
        layout.addLayout(row_target)

        row_share = QHBoxLayout()
        row_share.addWidget(QLabel("Number of Groups to Share:"))
        self.lg_share_count = QSpinBox()
        self.lg_share_count.setRange(0, 20)
        self.lg_share_count.setValue(20)
        row_share.addWidget(self.lg_share_count)
        layout.addLayout(row_share)

        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Transaction Type:"))
        self.lg_transaction_type = QComboBox()
        self.lg_transaction_type.addItem("Sale", "sale")
        self.lg_transaction_type.addItem("Rental", "rental")
        row_type.addWidget(self.lg_transaction_type)
        layout.addLayout(row_type)
        
        layout.addWidget(QLabel("Content Source:"))
        self.lg_source_group = QButtonGroup(self)
        
        source_grid = QGridLayout()
        source_grid.setSpacing(5)
        sources = ["Product ID", "Random Product", "Custom Content"]
        
        row, col = 0, 0
        for i, s in enumerate(sources):
            rb = QRadioButton(s)
            if i == 0: rb.setChecked(True)
            self.lg_source_group.addButton(rb, i)
            
            source_grid.addWidget(rb, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
                
        layout.addLayout(source_grid)

        self.lg_use_ai = QCheckBox("Sử dụng AI viết lại nội dung (Gemini AI)")
        self.lg_use_ai.setChecked(True)
        layout.addWidget(self.lg_use_ai)
        
        self.lg_pid_container = QWidget()
        lg_pid_layout = QVBoxLayout(self.lg_pid_container)
        lg_pid_layout.setContentsMargins(0, 0, 0, 0)
        row_pid = QHBoxLayout()
        row_pid.addWidget(QLabel("Product ID:"))
        self.lg_product_id = QLineEdit()
        row_pid.addWidget(self.lg_product_id)
        lg_pid_layout.addLayout(row_pid)
        
        self.lg_custom_container = QWidget()
        lg_custom_layout = QVBoxLayout(self.lg_custom_container)
        lg_custom_layout.setContentsMargins(0, 0, 0, 0)
        lg_custom_layout.addWidget(QLabel("Custom Title:"))
        self.lg_custom_title = QLineEdit()
        lg_custom_layout.addWidget(self.lg_custom_title)
        lg_custom_layout.addWidget(QLabel("Custom Description:"))
        self.lg_custom_desc = QTextEdit()
        self.lg_custom_desc.setMaximumHeight(50)
        lg_custom_layout.addWidget(self.lg_custom_desc)
        lg_custom_layout.addWidget(QLabel("Custom Images (Drag & Drop or Double-click):"))
        self.lg_custom_images = ImageDropWidget()
        lg_custom_layout.addWidget(self.lg_custom_images)
        
        layout.addWidget(self.lg_pid_container)
        layout.addWidget(self.lg_custom_container)
        self.lg_custom_container.setVisible(False)
        self.lg_source_group.idToggled.connect(self._on_lg_source_toggled)
        layout.addStretch()

    def _on_lg_source_toggled(self, btn_id: int, checked: bool) -> None:
        if checked:
            self.lg_pid_container.setVisible(btn_id == 0)
            self.lg_custom_container.setVisible(btn_id == 2)
            self.lg_use_ai.setVisible(btn_id != 2)

    def _build_discussion_group_ui(self) -> None:
        layout = self.action__content_discussion_group_layout
        
        row_target = QHBoxLayout()
        row_target.addWidget(QLabel("Target Group (UID / URL - Optional):"))
        self.dg_group_uid = QLineEdit()
        self.dg_group_uid.setPlaceholderText("Leave empty for auto/random group matching transaction type")
        row_target.addWidget(self.dg_group_uid)
        layout.addLayout(row_target)

        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Transaction Type:"))
        self.dg_transaction_type = QComboBox()
        self.dg_transaction_type.addItem("Rental (Cho thuê)", "rental")
        self.dg_transaction_type.addItem("Sale (Bán / Mua bán)", "sale")
        row_type.addWidget(self.dg_transaction_type)

        row_type.addWidget(QLabel("Max Scrolls:"))
        self.dg_max_scrolls = QSpinBox()
        self.dg_max_scrolls.setRange(0, 10)
        self.dg_max_scrolls.setValue(2)
        row_type.addWidget(self.dg_max_scrolls)
        layout.addLayout(row_type)
        
        layout.addWidget(QLabel("Content Source:"))
        self.dg_source_group = QButtonGroup(self)
        
        source_grid = QGridLayout()
        source_grid.setSpacing(5)
        sources = ["Product ID", "Random Product", "Custom Content"]
        
        row, col = 0, 0
        for i, s in enumerate(sources):
            rb = QRadioButton(s)
            if i == 0: rb.setChecked(True)
            self.dg_source_group.addButton(rb, i)
            
            source_grid.addWidget(rb, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
                
        layout.addLayout(source_grid)

        self.dg_use_ai = QCheckBox("Sử dụng AI viết lại nội dung (Gemini AI)")
        self.dg_use_ai.setChecked(True)
        layout.addWidget(self.dg_use_ai)
        
        self.dg_pid_container = QWidget()
        dg_pid_layout = QVBoxLayout(self.dg_pid_container)
        dg_pid_layout.setContentsMargins(0, 0, 0, 0)
        row_pid = QHBoxLayout()
        row_pid.addWidget(QLabel("Product ID:"))
        self.dg_product_id = QLineEdit()
        row_pid.addWidget(self.dg_product_id)
        dg_pid_layout.addLayout(row_pid)
        
        self.dg_custom_container = QWidget()
        dg_custom_layout = QVBoxLayout(self.dg_custom_container)
        dg_custom_layout.setContentsMargins(0, 0, 0, 0)
        dg_custom_layout.addWidget(QLabel("Custom Title:"))
        self.dg_custom_title = QLineEdit()
        dg_custom_layout.addWidget(self.dg_custom_title)
        dg_custom_layout.addWidget(QLabel("Custom Description:"))
        self.dg_custom_desc = QTextEdit()
        self.dg_custom_desc.setMaximumHeight(50)
        dg_custom_layout.addWidget(self.dg_custom_desc)
        dg_custom_layout.addWidget(QLabel("Custom Images (Drag & Drop or Double-click):"))
        self.dg_custom_images = ImageDropWidget()
        dg_custom_layout.addWidget(self.dg_custom_images)
        
        layout.addWidget(self.dg_pid_container)
        layout.addWidget(self.dg_custom_container)
        self.dg_custom_container.setVisible(False)
        self.dg_source_group.idToggled.connect(self._on_dg_source_toggled)
        layout.addStretch()

    def _on_dg_source_toggled(self, btn_id: int, checked: bool) -> None:
        if checked:
            self.dg_pid_container.setVisible(btn_id == 0)
            self.dg_custom_container.setVisible(btn_id == 2)
            self.dg_use_ai.setVisible(btn_id != 2)

    def _build_single_listing_ui(self) -> None:
        layout = self.action__content_single_listing_layout
        
        row_count = QHBoxLayout()
        row_count.addWidget(QLabel("Number of Groups:"))
        self.sl_group_count = QSpinBox()
        self.sl_group_count.setRange(1, 20)
        self.sl_group_count.setValue(3)
        row_count.addWidget(self.sl_group_count)

        row_count.addWidget(QLabel("Transaction Type:"))
        self.sl_transaction_type = QComboBox()
        self.sl_transaction_type.addItem("Sale (Bán / Mua bán)", "sale")
        self.sl_transaction_type.addItem("Rental (Cho thuê)", "rental")
        row_count.addWidget(self.sl_transaction_type)

        row_count.addWidget(QLabel("Max Scrolls:"))
        self.sl_max_scrolls = QSpinBox()
        self.sl_max_scrolls.setRange(0, 10)
        self.sl_max_scrolls.setValue(2)
        row_count.addWidget(self.sl_max_scrolls)
        layout.addLayout(row_count)
        
        layout.addWidget(QLabel("Content Source:"))
        self.sl_source_group = QButtonGroup(self)
        
        source_grid = QGridLayout()
        source_grid.setSpacing(5)
        sources = ["Product ID", "Random Product", "Custom Content"]
        
        row, col = 0, 0
        for i, s in enumerate(sources):
            rb = QRadioButton(s)
            if i == 0: rb.setChecked(True)
            self.sl_source_group.addButton(rb, i)
            
            source_grid.addWidget(rb, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
                
        layout.addLayout(source_grid)

        self.sl_use_ai = QCheckBox("Sử dụng AI viết lại nội dung (Gemini AI)")
        self.sl_use_ai.setChecked(True)
        layout.addWidget(self.sl_use_ai)
        
        self.sl_pid_container = QWidget()
        sl_pid_layout = QVBoxLayout(self.sl_pid_container)
        sl_pid_layout.setContentsMargins(0, 0, 0, 0)
        row_pid = QHBoxLayout()
        row_pid.addWidget(QLabel("Product ID:"))
        self.sl_product_id = QLineEdit()
        row_pid.addWidget(self.sl_product_id)
        sl_pid_layout.addLayout(row_pid)
        
        self.sl_custom_container = QWidget()
        sl_custom_layout = QVBoxLayout(self.sl_custom_container)
        sl_custom_layout.setContentsMargins(0, 0, 0, 0)
        sl_custom_layout.addWidget(QLabel("Custom Title:"))
        self.sl_custom_title = QLineEdit()
        sl_custom_layout.addWidget(self.sl_custom_title)
        sl_custom_layout.addWidget(QLabel("Custom Description:"))
        self.sl_custom_desc = QTextEdit()
        self.sl_custom_desc.setMaximumHeight(50)
        sl_custom_layout.addWidget(self.sl_custom_desc)
        sl_custom_layout.addWidget(QLabel("Custom Images (Drag & Drop or Double-click):"))
        self.sl_custom_images = ImageDropWidget()
        sl_custom_layout.addWidget(self.sl_custom_images)
        
        layout.addWidget(self.sl_pid_container)
        layout.addWidget(self.sl_custom_container)
        self.sl_custom_container.setVisible(False)
        self.sl_source_group.idToggled.connect(self._on_sl_source_toggled)
        layout.addStretch()

    def _on_sl_source_toggled(self, btn_id: int, checked: bool) -> None:
        if checked:
            self.sl_pid_container.setVisible(btn_id == 0)
            self.sl_custom_container.setVisible(btn_id == 2)
            self.sl_use_ai.setVisible(btn_id != 2)

    def get_value(self) -> Optional[dict]:
        """
        Extracts configuration data from UI elements.
        
        Returns:
            dict: Configuration parameters mapped to JobAction, or None if widget is inactive.
        """
        if not self.isEnabled() or not self.isVisible(): 
            return None
        action: Optional[JobAction] = self.action__actions_option.currentData()
        if not action:
            return None 
        data: Dict[str, Any] = {
            "action": action, 
            "params": {}
        }
        source_keys: List[str] = ["product_id", "random_product", "custom_content"]

        if action == JobAction.FB__SCROLL_FEED:
            data["params"]["time_s"] = self.sf_time.text()

        elif action == JobAction.FB__INTERACT_FEED:
            data["params"]["time_s"] = self.if_time.text()
            btn = self.if_react_group.checkedButton()
            data["params"]["reaction"] = btn.property("reaction_enum") if btn else None

        elif action == JobAction.FB__INTERACT_TARGET:
            data["params"]["target_id"] = self.it_target_id.text()
            data["params"]["time_s"] = self.it_time.text()
            data["params"]["comment"] = self.it_comment.toPlainText()
            btn = self.it_react_group.checkedButton()
            data["params"]["reaction"] = btn.property("reaction_enum") if btn else None

        elif action == JobAction.FB__JOIN_GROUP:
            raw_text = self.jg_group_uids.toPlainText()
            uids = [u.strip() for u in re.split(r'[\n,]+', raw_text) if u.strip()]
            data["params"]["group_uids"] = uids
            data["params"]["group_uid"] = uids[0] if uids else ""
            data["params"]["auto_rules"] = self.jg_auto_rules.isChecked()
            data["params"]["answer_text"] = self.jg_answer.text()
            data["params"]["delay_s"] = self.jg_delay_s.value()

        elif action == JobAction.FB__POST_GROUP:
            data["params"]["group_uid"] = self.pg_group_uid.text()
            data["params"]["post_mode"] = self.pg_mode_combo.currentData()
            source_id = self.pg_source_group.checkedId()
            data["params"]["source_type"] = source_keys[source_id]
            data["params"]["use_ai"] = self.pg_use_ai.isChecked() if source_id != 2 else False
            if source_id == 0:
                data["params"]["product_id"] = self.pg_product_id.text()
            elif source_id == 2:
                data["params"]["custom_title"] = self.pg_custom_title.text()
                data["params"]["custom_desc"] = self.pg_custom_desc.toPlainText()
                data["params"]["custom_images"] = self.pg_custom_images.get_paths()

        elif action == JobAction.FB__LIST_MARKETPLACE_AND_SHARE:
            data["params"]["share_groups_count"] = self.mp_share_count.value()
            data["params"]["transaction_type"] = self.mp_transaction_type.currentData() or self.mp_transaction_type.currentText().lower()
            source_id = self.mp_source_group.checkedId()
            data["params"]["source_type"] = source_keys[source_id]
            data["params"]["use_ai"] = self.mp_use_ai.isChecked() if source_id != 2 else False
            if source_id == 0:
                data["params"]["product_id"] = self.mp_product_id.text()
            elif source_id == 2:
                data["params"]["custom_title"] = self.mp_custom_title.text()
                data["params"]["custom_desc"] = self.mp_custom_desc.toPlainText()
                data["params"]["custom_images"] = self.mp_custom_images.get_paths()

        elif action == JobAction.FB__LIST_GROUP_SHARE:
            data["params"]["group_url"] = self.lg_group_uid.text()
            data["params"]["group_uid"] = self.lg_group_uid.text()
            data["params"]["share_groups_count"] = self.lg_share_count.value()
            data["params"]["transaction_type"] = self.lg_transaction_type.currentData() or self.lg_transaction_type.currentText().lower()
            source_id = self.lg_source_group.checkedId()
            data["params"]["source_type"] = source_keys[source_id]
            data["params"]["use_ai"] = self.lg_use_ai.isChecked() if source_id != 2 else False
            if source_id == 0:
                data["params"]["product_id"] = self.lg_product_id.text()
            elif source_id == 2:
                data["params"]["custom_title"] = self.lg_custom_title.text()
                data["params"]["custom_desc"] = self.lg_custom_desc.toPlainText()
                data["params"]["custom_images"] = self.lg_custom_images.get_paths()

        elif action == JobAction.FB__DISCUSSION_GROUP:
            data["params"]["group_uid"] = self.dg_group_uid.text()
            data["params"]["transaction_type"] = self.dg_transaction_type.currentData() or self.dg_transaction_type.currentText().lower()
            data["params"]["max_scrolls"] = self.dg_max_scrolls.value()
            source_id = self.dg_source_group.checkedId()
            data["params"]["source_type"] = source_keys[source_id]
            data["params"]["use_ai"] = self.dg_use_ai.isChecked() if source_id != 2 else False
            if source_id == 0:
                data["params"]["product_id"] = self.dg_product_id.text()
            elif source_id == 2:
                data["params"]["custom_title"] = self.dg_custom_title.text()
                data["params"]["custom_desc"] = self.dg_custom_desc.toPlainText()
                data["params"]["custom_images"] = self.dg_custom_images.get_paths()

        elif action == JobAction.FB__SINGLE_LISTING:
            data["params"]["group_count"] = self.sl_group_count.value()
            data["params"]["transaction_type"] = self.sl_transaction_type.currentData() or self.sl_transaction_type.currentText().lower()
            data["params"]["max_scrolls"] = self.sl_max_scrolls.value()
            source_id = self.sl_source_group.checkedId()
            data["params"]["source_type"] = source_keys[source_id]
            data["params"]["use_ai"] = self.sl_use_ai.isChecked() if source_id != 2 else False
            if source_id == 0:
                data["params"]["product_id"] = self.sl_product_id.text()
            elif source_id == 2:
                data["params"]["custom_title"] = self.sl_custom_title.text()
                data["params"]["custom_desc"] = self.sl_custom_desc.toPlainText()
                data["params"]["custom_images"] = self.sl_custom_images.get_paths()

        return data