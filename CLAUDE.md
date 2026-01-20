# CLAUDE.md

이 파일은 Claude Code가 프로젝트를 이해하는 데 필요한 정보를 담고 있습니다.

## 프로젝트 개요

티스토리 블로그 글 자동 생성 웹 서비스입니다. Google Trends에서 인기 키워드를 가져오거나, URL의 콘텐츠를 분석하여 Anthropic Claude API로 마크다운 형식의 블로그 글을 생성합니다.

## 기술 스택

- **백엔드**: FastAPI + Uvicorn
- **AI**: Anthropic Claude API (claude-sonnet-4)
- **트렌드**: trendspyg (Google Trends RSS/CSV)
- **웹 검색**: DuckDuckGo Search
- **프론트엔드**: 정적 HTML/CSS/JS (static 폴더)

## 프로젝트 구조

```
app/
├── main.py          # FastAPI 앱, API 엔드포인트 정의
├── writer.py        # Claude API를 이용한 글 생성 로직
├── trends.py        # Google Trends 키워드 수집 (캐시 포함)
├── search.py        # DuckDuckGo 웹/뉴스 검색, URL 콘텐츠 추출
└── rate_limit.py    # 인메모리 Rate Limiter

static/
├── index.html       # 메인 UI
├── app.js           # 프론트엔드 로직
└── style.css        # 스타일

tests/
├── test_api.py      # API 엔드포인트 테스트
├── test_trends.py   # 트렌드 수집 테스트
└── test_rate_limit.py # Rate Limiter 테스트
```

## 핵심 모듈 설명

### app/main.py
- FastAPI 앱 인스턴스 및 모든 API 엔드포인트 정의
- `GenerateRequest`, `GenerateFromUrlRequest`: Pydantic 모델로 요청 검증
- Rate Limiting: `generate_limiter` (분당 5회), `trends_limiter` (분당 20회)

### app/writer.py
- `generate_article_md()`: 키워드 기반 마크다운 글 생성
- `generate_article_md_stream()`: 스트리밍 버전
- `generate_article_from_url()`: URL 콘텐츠 기반 글 생성
- `generate_article_from_url_stream()`: 스트리밍 버전
- `_build_prompts()`, `_build_url_prompts()`: 프롬프트 생성 헬퍼

### app/trends.py
- `get_trending_keywords()`: Google Trends 키워드 수집
- `TrendsCache`: 10분 TTL 인메모리 캐시
- `REGIONS`: 지원 지역 (현재 한국만)
- `FALLBACK_KEYWORDS`: RSS 실패 시 사용할 예시 키워드

### app/search.py
- `search_web()`: DuckDuckGo 웹 검색 + 뉴스 검색
- `fetch_url_content()`: URL에서 제목, 본문, 메타 정보 추출
- `search_related_to_url()`: URL 분석 + 관련 검색 결과 수집

## 자주 사용하는 명령어

```bash
# 서버 실행
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 테스트 실행
pytest

# 커버리지 포함 테스트
pytest --cov=app --cov-report=term-missing

# 의존성 설치
python -m pip install -r requirements.txt
```

## 환경 변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `ANTHROPIC_API_KEY` | O (또는 웹에서 입력) | Claude API 키 |
| `CLAUDE_MODEL` | X | 사용할 Claude 모델 (기본: claude-sonnet-4-20250514) |
| `USE_CSV_TRENDS` | X | CSV 트렌드 수집 활성화 (기본: false) |

## API 엔드포인트

- `GET /api/regions`: 지원 지역 목록
- `GET /api/trends`: 인기 검색어 조회
- `POST /api/generate`: 키워드 기반 글 생성
- `POST /api/generate/stream`: 키워드 기반 글 스트리밍 생성
- `POST /api/generate-from-url`: URL 기반 글 생성
- `POST /api/generate-from-url/stream`: URL 기반 글 스트리밍 생성

## 코드 스타일

- Python 3.10+ 타입 힌트 사용
- Pydantic field_validator로 입력 검증
- 로깅: `logging.getLogger("app.모듈명")` 패턴
- 한국어 주석 및 사용자 메시지

## 테스트 작성 시 참고

- `httpx.AsyncClient` 또는 `TestClient` 사용
- API 키가 필요한 테스트는 환경 변수 또는 모킹 필요
- Rate Limiter 테스트 시 `limiter.requests.clear()` 로 초기화
