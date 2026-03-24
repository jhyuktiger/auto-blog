# Auto Blog Generator – 셋업 가이드

Claude API → GitHub Actions → Google Blogger 자동 발행 시스템

---

## 폴더 구조

```
auto-blog/
├── main.py                        # 핵심 로직
├── requirements.txt
├── .github/
│   └── workflows/
│       └── daily_post.yml         # 매일 자동 실행
└── README.md
```

---

## 1단계 – Google Blogger 설정

### 블로그 2개 생성
1. [blogger.com](https://blogger.com) 접속
2. 블로그 생성 → **한국어 블로그** (예: `ai-money-kr.blogspot.com`)
3. 블로그 생성 → **영어 블로그** (예: `ai-money-en.blogspot.com`)
4. 각 블로그의 URL에서 Blog ID 확인:
   - 설정 → 기본 → 블로그 ID (숫자)

### Google Cloud 서비스 계정 생성
1. [console.cloud.google.com](https://console.cloud.google.com) 접속
2. 새 프로젝트 생성 (예: `auto-blog`)
3. **API 및 서비스** → **라이브러리** → `Blogger API v3` 활성화
4. **API 및 서비스** → **사용자 인증 정보** → **서비스 계정 만들기**
   - 이름: `auto-blog-poster`
   - 역할: Editor
5. 서비스 계정 → **키** → **키 추가** → JSON 다운로드
6. 다운로드된 JSON 파일 내용을 복사해둠

### 서비스 계정을 블로그에 등록
1. Blogger → 설정 → 사용자 및 권한
2. **사용자 추가** → 서비스 계정 이메일 (`xxx@xxx.iam.gserviceaccount.com`) 입력
3. 역할: **관리자** 선택
4. 한국어 블로그, 영어 블로그 둘 다 반복

---

## 2단계 – GitHub 설정

### 레포지토리 생성
```bash
git init
git add .
git commit -m "init: auto blog generator"
git remote add origin https://github.com/YOUR_USERNAME/auto-blog.git
git push -u origin main
```

### GitHub Secrets 등록
레포지토리 → Settings → Secrets and variables → Actions → New repository secret

| Secret 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Console에서 복사 |
| `BLOGGER_CREDENTIALS_JSON` | 서비스 계정 JSON 파일 **전체 내용** (한 줄로) |
| `KO_BLOG_ID` | 한국어 블로그 숫자 ID |
| `EN_BLOG_ID` | 영어 블로그 숫자 ID |

> BLOGGER_CREDENTIALS_JSON: JSON 파일을 텍스트 에디터로 열어 전체 복사 후 붙여넣기

---

## 3단계 – 실행 확인

### 수동 테스트
GitHub → Actions → Daily Auto Blog Post → **Run workflow**

### 자동 실행 시간
매일 오전 9시 KST (UTC 00:00)

---

## 비용 계산

| 항목 | 비용 |
|---|---|
| Claude Haiku (글 2개/일) | ~$0.003/일 → 월 $0.09 |
| Google Blogger | 무료 |
| GitHub Actions | 무료 (Public repo) |
| **총합** | **월 $0.1 미만** |

---

## LeaderView 광고 삽입 (나중에)

`main.py` → `publish_post()` 함수 내 leaderview_banner 주석 해제:
```python
leaderview_banner = """
<div style="margin:24px 0;text-align:center;">
  <a href="https://leaderview.app" target="_blank">
    <img src="https://leaderview.app/banner.png" ...>
  </a>
</div>
"""
```

---

## 주제 추가 방법

`main.py` → `KO_TOPICS` 또는 `EN_TOPICS` 배열에 딕셔너리 추가:
```python
{"title": "새 글 제목", "keywords": ["키워드1", "키워드2"], "category": "AI"}
```

---

## 트러블슈팅

**Q: Actions 실행이 안 됨**
- Settings → Actions → General → Allow all actions 확인

**Q: Blogger 발행 실패**
- 서비스 계정 이메일이 블로그 관리자로 등록됐는지 확인
- Blogger API가 GCP에서 활성화됐는지 확인

**Q: JSON 파싱 에러**
- Claude가 가끔 마크다운 코드블록을 붙임 → main.py의 파싱 로직이 자동 처리
