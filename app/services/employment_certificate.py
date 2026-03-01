from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
import html
from io import BytesIO
from pathlib import Path
import re
import smtplib
from typing import Any

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from ..config import settings

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "employment_certificate.html"
_DEFAULT_TEMPLATE_CACHE: str | None = None

_KOREAN_FONT_NAME = "HYSMyeongJo-Medium"
_FALLBACK_FONT_NAME = "Helvetica"
_FONT_REGISTERED = False

EMPLOYMENT_CERTIFICATE_TEMPLATE_VARIABLES = (
    "company_name",
    "biz_reg_no",
    "ceo_name",
    "company_phone",
    "company_email",
    "company_address",
    "employee_name",
    "birth_date",
    "org_name",
    "position_name",
    "hire_date",
    "issue_number",
    "issue_date",
    "issue_date_long",
    "purpose_label",
)

EMPLOYMENT_CERTIFICATE_TEMPLATE_REQUIRED_VARIABLES = (
    "company_name",
    "employee_name",
    "org_name",
    "hire_date",
    "issue_number",
    "issue_date",
    "purpose_label",
)

_TEMPLATE_PLACEHOLDER_ALIASES: dict[str, tuple[str, ...]] = {
    "company_name": ("company_name", "companyname", "회사명", "회사이름"),
    "biz_reg_no": ("biz_reg_no", "bizregno", "business_number", "사업자등록번호", "사업자등록번호"),
    "ceo_name": ("ceo_name", "대표자", "대표자명"),
    "company_phone": ("company_phone", "company_tel", "전화번호", "회사전화번호", "회사연락처"),
    "company_email": ("company_email", "email", "회사이메일", "이메일"),
    "company_address": ("company_address", "주소", "회사주소"),
    "employee_name": ("employee_name", "name", "성명", "이름", "직원명"),
    "birth_date": ("birth_date", "birthdate", "생년월일"),
    "org_name": ("org_name", "소속", "부서", "현장", "현장명"),
    "position_name": ("position_name", "position", "직급", "직위", "권한"),
    "hire_date": ("hire_date", "hiredate", "입사일", "채용일"),
    "issue_number": ("issue_number", "issue_no", "발급번호", "문서번호"),
    "issue_date": ("issue_date", "issued_at", "발급일"),
    "issue_date_long": ("issue_date_long", "발급일한글", "발급일자"),
    "purpose_label": ("purpose_label", "purpose", "용도", "제출용도", "발급용도"),
}


PURPOSE_LABEL_MAP = {
    "BANK": "은행 제출",
    "GOV": "관공서 제출",
    "CARD": "카드사 제출",
    "OTHER": "기타",
}


@dataclass
class MailResult:
    sent: bool
    error: str | None = None


def _safe_text(value: Any, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _resolve_paragraph_tag(style_name: str) -> str:
    normalized = str(style_name or "").strip().lower()
    if normalized.startswith("heading"):
        match = re.search(r"(\d+)", normalized)
        if match:
            level = max(1, min(6, int(match.group(1))))
            return f"h{level}"
        return "h2"
    return "p"


def _collect_docx_cell_text(cell) -> str:
    lines = []
    for paragraph in getattr(cell, "paragraphs", []) or []:
        text = str(paragraph.text or "").strip()
        if text:
            lines.append(text)
    merged = " ".join(lines).strip()
    return merged


def convert_docx_template_to_html(docx_bytes: bytes) -> str:
    document: DocumentObject = Document(BytesIO(docx_bytes))
    parts: list[str] = ['<div class="employment-certificate-template">']
    has_content = False

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            raw_text = str(paragraph.text or "").strip()
            if not raw_text:
                continue
            has_content = True
            tag = _resolve_paragraph_tag(getattr(getattr(paragraph, "style", None), "name", ""))
            safe_text = html.escape(raw_text).replace("\n", "<br/>")
            parts.append(f"<{tag}>{safe_text}</{tag}>")
            continue

        if isinstance(child, CT_Tbl):
            table = Table(child, document)
            has_content = True
            parts.append("<table>")
            for row in table.rows:
                parts.append("<tr>")
                for cell in row.cells:
                    cell_text = _collect_docx_cell_text(cell)
                    safe_text = html.escape(cell_text).replace("\n", "<br/>") if cell_text else "&nbsp;"
                    parts.append(f"<td>{safe_text}</td>")
                parts.append("</tr>")
            parts.append("</table>")

    parts.append("</div>")
    if not has_content:
        raise ValueError("template docx is empty")
    return "\n".join(parts).strip()


def normalize_template_placeholders(template_html: str) -> str:
    normalized = str(template_html or "")
    if not normalized.strip():
        return normalized

    for canonical, aliases in _TEMPLATE_PLACEHOLDER_ALIASES.items():
        for alias in aliases:
            escaped = re.escape(alias)
            patterns = (
                re.compile(r"\{\{\s*" + escaped + r"\s*\}\}", flags=re.IGNORECASE),
                re.compile(r"\$\{\s*" + escaped + r"\s*\}", flags=re.IGNORECASE),
                re.compile(r"\[\[\s*" + escaped + r"\s*\]\]", flags=re.IGNORECASE),
                re.compile(r"<<\s*" + escaped + r"\s*>>", flags=re.IGNORECASE),
            )
            for pattern in patterns:
                normalized = pattern.sub(f"{{{{{canonical}}}}}", normalized)
    return normalized


def load_default_template_html() -> str:
    global _DEFAULT_TEMPLATE_CACHE
    if _DEFAULT_TEMPLATE_CACHE is not None:
        return _DEFAULT_TEMPLATE_CACHE
    _DEFAULT_TEMPLATE_CACHE = TEMPLATE_PATH.read_text(encoding="utf-8")
    return _DEFAULT_TEMPLATE_CACHE


def _register_pdf_font_once() -> str:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _KOREAN_FONT_NAME

    try:
        pdfmetrics.registerFont(UnicodeCIDFont(_KOREAN_FONT_NAME))
        _FONT_REGISTERED = True
        return _KOREAN_FONT_NAME
    except Exception:
        return _FALLBACK_FONT_NAME


def _wrap_text(text: str, max_chars: int = 48) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return ["-"]

    words = re.split(r"(\s+)", value)
    lines: list[str] = []
    line = ""
    for token in words:
        if not token:
            continue
        if len(line + token) <= max_chars:
            line += token
            continue
        if line.strip():
            lines.append(line.strip())
            line = ""
        if len(token) > max_chars:
            chunk = token
            while len(chunk) > max_chars:
                lines.append(chunk[:max_chars])
                chunk = chunk[max_chars:]
            line = chunk
        else:
            line = token
    if line.strip():
        lines.append(line.strip())
    return lines or ["-"]


def build_issue_number(request_id: str, issued_at: datetime | None = None) -> str:
    now = issued_at or datetime.now(timezone.utc)
    token = re.sub(r"[^a-zA-Z0-9]", "", str(request_id or "")).upper()[:6] or "000000"
    return f"EC-{now:%Y%m%d}-{token}"


def render_employment_certificate_html(context: dict[str, Any], template_html: str | None = None) -> str:
    template = str(template_html or "").strip() or load_default_template_html()
    rendered = template
    for key, raw in context.items():
        value = html.escape(_safe_text(raw, "-"))
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    rendered = re.sub(r"\{\{\s*[a-zA-Z0-9_]+\s*\}\}", "-", rendered)
    return rendered


def generate_employment_certificate_pdf(
    context: dict[str, Any],
    *,
    seal_image_bytes: bytes | None = None,
    rendered_html: str | None = None,
    template_html: str | None = None,
) -> bytes:
    resolved_html = str(rendered_html or "").strip()
    if not resolved_html:
        resolved_html = render_employment_certificate_html(context, template_html=template_html)

    plain_text = resolved_html
    plain_text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", plain_text)
    plain_text = re.sub(r"(?i)<br\s*/?>", "\n", plain_text)
    plain_text = re.sub(r"(?i)</(p|div|tr|h1|h2|h3|h4|h5|h6|li|table|section|article)>", "\n", plain_text)
    plain_text = re.sub(r"(?i)<li[^>]*>", "• ", plain_text)
    plain_text = re.sub(r"<[^>]+>", " ", plain_text)
    plain_text = html.unescape(plain_text)
    plain_lines = [line.strip() for line in plain_text.splitlines() if line.strip()]
    if not plain_lines:
        plain_lines = ["재직증명서"]

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4

    font_name = _register_pdf_font_once()

    def draw_label(x: float, y: float, text: str, size: int = 10):
        pdf.setFont(font_name, size)
        pdf.drawString(x, y, _safe_text(text, "-"))

    y = page_height - 56

    pdf.setFont(font_name, 24)
    pdf.drawCentredString(page_width / 2, y, "재직증명서")
    y -= 30

    pdf.setLineWidth(1)
    pdf.line(48, y, page_width - 48, y)
    y -= 20

    for line in plain_lines:
        wrapped = _wrap_text(line, 68)
        for item in wrapped:
            draw_label(52, y, item, 10)
            y -= 14
            if y < 120:
                pdf.showPage()
                pdf.setFont(font_name, 10)
                y = page_height - 56

    if seal_image_bytes:
        try:
            image = ImageReader(BytesIO(seal_image_bytes))
            pdf.drawImage(
                image,
                page_width - 160,
                max(48, y - 42),
                width=90,
                height=90,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            draw_label(page_width - 150, y - 20, "(도장 이미지 로드 실패)", 8)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _smtp_client():
    if settings.smtp_ssl:
        return smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        )
    return smtplib.SMTP(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.smtp_timeout_seconds,
    )


def send_certificate_mail(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    attachment_name: str,
    attachment_bytes: bytes,
) -> MailResult:
    target = str(to_email or "").strip()
    if not target:
        return MailResult(sent=False, error="RECIPIENT_EMPTY")

    if not settings.mail_enabled:
        return MailResult(sent=False, error="MAIL_DISABLED")
    if not settings.smtp_host:
        return MailResult(sent=False, error="SMTP_HOST_EMPTY")

    message = EmailMessage()
    message["Subject"] = f"{settings.mail_subject_prefix} {subject}".strip()
    message["From"] = settings.mail_from
    message["To"] = target
    message.set_content("재직증명서가 발급되었습니다. 첨부파일을 확인해 주세요.")
    message.add_alternative(html_body, subtype="html")
    message.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_name,
    )

    try:
        with _smtp_client() as client:
            if not settings.smtp_ssl and settings.smtp_starttls:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except Exception as exc:
        return MailResult(sent=False, error=str(exc))

    return MailResult(sent=True, error=None)


def build_purpose_label(purpose_code: str, purpose_text: str | None) -> str:
    normalized_code = str(purpose_code or "").strip().upper()
    label = PURPOSE_LABEL_MAP.get(normalized_code, normalized_code or "기타")
    if normalized_code == "OTHER" and str(purpose_text or "").strip():
        return f"기타 - {str(purpose_text).strip()}"
    return label
