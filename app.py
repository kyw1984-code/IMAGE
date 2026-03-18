"""
app.py
------
쿠팡 상품 상세페이지 분석 Streamlit 앱.

실행:
    streamlit run app.py

필요 설정:
    .streamlit/secrets.toml 에 GEMINI_API_KEY 설정
"""

import streamlit as st
import pandas as pd
from execution.scrape_coupang import scrape
from execution.analyze_images import analyze

# ─────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="쿠팡 상세페이지 분석기",
    page_icon="🛒",
    layout="wide",
)

SCORE_KEYS = ["썸네일 클릭률", "상단 후킹 지수", "구매 전환 설득력", "가독성"]

# ─────────────────────────────────────────────
# API Key 로드 (st.secrets 우선, .env fallback)
# ─────────────────────────────────────────────
def get_api_key() -> str | None:
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        return os.getenv("GEMINI_API_KEY")


# ─────────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────────
st.title("🛒 쿠팡 상세페이지 분석기")
st.caption("상품 URL을 입력하면 AI가 상세페이지를 분석하고 점수와 개선안을 제공합니다.")
st.divider()

# ─────────────────────────────────────────────
# 입력 영역
# ─────────────────────────────────────────────
url_input = st.text_input(
    "쿠팡 상품 URL",
    placeholder="https://www.coupang.com/vp/products/...",
    help="쿠팡 상품 페이지 URL을 붙여넣으세요.",
)

analyze_btn = st.button("분석 시작", type="primary", use_container_width=True)

# ─────────────────────────────────────────────
# 분석 실행
# ─────────────────────────────────────────────
if analyze_btn:
    if not url_input.strip():
        st.warning("URL을 입력해주세요.")
        st.stop()

    if "coupang.com" not in url_input:
        st.error("쿠팡 URL만 지원합니다. (coupang.com 도메인)")
        st.stop()

    api_key = get_api_key()
    if not api_key:
        st.error(
            "GEMINI_API_KEY가 설정되지 않았습니다.\n\n"
            "`.streamlit/secrets.toml` 에 `GEMINI_API_KEY = 'your-key'` 를 추가해주세요."
        )
        st.stop()

    # 1) 이미지 크롤링
    with st.spinner("🔍 쿠팡 페이지에서 이미지를 추출하는 중..."):
        try:
            scrape_result = scrape(url_input.strip())
        except Exception as e:
            st.error(f"이미지 추출 실패: {e}")
            st.stop()

    all_images = scrape_result.get("all_images", [])
    thumbnail = scrape_result.get("thumbnail")

    if not all_images:
        st.error("이미지를 찾을 수 없습니다. URL을 확인하거나 잠시 후 다시 시도해주세요.")
        st.stop()

    st.success(f"이미지 {len(all_images)}장 추출 완료")

    # 2) Gemini 분석
    with st.spinner("🤖 AI가 상세페이지를 분석하는 중... (30초~1분 소요)"):
        try:
            analysis = analyze(all_images, api_key)
        except Exception as e:
            st.error(f"Gemini 분석 실패: {e}")
            st.stop()

    # ─────────────────────────────────────────────
    # 결과 레이아웃: 좌측 이미지 | 우측 분석 결과
    # ─────────────────────────────────────────────
    st.divider()
    col_img, col_result = st.columns([1, 1], gap="large")

    # ── 좌측: 이미지 갤러리 ──────────────────────
    with col_img:
        st.subheader("📸 분석된 이미지")

        if thumbnail:
            st.image(thumbnail, caption="메인 썸네일", use_container_width=True)

        detail_imgs = scrape_result.get("detail_images", [])
        if detail_imgs:
            st.markdown("**상세 이미지**")
            for i, img_url in enumerate(detail_imgs, 1):
                try:
                    st.image(img_url, caption=f"상세 이미지 {i}", use_container_width=True)
                except Exception:
                    st.caption(f"이미지 {i} 로드 실패")

    # ── 우측: 분석 결과 ──────────────────────────
    with col_result:
        st.subheader("📊 분석 결과")

        # 오류 처리
        if analysis.get("error") == "no_images":
            st.error("분석할 이미지가 없습니다.")
            st.stop()

        scores = analysis.get("scores", {})
        total = analysis.get("total", sum(scores.get(k, 0) for k in SCORE_KEYS))
        improvements = analysis.get("improvements", [])

        # 총점 강조 표시
        score_color = (
            "#2ecc71" if total >= 80
            else "#f39c12" if total >= 60
            else "#e74c3c"
        )
        score_label = (
            "우수" if total >= 80
            else "보통" if total >= 60
            else "개선 필요"
        )

        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg, #1a1a2e, #16213e);
                border-radius: 16px;
                padding: 32px;
                text-align: center;
                margin-bottom: 24px;
                border: 2px solid {score_color};
            ">
                <div style="color: #aaa; font-size: 14px; margin-bottom: 8px;">총 점수</div>
                <div style="color: {score_color}; font-size: 72px; font-weight: 900; line-height: 1;">
                    {total}
                </div>
                <div style="color: #888; font-size: 16px; margin-top: 4px;">/ 100점</div>
                <div style="
                    display: inline-block;
                    background: {score_color};
                    color: white;
                    padding: 4px 16px;
                    border-radius: 20px;
                    font-size: 14px;
                    font-weight: 600;
                    margin-top: 12px;
                ">{score_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 항목별 점수 막대그래프
        st.markdown("**항목별 점수**")
        chart_data = pd.DataFrame(
            {"점수": [scores.get(k, 0) for k in SCORE_KEYS]},
            index=SCORE_KEYS,
        )
        st.bar_chart(chart_data, height=250, use_container_width=True)

        # 항목별 상세 점수 (수치 표)
        with st.expander("점수 상세 보기"):
            for key in SCORE_KEYS:
                score_val = scores.get(key, 0)
                pct = score_val / 25
                bar = "█" * int(pct * 20) + "░" * (20 - int(pct * 20))
                st.markdown(
                    f"**{key}** — {score_val}/25  \n"
                    f"`{bar}`"
                )

        st.divider()

        # 개선안
        st.markdown("**💡 개선안**")
        if analysis.get("parse_error"):
            st.warning("응답 파싱에 실패했습니다. 원문을 표시합니다.")
            for item in improvements:
                st.write(item)
        else:
            for item in improvements:
                st.markdown(f"- {item}")
