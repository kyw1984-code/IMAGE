"""
scrape_coupang.py
-----------------
쿠팡 상품 URL에서 슬라이더 이미지 + 상세페이지 이미지 URL 목록을 추출한다.

로컬   : undetected_chromedriver (GUI 모드)
Cloud  : nodriver + pyvirtualdisplay (WebDriver 프로토콜 미사용 → 봇 탐지 우회)

nodriver는 Chrome DevTools Protocol(CDP)을 직접 사용하므로
navigator.webdriver 플래그가 설정되지 않아 강력한 봇 탐지도 우회 가능.
"""

import sys
import json
import re
import time
import os
import asyncio

MAX_IMAGES = 10


def _clean_url(url: str) -> str:
    url = url.rstrip("\\'\"")
    if url.startswith("//"):
        url = "https:" + url
    return url


def _start_display():
    """Linux 환경에서 가상 디스플레이를 시작한다."""
    if os.name == "nt":
        return None
    try:
        from pyvirtualdisplay import Display
        d = Display(visible=False, size=(1280, 900))
        d.start()
        return d
    except Exception:
        return None


def _parse_images(page_src: str) -> tuple:
    """페이지 소스에서 썸네일·슬라이더·상세 이미지 URL을 추출한다."""
    og_match = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', page_src)
    if not og_match:
        og_match = re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', page_src)
    thumbnail = _clean_url(og_match.group(1)) if og_match else None

    slider_imgs = []
    for raw in re.findall(
        r'(//thumbnail\.coupangcdn\.com/thumbnails/remote/492x492ex/[^"\'>\s\\]+)', page_src
    ):
        u = _clean_url(raw)
        if u not in slider_imgs:
            slider_imgs.append(u)

    detail_imgs = []
    for raw in re.findall(
        r'(//thumbnail\.coupangcdn\.com/thumbnails/remote/q89/[^"\'>\s\\]+)', page_src
    ):
        u = _clean_url(raw)
        if u not in detail_imgs:
            detail_imgs.append(u)

    if not detail_imgs:
        for raw in re.findall(
            r'(https://image\d*\.coupangcdn\.com/image/retail/images/[^"\'>\s\\]+)', page_src
        ):
            u = _clean_url(raw)
            if u not in detail_imgs:
                detail_imgs.append(u)

    return thumbnail, slider_imgs, detail_imgs


# ── nodriver 기반 스크래핑 (Streamlit Cloud) ─────────────────────────────────

async def _scrape_nodriver(url: str) -> dict:
    import nodriver as uc

    debug_lines = []
    display = _start_display()

    # nodriver: 시스템 Chromium 경로 탐색
    chrome_path = None
    for p in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
        if os.path.exists(p):
            chrome_path = p
            break

    browser = await uc.start(
        headless=False,
        browser_executable_path=chrome_path,
        browser_args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1280,900",
            "--lang=ko-KR",
        ],
    )

    try:
        tab = await browser.get(url)
        await asyncio.sleep(5)

        title = await tab.evaluate("document.title")
        debug_lines.append(f"page_title: {title}")

        if "Access Denied" in str(title) or "denied" in str(title).lower():
            raise RuntimeError(f"쿠팡이 접근을 차단했습니다. (title: {title})")

        # 절반까지 스크롤
        height = await tab.evaluate("document.body.scrollHeight")
        debug_lines.append(f"page_height: {height}")

        for pos in range(0, int(height) // 2, 600):
            await tab.evaluate(f"window.scrollTo(0, {pos})")
            await asyncio.sleep(0.2)
        await asyncio.sleep(1)

        # "상품정보 더보기" 버튼 클릭
        try:
            await tab.evaluate("""
                (function() {
                    var icon = document.querySelector('[class*="seemore"]');
                    if (!icon) return;
                    var el = icon;
                    for (var i = 0; i < 5; i++) {
                        el = el.parentElement;
                        if (!el) break;
                        if (el.tagName === 'BUTTON' || el.tagName === 'A' ||
                            el.getAttribute('role') === 'button') { el.click(); return; }
                    }
                    if (icon.parentElement) icon.parentElement.click();
                })()
            """)
            await asyncio.sleep(3)
            debug_lines.append("더보기 클릭 완료")
        except Exception as e:
            debug_lines.append(f"더보기 클릭 실패: {e}")

        # 나머지 스크롤
        for pos in range(int(height) // 2, int(height), 600):
            await tab.evaluate(f"window.scrollTo(0, {pos})")
            await asyncio.sleep(0.2)
        await tab.evaluate(f"window.scrollTo(0, {int(height)})")
        await asyncio.sleep(2)

        page_src = await tab.get_content()

    finally:
        await browser.stop()
        if display:
            try:
                display.stop()
            except Exception:
                pass

    thumbnail, slider_imgs, detail_imgs = _parse_images(page_src)

    all_images: list[str] = []
    for img in ([thumbnail] if thumbnail else []) + slider_imgs + detail_imgs:
        if img and img not in all_images:
            all_images.append(img)

    debug_lines += [
        f"thumbnail: {thumbnail}",
        f"slider_imgs: {len(slider_imgs)}",
        f"detail_imgs: {len(detail_imgs)}",
        f"all_images: {len(all_images)}",
    ]

    return {
        "thumbnail": thumbnail,
        "detail_images": detail_imgs[:MAX_IMAGES],
        "all_images": all_images[:MAX_IMAGES],
        "debug": "\n".join(debug_lines),
    }


# ── undetected_chromedriver 기반 (로컬 Windows) ──────────────────────────────

def _scrape_local(url: str) -> dict:
    import undetected_chromedriver as uc

    debug_lines = []
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=ko-KR")
    options.add_argument("--window-size=1280,900")
    driver = uc.Chrome(options=options)

    try:
        driver.get(url)
        time.sleep(5)

        title = driver.title
        debug_lines.append(f"page_title: {title}")

        if "Access Denied" in title:
            raise RuntimeError(f"쿠팡이 접근을 차단했습니다. (title: {title})")

        height = driver.execute_script("return document.body.scrollHeight")
        debug_lines.append(f"page_height: {height}")

        for pos in range(0, height // 2, 600):
            driver.execute_script(f"window.scrollTo(0, {pos})")
            time.sleep(0.3)
        time.sleep(1)

        try:
            more_btn = driver.execute_script("""
                var icon = document.querySelector('[class*="seemore"]');
                if (!icon) return null;
                var el = icon;
                for (var i = 0; i < 5; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    if (el.tagName === 'BUTTON' || el.tagName === 'A' ||
                        el.getAttribute('role') === 'button') return el;
                }
                return icon.parentElement;
            """)
            if more_btn:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", more_btn)
                time.sleep(0.8)
                driver.execute_script("arguments[0].click();", more_btn)
                time.sleep(3)
                debug_lines.append("더보기 클릭 완료")
        except Exception as e:
            debug_lines.append(f"더보기 클릭 실패: {e}")

        for pos in range(height // 2, height, 600):
            driver.execute_script(f"window.scrollTo(0, {pos})")
            time.sleep(0.3)
        driver.execute_script(f"window.scrollTo(0, {height})")
        time.sleep(2)

        page_src = driver.page_source

    finally:
        driver.quit()

    thumbnail, slider_imgs, detail_imgs = _parse_images(page_src)

    all_images: list[str] = []
    for img in ([thumbnail] if thumbnail else []) + slider_imgs + detail_imgs:
        if img and img not in all_images:
            all_images.append(img)

    debug_lines += [
        f"thumbnail: {thumbnail}",
        f"slider_imgs: {len(slider_imgs)}",
        f"detail_imgs: {len(detail_imgs)}",
        f"all_images: {len(all_images)}",
    ]

    return {
        "thumbnail": thumbnail,
        "detail_images": detail_imgs[:MAX_IMAGES],
        "all_images": all_images[:MAX_IMAGES],
        "debug": "\n".join(debug_lines),
    }


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

def scrape(url: str) -> dict:
    """환경을 자동 감지하여 쿠팡 이미지를 추출한다."""
    try:
        import undetected_chromedriver  # noqa: F401
        return _scrape_local(url)
    except ImportError:
        pass

    # Cloud: nodriver (asyncio)
    return asyncio.run(_scrape_nodriver(url))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: scrape_coupang.py <url>"}))
        sys.exit(1)
    try:
        result = scrape(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
