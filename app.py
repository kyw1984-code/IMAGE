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
from execution.analyze_images import analyze, analyze_bytes

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
# 분석 결과 표시 함수
# ─────────────────────────────────────────────
def show_results(analysis: dict, images_for_display: list):
    st.divider()
    col_img, col_result = st.columns([1, 1], gap="large")

    # ── 좌측: 이미지 갤러리 ──────────────────────
    with col_img:
        st.subheader("📸 분석된 이미지")
        for i, img in enumerate(images_for_display, 1):
            try:
                st.image(img, caption=f"이미지 {i}", use_container_width=True)
            except Exception:
                st.caption(f"이미지 {i} 로드 실패")

    # ── 우측: 분석 결과 ──────────────────────────
    with col_result:
        st.subheader("📊 분석 결과")

        if analysis.get("error") == "no_images":
            st.error("분석할 이미지가 없습니다.")
            return

        scores = analysis.get("scores", {})
        total = analysis.get("total", sum(scores.get(k, 0) for k in SCORE_KEYS))
        improvements = analysis.get("improvements", [])

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

        st.markdown("**항목별 점수**")
        chart_data = pd.DataFrame(
            {"점수": [scores.get(k, 0) for k in SCORE_KEYS]},
            index=SCORE_KEYS,
        )
        st.bar_chart(chart_data, height=250, use_container_width=True)

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

        st.markdown("**💡 개선안**")
        if analysis.get("parse_error"):
            st.warning("응답 파싱에 실패했습니다. 원문을 표시합니다.")
            for item in improvements:
                st.write(item)
        else:
            for item in improvements:
                st.markdown(f"- {item}")


# ─────────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────────
st.title("🛒 쿠팡 상세페이지 분석기")
st.caption("상세페이지 이미지를 AI가 분석하여 점수와 개선안을 제공합니다.")
st.divider()

api_key = get_api_key()
if not api_key:
    st.error(
        "GEMINI_API_KEY가 설정되지 않았습니다.\n\n"
        "`.streamlit/secrets.toml` 에 `GEMINI_API_KEY = 'your-key'` 를 추가해주세요."
    )
    st.stop()

# ─────────────────────────────────────────────
# 탭: URL 입력 / 이미지 직접 업로드
# ─────────────────────────────────────────────
tab_url, tab_upload = st.tabs(["🔗 쿠팡 URL로 분석", "📁 이미지 직접 업로드"])

# ── 탭 1: URL 입력 ──────────────────────────
with tab_url:
    st.info("쿠팡 상품 URL을 입력하면 자동으로 이미지를 추출하여 분석합니다. (로컬 실행 환경 권장)")

    url_input = st.text_input(
        "쿠팡 상품 URL",
        placeholder="https://www.coupang.com/vp/products/...",
        help="쿠팡 상품 페이지 URL을 붙여넣으세요.",
        key="url_input",
    )

    if st.button("URL로 분석 시작", type="primary", use_container_width=True, key="btn_url"):
        if not url_input.strip():
            st.warning("URL을 입력해주세요.")
        elif "coupang.com" not in url_input:
            st.error("쿠팡 URL만 지원합니다. (coupang.com 도메인)")
        else:
            from execution.scrape_coupang import scrape

            with st.spinner("🔍 쿠팡 페이지에서 이미지를 추출하는 중..."):
                try:
                    scrape_result = scrape(url_input.strip())
                except Exception as e:
                    st.error(f"이미지 추출 실패: {e}")
                    st.stop()

            all_images = scrape_result.get("all_images", [])
            thumbnail = scrape_result.get("thumbnail")

            if not all_images:
                debug_info = scrape_result.get("debug", "")
                st.error("이미지를 찾을 수 없습니다. 아래 '이미지 직접 업로드' 탭을 이용해주세요.")
                if debug_info:
                    with st.expander("🔍 디버그 정보"):
                        st.code(debug_info)
                st.stop()

            st.success(f"이미지 {len(all_images)}장 추출 완료")

            with st.spinner("🤖 AI가 상세페이지를 분석하는 중... (30초~1분 소요)"):
                try:
                    analysis = analyze(all_images, api_key)
                except Exception as e:
                    st.error(f"Gemini 분석 실패: {e}")
                    st.stop()

            display_imgs = (
                [thumbnail] if thumbnail else []
            ) + scrape_result.get("detail_images", [])

            show_results(analysis, display_imgs)

# ── 탭 2: 이미지 직접 업로드 ─────────────────
with tab_upload:
    st.info(
        "상세페이지 이미지를 직접 업로드하여 분석합니다. "
        "쿠팡 상품 페이지에서 이미지를 저장한 후 여기에 올려주세요. (최대 10장)"
    )

    uploaded_files = st.file_uploader(
        "이미지 파일 선택 (JPG, PNG, WEBP)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="file_uploader",
    )

    if st.button("업로드 이미지 분석 시작", type="primary", use_container_width=True, key="btn_upload"):
        if not uploaded_files:
            st.warning("분석할 이미지를 업로드해주세요.")
        else:
            files = uploaded_files[:10]
            st.success(f"이미지 {len(files)}장 업로드 완료")

            with st.spinner("🤖 AI가 상세페이지를 분석하는 중... (30초~1분 소요)"):
                try:
                    image_bytes_list = [f.read() for f in files]
                    analysis = analyze_bytes(image_bytes_list, api_key)
                except Exception as e:
                    st.error(f"Gemini 분석 실패: {e}")
                    st.stop()

            # 표시용 이미지: 업로드된 파일을 다시 읽음
            display_imgs = []
            for f in files:
                f.seek(0)
                display_imgs.append(f)

            show_results(analysis, display_imgs)
