# Directive: 쿠팡 상품 상세페이지 분석

## 목적
쿠팡 상품 URL을 입력받아 상세페이지 이미지를 추출하고, Google Gemini API로 분석하여 점수와 개선안을 제공한다.

## 입력
- 쿠팡 상품 URL (예: https://www.coupang.com/vp/products/...)

## 도구 / 스크립트
- `execution/scrape_coupang.py` — URL에서 썸네일·상세 이미지 URL 목록 추출
- `execution/analyze_images.py` — 이미지 목록을 Gemini에 전달하고 분석 결과 반환

## 출력
- 4개 항목 점수 (각 25점 만점): 썸네일 클릭률, 상단 후킹 지수, 구매 전환 설득력, 가독성
- 총점 (100점 만점)
- 항목별 개선안 (불렛포인트)

## 분석 프롬프트 (Gemini 전송용)
```
너는 10년 차 이커머스 상세페이지 컨설팅 전문가야.
다음 이미지를 보고 아래 4개 항목을 각각 25점 만점으로 평가해줘:
1. 썸네일 클릭률
2. 상단 후킹 지수
3. 구매 전환 설득력
4. 가독성

총합 100점 만점으로 계산하고, 구체적인 개선안을 불렛포인트로 작성해.

반드시 아래 JSON 형식으로만 응답해:
{
  "scores": {
    "썸네일 클릭률": <0-25 정수>,
    "상단 후킹 지수": <0-25 정수>,
    "구매 전환 설득력": <0-25 정수>,
    "가독성": <0-25 정수>
  },
  "total": <총합 정수>,
  "improvements": [
    "개선안 1",
    "개선안 2",
    ...
  ]
}
```

## 엣지 케이스 & 주의사항
- 쿠팡은 User-Agent 없이 요청하면 403 반환 → 반드시 브라우저 헤더 포함
- 상세 이미지(desc-img)가 없는 경우 썸네일만으로 분석 진행
- Gemini에 전달하는 이미지는 최대 10장으로 제한 (토큰/비용 관리)
- 이미지 다운로드 실패 시 해당 URL 스킵하고 나머지로 진행
- Gemini 응답이 JSON 파싱 실패 시 raw 텍스트를 fallback으로 표시

## 학습된 내용 (업데이트됨)
- 쿠팡은 headless 브라우저(Playwright/Selenium 기본)를 전면 차단 → undetected-chromedriver headed 모드 필수
- 슬라이더 이미지: `//thumbnail.coupangcdn.com/thumbnails/remote/492x492ex/` 패턴
- 상세 이미지: "상품정보 더보기" 버튼 클릭 후 `//thumbnail.coupangcdn.com/thumbnails/remote/q89/` 패턴으로 로드됨
- "더보기" 버튼 셀렉터: `div.expand` (CSS class) 또는 `[class*='seemore']`
- 버튼 클릭은 JavaScript click (`arguments[0].click()`) 사용 - 일반 click()은 인터셉트될 수 있음
