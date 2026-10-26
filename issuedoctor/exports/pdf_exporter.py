"""PDF export.

The formal server-side PDF export requires Playwright plus a Chromium download,
which is a large optional dependency. This module therefore never imports
Playwright at module scope. When the ``pdf`` capability is absent,
:func:`export_pdf` raises :class:`issuedoctor.errors.IssueDoctorError` with an
actionable message; the browser print page remains fully available as the
always-working export path.
"""

from collections.abc import Callable

from issuedoctor.capabilities import (
    INSTALL_HINTS,
    OptionalDependencyError,
    is_available,
)
from issuedoctor.errors import IssueDoctorError


def pdf_available() -> bool:
    """True when server-side PDF rendering can be used."""
    return is_available("pdf")


def export_pdf(html: str, renderer: Callable[[str], bytes] | None = None) -> bytes:
    try:
        return (renderer or _playwright_renderer)(html)
    except OptionalDependencyError as exc:
        raise IssueDoctorError(
            "PDF_CAPABILITY_MISSING",
            f"正式 PDF 导出需要可选组件 Playwright 与 Chromium。安装方式：{exc.install_hint}，"
            "然后执行 python -m playwright install chromium。"
            "在此之前可以使用网页报告页的浏览器打印功能导出 PDF。",
            status_code=503,
        ) from exc
    except IssueDoctorError:
        raise
    except Exception as exc:
        raise IssueDoctorError(
            "PDF_RENDER_FAILED",
            "正式 PDF 渲染失败，请确认 Playwright Chromium 已安装",
            status_code=500,
        ) from exc


def _playwright_renderer(html: str) -> bytes:
    if not is_available("pdf"):
        raise OptionalDependencyError("pdf")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_content(html, wait_until="networkidle")
            return page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "15mm", "right": "13mm", "bottom": "15mm", "left": "13mm"},
            )
        finally:
            browser.close()


__all__ = ["export_pdf", "pdf_available", "INSTALL_HINTS"]
