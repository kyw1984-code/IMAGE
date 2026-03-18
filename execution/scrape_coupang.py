"""
scrape_coupang.py
-----------------
쿠팡 상품 URL에서 슬라이더 이미지 + 상세페이지 이미지 URL 목록을 추출한다.
undetected-chromedriver (headed Chrome)로 봇 탐지를 우회한다.

Usage:
    python execution/scrape_coupang.py <coupang_url>

Output (stdout, JSON):
    {
        "thumbnail": "https://...",
        "detail_images": ["https://...", ...],
        "all_images": ["https://...", ...]
    }
"""

import sys
import json
import re
import time
import undetected_chromedriver as uc

MAX_IMAGES = 10  # Gemini 비용 관리: 최대 10장


def _clean_url(url: str) -> str:
    """프로토콜 상대 URL을 절대 URL로 변환하고 후행 특수문자를 제거한다."""
    url = url.rstrip("\\\"'")
    if url.startswith("//"):
        url = "https:" + url
    return url


def _make_driver() -> uc.Chrome:
    """봇 탐지 우회 설정이 적용된 Chrome 드라이버를 반환한다."""
    options = uc.ChromeOptions()
    # headless 사용 시 쿠팡 봇 탐지에 걸리므로 비활성화
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=ko-KR")
    options.add_argument("--window-size=1280,900")
    return uc.Chrome(options=options)


def scrape(url: str) -> dict:
    """
    쿠팡 상품 URL에서 이미지를 추출한다.

    Returns:
        {
            "thumbnail": str | None,       # og:image (메인 대표 이미지)
            "detail_images": list[str],    # 상세페이지 이미지
            "all_images": list[str],       # 썸네일 + 슬라이더 + 상세 (중복 제거)
        }
    """
    driver = _make_driver()
    try:
        driver.get(url)
        time.sleep(5)

        # 절반까지 스크롤하여 "상품정보 더보기" 버튼 노출
        height = driver.execute_script("return document.body.scrollHeight")
        for pos in range(0, height // 2, 600):
            driver.execute_script(f"window.scrollTo(0, {pos})")
            time.sleep(0.3)
        time.sleep(1)

        # "상품정보 더보기" 버튼 클릭
        # product-detail-seemore-icon-wpui 아이콘의 부모 button이 실제 클릭 대상
        try:
            more_btn = driver.execute_script("""
                var icon = document.querySelector('[class*=\"seemore\"]');
                if (!icon) return null;
                // 부모 체인에서 button 또는 클릭 가능한 요소 탐색
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
            pass  # 버튼 없으면 그냥 진행

        # 버튼 클릭 후 페이지 끝까지 스크롤 → 상세 이미지 lazy load 트리거
        height = driver.execute_script("return document.body.scrollHeight")
        for pos in range(height // 2, height, 600):
            driver.execute_script(f"window.scrollTo(0, {pos})")
            time.sleep(0.3)
        driver.execute_script(f"window.scrollTo(0, {height})")
        time.sleep(2)

        page_src = driver.page_source

    finally:
        driver.quit()

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
        url_clean = _clean_url(raw)
        if url_clean not in slider_imgs:
            slider_imgs.append(url_clean)

    # ── 상세페이지 이미지 (q89 고화질) ─────────────────────
    # "상품정보 더보기" 클릭 후 나타나는 대형 설명 이미지
    detail_q89_raw = re.findall(
        r'(//thumbnail\.coupangcdn\.com/thumbnails/remote/q89/[^"\'>\s\\]+)', page_src
    )
    detail_imgs = []
    for raw in detail_q89_raw:
        url_clean = _clean_url(raw)
        if url_clean not in detail_imgs:
            detail_imgs.append(url_clean)

    # q89 없으면 imageNN.coupangcdn.com/image/retail 로 fallback
    if not detail_imgs:
        detail_raw = re.findall(
            r'(https://image\d*\.coupangcdn\.com/image/retail/images/[^"\'>\s\\]+)', page_src
        )
        for raw in detail_raw:
            url_clean = _clean_url(raw)
            if url_clean not in detail_imgs:
                detail_imgs.append(url_clean)

    # ── 전체 이미지 조합 (썸네일 → 슬라이더 → 상세, 중복 제거) ──
    all_images: list[str] = []
    for img in ([thumbnail] if thumbnail else []) + slider_imgs + detail_imgs:
        if img and img not in all_images:
            all_images.append(img)

    return {
        "thumbnail": thumbnail,
        "detail_images": detail_imgs[:MAX_IMAGES],
        "all_images": all_images[:MAX_IMAGES],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: scrape_coupang.py <url>"}))
        sys.exit(1)

    target_url = sys.argv[1]
    try:
        result = scrape(target_url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
