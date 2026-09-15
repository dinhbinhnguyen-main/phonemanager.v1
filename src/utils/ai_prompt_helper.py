# src/utils/ai_prompt_helper.py
import re
import random
from typing import Dict, List, Optional, Tuple


REAL_ESTATE_ANGLES = [
    {
        "name": "Thực tế & Súc tích",
        "description": "Đi thẳng vào thông số cốt lõi (vị trí, diện tích, công năng, giá), không văn vẻ rườm rà."
    },
    {
        "name": "Trải nghiệm sống & Tiện ích",
        "description": "Nêu bật không gian sống thoáng đãng, thuận tiện đi lại, gần trường, chợ, siêu thị."
    },
    {
        "name": "Góc nhìn giá trị & Tiềm năng",
        "description": "Sắc bén, nhấn mạnh vị trí đẹp, tính thanh khoản cao, phù hợp ở hoặc khai thác cho thuê."
    },
    {
        "name": "Gợi mở nhu cầu",
        "description": "Mở đầu tự nhiên bằng gợi ý tìm nhà an cư hoặc giữ tài sản hợp lý trong tầm tài chính."
    },
    {
        "name": "Review chân thực",
        "description": "Khách quan, gần gũi như người đi xem nhà thực tế chia sẻ lại các điểm cộng lớn."
    }
]

# Danh sách từ cấm / sáo rỗng / giật tít câu view / vi phạm chính sách Meta / dễ bị quét Spam
FORBIDDEN_CLICHES = [
    # Từ sáo rỗng & giật gân
    "siêu phẩm", "cực phẩm", "cơ hội vàng", "đẹp lung linh", "đẹp ngỡ ngàng",
    "không thể bỏ qua", "nhanh tay kẻo lỡ", "hoa hậu", "ngọc trinh", "hàng hiếm",
    "đỉnh cao", "rẻ tụt quần", "rẻ sập sàn", "rẻ nhất quả đất", "sốc", "khủng",
    # Từ vi phạm chính sách tài chính / BĐS tiêu cực (dễ bị shadowban/spam flag)
    "vỡ nợ", "cắt lỗ", "bán tháo", "ngộp thở", "ngộp ngân hàng", "phát mãi",
    "túng tiền", "cam kết sinh lời", "bao lời", "lời gấp đôi",
    # Từ nhạy cảm & engagement bait
    "chính chủ", "chia sẻ ngay", "tag bạn bè", "thả tim", "chấm bài"
]

RANDOM_ICONS_POOL = [
    "🏡", "📍", "🌿", "🔑", "✨", "📌", "☀️", "🏷️", "🏢", "🛋️", "📐", "🚗", "🌳", "🪴"
]


class AIPromptHelper:
    """
    Helper to generate concise, Facebook SEO-optimized, policy-compliant prompts 
    and robustly parse responses for Gemini AI rewrites.
    """

    @staticmethod
    def build_real_estate_rewrite_prompt(raw_title: str, raw_desc: str) -> str:
        """
        Builds a compact prompt for Facebook real estate posts.
        Optimized for:
        - Brevity (under 100 words, no reader fatigue)
        - Facebook SEO (keyword in top lines, 3-4 hashtags)
        - Meta Policy & Anti-spam compliance (no clickbait, no engagement bait, no markdown stars, max 2-3 icons)
        - Contact Call To Action: Retain and format phone number/Zalo/contact if present in original text, call to action clearly
        """
        angle = random.choice(REAL_ESTATE_ANGLES)
        cliches_sample = ", ".join([f'"{c}"' for c in random.sample(FORBIDDEN_CLICHES, min(6, len(FORBIDDEN_CLICHES)))])
        sample_icons = " ".join(random.sample(RANDOM_ICONS_POOL, min(3, len(RANDOM_ICONS_POOL))))

        prompt = f"""Bạn là chuyên gia viết bài BĐS chuẩn SEO Facebook, tuân thủ nghiêm ngặt chính sách và thuật toán chống spam của Meta.

Nhiệm vụ: Viết lại tin BĐS sau thành bài đăng Facebook NGẮN GỌN, TỰ NHIÊN, DỄ ĐỌC.
Góc nhìn thể hiện: {angle['name']} ({angle['description']}).

TIÊU CHUẨN NỘI DUNG & SEO FACEBOOK:
1. Độ dài & Bố cục: Ngắn gọn (dưới 100 từ), 3-5 dòng/gạch đầu dòng ngắt quãng thoáng mắt, tối ưu hiển thị trên điện thoại.
2. Chuẩn SEO Facebook: Dòng đầu nêu rõ [Loại BĐS] + [Vị trí/Quận/Đường] + Điểm sáng chính để tối ưu tìm kiếm trên Facebook.
3. Thân bài: Đi thẳng vào thông tin người mua cần (diện tích, kết cấu, tiện ích nổi bật, giá bán/thuê). Giữ đúng thông số gốc, bỏ mục trống/0/mã tin/PID.
4. Kêu gọi liên hệ (CTA): Kêu gọi người xem liên hệ để xem nhà, nhận thông tin chi tiết hoặc tư vấn. NẾU trong bản gốc CÓ số điện thoại (SĐT), Zalo hoặc tên liên hệ, BẮT BUỘC giữ nguyên và trình bày rõ ràng (ví dụ: "📞 Liên hệ / Zalo: [SĐT] - [Tên] để xem nhà trực tiếp"). NẾU bản gốc không có SĐT thì kêu gọi "inbox ngay" hoặc "nhắn tin trực tiếp".
5. Cuối bài: Kèm đúng 3-4 hashtag chuẩn SEO (ví dụ: #nhadep #bds_khuvuc #muabannhadat).

CHỐNG SPAM & TUÂN THỦ CHÍNH SÁCH FACEBOOK:
- CẤM TỪ SÁO RỖNG & GIẬT TÍT: Không dùng {cliches_sample}.
- CẤM TỪ TIÊU CỰC / VI PHẠM TÀI CHÍNH: Tuyệt đối không dùng "vỡ nợ", "cắt lỗ", "bán tháo", "ngộp", "phát mãi", "cam kết lời".
- CẤM MỒI TƯƠNG TÁC (Engagement Bait): Không dùng "chia sẻ ngay", "tag bạn bè", "thả tim", "chấm bài".
- THÔNG TIN LIÊN HỆ: Giữ đúng số điện thoại / Zalo từ bản gốc (nếu có), không tự bịa đặt SĐT mới.
- CẤM ĐỊNH DẠNG SPAM: Không dùng markdown (**), không viết hoa toàn bộ (ALL CAPS), chỉ dùng 2-3 icon nhẹ nhàng ({sample_icons}).

BẮT BUỘC TRẢ VỀ THEO CẤU TRÚC (ngăn cách chính xác bằng dòng '===SPLIT===', không thêm lời dẫn hay giải thích):
Tiêu đề mới (dưới 85 ký tự, chuẩn SEO)
===SPLIT===
Nội dung mô tả mới

Tiêu đề gốc: {raw_title}
Mô tả gốc: {raw_desc}"""

        return prompt.strip()

    @staticmethod
    def parse_real_estate_rewrite_response(
        response: str,
        default_title: str = "",
        default_desc: str = ""
    ) -> Tuple[str, str]:
        """
        Robustly parses the title and description from Gemini's rewrite response.
        Handles variations of ===SPLIT=== delimiter, label-based outputs (Tiêu đề / Mô tả),
        or fallback first-line splitting. Also strips accidental markdown formatting.

        Returns:
            Tuple[str, str]: (rewritten_title, rewritten_desc)
        """
        if not response or not response.strip():
            return default_title, default_desc

        clean_text = response.strip()

        def _clean_part(part: str, is_title: bool = False) -> str:
            p = part.strip()
            # Remove markdown code blocks if wrapped
            p = re.sub(r"^```[a-zA-Z]*\n?", "", p)
            p = re.sub(r"\n?```$", "", p)
            p = p.strip()

            # Remove wrapping quotes or brackets
            if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
                p = p[1:-1].strip()
            if p.startswith("[") and p.endswith("]"):
                p = p[1:-1].strip()

            if is_title:
                # Remove leading labels like "Tiêu đề:", "Tiêu đề mới:", "Title:", "#", etc.
                p = re.sub(r"^(?:tiêu\s*đề(?:\s*mới)?|title)\s*[:：\-]\s*", "", p, flags=re.IGNORECASE)
                if p.startswith("[") and p.endswith("]"):
                    p = p[1:-1].strip()
                p = re.sub(r"^#+\s*", "", p)
            else:
                # Remove leading labels like "Mô tả:", "Mô tả mới:", "Description:", "Nội dung:", etc.
                p = re.sub(r"^(?:mô\s*tả(?:\s*mới)?|description|nội\s*dung(?:\s*mới)?)\s*[:：\-]\s*", "", p, flags=re.IGNORECASE)
                if p.startswith("[") and p.endswith("]"):
                    p = p[1:-1].strip()

            # Clean markdown bold/italic asterisks (e.g. **text** -> text) to prevent raw formatting on FB
            p = re.sub(r"\*\*(.*?)\*\*", r"\1", p)
            p = re.sub(r"\*(.*?)\*", r"\1", p)

            return p.strip()

        # 1. Check for ===SPLIT=== or variations (e.g. === SPLIT ===, ---SPLIT---, **===SPLIT===**, etc.)
        split_match = re.search(r'(?:^|\n)\s*[\*=_#-]*\s*SPLIT\s*[\*=_#-]*\s*(?:\n|$)', clean_text, re.IGNORECASE)
        if split_match:
            title_part = clean_text[:split_match.start()]
            desc_part = clean_text[split_match.end():]
            title = _clean_part(title_part, is_title=True)
            desc = _clean_part(desc_part, is_title=False)
            return title or default_title, desc or default_desc

        # 2. Check for labeled format (e.g. "Tiêu đề: ... \nMô tả: ...")
        label_match = re.search(
            r'(?:^|\n)\s*(?:tiêu\s*đề(?:\s*mới)?|title)\s*[:：\-]\s*(.*?)\n+\s*(?:mô\s*tả(?:\s*mới)?|description|nội\s*dung(?:\s*mới)?)\s*[:：\-]\s*(.*)',
            clean_text,
            re.DOTALL | re.IGNORECASE
        )
        if label_match:
            title = _clean_part(label_match.group(1), is_title=True)
            desc = _clean_part(label_match.group(2), is_title=False)
            return title or default_title, desc or default_desc

        # 3. Fallback: Split by first non-empty line if it looks like a title (< 120 chars) and there are more lines
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
        if len(lines) >= 2 and len(lines[0]) <= 120:
            title = _clean_part(lines[0], is_title=True)
            desc_raw = clean_text[clean_text.find(lines[0]) + len(lines[0]):].strip()
            desc = _clean_part(desc_raw, is_title=False)
            return title or default_title, desc or default_desc

        # 4. Single block returned:
        if not default_title and default_desc:
            return default_title, _clean_part(clean_text, is_title=False)
        if default_title and not default_desc:
            return _clean_part(clean_text, is_title=True), default_desc

        # Default fallback: Treat entire text as description, retain default title
        return default_title, _clean_part(clean_text, is_title=False)

    @staticmethod
    def build_product_title_rewrite_prompt(raw_title: str) -> str:
        """
        Builds a compact prompt to rewrite product title under 85 characters,
        optimized for Facebook Marketplace/Group search without spam triggers.
        """
        styles = [
            "Ngắn gọn, rõ tên sản phẩm và điểm nổi bật chính.",
            "Tự nhiên, chuẩn từ khóa tìm kiếm trên Marketplace/Group.",
            "Trực diện, súc tích, nêu rõ loại sản phẩm và tình trạng."
        ]
        chosen_style = random.choice(styles)
        cliches_sample = ", ".join([f'"{c}"' for c in random.sample(FORBIDDEN_CLICHES, min(5, len(FORBIDDEN_CLICHES)))])

        prompt = f"""Viết lại tiêu đề sản phẩm sau thành 1 dòng ngắn gọn, chuẩn SEO Facebook (dưới 85 ký tự) bằng tiếng Việt.
- Phong cách: {chosen_style}
- Cấu trúc chuẩn SEO: [Tên sản phẩm] + [Đặc điểm/Phiên bản chính] + [Tình trạng/Khu vực].
- Tuyệt đối không dùng từ ngữ giật tít, sáo rỗng: {cliches_sample}.
- Không viết hoa toàn bộ (ALL CAPS), không dùng ký tự đặc biệt gây spam.
- Chỉ trả về DUY NHẤT tiêu đề mới, không kèm lời chào hay giải thích.

Tiêu đề gốc: {raw_title}"""
        return prompt.strip()

    @staticmethod
    def build_product_description_rewrite_prompt(raw_desc: str) -> str:
        """
        Builds a compact prompt to rewrite product description.
        Optimized for brevity, readability, mobile layout, and policy compliance.
        """
        tones = [
            "Tự nhiên, chân thật, rõ ràng cho người mua.",
            "Gãy gọn, súc tích, làm nổi bật thông số và tình trạng.",
            "Thân thiện, nhiệt tình, hướng tới trải nghiệm thực tế."
        ]
        chosen_tone = random.choice(tones)
        cliches_sample = ", ".join([f'"{c}"' for c in random.sample(FORBIDDEN_CLICHES, min(5, len(FORBIDDEN_CLICHES)))])

        prompt = f"""Viết lại mô tả sản phẩm sau bằng tiếng Việt ngắn gọn, ngắt dòng thoáng mắt dễ đọc trên mobile:
- Phong cách: {chosen_tone}
- Bố cục: 3-4 gạch đầu dòng nêu tình trạng & thông số cốt lõi + Giá + Kêu gọi liên hệ (Số điện thoại / Zalo / Gọi trực tiếp / Inbox).
- Giữ đúng thông số kỹ thuật, giá từ bản gốc. NẾU bản gốc có số điện thoại (SĐT), Zalo hoặc tên liên hệ, BẮT BUỘC giữ nguyên và trình bày rõ ràng, thuận tiện cho người mua liên hệ (ví dụ: "📞 Hotline/Zalo: [SĐT] - [Tên]"). Nếu không có SĐT thì kêu gọi "Inbox ngay" hoặc "Nhắn tin trực tiếp".
- Chống spam & chính sách: Không in đậm (**), không viết hoa toàn bộ từ, không dùng từ sáo rỗng ({cliches_sample}), không mồi tương tác (tag/share).
- Cuối bài: 2-3 hashtag chuẩn từ khóa tìm kiếm sản phẩm.
- Chỉ trả về DUY NHẤT nội dung mô tả mới, không kèm lời chào hay giải thích.

Mô tả gốc:
{raw_desc}"""
        return prompt.strip()

    @staticmethod
    def build_general_rewrite_prompt(text: str, context_type: str = "bài viết thảo luận Facebook") -> str:
        """
        Builds a compact rewrite prompt for general discussion or text posts.
        """
        tones = [
            "Tự nhiên, đời thường như người thật chia sẻ trải nghiệm.",
            "Ngắn gọn, súc tích, nêu bật ý cốt lõi.",
            "Tươi vui, tích cực, gần gũi.",
            "Gợi mở, tự nhiên, không quảng cáo lộ liễu."
        ]
        chosen_tone = random.choice(tones)

        prompt = f"""Viết lại đoạn nội dung sau thành một {context_type} ngắn gọn, tự nhiên bằng tiếng Việt.
- Phong cách: {chosen_tone}
- Giữ nguyên thông điệp chính, loại bỏ câu từ thừa thãi rườm rà.
- Kêu gọi liên hệ: Nếu bài viết gốc có thông tin liên hệ (số điện thoại, Zalo, tên liên hệ), hãy giữ nguyên và lồng ghép lời kêu gọi liên hệ (gọi điện, nhắn Zalo, inbox) một cách tự nhiên, thiện cảm.
- Tuân thủ chính sách Facebook: Không giật tít câu view, không dùng từ ngữ cam kết quá đà, không markdown (**).
- Chỉ trả về DUY NHẤT nội dung mới, không kèm lời chào hay câu dẫn.

Nội dung gốc:
{text}"""
        return prompt.strip()
