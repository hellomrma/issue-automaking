"""트렌드 키워드 기반 티스토리 글 생성 웹 서비스"""
import logging
import os
import re
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger("app.main")
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from app.rate_limit import generate_limiter, rate_limit, trends_limiter
from app.search import fetch_url_content, search_related_to_url, search_web
from app.trends import REGIONS, get_trending_keywords
from app.writer import (
    generate_article_from_url,
    generate_article_from_url_stream,
    generate_article_md,
    generate_article_md_stream,
)

load_dotenv()

app = FastAPI(title="티스토리 글 자동 생성", version="1.0.0")


# ---------- API ----------

@app.get("/api/regions")
def api_regions():
    """지원 지역 목록 (트렌드용)"""
    return {"regions": [{"id": k, "name": v[0]} for k, v in REGIONS.items()]}


@app.get("/api/trends")
def api_trends(
    request: Request,
    region: str = Query("south_korea", description="지역 코드"),
    limit: int = Query(20, ge=1, le=100, description="키워드 개수 (한국 CSV 시 80 등 더 많이 요청 가능)"),
    _: None = Depends(rate_limit(trends_limiter)),
):
    """인기 검색어(트렌드) 키워드 목록"""
    try:
        keywords, source, google_keywords, recommend_keywords = get_trending_keywords(region=region, limit=limit)
        return {
            "keywords": keywords,
            "region": region,
            "source": source,
            "google": google_keywords,
            "recommend": recommend_keywords,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ---------- 공통 검증 함수 ----------

def _validate_api_key(v: Optional[str]) -> Optional[str]:
    """API 키 검증"""
    if v is None:
        return v
    v = v.strip()
    if not v:
        return None
    if not (v.startswith("sk-ant-") or v.startswith("sk-")):
        raise ValueError("올바른 API 키 형식이 아닙니다.")
    if len(v) < 20:
        raise ValueError("API 키가 너무 짧습니다.")
    return v


def _validate_lang(v: str) -> str:
    """언어 검증"""
    if v not in ("ko", "en"):
        raise ValueError("지원하지 않는 언어입니다. (ko, en)")
    return v


def _validate_style(v: str) -> str:
    """스타일 검증"""
    valid_styles = ("정보성", "리뷰", "How-to", "뉴스해설")
    if v not in valid_styles:
        raise ValueError(f"지원하지 않는 스타일입니다. ({', '.join(valid_styles)})")
    return v


def _validate_length(v: str) -> str:
    """길이 검증"""
    valid_lengths = ("short", "medium", "long")
    if v not in valid_lengths:
        raise ValueError(f"지원하지 않는 길이입니다. ({', '.join(valid_lengths)})")
    return v


def _validate_guide(v: Optional[str]) -> Optional[str]:
    """가이드 검증"""
    if v is None:
        return v
    v = v.strip()
    if not v:
        return None
    if len(v) > 1000:
        raise ValueError("가이드는 1000자 이하여야 합니다.")
    return v


def _validate_url(v: str, required: bool = True) -> Optional[str]:
    """URL 검증"""
    if v is None:
        return v
    v = v.strip()
    if not v:
        if required:
            raise ValueError("URL을 입력해 주세요.")
        return None
    if not v.startswith(("http://", "https://")):
        raise ValueError("올바른 URL 형식이 아닙니다. (http:// 또는 https://로 시작해야 합니다)")
    if len(v) > 2000:
        raise ValueError("URL이 너무 깁니다.")
    return v


# ---------- 요청 모델 ----------

class BaseGenerateRequest(BaseModel):
    """글 생성 요청의 공통 베이스 클래스"""
    anthropic_api_key: Optional[str] = None
    lang: str = "ko"
    style: str = "정보성"
    length: str = "medium"
    use_emoji: bool = False
    use_web_search: bool = True
    guide: Optional[str] = None

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_api_key(cls, v: Optional[str]) -> Optional[str]:
        return _validate_api_key(v)

    @field_validator("lang")
    @classmethod
    def validate_lang(cls, v: str) -> str:
        return _validate_lang(v)

    @field_validator("style")
    @classmethod
    def validate_style(cls, v: str) -> str:
        return _validate_style(v)

    @field_validator("length")
    @classmethod
    def validate_length(cls, v: str) -> str:
        return _validate_length(v)

    @field_validator("guide")
    @classmethod
    def validate_guide(cls, v: Optional[str]) -> Optional[str]:
        return _validate_guide(v)


class GenerateRequest(BaseGenerateRequest):
    """키워드 기반 글 생성 요청"""
    keyword: str
    reference_url: Optional[str] = None

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("키워드는 2자 이상이어야 합니다.")
        if len(v) > 100:
            raise ValueError("키워드는 100자 이하여야 합니다.")
        return v

    @field_validator("reference_url")
    @classmethod
    def validate_reference_url(cls, v: Optional[str]) -> Optional[str]:
        return _validate_url(v, required=False)


class GenerateFromUrlRequest(BaseGenerateRequest):
    """URL 기반 글 생성 요청"""
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return _validate_url(v, required=True)


@app.post("/api/generate")
def api_generate(
    request: Request,
    body: GenerateRequest,
    _: None = Depends(rate_limit(generate_limiter)),
):
    """키워드로 블로그 글(마크다운) 생성"""
    api_key = body.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY 환경변수 또는 요청 body의 anthropic_api_key를 설정해 주세요.",
        )
    if not (body.keyword or "").strip():
        raise HTTPException(status_code=400, detail="keyword를 입력해 주세요.")
    web_context = ""
    if body.use_web_search:
        try:
            web_context = search_web(
                body.keyword.strip(),
                max_results=5,
                region="kr-ko" if body.lang == "ko" else "wt-wt",
                timelimit="m",
            )
        except Exception as e:
            logger.warning("search_web before generate: %s", e)

    # 참고 URL 콘텐츠 가져오기
    reference_content = None
    if body.reference_url:
        try:
            ref_data = fetch_url_content(body.reference_url)
            ref_parts = []
            if ref_data.get("title"):
                ref_parts.append(f"제목: {ref_data['title']}")
            if ref_data.get("description"):
                ref_parts.append(f"설명: {ref_data['description']}")
            if ref_data.get("content"):
                ref_parts.append(f"본문:\n{ref_data['content'][:4000]}")
            reference_content = "\n\n".join(ref_parts) if ref_parts else None
        except Exception as e:
            logger.warning("fetch_url_content for reference_url failed: %s", e)

    try:
        md = generate_article_md(
            keyword=body.keyword.strip(),
            api_key=api_key,
            lang=body.lang,
            style=body.style,
            use_emoji=body.use_emoji,
            web_context=web_context or None,
            length=body.length,
            guide=body.guide,
            reference_content=reference_content,
        )
        return {"markdown": md, "keyword": body.keyword}
    except Exception as e:
        err_raw = getattr(e, "message", None) or getattr(e, "body", None) or str(e)
        msg = (err_raw if isinstance(err_raw, str) else str(err_raw)).lower()
        logger.exception("generate_article_md failed")

        if any(x in msg for x in ("credit", "billing", "purchase credits", "too low", "upgrade", "plans")) or ("balance" in msg and "low" in msg):
            detail = "Claude(Anthropic) API 크레딧이 부족합니다. https://console.anthropic.com/ → Plans & Billing 에서 크레딧을 충전해 주세요."
        elif "rate" in msg and "limit" in msg:
            detail = "Claude API 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
        elif "invalid" in msg and ("key" in msg or "api" in msg) or "authentication" in msg:
            detail = "Claude API 키가 올바르지 않습니다. 키를 확인해 주세요."
        elif "not_found" in msg and "model" in msg:
            detail = "설정된 Claude 모델을 찾을 수 없습니다. .env 의 CLAUDE_MODEL 을 확인하거나, 최신 Anthropic 문서의 모델 목록을 참고해 주세요."
        else:
            detail = str(e)
        raise HTTPException(status_code=502, detail=detail)


@app.post("/api/generate/stream")
def api_generate_stream(
    request: Request,
    body: GenerateRequest,
    _: None = Depends(rate_limit(generate_limiter)),
):
    """키워드로 블로그 글(마크다운) 스트리밍 생성"""
    api_key = body.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY 환경변수 또는 요청 body의 anthropic_api_key를 설정해 주세요.",
        )
    if not (body.keyword or "").strip():
        raise HTTPException(status_code=400, detail="keyword를 입력해 주세요.")

    web_context = ""
    if body.use_web_search:
        try:
            web_context = search_web(
                body.keyword.strip(),
                max_results=5,
                region="kr-ko" if body.lang == "ko" else "wt-wt",
                timelimit="m",
            )
        except Exception as e:
            logger.warning("search_web before generate: %s", e)

    # 참고 URL 콘텐츠 가져오기
    reference_content = None
    if body.reference_url:
        try:
            ref_data = fetch_url_content(body.reference_url)
            ref_parts = []
            if ref_data.get("title"):
                ref_parts.append(f"제목: {ref_data['title']}")
            if ref_data.get("description"):
                ref_parts.append(f"설명: {ref_data['description']}")
            if ref_data.get("content"):
                ref_parts.append(f"본문:\n{ref_data['content'][:4000]}")
            reference_content = "\n\n".join(ref_parts) if ref_parts else None
        except Exception as e:
            logger.warning("fetch_url_content for reference_url failed: %s", e)

    def generate():
        try:
            for chunk in generate_article_md_stream(
                keyword=body.keyword.strip(),
                api_key=api_key,
                lang=body.lang,
                style=body.style,
                use_emoji=body.use_emoji,
                web_context=web_context or None,
                length=body.length,
                guide=body.guide,
                reference_content=reference_content,
            ):
                yield chunk
        except Exception as e:
            err_raw = getattr(e, "message", None) or getattr(e, "body", None) or str(e)
            msg = (err_raw if isinstance(err_raw, str) else str(err_raw)).lower()
            logger.exception("generate_article_md_stream failed")
            if any(x in msg for x in ("credit", "billing", "purchase credits", "too low", "upgrade", "plans")):
                yield f"\n\n[ERROR] Claude(Anthropic) API 크레딧이 부족합니다."
            elif "rate" in msg and "limit" in msg:
                yield f"\n\n[ERROR] Claude API 요청 한도를 초과했습니다."
            elif "invalid" in msg and ("key" in msg or "api" in msg):
                yield f"\n\n[ERROR] Claude API 키가 올바르지 않습니다."
            else:
                yield f"\n\n[ERROR] {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@app.post("/api/generate-from-url")
def api_generate_from_url(
    request: Request,
    body: GenerateFromUrlRequest,
    _: None = Depends(rate_limit(generate_limiter)),
):
    """URL 콘텐츠를 분석하여 블로그 글(마크다운) 생성"""
    api_key = body.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY 환경변수 또는 요청 body의 anthropic_api_key를 설정해 주세요.",
        )

    # URL 콘텐츠 가져오기 및 관련 검색
    try:
        url_content, related_search = search_related_to_url(
            body.url,
            max_results=5 if body.use_web_search else 0,
            max_news=5 if body.use_web_search else 0,
            region="kr-ko" if body.lang == "ko" else "wt-wt",
            timelimit="m",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning("search_related_to_url failed: %s", e)
        raise HTTPException(status_code=502, detail=f"URL 분석 중 오류가 발생했습니다: {e}")

    try:
        md = generate_article_from_url(
            url_content=url_content,
            api_key=api_key,
            lang=body.lang,
            style=body.style,
            use_emoji=body.use_emoji,
            related_search=related_search if body.use_web_search else None,
            length=body.length,
            guide=body.guide,
        )
        return {
            "markdown": md,
            "url": body.url,
            "analyzed_title": url_content.get("title", ""),
            "keywords": url_content.get("keywords", []),
        }
    except Exception as e:
        err_raw = getattr(e, "message", None) or getattr(e, "body", None) or str(e)
        msg = (err_raw if isinstance(err_raw, str) else str(err_raw)).lower()
        logger.exception("generate_article_from_url failed")

        if any(x in msg for x in ("credit", "billing", "purchase credits", "too low", "upgrade", "plans")) or ("balance" in msg and "low" in msg):
            detail = "Claude(Anthropic) API 크레딧이 부족합니다. https://console.anthropic.com/ → Plans & Billing 에서 크레딧을 충전해 주세요."
        elif "rate" in msg and "limit" in msg:
            detail = "Claude API 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
        elif "invalid" in msg and ("key" in msg or "api" in msg) or "authentication" in msg:
            detail = "Claude API 키가 올바르지 않습니다. 키를 확인해 주세요."
        else:
            detail = str(e)
        raise HTTPException(status_code=502, detail=detail)


@app.post("/api/generate-from-url/stream")
def api_generate_from_url_stream(
    request: Request,
    body: GenerateFromUrlRequest,
    _: None = Depends(rate_limit(generate_limiter)),
):
    """URL 콘텐츠를 분석하여 블로그 글(마크다운) 스트리밍 생성"""
    api_key = body.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY 환경변수 또는 요청 body의 anthropic_api_key를 설정해 주세요.",
        )

    # URL 콘텐츠 가져오기 및 관련 검색
    try:
        url_content, related_search = search_related_to_url(
            body.url,
            max_results=5 if body.use_web_search else 0,
            max_news=5 if body.use_web_search else 0,
            region="kr-ko" if body.lang == "ko" else "wt-wt",
            timelimit="m",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning("search_related_to_url failed: %s", e)
        raise HTTPException(status_code=502, detail=f"URL 분석 중 오류가 발생했습니다: {e}")

    def generate():
        try:
            for chunk in generate_article_from_url_stream(
                url_content=url_content,
                api_key=api_key,
                lang=body.lang,
                style=body.style,
                use_emoji=body.use_emoji,
                related_search=related_search if body.use_web_search else None,
                length=body.length,
                guide=body.guide,
            ):
                yield chunk
        except Exception as e:
            err_raw = getattr(e, "message", None) or getattr(e, "body", None) or str(e)
            msg = (err_raw if isinstance(err_raw, str) else str(err_raw)).lower()
            logger.exception("generate_article_from_url_stream failed")
            if any(x in msg for x in ("credit", "billing", "purchase credits", "too low", "upgrade", "plans")):
                yield f"\n\n[ERROR] Claude(Anthropic) API 크레딧이 부족합니다."
            elif "rate" in msg and "limit" in msg:
                yield f"\n\n[ERROR] Claude API 요청 한도를 초과했습니다."
            elif "invalid" in msg and ("key" in msg or "api" in msg):
                yield f"\n\n[ERROR] Claude API 키가 올바르지 않습니다."
            else:
                yield f"\n\n[ERROR] {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


class SaveMarkdownRequest(BaseModel):
    content: str
    filename: Optional[str] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("저장할 내용이 없습니다.")
        return v

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # 안전한 문자만 유지 (한글, 영문, 숫자, 하이픈, 언더스코어)
        safe_chars = []
        for c in v:
            if c.isalnum() or c in "-_" or ('\uac00' <= c <= '\ud7a3'):
                safe_chars.append(c)
        v = "".join(safe_chars).strip()
        if len(v) > 100:
            v = v[:100]
        return v if v else None


def _get_safe_filepath(downloads_dir: "Path", filename: str) -> "Path":
    """안전한 파일 경로 생성 (경로 탐색 공격 방지)"""
    from pathlib import Path

    # 파일명에서 경로 구분자 제거
    safe_filename = Path(filename).name

    # 추가 안전 검사: 숨김 파일 방지
    if safe_filename.startswith("."):
        safe_filename = safe_filename[1:] or "article"

    filepath = downloads_dir / safe_filename

    # 경로가 downloads 디렉토리 내부인지 확인 (심볼릭 링크 추적)
    try:
        resolved = filepath.resolve()
        downloads_resolved = downloads_dir.resolve()
        if not str(resolved).startswith(str(downloads_resolved)):
            raise ValueError("잘못된 파일 경로입니다.")
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"파일 경로가 유효하지 않습니다: {e}")

    return filepath


@app.post("/api/save-markdown")
def api_save_markdown(body: SaveMarkdownRequest):
    """마크다운 파일을 downloads 폴더에 저장"""
    from pathlib import Path

    downloads_dir = Path(__file__).parent.parent / "downloads"
    downloads_dir.mkdir(exist_ok=True)

    # 파일명 생성
    if body.filename:
        filename = body.filename
        if not filename.endswith(".md"):
            filename += ".md"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"article_{timestamp}.md"

    # 안전한 파일 경로 생성
    filepath = _get_safe_filepath(downloads_dir, filename)

    # 파일이 이미 존재하면 번호 추가
    base = filepath.stem
    ext = filepath.suffix
    counter = 1
    while filepath.exists():
        new_filename = f"{base}_{counter}{ext}"
        filepath = _get_safe_filepath(downloads_dir, new_filename)
        counter += 1

    try:
        filepath.write_text(body.content, encoding="utf-8")
        return {"success": True, "filename": filepath.name, "path": f"downloads/{filepath.name}"}
    except Exception as e:
        logger.exception("Failed to save markdown file")
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {e}")


# ---------- 정적 파일 (프론트) ----------

static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
