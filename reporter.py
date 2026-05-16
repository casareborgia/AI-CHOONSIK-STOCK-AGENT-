# ==============================================================================
# [AI Trading Agent] 출력 모듈 (Reporter)
# ==============================================================================
# 파이프라인의 최종 분석 결과를 정제하여 마크다운(Markdown) 리포트 파일로 저장하고,
# 텔레그램 등의 메신저 발송을 위한 요약 텍스트를 포맷팅합니다.
# 
# [정합성 극대화] 거래량 배수가 낮을 때도 '급증'이라고 하드코딩되던 논리적 오류를
# 동적 분기(급증/평균/응축)로 해결하고, 4대 시장 지수 행 누락 방지 로직을 유지합니다.

import sys
import os
from datetime import datetime

# 설정 및 엔진 임포트
import config
from core.technical_engine import analyze_technical_signals


def generate_markdown_report(leading_sectors, candidates):
    """
    분석 결과를 기반으로 일간 종합 마크다운 리포트를 생성 및 저장합니다.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_filename = f"daily_briefing_{today_str}.md"
    
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(config.OUTPUT_DIR, report_filename)
    
    strong_buys = [c for c in candidates if "매수" in c.get('signal', '') or "폭발" in c.get('signal', '')]
    
    print("\n📊 [리포팅 준비] 미국 4대 대표 시장 지수 파동 현황 집계 중...")
    index_candidates = [
        {'ticker': symbol, 'name': name, 'sector': 'Market Index', 'track': 'Index'} 
        for name, symbol in config.MARKET_INDICES.items()
    ]
    
    index_signals = analyze_technical_signals(index_candidates)
    sig_map = {item['ticker']: item for item in index_signals}
    
    index_name_map = {
        'DIA': '다우존스 (DIA)',
        'QQQ': '나스닥 100 (QQQ)',
        'SPY': 'S&P 500 (SPY)',
        'IWM': '러셀 2000 (IWM)'
    }
    
    md_content = f"""# 📈 [AI 춘식 MK1] 미국 주식 파동에너지 퀀트 브리핑 ({today_str})

본 리포트는 **파동에너지 이론(Wave Energy Theory)**을 바탕으로 자금 흐름, 기본적 가치, 기술적 타점을 입체 분석한 기관급 자동 스크리닝 결과입니다.
*(데이터 소스: Yahoo Finance API 정규장 종가 기준)*

---

## 📊 1. 미국 4대 시장 지수 파동 현황
현재 증시 전체의 투심을 지배하는 핵심 지수 4개의 파동에너지 및 기술적 상태입니다.

| 지수명 (티커) | 현재 종가 | 파동 시그널 상태 | 스토캐스틱 요약 |
| :--- | :---: | :---: | :---: |
"""
    
    for symbol in ['DIA', 'QQQ', 'SPY', 'IWM']:
        disp_name = index_name_map.get(symbol, symbol)
        item = sig_map.get(symbol, {})
        
        close_val = item.get('close', 0.0)
        sig_str = item.get('signal', '데이터 집계 지연')
        stoch_str = item.get('stoch_summary', 'N/A')
        
        if "매수" in sig_str or "폭발" in sig_str:
            sig_str = f"**{sig_str}**"
            
        md_content += f"| **{disp_name}** | ${close_val:,.2f} | {sig_str} | `{stoch_str}` |\n"
        
    md_content += f"""
> **💡 지수 분석 팁**: 대형주(SPY/QQQ)와 소형주(IWM)의 시그널 괴리가 발생할 경우, 상승 시그널이 강한 시장에 속한 종목군에 비중을 실어 대응하십시오.

---

## 🏆 2. 오늘의 탑다운 주도 섹터 (자금 유입 최상위)
현재 미국 증시 전체에서 자금이 집중되고 있는 상위 주도 섹터입니다.
"""
    
    for idx, sec in enumerate(leading_sectors, 1):
        md_content += f"- **TOP {idx}**: `{sec}`\n"
        
    md_content += f"""
> **💡 탑다운 전략 안내**: 소외 섹터의 종목은 가급적 매수를 피하고, 위 주도 섹터 내부에서 파동 시그널이 발생한 종목을 최우선 공략하십시오.

---

## 🎯 3. 정밀 타점 포착 핵심 후보군 (총 {len(strong_buys)}개)
- **Track A (펀더멘털 스윙 트랙)**: {len([c for c in strong_buys if c.get('track', 'Track A') == 'Track A'])}개 포착
- **Track B (SNS 모멘텀 급등 트랙)**: {len([c for c in strong_buys if c.get('track') == 'Track B'])}개 포착

"""
    
    if not strong_buys:
        md_content += "오늘 시장에서는 거래량 급증을 동반한 완벽한 찐폭발/매수 타점 종목이 포착되지 않았습니다. 현금 비중 유지를 권장합니다.\n"
    else:
        for idx, item in enumerate(strong_buys, 1):
            track = item.get('track', 'Track A')
            badge = "🌲 **[우량주 트랙]**" if track == 'Track A' else "🚀 **[SNS 모멘텀]**"
            
            # [거래량 문자열 동적 분기] GPT 지적사항 완벽 반영
            vol_val = item.get('vol_ratio', 1.0)
            if vol_val >= 1.2:
                vol_desc = f"**{vol_val:.1f}배** 급증 (수급 유입)"
            elif vol_val >= 0.8:
                vol_desc = f"**{vol_val:.1f}배** (평균 수준)"
            else:
                vol_desc = f"**{vol_val:.1f}배** (저조 / 추세 지속을 위한 에너지 응축 구간)"
                
            disp_sec = item.get('disp_sector', item.get('sector', 'Unknown'))
            close_val = item.get('close', 0.0)
            high_val = item.get('high', 0.0)
            low_val = item.get('low', 0.0)
            
            # 가격 오차 플래그 판별
            price_flag = ""
            if high_val > 0 and low_val > 0:
                if close_val > high_val or close_val < low_val:
                    price_flag = " `⚠️ 데이터 소스 오차 주의`"
                
            md_content += f"### {idx}. {badge} {item.get('name', item['ticker'])} (`{item['ticker']}`)\n\n"
            md_content += f"- **시그널 상태**: **{item.get('signal', '알 수 없음')}**\n"
            md_content += f"- **소속 섹터**: {disp_sec}\n"
            md_content += f"- **현재 종가**: ${close_val:,.2f}{price_flag}\n"
            md_content += f"- **거래량 배수**: 20일 평균 대비 {vol_desc}\n"
            
            if track == 'Track A':
                pe_str = f" | P/E: {item.get('pe', 0.0):.2f}" if item.get('pe', 0.0) > 0 else ""
                peg_str = f" | PEG: {item.get('peg', 0.0):.2f}" if item.get('peg', 0.0) > 0 else ""
                md_content += f"- **재무 및 가치 검증**: 기관 지분율 {item.get('inst_own', 0.0):.1f}% | 잉여현금흐름(FCF) ${item.get('fcf', 0):,.0f}{pe_str}{peg_str}\n"
            else:
                pe_str = f" | P/E: {item.get('pe', 0.0):.2f}" if item.get('pe', 0.0) > 0 else ""
                md_content += f"- **모멘텀 지표**: 최근 24시간 내 최소 **{item.get('mentions', 0)}회** 이상 커뮤니티 언급 폭증{pe_str}\n"
                
            md_content += f"- **파동 요약**: `{item.get('stoch_summary', '')}`\n\n"
            
            ai_text = item.get('ai_briefing', 'AI 브리핑 생성 누락 또는 제외됨')
            md_content += f"#### 🤖 로컬 AI 심층 내러티브 분석\n"
            md_content += f"{ai_text}\n\n"
            md_content += "---\n"
            
    md_content += """
## ⚠️ 4. 리스크 관리 고지
- 본 리포트는 알고리즘에 의해 자동 생성된 참고 자료이며, 법적인 투자 권유나 책임의 근거로 사용될 수 없습니다.
- 제시된 기계적 손절 라인(예: 5일선 또는 20일선 이탈)을 엄격히 준수하여 계좌를 보호하십시오.

---
**[지표 범례 안내]**
* **S / M / L**: 각각 단기(5.3.3), 중기(10.5.5), 장기(20.12.12) 스토캐스틱 파동 지표를 의미합니다.
* **▲ / ▼**: 스토캐스틱 %K가 %D를 상향 돌파(상승 추세)했는지, 하향 이탈(하락 추세)했는지를 나타냅니다.
"""
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
        
    print(f"\n📝 [5단계-A: 리포팅] 일간 종합 분석 리포트 생성 완료: {report_path}")
    return report_path


def format_telegram_message(leading_sectors, candidates):
    """
    모바일에서 한눈에 보기 편하도록 핵심 시그널만 텔레그램용 문자열로 압축합니다.
    """
    strong_buys = [c for c in candidates if "매수" in c.get('signal', '') or "폭발" in c.get('signal', '')]
    
    msg = f"🔔 [AI 춘식 MK1.5 분석 보고]\n"
    msg += f"📊 지수 스캔: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    msg += f"🏆 주도 섹터: {', '.join(leading_sectors[:2])}\n"
    msg += f"🔥 타점 포착 ({len(strong_buys)}개):\n"
    
    for c in strong_buys:
        track_icon = "🌲" if c.get('track', 'Track A') == 'Track A' else "🚀"
        msg += f"- {track_icon} {c['ticker']} ({c.get('signal', '')[:5]} | {c.get('vol_ratio',1.0):.1f}배)\n"
        
    msg += f"\n📂 상세 리포트가 생성되었습니다."
    return msg


async def send_telegram_message(message_text):
    """
    설정된 봇 토큰과 채팅 ID를 사용하여 텔레그램 메시지를 실제로 전송합니다.
    """
    import httpx
    
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("\n⚠️ 텔레그램 설정이 비어 있어 메시지를 전송하지 않습니다.")
        return False
        
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                print(f"✅ 텔레그램 알림 발송 성공!")
                return True
            else:
                print(f"❌ 텔레그램 발송 실패 (상태 코드: {resp.status_code}): {resp.text}")
                return False
    except Exception as e:
        print(f"❌ 텔레그램 전송 중 예외 발생: {e}")
        return False


if __name__ == "__main__":
    sample_secs = ['Technology']
    sample_cands = [{
        'ticker': 'AAPL', 
        'name': 'Apple Inc.', 
        'signal': '🔥 찐폭발 (강력매수)', 
        'close': 150.0,
        'inst_own': 65.0, 
        'fcf': 5000000, 
        'vol_ratio': 0.5,
        'sector': 'Technology',
        'stoch_summary': 'S:▲ M:▲ L:▲',
        'ai_briefing': '샘플 텍스트'
    }]
    generate_markdown_report(sample_secs, sample_cands)
