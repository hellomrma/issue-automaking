# 티스토리 글 자동 생성

인터넷 트렌드 키워드를 찾고, 해당 키워드에 맞는 블로그 글을 **마크다운(.md)** 으로 만들어 주는 웹 서비스입니다.
티스토리에 바로 붙여 넣어 사용할 수 있습니다.

## 기능

- **트렌드 키워드**: Google Trends(trendspyg) 인기 검색어 (한국). CSV 모드로 최대 수백 개 조회 가능(Chrome 필요), 실패 시 RSS(~10개) 또는 예시 키워드
- **키워드 기반 글 생성**: 선택/입력한 키워드로 Anthropic Claude를 이용해 티스토리용 마크다운 글 생성
- **URL 기반 글 생성**: 웹페이지 URL을 입력하면 해당 콘텐츠를 분석하여 새로운 관점의 블로그 글 생성
- **최신 정보 반영**: 키워드로 웹 검색 + 뉴스 기사(DuckDuckGo, 최근 1개월)를 참고해 시의성 있는 내용 포함 (선택, 기본 on)
- **스타일**: 정보성, 리뷰, How-to, 뉴스해설 중 선택
- **길이 옵션**: 짧게(400~600자), 보통(800~1,200자), 길게(1,200~1,800자) 선택 가능
- **태그**: 글 끝에 `#태그` 형태 5~10개 자동 포함
- **다운로드**: 생성된 글을 `.md` 파일로 저장하거나 클립보드에 복사

## 요구 사항

- Python 3.10+
- Claude API 키 (Anthropic, 글 생성용)

## 설치 및 실행

```bash
# 1. 가상환경 생성 및 활성화 (권장)
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS / Linux

# 2. 의존성 설치 (pip 대신 python -m pip 사용 권장)
python -m pip install -r requirements.txt

# 3. 환경변수 (선택, 웹에서 API 키 입력 가능)
copy env.example .env
# .env 에 ANTHROPIC_API_KEY=sk-ant-... 입력 (https://console.anthropic.com/ 에서 발급)

# 4. 서버 실행
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Windows만:** `install.bat` 더블클릭 → 의존성 설치, `run.bat` 더블클릭 → 서버 실행.

브라우저에서 **http://localhost:8000** 로 접속합니다.

### pip install 이 안 될 때

- `pip` 대신 **`python -m pip install -r requirements.txt`** 를 사용하세요.
- `python -m pip --version` 이 동작하는지 확인하고, `python` / `python3` 중 시스템에 맞는 명령을 쓰세요.

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/regions` | 트렌드 지원 지역 목록 |
| GET | `/api/trends?region=south_korea&limit=30` | Google 인기 검색어 |
| POST | `/api/generate` | 키워드로 마크다운 글 생성 |
| POST | `/api/generate/stream` | 키워드로 마크다운 글 스트리밍 생성 |
| POST | `/api/generate-from-url` | URL 콘텐츠 기반 마크다운 글 생성 |
| POST | `/api/generate-from-url/stream` | URL 콘텐츠 기반 마크다운 글 스트리밍 생성 |

### 글 생성 요청 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `keyword` | string | (필수) | 글 주제 키워드 |
| `url` | string | (필수, URL 기반) | 분석할 웹페이지 URL |
| `anthropic_api_key` | string | 환경변수 | Claude API 키 |
| `style` | string | "정보성" | 정보성, 리뷰, How-to, 뉴스해설 |
| `lang` | string | "ko" | ko(한국어), en(영어) |
| `length` | string | "medium" | short, medium, long |
| `use_emoji` | boolean | false | 이모지 사용 여부 |
| `use_web_search` | boolean | true | 최신 웹 검색 반영 여부 |

## 사용 흐름

### 키워드 기반 글 생성
1. **인기 검색어 불러오기** → **인기 검색어 불러오기** 버튼 클릭
2. **키워드 선택** → 트렌드 목록에서 클릭하거나 직접 입력
3. **글 생성** → 스타일/길이 선택 후 생성 (Claude API 키 필요)
4. **복사 / MD 저장** → 티스토리 에디터에 붙여 넣거나 파일로 보관

### URL 기반 글 생성
1. **URL 입력** → 참고할 웹페이지 URL 입력
2. **글 생성** → 원본 콘텐츠를 분석하여 새로운 관점의 글 생성
3. **복사 / MD 저장** → 티스토리 에디터에 붙여 넣거나 파일로 보관

## 트렌드 출처

- **구글**: [Google Trends](https://trends.google.com/) ( [trendspyg](https://pypi.org/project/trendspyg/) )
  - **RSS**: 모든 지역, 약 10~20개 (빠름)
  - **CSV(한국만)**: Chrome 설치 시 최대 ~480개. 실패 시 RSS로 자동 전환

## 라이선스

MIT
