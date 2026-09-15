# src/services/external_data_service.py
import os
import sys
import re
import random
from typing import List, Optional, Dict, Any
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from src.repositories.external_data_repo import ExternalDataRepository
from src.entities import (
    RealEstateProduct, 
    RealEstateTemplate, 
    RealEstateTemplate__Name,
    RealEstateProduct__TransactionType,
    RealEstateProduct__Category
)
from src.utils.mapper import enrich_real_estate_product
from src.utils.logger import logger
from src.utils.yaml_handler import realestate_config
from src.services.gemini_service import GeminiService

SETTING_FIELD_MAP: Dict[str, str] = {
    "transaction_type": "transactions",
    "status": "status",
    "category": "categories",
    "province": "provinces",
    "district": "districts",
    "ward": "wards",
    "building_line": "building_lines",
    "legal": "legals",
    "furniture": "furniture",
}


class ExternalDataService:
    """
    Service layer for managing external real estate data operations.
    Handles product retrieval, content generation through template processing, 
    AI rewriting via Gemini, and image resource management.
    """
    def __init__(self, repository: ExternalDataRepository, gemini_service: Optional[GeminiService] = None):
        self.repo = repository
        self.image_container_dir = repository.image_container_dir
        self.gemini_service = gemini_service or GeminiService()

    def get_all_products_raw(self) -> List[RealEstateProduct]:
        """
        Retrieves all real estate products in their raw entity format.
        """
        return self.repo.get_all_products()

    def get_all_products_display(self) -> List[Dict[str, Any]]:
        """
        Retrieves all real estate products enriched with display-friendly values.
        """
        products = self.repo.get_all_products()
        return [enrich_real_estate_product(p) for p in products]

    def get_product_pids(self) -> List[str]:
        """
        Retrieves a list of all available Product IDs (PIDs).
        """
        return self.repo.get_all_pid()

    def get_product_details(self, pid: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves details for a specific product by its PID and enriches it for display.
        """
        product = self.repo.get_one_product(pid)
        if product:
            return enrich_real_estate_product(product)
        return None

    def _normalize_transaction_type(
        self, transaction_type: Any
    ) -> RealEstateProduct__TransactionType:
        """
        Normalizes various transaction_type representations (Enum, str, int)
        to RealEstateProduct__TransactionType. Defaults to SALE.
        """
        if isinstance(transaction_type, RealEstateProduct__TransactionType):
            return transaction_type
        if isinstance(transaction_type, int):
            try:
                return list(RealEstateProduct__TransactionType)[transaction_type]
            except (IndexError, ValueError):
                return RealEstateProduct__TransactionType.SALE
        if isinstance(transaction_type, str):
            val = transaction_type.strip().lower()
            for item in RealEstateProduct__TransactionType:
                if item.value == val or item.name.lower() == val:
                    return item
        return RealEstateProduct__TransactionType.SALE

    def get_random_product_for_posting(
        self, transaction_type: Any = RealEstateProduct__TransactionType.SALE, days: int = 7
    ) -> Optional[Dict[str, Any]]:
        """
        Selects a random product updated within a specific timeframe for social media posting.
        Falls back to alternative transaction type (rental <-> sale) if no product is found.
        """
        target_type = self._normalize_transaction_type(transaction_type)
        fallback_type = (
            RealEstateProduct__TransactionType.SALE 
            if target_type == RealEstateProduct__TransactionType.RENTAL 
            else RealEstateProduct__TransactionType.RENTAL
        )

        product = self.repo.get_one_recent_product(target_type, days)
        if not product:
            logger.info(f"No recent product found for '{target_type.value}', falling back to '{fallback_type.value}'.")
            product = self.repo.get_one_recent_product(fallback_type, days)

        if product:
            logger.info(f"Selected random product: {product.pid} ({product.street}) - Type: {product.transaction_type}")
            return enrich_real_estate_product(product)

        logger.warning(
            f"No recent product found for transaction type {target_type.value} or fallback {fallback_type.value} in last {days} days."
        )
        return None

    def get_random_pid(
        self, transaction_type: Any = RealEstateProduct__TransactionType.SALE, days: int = 7
    ) -> Optional[str]:
        """
        Retrieves a random PID from the most recent products with fallback support between rental and sale.
        """
        target_type = self._normalize_transaction_type(transaction_type)
        fallback_type = (
            RealEstateProduct__TransactionType.SALE 
            if target_type == RealEstateProduct__TransactionType.RENTAL 
            else RealEstateProduct__TransactionType.RENTAL
        )

        product = self.repo.get_one_recent_product(transaction_type=target_type, recent_day=days)
        if not product:
            logger.info(f"No recent product found for '{target_type.value}', falling back to '{fallback_type.value}'.")
            product = self.repo.get_one_recent_product(transaction_type=fallback_type, recent_day=days)

        if not product:
            logger.warning(f"No recent product found for both '{target_type.value}' and '{fallback_type.value}' in last {days} days.")
            return None
        return product.pid

    def get_smart_template(
        self, transaction_type: Any, category: Any, template_name: RealEstateTemplate__Name
    ) -> Optional[RealEstateTemplate]:
        """
        Finds the most suitable template based on transaction type and category, 
        falling back to default if necessary.
        """
        template = self.repo.get_random_template(template_name, transaction_type, category)

        if template:
            return template
        logger.info(
            f"Specific template '{template_name.value}' not found for cat {category}, falling back to default."
        )
        return self.repo.get_default_template(template_name, transaction_type, category)

    def generate_content_for_product(
        self, product_dict: Dict[str, Any], use_ai: bool = True
    ) -> Dict[str, Any]:
        """
        Generates final Title and Description for a product by processing templates,
        replacing dynamic tags with actual product data, and optionally rewriting with Gemini AI.
        """
        trans_type = product_dict.get("transaction_type")
        cat = product_dict.get("category")

        title_tmpl_obj = self.get_smart_template(trans_type, cat, RealEstateTemplate__Name.TITLE)
        desc_tmpl_obj = self.get_smart_template(trans_type, cat, RealEstateTemplate__Name.DESCRIPTION)

        raw_title = title_tmpl_obj.value if title_tmpl_obj else ""
        raw_desc = desc_tmpl_obj.value if desc_tmpl_obj else ""

        final_title = self._process_template_replacement(raw_title, product_dict).upper()
        final_desc = self._process_template_replacement(raw_desc, product_dict)
        
        # If AI rewriting is enabled and API key is present, rewrite title and description
        if use_ai and self.gemini_service:
            try:
                ai_title, ai_desc = self.gemini_service.rewrite_real_estate(
                    raw_title=final_title, 
                    raw_desc=final_desc
                )
                if ai_title:
                    final_title = ai_title
                if ai_desc:
                    final_desc = ai_desc
            except Exception as e:
                logger.warning(f"⚠️ Failed to rewrite content with Gemini AI: {e}. Keeping template content.")

        return {
            "title": final_title,
            "description": final_desc,
            "image_paths": [],
        }

    def generate_content_by_pid(self, pid: str, use_ai: bool = True) -> Optional[Dict[str, Any]]:
        """
        Orchestrates the full content generation flow: retrieves product data, 
        processes templates (with optional AI rewrite), and identifies associated image paths.
        """
        product_dict = self.get_product_details(pid)
        if not product_dict:
            logger.warning(f"Product PID {pid} not found via generate_content_by_pid.")
            return None

        result = self.generate_content_for_product(product_dict, use_ai=use_ai)
        
        product_id = product_dict.get("id")
        # Lấy hình ảnh từ thư mục source gốc (source_{product_id}) thay vì thư mục đã đóng watermark
        img_dir = os.path.join(
            self.image_container_dir, str(product_id), f"source_{product_id}"
        )
        if not os.path.exists(img_dir):
            fallback_source = os.path.join(self.image_container_dir, str(product_id), "source")
            if os.path.exists(fallback_source):
                img_dir = fallback_source
            else:
                fallback_watermark = os.path.join(
                    self.image_container_dir, str(product_id), f"with_watermark_{product_id}"
                )
                if os.path.exists(fallback_watermark):
                    img_dir = fallback_watermark

        result["image_paths"] = self.get_images_from_folder(img_dir)

        return result

    def _process_template_replacement(
        self, template: str, product_dict: Dict[str, Any]
    ) -> str:
        """
        Core logic for parsing template tags and replacing them with product data.
        Supports configuration mapping, numeric formatting, and randomized icon insertion.
        """
        if not template:
            return ""

        replacements: Dict[str, str] = {}

        for attr_name, config_list_name in SETTING_FIELD_MAP.items():
            text_val = product_dict.get(f"{attr_name}_text") or ""

            if attr_name in ["ward", "district", "province"]:
                text_val = str(text_val).title()

            replacements[f"<{attr_name}>"] = text_val

        replacements["<pid>"] = str(product_dict.get("pid") or "")
        replacements["<street>"] = str(product_dict.get("street") or "").title()
        replacements["<description>"] = str(product_dict.get("description") or "")
        replacements["<function>"] = str(product_dict.get("function") or "")

        replacements["<area>"] = str(product_dict.get("area") or "0")
        replacements["<price>"] = product_dict.get("price_formatted", "0")
        replacements["<structure>"] = str(product_dict.get("structure") or "0")
        replacements["<unit>"] = product_dict.get("unit_text") or ""

        phone = (
            realestate_config.contact_phones[0]
            if realestate_config.contact_phones
            else ""
        )
        name = (
            realestate_config.contact_names[0]
            if realestate_config.contact_names
            else ""
        )
        phone_icon = (
            realestate_config.contact_phone_icons[0]
            if realestate_config.contact_phone_icons
            else phone
        )

        replacements["<phone_number>"] = phone
        replacements["<name>"] = name
        replacements["<phone_number_icon>"] = phone_icon

        final_content = template
        for tag, val in replacements.items():
            final_content = final_content.replace(tag, str(val))

        icons_list = realestate_config.icons
        if icons_list:
            def random_icon_replacer(match):
                return random.choice(icons_list)

            final_content = re.sub(r"<icon>", random_icon_replacer, final_content)
        else:
            final_content = final_content.replace("<icon>", "")
        return final_content.strip()

    def get_images_from_folder(self, folder_path: str) -> List[str]:
        """
        Scans a directory for valid image files and returns their full paths sorted by name.
        """
        normalized_path = os.path.abspath(os.path.normpath(folder_path))

        if not os.path.exists(normalized_path):
            logger.warning(f"❌ Image folder not found: {normalized_path}")
            return []

        valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"}
        image_paths = []

        try:
            for filename in os.listdir(normalized_path):
                if filename.startswith("."):
                    continue

                ext = os.path.splitext(filename)[1].lower()
                if ext in valid_extensions:
                    full_path = os.path.join(normalized_path, filename)
                    image_paths.append(full_path)

            image_paths.sort()
            return image_paths

        except Exception as e:
            logger.error(f"Error scanning image folder {normalized_path}: {e}")
            return []


if __name__ == "__main__":
    import json
    from PySide6.QtCore import QCoreApplication

    # 1. Khởi tạo QCoreApplication (Bắt buộc để QSqlDatabase/SQL Drivers hoạt động)
    app = QCoreApplication.instance()
    if not app:
        app = QCoreApplication(sys.argv)

    # Khởi tạo repo và service để chạy độc lập
    test_repo = ExternalDataRepository()
    test_service = ExternalDataService(test_repo)

    print("="*50)
    print("🧪 TESTING EXTERNAL DATA SERVICE")
    print("="*50)

    # 1. Get list of PIDs
    pids = test_service.get_product_pids()
    print(f"[*] Total PIDs found: {len(pids)}")

    if pids:
        sample_pid = pids[0]
        
        # 2. Get product details
        print(f"\n[*] Fetching product details for PID: {sample_pid}")
        details = test_service.get_product_details(sample_pid)
        if details:
            print(f"-> Success. Street: {details.get('street')}, Price: {details.get('price_formatted')}")

        # 3. Test content generation
        print(f"\n[*] Testing content generation for PID: {sample_pid}")
        content = test_service.generate_content_by_pid(sample_pid)
        if content:
            print("-" * 30)
            print(f"TITLE:\n{content.get('title')}")
            print(f"\nIMAGES FOUND: {len(content.get('image_paths', []))}")
            print("-" * 30)
            print(f"DESCRIPTION:\n{content.get('description')}")

    else:
        print("[!] No data found in database for testing.")

    print("\n" + "="*50)
    