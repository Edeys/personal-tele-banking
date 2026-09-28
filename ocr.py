"""OCR biên lai bằng LLM vision (endpoint OpenAI-compatible).

Prompt build ĐỘNG từ config.categories của user — không còn 14 prefix Firefly
hardcode. Phần kế thừa từ bản cũ (đã proven): _extract_json chịu được JSON
thuần / SSE stream / JSON bọc markdown, _normalize chuẩn hoá ngày giờ số tiền,
_validate + 1 lần fix-call, và chặn sớm ảnh trắng (model hay bịa số tiền).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from io import BytesIO

from openai import OpenAI
from PIL import Image

logger = logging.getLogger(__name__)

API_TIMEOUT = 90
MAX_TOKENS = 1500
RECEIPT_MAX_EDGE = 1600
RECEIPT_JPEG_QUALITY = 88


def _probe_png() -> bytes:
    """Ảnh 160x48 nhỏ để test model có nhận input ảnh hay không."""
    from PIL import ImageDraw

    img = Image.new("RGB", (160, 48), "white")
    ImageDraw.Draw(img).text((10, 16), "45.000 VND", fill="black")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _human_llm_error(exc: Exception, model: str) -> str:
    """Dịch lỗi endpoint LLM thành việc người dùng phải làm trong .env."""
    text = str(exc)
    low = text.lower()
    if "image" in low and any(k in low for k in ("support", "accept", "content_type", "invalid")):
        return (
            f"Model {model} không đọc được ảnh — đổi LLM_OCR_MODEL sang model vision "
            "(ví dụ qwen/qwen2.5-vl-72b-instruct)."
        )
    if "401" in low or "unauthorized" in low or "invalid api key" in low:
        return "LLM_API_KEY sai hoặc tài khoản chưa nạp tiền."
    if "404" in low or ("model" in low and "not found" in low):
        return f"Không tìm thấy model {model} — kiểm tra lại LLM_OCR_MODEL."
    if "timeout" in low or "timed out" in low:
        return f"Model {model} phản hồi chậm — thử lại, hoặc đổi sang model nhanh hơn."
    if "connection" in low or "name or service" in low or "max retries" in low:
        return "Không gọi được LLM_BASE_URL — kiểm tra lại địa chỉ endpoint."
    return text[:300]

_PROMPT_TEMPLATE = """Đọc ảnh giao dịch, trả JSON CHÍNH XÁC:

BANKING: {{"loai":"banking","ngay_thang":"DD/MM/YYYY","thoi_gian":"HH:MM","ngan_hang_gui":"","ngan_hang_nhan":"","nguoi_nhan":"","stk_nhan":"","so_tien":2000000,"ma_giao_dich":"","noi_dung":"","ghi_chu":"","danh_muc_lon":"","nhom_chi_phi":""}}

SHOPPE/TIKTOK: {{"loai":"shoppe","ngay_thang":"DD/MM/YYYY","thoi_gian":"HH:MM","danh_muc_lon":"","nhom_chi_phi":"","noi_dung":"Shop ABC: SP1 x2, SP2 x1 = 350000","don_hang":[{{"ten_shop":"","ten_san_pham":"","so_luong":1,"so_tien":150000}}]}}

QUAN TRỌNG - ĐỌC KỸ:
1. TÊN NGƯỜI NHẬN (nguoi_nhan): giữ NGUYÊN XI như trong ảnh, KHÔNG thêm dấu, KHÔNG sửa lỗi chính tả
2. NỘI DUNG CHUYỂN KHOẢN (noi_dung): giữ nguyên gốc, viết hoa/thường như trong ảnh
3. MÃ GIAO DỊCH (ma_giao_dich): nhập chính xác mã từ biên lai
4. NGÂN HÀNG GỬI (ngan_hang_gui): NHÌN LÊN PHÍA TRÊN CÙNG để tìm logo/tên ngân hàng gửi. Nếu không thấy → để trống ""
5. NGÂN HÀNG NHẬN (ngan_hang_nhan): tìm dòng "Tại:" hoặc "NH:" hoặc "Tại NH:" trong biên lai, rút gọn thành tên thông dụng: "NHTMCP Tiên Phong" → "TPBank", "NHTMCP Ngoại Thương" → "Vietcombank", "NHTMCP Công Thương" → "VietinBank", "NHTMCP Đầu tư và Phát triển" → "BIDV", "NHTMCP Quân Đội" → "MB Bank", "NHTMCP Kỹ Thương" → "Techcombank", "Ngân hàng TMCP Sài Gòn Thương Tín" → "Sacombank". Nếu không thấy → để trống ""
6. NỘI DUNG CHI TIẾT (ghi_chu): mô tả ngắn mục đích giao dịch nếu suy ra được (VD "ăn trưa", "đổ xăng")

PHÂN LOẠI GIAO DỊCH:
- danh_muc_lon: CHỌN CHÍNH XÁC 1 trong các nhóm sau (đúng nguyên văn), dựa vào nội dung chuyển khoản:
{groups}
- nhom_chi_phi: nếu nhóm được chọn có "hạng mục con", CHỌN CHÍNH XÁC 1 trong các hạng mục con đó (đúng nguyên văn); nhóm không có hạng mục con thì để trống ""
- Nếu không suy ra được → để trống ""

QUY TẮC:
- so_tien: số nguyên KHÔNG dấu chấm hay "vnd"
- Shoppe nhiều đơn: thêm nhiều object vào don_hang; noi_dung = tên shop + danh sách sản phẩm và số lượng, tổng tiền
- Chỉ trả JSON thuần, ko markdown, ko text khác"""


def build_prompt(categories: dict[str, list[str]] | None) -> str:
    lines: list[str] = []
    for group, subs in (categories or {}).items():
        if subs:
            opts = ", ".join(f'"{s}"' for s in subs)
            lines.append(f'  · "{group}" — hạng mục con: {opts}')
        else:
            lines.append(f'  · "{group}" — (không có hạng mục con)')
    block = "\n".join(lines) if lines else "  (người dùng chưa cấu hình danh mục — để trống)"
    return _PROMPT_TEMPLATE.format(groups=block)


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        text = re.sub(r"```\s*$", "", text).strip()
    return text


def _extract_json(raw: str) -> dict | None:
    """Chịu được mọi kiểu response: JSON thuần có/không đuôi `data: [DONE]`,
    SSE stream (nhiều dòng `data: {...}`) dù request stream=False, JSON bị bọc
    markdown hoặc có chữ dẫn chuyện xung quanh. Trả dict hoặc None.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()

    if text.startswith("data:") or "\ndata:" in text:
        parts = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            for ch in obj.get("choices", []) or []:
                if not isinstance(ch, dict):
                    continue
                msg = ch.get("message") or {}
                delta = ch.get("delta") or {}
                if isinstance(msg, dict) and msg.get("content"):
                    parts.append(msg["content"])
                if isinstance(delta, dict) and delta.get("content"):
                    parts.append(delta["content"])
        if parts:
            text = "".join(parts)
        elif not text.lstrip().startswith("{"):
            return None

    text = _clean_json(text)
    idx = text.find("{")
    if idx < 0:
        logger.warning("OCR không có JSON: %s", text[:200])
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(text[idx:])
    except Exception as e:
        logger.warning("OCR json lỗi: %s | %s", e, text[:200])
        return None
    return obj if isinstance(obj, dict) else None


def _to_amount(value) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    digits = "".join(c for c in str(value) if c.isdigit())
    return int(digits) if digits else 0


def _normalize(result: dict) -> None:
    if "so_tien" in result:
        result["so_tien"] = _to_amount(result.get("so_tien"))

    ngay = str(result.get("ngay_thang") or "").strip()
    if ngay:
        m = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", ngay)
        if m:
            result["ngay_thang"] = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"

    gio = str(result.get("thoi_gian") or "").strip()
    if gio:
        m = re.search(r"(\d{1,2})\s*[:hH]\s*(\d{1,2})", gio)
        if m and 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59:
            result["thoi_gian"] = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"

    loai = str(result.get("loai") or "").strip().lower()
    result["loai"] = "shoppe" if loai in ("shoppe", "shopee", "tiktok") else "banking"


def _validate(result: dict, categories: dict[str, list[str]]) -> list:
    problems: list[str] = []
    loai = str(result.get("loai") or "banking")

    if loai == "banking":
        if _to_amount(result.get("so_tien")) <= 0:
            problems.append(f"so_tien={result.get('so_tien')!r} phải là số tiền > 0")
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", str(result.get("ngay_thang") or "")):
            problems.append(f"ngay_thang={result.get('ngay_thang')!r} phải là DD/MM/YYYY")
    elif not result.get("don_hang") and not result.get("noi_dung"):
        problems.append("thiếu don_hang và noi_dung")

    gio = str(result.get("thoi_gian") or "").strip()
    if gio and not re.fullmatch(r"\d{2}:\d{2}", gio):
        problems.append(f"thoi_gian={gio!r} phải là HH:MM")

    group = str(result.get("danh_muc_lon") or "").strip()
    sub = str(result.get("nhom_chi_phi") or "").strip()
    if group and group not in categories:
        problems.append(f"danh_muc_lon={group!r} không thuộc nhóm đã cấu hình")
    if sub:
        if group in categories:
            if sub not in (categories.get(group) or []):
                problems.append(f"nhom_chi_phi={sub!r} không thuộc nhóm {group!r}")
        elif not any(sub in subs for subs in categories.values()):
            problems.append(f"nhom_chi_phi={sub!r} không thuộc hạng mục nào đã cấu hình")

    return problems


class OCRExtractor:
    def __init__(self, llm_config: dict, config=None):
        self.client = OpenAI(
            base_url=llm_config["base_url"],
            api_key=llm_config["api_key"],
            timeout=API_TIMEOUT,
        )
        self.model = llm_config.get("ocr_model", "OCR")
        self.config = config
        self._prompt = build_prompt(config.categories if config else {})

    def refresh_prompt(self) -> None:
        self._prompt = build_prompt(self.config.categories if self.config else {})

    def ping(self, timeout: float = 30) -> str | None:
        """Gọi model 1 lần với ảnh nhỏ. `None` = endpoint/key/model đều chạy.

        Khác với `extract`: không validate kết quả, chỉ muốn biết endpoint
        có trả lời và model có nhận input ảnh hay không. Dùng cho preflight
        lúc khởi động và cho lệnh `/test`.
        """
        try:
            data_uri = self._prepare(_probe_png())
            raw = self._call_sdk(
                [
                    {"type": "text", "text": "Trả về đúng một chữ: OK"},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
                timeout=timeout,
            )
        except Exception as e:
            logger.warning("OCR ping failed: %s", str(e)[:200])
            return _human_llm_error(e, self.model)
        return None if (raw or "").strip() else "Model nhận ảnh nhưng không trả lời."

    def _call_sdk(self, content, timeout: float | None = None) -> str:
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": content},
            ],
            max_tokens=MAX_TOKENS,
            timeout=timeout or API_TIMEOUT,
        )
        try:
            resp = self.client.chat.completions.create(temperature=0.0, **kwargs)
        except Exception as e:
            if "temperature" in str(e).lower():
                logger.warning("Retry không temperature: %s", str(e)[:150])
                resp = self.client.chat.completions.create(**kwargs)
            else:
                raise
        return resp.choices[0].message.content or ""

    def _prepare(self, image_bytes: bytes) -> str:
        img = Image.open(BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > RECEIPT_MAX_EDGE:
            scale = RECEIPT_MAX_EDGE / float(max(w, h))
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=RECEIPT_JPEG_QUALITY)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

    def _parse(self, raw: str) -> dict | None:
        result = _extract_json(raw)
        if result is None:
            return None
        _normalize(result)
        return result

    def extract(self, image_bytes: bytes) -> dict:
        t0 = time.perf_counter()
        cats = self.config.categories if self.config else {}
        try:
            data_uri = self._prepare(image_bytes)
        except Exception as e:
            logger.exception("OCR prepare error")
            return {"error": f"Không xử lý được ảnh: {e}"}

        multimodal = [
            {"type": "text", "text": "Đọc ảnh chuyển khoản này:"},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]
        markdown = f"Đọc ảnh chuyển khoản này:\n![receipt]({data_uri})"

        attempts: list = []
        raw = None
        for i, content in enumerate((multimodal, markdown), start=1):
            try:
                raw = self._call_sdk(content)
                attempts.append(i)
                break
            except Exception as e:
                logger.warning("OCR call %d failed: %s", i, str(e)[:200])
        if raw is None:
            return {"error": "Không đọc được ảnh (model không phản hồi)"}

        result = self._parse(raw)
        if result is None:
            try:
                result = self._parse(self._call_sdk(multimodal))
                attempts.append("reparse")
            except Exception as e:
                logger.warning("OCR reparse failed: %s", str(e)[:200])
        if result is None:
            return {"error": "Lỗi đọc ảnh, thử lại"}

        problems = _validate(result, cats)
        if problems:
            fix_msg = (
                "LẦN TRƯỚC bạn đọc SAI các trường sau: "
                + "; ".join(problems)
                + ". Hãy đọc lại ảnh và trả JSON ĐẦY ĐỦ, đảm bảo các trường này đúng."
            )
            try:
                fixed = self._parse(
                    self._call_sdk([multimodal[0], multimodal[1], {"type": "text", "text": fix_msg}])
                )
            except Exception as e:
                logger.warning("OCR fix-call failed: %s", str(e)[:200])
                fixed = None
            if fixed is not None and len(_validate(fixed, cats)) < len(problems):
                result, problems = fixed, _validate(fixed, cats)
                attempts.append("fix")
            elif fixed is not None:
                logger.info("OCR fix không cải thiện")

        if problems:
            logger.warning("OCR validate còn lỗi: %s", problems)

        group = str(result.get("danh_muc_lon") or "").strip()
        sub = str(result.get("nhom_chi_phi") or "").strip()
        if group and group not in cats:
            logger.info("OCR nhóm không hợp lệ, bỏ trống: %s", group)
            result["danh_muc_lon"] = ""
            group = ""
        if sub and group and sub not in (cats.get(group) or []):
            result["nhom_chi_phi"] = ""
        elif sub and not group and not any(sub in subs for subs in cats.values()):
            result["nhom_chi_phi"] = ""

        logger.info(
            "OCR %.1fs | model=%s | attempts=%s | problems=%s | loai=%s",
            time.perf_counter() - t0, self.model, attempts, len(problems), result.get("loai"),
        )

        if str(result.get("loai")) == "banking":
            if _to_amount(result.get("so_tien")) <= 0:
                return {"error": "Không đọc được số tiền — bấm OCR lại hoặc gửi lại ảnh"}
            if not (result.get("nguoi_nhan") or result.get("noi_dung") or result.get("ma_giao_dich")):
                return {"error": "Không đọc được người nhận/nội dung/mã GD — gửi lại ảnh rõ hơn"}
        return result
