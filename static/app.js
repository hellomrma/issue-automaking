const EL = {
  fetchTrends: document.getElementById("fetchTrends"),
  trendsStatus: document.getElementById("trendsStatus"),
  trendsContainer: document.getElementById("trendsContainer"),
  keyword: document.getElementById("keyword"),
  sourceUrl: document.getElementById("sourceUrl"),
  referenceUrl: document.getElementById("referenceUrl"),
  guide: document.getElementById("guide"),
  modeKeyword: document.getElementById("modeKeyword"),
  modeUrl: document.getElementById("modeUrl"),
  keywordInputSection: document.getElementById("keywordInputSection"),
  urlInputSection: document.getElementById("urlInputSection"),
  styleRadios: document.querySelectorAll('input[name="style"]'),
  useWebSearch: document.getElementById("useWebSearch"),
  useEmoji: document.getElementById("useEmoji"),
  apiKey: document.getElementById("apiKey"),
  saveKey: document.getElementById("saveKey"),
  generate: document.getElementById("generate"),
  cancelGenerate: document.getElementById("cancelGenerate"),
  generateStatus: document.getElementById("generateStatus"),
  output: document.getElementById("output"),
  preview: document.getElementById("preview"),
  tabSource: document.getElementById("tabSource"),
  tabPreview: document.getElementById("tabPreview"),
  charCount: document.getElementById("charCount"),
  copyMd: document.getElementById("copyMd"),
  copyHtml: document.getElementById("copyHtml"),
  genMeta: document.getElementById("genMeta"),
  metaStatus: document.getElementById("metaStatus"),
  metaPanel: document.getElementById("metaPanel"),
  downloadMd: document.getElementById("downloadMd"),
  actionStatus: document.getElementById("actionStatus"),
};

// 현재 입력 모드 (keyword 또는 url)
let currentInputMode = "keyword";

// 글자 수 업데이트 함수
function updateCharCount() {
  const text = EL.output?.textContent || "";
  const count = text.length;
  if (EL.charCount) {
    const sheets = Math.ceil(count / 200);
    EL.charCount.textContent = count
      ? `${count.toLocaleString()}자 (200자 원고지 ${sheets.toLocaleString()}매)`
      : "0자";
  }
}

// 결과 영역 아래 짧은 알림 (alert 대신)
let actionStatusTimer = null;
function notify(text, type = "success") {
  if (!EL.actionStatus) return;
  setStatus(EL.actionStatus, text, type + " inline");
  clearTimeout(actionStatusTimer);
  actionStatusTimer = setTimeout(() => setStatus(EL.actionStatus, "", "inline"), 4000);
}

function getRadioValue(name, fallback) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || fallback;
}

// 현재 진행 중인 요청을 취소하기 위한 AbortController
let currentAbortController = null;

const STORAGE_KEY = "tistory_writer_anthropic_key";

const API_OFF_MSG = "API 서버에 연결되지 않았습니다. run.bat을 실행한 뒤 주소창에 http://localhost:8000 으로 접속해 주세요.";

function setStatus(el, text, type = "") {
  el.textContent = text || "";
  el.className = "status " + (type || "");
}

function parseJsonOrFail(text, onHtml) {
  try {
    return JSON.parse(text);
  } catch (_) {
    if (typeof text === "string" && text.trimStart().startsWith("<")) {
      throw new Error(onHtml || API_OFF_MSG);
    }
    throw new Error("응답 형식 오류");
  }
}

function loadStoredApiKey() {
  try {
    // sessionStorage 사용 (브라우저 세션 종료 시 자동 삭제)
    const v = sessionStorage.getItem(STORAGE_KEY);
    if (v && EL.apiKey) EL.apiKey.value = v;
  } catch (_) {}
}

function saveApiKey() {
  if (!EL.saveKey?.checked) return;
  try {
    // sessionStorage 사용 (localStorage보다 안전)
    sessionStorage.setItem(STORAGE_KEY, EL.apiKey?.value || "");
  } catch (_) {}
}

function clearApiKey() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch (_) {}
}

// 입력 모드 전환 함수
function switchInputMode(mode) {
  currentInputMode = mode;
  if (mode === "keyword") {
    EL.modeKeyword?.classList.add("active");
    EL.modeUrl?.classList.remove("active");
    EL.keywordInputSection?.classList.remove("hidden");
    EL.urlInputSection?.classList.add("hidden");
  } else {
    EL.modeKeyword?.classList.remove("active");
    EL.modeUrl?.classList.add("active");
    EL.keywordInputSection?.classList.add("hidden");
    EL.urlInputSection?.classList.remove("hidden");
  }
}

EL.modeKeyword?.addEventListener("click", () => switchInputMode("keyword"));
EL.modeUrl?.addEventListener("click", () => switchInputMode("url"));

// 1. 트렌드 키워드 개수
const TRENDS_LIMIT_KR = 50;

EL.fetchTrends?.addEventListener("click", async () => {
  EL.trendsContainer.innerHTML = "";
  setStatus(EL.trendsStatus, "인기 검색어 불러오는 중…", "loading");
  EL.fetchTrends.disabled = true;
  try {
    const regRes = await fetch("/api/regions");
    const regText = await regRes.text();
    const regData = parseJsonOrFail(regText);
    const regions = regData.regions || [];
    if (regions.length === 0) {
      setStatus(EL.trendsStatus, "지역 목록을 가져올 수 없습니다.", "error");
      return;
    }

    const results = await Promise.allSettled(
      regions.map((r) =>
        fetch(`/api/trends?region=${encodeURIComponent(r.id)}&limit=${TRENDS_LIMIT_KR}`)
          .then((res) => res.text())
          .then((text) => {
            const d = parseJsonOrFail(text);
            return {
              ...r,
              keywords: d.keywords || [],
              google: d.google || [],
              recommend: d.recommend || [],
              source: d.source || "fallback"
            };
          })
      )
    );

    let okCount = 0;
    let totalKw = 0;

    // 키워드 목록 생성 헬퍼 함수
    function createKeywordList(keywords) {
      const ul = document.createElement("ul");
      ul.className = "keywords";
      keywords.forEach((k) => {
        const li = document.createElement("li");

        const text = document.createElement("button");
        text.type = "button";
        text.className = "keyword-text";
        text.textContent = k;
        text.addEventListener("click", () => {
          EL.keyword.value = k;
          switchInputMode("keyword");
          EL.trendsContainer.querySelectorAll("li.selected").forEach((el) => el.classList.remove("selected"));
          li.classList.add("selected");
        });

        const searchBtn = document.createElement("a");
        searchBtn.className = "keyword-search";
        searchBtn.href = `https://news.google.com/search?q=${encodeURIComponent(k)}&hl=ko&gl=KR`;
        searchBtn.target = "_blank";
        searchBtn.rel = "noopener noreferrer";
        searchBtn.title = "구글 뉴스에서 검색";
        searchBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;
        searchBtn.addEventListener("click", (e) => e.stopPropagation());

        li.appendChild(text);
        li.appendChild(searchBtn);
        ul.appendChild(li);
      });
      return ul;
    }

    function appendKeywordBlock(title, keywords) {
      const block = document.createElement("div");
      block.className = "region-trends";
      const h4 = document.createElement("h4");
      h4.textContent = `${title} ${keywords.length}개`;
      block.appendChild(h4);
      block.appendChild(createKeywordList(keywords));
      EL.trendsContainer.appendChild(block);
    }

    let recommendOnly = false;
    results.forEach((res) => {
      if (res.status !== "fulfilled") return;
      const { google, recommend } = res.value;

      if (google.length) {
        okCount += 1;
        totalKw += google.length;
        appendKeywordBlock("Google 실시간 검색어", google);
      } else if (recommend.length) {
        // 실시간 검색어를 못 받으면 추천 주제로 대신 채움
        okCount += 1;
        totalKw += recommend.length;
        recommendOnly = true;
        appendKeywordBlock("추천 주제", recommend);
      }
    });

    if (okCount === 0) {
      setStatus(EL.trendsStatus, "검색어를 불러오지 못했습니다. 네트워크 연결과 서버 실행 상태를 확인해 주세요.", "error");
      return;
    }
    setStatus(
      EL.trendsStatus,
      recommendOnly
        ? "실시간 검색어를 받지 못해 추천 주제를 보여 드립니다. 누르면 키워드로 들어갑니다."
        : "누르면 키워드로 들어갑니다.",
      recommendOnly ? "warning" : ""
    );
  } catch (e) {
    const msg = (e.message === "Failed to fetch" || e.message === "Load failed") ? API_OFF_MSG : (e.message || "오류가 났습니다.");
    setStatus(EL.trendsStatus, msg, "error");
  } finally {
    EL.fetchTrends.disabled = false;
  }
});

// 선택된 스타일 가져오기
function getSelectedStyle() {
  for (const radio of EL.styleRadios) {
    if (radio.checked) return radio.value;
  }
  return "정보성";
}

// 2. 글 생성 (스트리밍)
async function generateArticle() {
  let apiEndpoint, body;

  // 공통 옵션
  const guide = (EL.guide?.value || "").trim();
  const selectedStyle = getSelectedStyle();

  if (currentInputMode === "url") {
    // URL 기반 생성
    const url = (EL.sourceUrl?.value || "").trim();
    if (!url) {
      setStatus(EL.generateStatus, "분석할 URL을 입력해 주세요.", "error");
      return;
    }
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      setStatus(EL.generateStatus, "올바른 URL 형식이 아닙니다. (http:// 또는 https://로 시작해야 합니다)", "error");
      return;
    }
    apiEndpoint = "/api/generate-from-url/stream";
    body = {
      url: url,
      style: selectedStyle,
      length: getRadioValue("length", "medium"),
      lang: "ko",
      use_emoji: !!EL.useEmoji?.checked,
      use_web_search: !!EL.useWebSearch?.checked,
    };
    if (guide) body.guide = guide;
  } else {
    // 키워드 기반 생성
    const kw = (EL.keyword?.value || "").trim();
    if (!kw) {
      setStatus(EL.generateStatus, "키워드를 입력하거나 트렌드에서 선택해 주세요.", "error");
      return;
    }
    const referenceUrl = (EL.referenceUrl?.value || "").trim();
    apiEndpoint = "/api/generate/stream";
    body = {
      keyword: kw,
      style: selectedStyle,
      length: getRadioValue("length", "medium"),
      lang: "ko",
      use_emoji: !!EL.useEmoji?.checked,
      use_web_search: !!EL.useWebSearch?.checked,
    };
    if (guide) body.guide = guide;
    if (referenceUrl) body.reference_url = referenceUrl;
  }

  const key = (EL.apiKey?.value || "").trim();
  if (key) body.anthropic_api_key = key;

  // AbortController 생성
  currentAbortController = new AbortController();

  const loadingMsg = currentInputMode === "url" ? "URL을 분석하고 글을 생성하고 있습니다…" : "글을 생성하고 있습니다…";
  setStatus(EL.generateStatus, loadingMsg, "loading");
  EL.generate.disabled = true;
  EL.cancelGenerate?.classList.remove("hidden");
  EL.output.textContent = "";
  EL.output.classList.add("streaming");
  switchTab("source");
  updateCharCount();
  clearMeta();
  saveApiKey();

  try {
    const res = await fetch(apiEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: currentAbortController.signal,
    });

    if (!res.ok) {
      const errText = await res.text();
      let errData;
      try { errData = JSON.parse(errText); } catch (_) {}
      throw new Error(errData?.detail || "생성에 실패했습니다.");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let fullText = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      fullText += chunk;
      EL.output.textContent = fullText;
      updateCharCount();
      // 스크롤을 맨 아래로
      EL.output.scrollTop = EL.output.scrollHeight;
    }

    // 코드 블록(```)으로 감싸진 경우 벗겨내기
    const fenced = fullText.trim().match(/^```[^\n]*\n([\s\S]*?)\n```\s*$/);
    if (fenced) {
      fullText = fenced[1];
      EL.output.textContent = fullText;
      updateCharCount();
    }

    // 에러 / 잘림 경고 체크
    const warnMatch = fullText.match(/\n*\[WARN\]\s*(.+)\s*$/);
    if (fullText.includes("[ERROR]")) {
      const errMatch = fullText.match(/\[ERROR\]\s*(.+)/);
      setStatus(EL.generateStatus, errMatch ? errMatch[1] : "생성 중 오류가 발생했습니다.", "error");
    } else if (warnMatch) {
      EL.output.textContent = fullText.slice(0, warnMatch.index);
      updateCharCount();
      setStatus(EL.generateStatus, warnMatch[1], "warning");
    } else {
      setStatus(EL.generateStatus, "다 썼습니다. ‘티스토리용 복사’로 에디터에 바로 붙여넣을 수 있습니다.", "success");
    }
  } catch (e) {
    if (e.name === "AbortError") {
      setStatus(EL.generateStatus, "생성을 멈췄습니다. 지금까지 쓴 부분은 남아 있습니다.", "warning");
    } else {
      const msg = (e.message === "Failed to fetch" || e.message === "Load failed") ? API_OFF_MSG : (e.message || "오류가 났습니다.");
      setStatus(EL.generateStatus, msg, "error");
    }
  } finally {
    EL.generate.disabled = false;
    EL.cancelGenerate?.classList.add("hidden");
    currentAbortController = null;
    EL.output.classList.remove("streaming");
  }
}

EL.generate?.addEventListener("click", generateArticle);

// 취소 버튼
EL.cancelGenerate?.addEventListener("click", () => {
  if (currentAbortController) {
    currentAbortController.abort();
  }
});

// 3. 복사 / 다운로드
EL.copyMd?.addEventListener("click", () => {
  const text = EL.output?.textContent || "";
  if (!text) return;
  navigator.clipboard.writeText(text).then(
    () => notify("마크다운을 복사했습니다."),
    () => notify("복사하지 못했습니다. 브라우저의 클립보드 권한을 확인해 주세요.", "error")
  );
});

// 티스토리 에디터용 HTML 복사
// 기본 모드에는 서식째(text/html), HTML 모드에는 소스(text/plain)로 붙여넣어집니다.
EL.copyHtml?.addEventListener("click", async () => {
  const md = EL.output?.textContent || "";
  if (!md.trim()) return;
  const html = renderMarkdownHtml(md);
  if (html === null) {
    notify("변환 도구를 불러오지 못했습니다. 인터넷 연결을 확인하고 새로고침해 주세요.", "error");
    return;
  }
  try {
    if (typeof ClipboardItem !== "undefined") {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([html], { type: "text/plain" }),
        }),
      ]);
    } else {
      await navigator.clipboard.writeText(html);
    }
    notify("복사했습니다. 티스토리 에디터에 붙여넣으세요.");
  } catch (_) {
    notify("복사하지 못했습니다. 브라우저의 클립보드 권한을 확인해 주세요.", "error");
  }
});

// 제목 후보 · SEO 메타 설명 추천
function clearMeta() {
  if (EL.metaPanel) {
    EL.metaPanel.innerHTML = "";
    EL.metaPanel.classList.add("hidden");
  }
  if (EL.metaStatus) setStatus(EL.metaStatus, "");
}

function createMetaList(title, items) {
  const frag = document.createDocumentFragment();
  const h4 = document.createElement("h4");
  h4.textContent = title;
  const ul = document.createElement("ul");
  items.forEach((text) => {
    const li = document.createElement("li");
    li.className = "meta-item";
    li.textContent = text;
    li.title = "클릭하면 복사";
    li.addEventListener("click", () => {
      navigator.clipboard.writeText(text).then(
        () => setStatus(EL.metaStatus, "복사했습니다.", "success"),
        () => setStatus(EL.metaStatus, "복사에 실패했습니다.", "error")
      );
    });
    ul.appendChild(li);
  });
  frag.appendChild(h4);
  frag.appendChild(ul);
  return frag;
}

EL.genMeta?.addEventListener("click", async () => {
  const md = EL.output?.textContent || "";
  if (!md.trim()) {
    setStatus(EL.metaStatus, "먼저 글을 생성해 주세요.", "error");
    return;
  }
  const body = { markdown: md };
  const key = (EL.apiKey?.value || "").trim();
  if (key) body.anthropic_api_key = key;

  clearMeta();
  setStatus(EL.metaStatus, "제목 후보와 메타 설명을 만드는 중…", "loading");
  EL.genMeta.disabled = true;
  try {
    const res = await fetch("/api/meta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = parseJsonOrFail(await res.text());
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? data.detail[0]?.msg : data.detail;
      throw new Error(detail || "생성에 실패했습니다.");
    }
    EL.metaPanel.appendChild(createMetaList("제목 후보", data.titles || []));
    EL.metaPanel.appendChild(createMetaList("메타 설명", [data.meta_description || ""]));
    EL.metaPanel.classList.remove("hidden");
    setStatus(EL.metaStatus, "항목을 클릭하면 복사됩니다.", "success");
  } catch (e) {
    const msg = (e.message === "Failed to fetch" || e.message === "Load failed") ? API_OFF_MSG : (e.message || "오류가 났습니다.");
    setStatus(EL.metaStatus, msg, "error");
  } finally {
    EL.genMeta.disabled = false;
  }
});

EL.downloadMd?.addEventListener("click", async () => {
  const text = EL.output?.textContent || "";
  if (!text) return;
  const kw = (EL.keyword?.value || "article").replace(/[^\w\uac00-\ud7a3\s-]/g, "").trim() || "article";
  const filename = `tistory_${kw}_${Date.now().toString(36)}`;

  try {
    const res = await fetch("/api/save-markdown", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, filename }),
    });
    const data = await res.json();
    if (data.success) {
      notify(`${data.path}에 저장했습니다.`);
    } else {
      notify(`저장하지 못했습니다: ${data.detail || "서버 응답을 확인해 주세요."}`, "error");
    }
  } catch (e) {
    notify(`저장하지 못했습니다: ${e.message}`, "error");
  }
});

// 4. 탭 전환 (마크다운 / 미리보기)
function switchTab(tab) {
  if (tab === "source") {
    EL.tabSource?.classList.add("active");
    EL.tabPreview?.classList.remove("active");
    EL.output?.classList.remove("hidden");
    EL.preview?.classList.add("hidden");
  } else {
    EL.tabSource?.classList.remove("active");
    EL.tabPreview?.classList.add("active");
    EL.output?.classList.add("hidden");
    EL.preview?.classList.remove("hidden");
    // 미리보기 렌더링
    updatePreview();
  }
}

// 마크다운 → 안전한 HTML (LLM 출력에 섞인 스크립트 등 제거). 라이브러리가 없으면 null
function renderMarkdownHtml(md) {
  if (typeof marked === "undefined" || typeof DOMPurify === "undefined") return null;
  return DOMPurify.sanitize(marked.parse(md));
}

function updatePreview() {
  const md = EL.output?.textContent || "";
  if (!md.trim()) {
    EL.preview.innerHTML = "";
    return;
  }
  try {
    const html = renderMarkdownHtml(md);
    if (html !== null) {
      EL.preview.innerHTML = html;
    } else {
      EL.preview.textContent = "마크다운 렌더링 라이브러리를 불러오지 못했습니다.";
    }
  } catch (e) {
    EL.preview.textContent = `렌더링 오류: ${e.message}`;
  }
}

EL.tabSource?.addEventListener("click", () => switchTab("source"));
EL.tabPreview?.addEventListener("click", () => switchTab("preview"));

// 5. 키보드 단축키
document.addEventListener("keydown", (e) => {
  // Ctrl+Enter: 글 생성
  if (e.ctrlKey && e.key === "Enter") {
    e.preventDefault();
    if (!EL.generate?.disabled) {
      generateArticle();
    }
  }
  // Escape: 생성 취소
  if (e.key === "Escape" && currentAbortController) {
    e.preventDefault();
    currentAbortController.abort();
  }
});

// 저장된 API 키 불러오기
loadStoredApiKey();
