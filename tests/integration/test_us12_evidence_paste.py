"""Spec 012 US5: screenshots pasted into a case's evidence show inline, survive Save, open full size, print."""
import base64
import os
import struct
import zlib
from pathlib import Path

import pytest

from tcadvisor.report.html import _TEMPLATE


def test_report_has_paste_support_and_inline_images():
    """Static part (no browser): the template wires paste, inline evidence images, the viewer and print styles."""
    assert "addEventListener('paste'" in _TEMPLATE and "getAsFile()" in _TEMPLATE and "'paste')" in _TEMPLATE
    assert 'class="thumb evimg"' in _TEMPLATE and 'id="lightbox"' in _TEMPLATE
    assert "#lightbox{display:none!important}" in _TEMPLATE and ".thumb,.evimg{max-width:100%" in _TEMPLATE
    assert 'tabindex="0"' in _TEMPLATE and "pasted-${" in _TEMPLATE


def _png(w: int = 4, h: int = 3) -> bytes:
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_paste_save_reopen_zoom_print(project, tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"  # preinstalled Chromium (cloud / CI images); else Playwright's own browser
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    project.analyze("--commit-range", "HEAD~1..HEAD")
    html = project.out / "report.html"
    b64 = base64.b64encode(_png()).decode()
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        except Exception as exc:  # noqa: BLE001 - no browser in this environment
            pytest.skip(f"chromium not available: {exc}")
        page = browser.new_page(accept_downloads=True)
        page.goto(html.as_uri())
        page.locator('[data-act="tog"]').first.click()
        page.locator(".drop").first.focus()
        page.evaluate("""b64 => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const dt = new DataTransfer();
            dt.items.add(new File([bytes], 'image.png', {type: 'image/png'}));
            const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
            document.querySelector('.drop').dispatchEvent(ev);
        }""", b64)
        img = page.locator("img.evimg").first
        img.wait_for()
        assert page.evaluate("document.querySelector('img.evimg').naturalWidth") == 4
        assert img.get_attribute("alt").startswith("pasted-TC-")
        page.locator('input[type=radio][value="pass"]').first.check()
        with page.expect_download() as dl:
            page.locator('[data-act="save"]').first.click()
        saved = tmp_path / "filled.html"
        dl.value.save_as(saved)
        page.goto(Path(saved).as_uri())  # reopened offline: the image is embedded
        page.emulate_media(media="print")
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        shown = page.locator("img.evimg").first
        shown.wait_for()
        assert page.evaluate("document.querySelector('img.evimg').naturalWidth") == 4
        assert shown.is_visible()
        page.emulate_media(media="screen")
        page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        page.locator('[data-act="tog"]').first.click()
        page.locator("img.evimg").first.click()
        assert page.locator("#lightbox.on img").get_attribute("src").startswith("data:image/png;base64,")
        page.keyboard.press("Escape")
        assert page.locator("#lightbox.on").count() == 0
        browser.close()
    from tcadvisor.report.results import read_results
    block = read_results(saved)
    att = next(iter(block["attachments"].values()))
    assert att["origin"] == "paste" and att["type"] == "image/png" and att["name"].startswith("pasted-TC-")
