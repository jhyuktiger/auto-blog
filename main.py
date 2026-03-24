"""
Auto Blog Generator
Claude API → Google Blogger API
매일 한국어 1개 + 영어 1개 자동 발행
"""

import os
import json
import random
import datetime
import anthropic
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ── Config ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
BLOGGER_REFRESH_TOKEN = os.environ["BLOGGER_REFRESH_TOKEN"]
BLOGGER_CLIENT_ID = os.environ["BLOGGER_CLIENT_ID"]
BLOGGER_CLIENT_SECRET = os.environ["BLOGGER_CLIENT_SECRET"]
KO_BLOG_ID = os.environ["KO_BLOG_ID"]
EN_BLOG_ID = os.environ["EN_BLOG_ID"]

# ── Topic Pools (고단가 키워드 중심) ────────────────────
KO_TOPICS = [
    # AI/바이브코딩
    {"title": "Claude API로 자동화 도구 만드는 법 (초보자 완전 가이드)", "keywords": ["Claude API", "AI 자동화", "바이브코딩"], "category": "AI"},
    {"title": "바이브코딩이란? 2025년 개발자 없이 앱 만드는 방법", "keywords": ["바이브코딩", "Cursor", "bolt.new"], "category": "AI"},
    {"title": "ChatGPT vs Claude 실전 비교 – 어떤 AI가 더 유용한가", "keywords": ["ChatGPT", "Claude", "AI 비교"], "category": "AI"},
    {"title": "Cursor AI로 코딩 10배 빠르게 하는 실전 팁", "keywords": ["Cursor AI", "AI 코딩", "개발 생산성"], "category": "AI"},
    {"title": "AI로 월 100만원 버는 현실적인 방법 5가지", "keywords": ["AI 부업", "AI 수익화", "AI 활용"], "category": "AI"},
    {"title": "n8n 자동화로 반복 업무 없애는 방법 (무료)", "keywords": ["n8n", "업무 자동화", "노코드"], "category": "AI"},
    # 재테크/투자
    {"title": "비트코인 2025 전망 – 반감기 이후 실제로 어떻게 될까", "keywords": ["비트코인 전망", "BTC 2025", "암호화폐"], "category": "투자"},
    {"title": "달러 ETF로 환율 헤지하는 방법 완전 정리", "keywords": ["달러 ETF", "환율 헤지", "달러 투자"], "category": "투자"},
    {"title": "미국 주식 배당금 세금 완벽 정리 (2025 기준)", "keywords": ["미국 주식 세금", "배당 세금", "해외 주식"], "category": "투자"},
    {"title": "S&P500 ETF 매달 적립식 투자 10년 시뮬레이션", "keywords": ["S&P500", "ETF 투자", "적립식"], "category": "투자"},
    {"title": "코인 선물거래 리스크 관리 – 청산 당하지 않는 법", "keywords": ["선물거래", "코인 리스크", "청산 방지"], "category": "투자"},
    {"title": "ISA 계좌 완전 정복 – 세금 혜택 최대로 쓰는 방법", "keywords": ["ISA 계좌", "절세", "재테크"], "category": "투자"},
]

EN_TOPICS = [
    # AI tools / vibe coding
    {"title": "Vibe Coding in 2025: Build Apps Without Writing Code", "keywords": ["vibe coding", "no-code", "AI development"], "category": "AI"},
    {"title": "Claude API Tutorial: Automate Any Task in 30 Minutes", "keywords": ["Claude API", "AI automation", "Python"], "category": "AI"},
    {"title": "Best AI Tools for Side Hustle in 2025 (Ranked)", "keywords": ["AI tools", "side hustle", "make money AI"], "category": "AI"},
    {"title": "Cursor vs GitHub Copilot: Which AI Coding Tool Wins in 2025?", "keywords": ["Cursor AI", "GitHub Copilot", "AI coding"], "category": "AI"},
    {"title": "How to Make $1000/Month Using Claude and n8n Automation", "keywords": ["Claude automation", "n8n", "passive income AI"], "category": "AI"},
    {"title": "Build a Crypto Dashboard with AI in One Day (No Code)", "keywords": ["crypto dashboard", "vibe coding", "bolt.new"], "category": "AI"},
    # Finance / Investing
    {"title": "Bitcoin Halving Cycle Explained: What History Says About 2025", "keywords": ["Bitcoin halving", "BTC price prediction", "crypto investing"], "category": "Finance"},
    {"title": "S&P 500 vs Bitcoin: 10-Year Return Comparison", "keywords": ["S&P 500", "Bitcoin investment", "portfolio"], "category": "Finance"},
    {"title": "How to Invest in US Stocks from Korea (Step-by-Step)", "keywords": ["invest US stocks Korea", "overseas investing", "ETF"], "category": "Finance"},
    {"title": "Dollar Cost Averaging Bitcoin: 3-Year Simulation Results", "keywords": ["DCA Bitcoin", "crypto strategy", "dollar cost averaging"], "category": "Finance"},
    {"title": "Best High-Dividend ETFs for Passive Income in 2025", "keywords": ["dividend ETF", "passive income", "high yield"], "category": "Finance"},
    {"title": "Crypto Fear & Greed Index: How to Use It to Time the Market", "keywords": ["fear greed index", "crypto timing", "market sentiment"], "category": "Finance"},
]

# ── Claude API로 글 생성 ─────────────────────────────────
def generate_post(topic: dict, lang: str) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.date.today().strftime("%Y년 %m월 %d일" if lang == "ko" else "%B %d, %Y")

    if lang == "ko":
        system = """당신은 한국의 전문 블로거입니다.
애드센스 수익을 극대화하는 SEO 최적화 블로그 글을 작성합니다.
규칙:
- HTML 형식으로 작성 (h2, h3, p, ul, li, strong 태그 사용)
- 2000~3000자 분량
- 키워드를 자연스럽게 3~5회 반복
- 서론 → 본론(3~5개 섹션) → 결론 구조
- 실용적이고 구체적인 내용
- 과장 표현, 투자 권유 금지
- 마지막에 면책 조항: "본 글은 정보 제공 목적이며 투자 권유가 아닙니다." (투자 주제인 경우)
- 절대 허위 정보 작성 금지"""

        user_prompt = f"""오늘 날짜: {today}

제목: {topic['title']}
키워드: {', '.join(topic['keywords'])}
카테고리: {topic['category']}

위 주제로 SEO 최적화된 블로그 글을 HTML 형식으로 작성해주세요.
JSON으로 응답하세요:
{{
  "title": "최종 제목",
  "html_content": "HTML 본문",
  "labels": ["태그1", "태그2", "태그3"]
}}"""

    else:  # en
        system = """You are a professional blogger writing high-quality SEO content.
Rules:
- Write in HTML format (use h2, h3, p, ul, li, strong tags)
- 1500-2500 words
- Naturally include keywords 3-5 times
- Structure: intro → body (3-5 sections) → conclusion
- Practical, specific, actionable content
- No investment advice or guarantees
- Add disclaimer at the end for finance topics: "This article is for informational purposes only and does not constitute financial advice."
- Never write false information"""

        user_prompt = f"""Today: {today}

Title: {topic['title']}
Keywords: {', '.join(topic['keywords'])}
Category: {topic['category']}

Write an SEO-optimized blog post in HTML format.
Respond in JSON:
{{
  "title": "Final Title",
  "html_content": "HTML body content",
  "labels": ["tag1", "tag2", "tag3"]
}}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",  # 비용 절감용 Haiku
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw = message.content[0].text
    # JSON 파싱
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])


# ── Google Blogger API (OAuth) ───────────────────────────
def get_blogger_service():
    creds = Credentials(
        token=None,
        refresh_token=BLOGGER_REFRESH_TOKEN,
        client_id=BLOGGER_CLIENT_ID,
        client_secret=BLOGGER_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/blogger"]
    )
    creds.refresh(Request())
    return build("blogger", "v3", credentials=creds)


def publish_post(service, blog_id: str, title: str, html_content: str, labels: list):
    # LeaderView 광고 배너 (나중에 활성화)
    leaderview_banner = """
<!-- LeaderView AD (reserved) -->
<!-- <div style="margin:24px 0;text-align:center;">
  <a href="https://leaderview.app" target="_blank">
    <img src="https://leaderview.app/banner.png" alt="LeaderView - 실시간 크립토 대시보드" style="max-width:728px;width:100%;border-radius:8px;">
  </a>
</div> -->
"""
    full_content = leaderview_banner + html_content

    body = {
        "title": title,
        "content": full_content,
        "labels": labels,
    }
    result = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    return result.get("url", "")


# ── 메인 실행 ────────────────────────────────────────────
def main():
    print("🚀 Auto Blog Generator 시작")
    service = get_blogger_service()

    # 오늘 날짜 기반 랜덤 시드 (매일 다른 주제)
    today_seed = int(datetime.date.today().strftime("%Y%m%d"))
    random.seed(today_seed)

    # 한국어 글 생성 & 발행
    ko_topic = random.choice(KO_TOPICS)
    print(f"📝 KO 주제: {ko_topic['title']}")
    ko_post = generate_post(ko_topic, "ko")
    ko_url = publish_post(service, KO_BLOG_ID, ko_post["title"], ko_post["html_content"], ko_post["labels"])
    print(f"✅ KO 발행 완료: {ko_url}")

    # 영어 글 생성 & 발행
    en_topic = random.choice(EN_TOPICS)
    print(f"📝 EN 주제: {en_topic['title']}")
    en_post = generate_post(en_topic, "en")
    en_url = publish_post(service, EN_BLOG_ID, en_post["title"], en_post["html_content"], en_post["labels"])
    print(f"✅ EN 발행 완료: {en_url}")

    print("🎉 완료!")


if __name__ == "__main__":
    main()
