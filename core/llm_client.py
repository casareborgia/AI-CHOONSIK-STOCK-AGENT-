# ==============================================================================
# [AI Trading Agent] 코어 공통 모듈: 로컬 LLM 클라이언트 (Ollama)
# ==============================================================================
# Ollama 통신 및 신뢰불가 텍스트 정제 로직의 단일 구현체.
# ai_verify.py / thesis_evaluator.py 등에서 중복 구현되던 것을 통합하여
# 재시도/백오프 등 견고성 로직을 한 곳에서 관리한다.

import json
import re
import time
import urllib.request
import urllib.parse

import config


def validate_url(url: str) -> bool:
    """SSRF 방지를 위해 URL의 호스트네임이 허용된 Ollama 엔드포인트 도메인인지 검증합니다."""
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        
        # 1. 설정된 OLLAMA_ENDPOINT 호스트와 매칭되는지 확인
        endpoint_host = urllib.parse.urlparse(config.OLLAMA_ENDPOINT).hostname
        if endpoint_host and hostname.lower() == endpoint_host.lower():
            return True
            
        # 2. 로컬호스트 등 기본 검증
        if hostname.lower() in {"localhost", "127.0.0.1"}:
            return True
    except Exception:
        pass
    return False


class OllamaUnavailable(Exception):
    """재시도 후에도 Ollama 서버 응답을 받지 못한 경우 발생."""
    pass


def clean_untrusted_text(text: str) -> str:
    """외부 신뢰할 수 없는 텍스트에서 백틱 및 구분자 위조 시도를 무력화하고 정제합니다."""
    if not text:
        return ""
    s = str(text).replace("```", "'''")
    # 구분자 토큰 위조 차단: <<<UNTRUSTED_...>>> 패턴을 통째로 중화
    s = re.sub(r"<<<\s*UNTRUSTED[^>]*>>>", "[차단된 구분자]", s, flags=re.IGNORECASE)
    return s


def call_ollama(prompt: str, model_type: str = "heavy", timeout: int = 60, max_retries: int = 3) -> str:
    """
    로컬 Ollama 서버와 통신하여 전체(non-stream) 텍스트 응답을 반환합니다.
    재시도/백오프를 내장하며, 최종 실패 시 OllamaUnavailable 예외를 발생시킵니다.
    (폴백 동작은 호출 측에서 정책에 맞게 처리한다.)
    """
    url = config.OLLAMA_ENDPOINT
    if not validate_url(url):
        raise ValueError(f"Blocked unsafe or disallowed URL (SSRF Prevention): {url}")
    target_model = config.HEAVY_LLM_MODEL if model_type == "heavy" else config.LIGHT_LLM_MODEL
    payload = {
        "model": target_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # 날짜 등 팩트 정확성을 극대화하기 위해 온도 최소화
            "top_p": 0.95
        }
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                return res_data.get("response", "응답 생성 실패")
        except Exception as e:
            last_error = e
            print(f"⚠️ [call_ollama] {attempt}차 호출 실패 ({e}). 재시도 대기 중...")
            time.sleep(attempt * 2)

    raise OllamaUnavailable(f"Ollama 호출 {max_retries}회 모두 실패: {last_error}")
