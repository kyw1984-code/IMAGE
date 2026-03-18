"""
scrape_coupang.py
-----------------
쿠팡 상품 URL에서 슬라이더 이미지 + 상세페이지 이미지 URL 목록을 추출한다.

Cloud  : curl_cffi (Chrome TLS/HTTP2 핑거프린트 위장 → 브라우저 없이 봇 탐지 우회)
로컬   : undetected_chromedriver (GUI 모드, 버튼 클릭까지 지원)
"""

import sys
import json
import re
import time

MAX_IMAGES = 10

# Chrome 124 수준의 요청 헤더
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _clean_url(url: str) -> str:
    url = url.rstrip("\\'\"")
    if url.startswith("//"):
        url = "https:" + url
    return url


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

    # 상세 이미지: q89 우선, 없으면 image\d*.coupangcdn fallback
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


def _scrape_cloud(url: str) -> dict:
    """
    curl_cffi로 Chrome TLS/HTTP2 핑거프린트를 위장하여 페이지를 가져온다.
    브라우저 없이 동작 → Streamlit Cloud에서 사용.
    메인 페이지 먼저 방문 → 쿠키 획득 → 상품 페이지 접근.
    """
    from curl_cffi import requests as curl_requests

    debug_lines = []
    session = curl_requests.Session(impersonate="chrome124")

    # 메인 페이지 먼저 방문하여 쿠키/세션 획득
    try:
        warm_resp = session.get("https://www.coupang.com/", headers=_HEADERS, timeout=20)
        debug_lines.append(f"warm_status: {warm_resp.status_code}")
        time.sleep(1.5)
    except Exception as e:
        debug_lines.append(f"warm_failed: {e}")

    resp = session.get(url, headers={**_HEADERS, "Referer": "https://www.coupang.com/"}, timeout=30)
    debug_lines.append(f"status_code: {resp.status_code}")

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} 오류")

    page_src = resp.text
    debug_lines.append(f"page_src_len: {len(page_src)}")

    if "Access Denied" in page_src[:2000] or "<title>Access Denied</title>" in page_src:
        raise RuntimeError("쿠팡이 접근을 차단했습니다. (Access Denied)")

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


def _scrape_local(url: str) -> dict:
    """undetected_chromedriver (로컬 Windows, GUI 모드)"""
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
        for pos in range(0, height // 2, 600):
            driver.execute_script(f"window.scrollTo(0, {pos})")
            time.sleep(0.3)
        time.sleep(1)

        # "상품정보 더보기" 버튼 클릭
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


def scrape(url: str) -> dict:
    """환경을 자동 감지하여 쿠팡 이미지를 추출한다."""
    try:
        import undetected_chromedriver  # noqa: F401
        return _scrape_local(url)
    except ImportError:
        return _scrape_cloud(url)


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
