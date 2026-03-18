"""
analyze_images.py
-----------------
이미지 URL 목록을 Google Gemini 1.5 Flash API에 전달하여 상세페이지 분석 결과를 반환한다.

Usage:
    python execution/analyze_images.py <image_url1> [image_url2 ...]

Output (stdout, JSON):
    {
        "scores": {
            "썸네일 클릭률": 20,
            "상단 후킹 지수": 18,
            "구매 전환 설득력": 22,
            "가독성": 19
        },
        "total": 79,
        "improvements": ["개선안 1", "개선안 2", ...]
    }

환경 변수:
    GEMINI_API_KEY — Google Gemini API 키 (.env 또는 시스템 환경변수)
"""

import sys
import json
import os
import re
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import requests
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# 분석 프롬프트 (directive에서 정의된 내용)
ANALYSIS_PROMPT = """너는 10년 차 이커머스 상세페이지 컨설팅 전문가야.
다음 이미지를 보고 아래 4개 항목을 각각 25점 만점으로 평가해줘:
1. 썸네일 클릭률
2. 상단 후킹 지수
3. 구매 전환 설득력
4. 가독성

총합 100점 만점으로 계산하고, 구체적인 개선안을 불렛포인트로 작성해.

반드시 아래 JSON 형식으로만 응답해 (다른 텍스트 없이):
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
    "개선안 2"
  ]
}"""

SCORE_KEYS = ["썸네일 클릭률", "상단 후킹 지수", "구매 전환 설득력", "가독성"]


def download_image_bytes(url: str) -> bytes | None:
    """이미지 URL에서 바이트 데이터를 다운로드한다. 실패 시 None 반환."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.coupang.com/",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"[warn] 이미지 다운로드 실패 ({url}): {e}", file=sys.stderr)
        return None


def parse_gemini_response(raw_text: str) -> dict:
    """
    Gemini 응답 텍스트에서 JSON을 파싱한다.
    JSON 파싱 실패 시 fallback 구조로 반환한다.
    """
    # JSON 블록 추출 시도 (```json ... ``` 또는 { ... })
    json_match = re.search(r"\{[\s\S]*\}", raw_text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            # 필수 키 검증
            if "scores" in data and "improvements" in data:
                # total 재계산 (Gemini가 잘못 계산할 수 있음)
                scores = data["scores"]
                data["total"] = sum(scores.get(k, 0) for k in SCORE_KEYS)
                return data
        except json.JSONDecodeError:
            pass

    # Fallback: 파싱 실패 시 raw 텍스트를 improvements에 담아 반환
    return {
        "scores": {k: 0 for k in SCORE_KEYS},
        "total": 0,
        "improvements": [raw_text],
        "parse_error": True,
    }


def analyze(image_urls: list[str], api_key: str) -> dict:
    """
    이미지 URL 목록을 Gemini 1.5 Flash에 전달하여 분석 결과를 반환한다.

    Args:
        image_urls: 분석할 이미지 URL 목록
        api_key: Google Gemini API 키

    Returns:
        파싱된 분석 결과 딕셔너리
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # 이미지 다운로드 (실패한 이미지는 스킵)
    image_parts = []
    for url in image_urls:
        img_bytes = download_image_bytes(url)
        if img_bytes:
            image_parts.append({
                "mime_type": "image/jpeg",
                "data": img_bytes,
            })

    if not image_parts:
        return {
            "scores": {k: 0 for k in SCORE_KEYS},
            "total": 0,
            "improvements": ["이미지를 불러오지 못했습니다. URL을 확인해주세요."],
            "error": "no_images",
        }

    # Gemini 요청 구성: [프롬프트] + [이미지들]
    contents = [ANALYSIS_PROMPT] + [
        {"mime_type": part["mime_type"], "data": part["data"]}
        for part in image_parts
    ]

    response = model.generate_content(contents)
    raw_text = response.text.strip()

    return parse_gemini_response(raw_text)


def analyze_bytes(image_bytes_list: list[bytes], api_key: str) -> dict:
    """
    이미지 바이트 목록을 Gemini 1.5 Flash에 전달하여 분석 결과를 반환한다.
    (파일 업로드 모드에서 사용)
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    image_parts = [
        {"mime_type": "image/jpeg", "data": b}
        for b in image_bytes_list
        if b
    ]

    if not image_parts:
        return {
            "scores": {k: 0 for k in SCORE_KEYS},
            "total": 0,
            "improvements": ["이미지를 불러오지 못했습니다."],
            "error": "no_images",
        }

    contents = [ANALYSIS_PROMPT] + [
        {"mime_type": part["mime_type"], "data": part["data"]}
        for part in image_parts
    ]

    response = model.generate_content(contents)
    raw_text = response.text.strip()
    return parse_gemini_response(raw_text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: analyze_images.py <url1> [url2 ...]"}))
        sys.exit(1)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(json.dumps({"error": "GEMINI_API_KEY 환경변수가 설정되지 않았습니다."}))
        sys.exit(1)

    urls = sys.argv[1:]
    try:
        result = analyze(urls, api_key)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
