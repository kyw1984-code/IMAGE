"""
scrape_coupang.py
-----------------
쿠팡 상품 URL에서 슬라이더 이미지 + 상세페이지 이미지 URL 목록을 추출한다.

로컬: undetected_chromedriver (GUI 모드)
Streamlit Cloud: Xvfb 가상 디스플레이 + selenium-stealth (headed Chrome on virtual display)

Usage:
    python execution/scrape_coupang.py <coupang_url>
"""

import sys
import json
import re
import time

MAX_IMAGES = 10


def _clean_url(url: str) -> str:
    url = url.rstrip("\\\\""\\'")
    if url.startswith("//"):
        url = "https:" + url
    return url


def _make_driver_local():
    """로컬 환경: undetected_chromedriver (GUI 모드, 봇 탐지 우회)"""
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=ko-KR")
    options.add_argument("--window-size=1280,900")
    return uc.Chrome(options=options), None


def _make_driver_cloud():
    """Streamlit Cloud: Xvfb 가상 디스플레이 + selenium-stealth"""
    from pyvirtualdisplay import Display
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium_stealth import stealth

    display = Display(visible=False, size=(1280, 900))
    display.start()

    options = Options()
    # Streamlit Cloud chromium 경로 (Debian Trixie: /usr/bin/chromium)
    import os
    for binary in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
        if os.path.exists(binary):
            options.binary_location = binary
            break

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--lang=ko-KR")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--start-maximized")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("prefs", {
        "intl.accept_languages": "ko-KR,ko",
    })

    # Streamlit Cloud chromedriver 경로 (Debian Trixie: /usr/bin/chromedriver)
    for driver_path in ["/usr/bin/chromedriver", "/usr/bin/chromium-driver",
                        "/usr/lib/chromium/chromedriver"]:
        if os.path.exists(driver_path):
            service = Service(driver_path)
            break
    else:
        service = Service()

    driver = webdriver.Chrome(service=service, options=options)

    stealth(
        driver,
        languages=["ko-KR", "ko"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    return driver, display


def _make_driver():
    """환경을 자동 감지하여 적절한 드라이버를 반환한다."""
    try:
        import undetected_chromedriver  # noqa: F401
        return _make_driver_local()
    except (ImportError, Exception):
        return _make_driver_cloud()


def scrape(url: str) -> dict:
    debug_lines = []
    driver, display = _make_driver()
    try:
        driver.get(url)
        time.sleep(5)

        page_title = driver.title
        debug_lines.append(f"page_title: {page_title}")
        debug_lines.append(f"url: {driver.current_url}")

        # Access Denied 탐지
        if "Access Denied" in page_title or "denied" in page_title.lower():
            raise RuntimeError(f"쿠팡이 접근을 차단했습니다. (title: {page_title})")

        # 절반까지 스크롤 → "상품정보 더보기" 버튼 노출
        height = driver.execute_script("return document.body.scrollHeight")
        debug_lines.append(f"page_height: {height}")
        for pos in range(0, height // 2, 600):
            driver.execute_script(f"window.scrollTo(0, {pos})")
            time.sleep(0.3)
        time.sleep(1)

        # "상품정보 더보기" 버튼 클릭
        # product-detail-seemore-icon-wpui 아이콘의 부모 button이 클릭 대상
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
        except Exception:
            pass

        # 버튼 클릭 후 페이지 끝까지 스크롤 → 상세 이미지 lazy load
        height = driver.execute_script("return document.body.scrollHeight")
        for pos in range(height // 2, height, 600):
            driver.execute_script(f"window.scrollTo(0, {pos})")
            time.sleep(0.3)
        driver.execute_script(f"window.scrollTo(0, {height})")
        time.sleep(2)

        page_src = driver.page_source

    finally:
        driver.quit()
        if display:
            try:
                display.stop()
            except Exception:
                pass

    # ── og:image (메인 썸네일) ────────────────────────────
    og_match = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', page_src)
    if not og_match:
        og_match = re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', page_src)
    thumbnail = _clean_url(og_match.group(1)) if og_match else None

    # ── 슬라이더 이미지 (492x492) ────────────────────────
    slider_raw = re.findall(
        r'(//thumbnail\.coupangcdn\.com/thumbnails/remote/492x492ex/[^"\'>\s\\]+)', page_src
    )
    slider_imgs = []
    for raw in slider_raw:
        u = _clean_url(raw)
        if u not in slider_imgs:
            slider_imgs.append(u)

    # ── 상세페이지 이미지 (q89 고화질, 더보기 클릭 후 로드) ──
    detail_raw = re.findall(
        r'(//thumbnail\.coupangcdn\.com/thumbnails/remote/q89/[^"\'>\s\\]+)', page_src
    )
    detail_imgs = []
    for raw in detail_raw:
        u = _clean_url(raw)
        if u not in detail_imgs:
            detail_imgs.append(u)

    # q89 없으면 image\d*.coupangcdn.com/image/retail fallback
    if not detail_imgs:
        for raw in re.findall(
            r'(https://image\d*\.coupangcdn\.com/image/retail/images/[^"\'>\s\\]+)', page_src
        ):
            u = _clean_url(raw)
            if u not in detail_imgs:
                detail_imgs.append(u)

    # ── 전체 이미지 조합 (썸네일 → 슬라이더 → 상세) ──
    all_images: list[str] = []
    for img in ([thumbnail] if thumbnail else []) + slider_imgs + detail_imgs:
        if img and img not in all_images:
            all_images.append(img)

    debug_lines.append(f"thumbnail: {thumbnail}")
    debug_lines.append(f"slider_imgs: {len(slider_imgs)}")
    debug_lines.append(f"detail_imgs: {len(detail_imgs)}")
    debug_lines.append(f"all_images: {len(all_images)}")

    return {
        "thumbnail": thumbnail,
        "detail_images": detail_imgs[:MAX_IMAGES],
        "all_images": all_images[:MAX_IMAGES],
        "debug": "\n".join(debug_lines),
    }


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
