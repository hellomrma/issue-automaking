const EL = {
  fetchTrends: document.getElementById("fetchTrends"),
  multiPick: document.getElementById("multiPick"),
  trendsStatus: document.getElementById("trendsStatus"),
  trendsContainer: document.getElementById("trendsContainer"),
  trendNews: document.getElementById("trendNews"),
  batchBar: document.getElementById("batchBar"),
  batchCount: document.getElementById("batchCount"),
  batchStart: document.getElementById("batchStart"),
  batchStop: document.getElementById("batchStop"),
  batchList: document.getElementById("batchList"),
  keyword: document.getElementById("keyword"),
  dupNotice: document.getElementById("dupNotice"),
  sourceUrl: document.getElementById("sourceUrl"),
  referenceUrl: document.getElementById("referenceUrl"),
  guide: document.getElementById("guide"),
  modeKeyword: document.getElementById("modeKeyword"),
  modeUrl: document.getElementById("modeUrl"),
  keywordInputSection: document.getElementById("keywordInputSection"),
  urlInputSection: document.getElementById("urlInputSection"),
  styleRadios: document.querySelectorAll('input[name="style"]'),
  useWebSearch: document.getElementById("useWebSearch"),
  useClaudeSearch: document.getElementById("useClaudeSearch"),
  includeSources: document.getElementById("includeSources"),
  useEmoji: document.getElementById("useEmoji"),
  apiKey: document.getElementById("apiKey"),
  saveKey: document.getElementById("saveKey"),
  generate: document.getElementById("generate"),
  cancelGenerate: document.getElementById("cancelGenerate"),
  generateStatus: document.getElementById("generateStatus"),
  historySearch: document.getElementById("historySearch"),
  historyList: document.getElementById("historyList"),
  historyCount: document.getElementById("historyCount"),
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
  reviseBar: document.getElementById("reviseBar"),
  reviseTarget: document.getElementById("reviseTarget"),
  reviseInstruction: document.getElementById("reviseInstruction"),
  revise: document.getElementById("revise"),
  revisePresets: document.querySelectorAll("[data-revise-preset]"),
  reviseStatus: document.getElementById("reviseStatus"),
};

// 현재 입력 모드 (keyword 또는 url)
let currentInputMode = "keyword";

// 화면에 열린 글의 이력 id (다듬기 결과를 이력에 반영할 때 사용)
let currentHistoryId = null;

// 트렌드 키워드별 관련 뉴스 (서버 /api/trends 의 news)
let trendNews = {};

// 여러 개 고르기 모드와 선택된 키워드
let multiPickMode = false;
const pickedKeywords = new Set();
const MAX_BATCH = 10;

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

// 오류 응답 본문에서 사용자용 메시지 추출 (FastAPI 422는 detail이 배열)
function errorDetail(data, fallback) {
  const detail = Array.isArray(data?.detail) ? data.detail[0]?.msg : data?.detail;
  return detail || fallback;
}

function friendlyError(e) {
  return (e.message === "Failed to fetch" || e.message === "Load failed") ? API_OFF_MSG : (e.message || "오류가 났습니다.");
}

function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleDateString("ko-KR", { month: "long", day: "numeric" }) + " " +
    d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
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

function withApiKey(body) {
  const key = (EL.apiKey?.value || "").trim();
  if (key) body.anthropic_api_key = key;
  return body;
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

// 응답 스트림을 끝까지 읽으며 지금까지의 텍스트를 onText로 전달
async function readStream(res, onText) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let text = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    text += decoder.decode(value, { stream: true });
    onText(text);
  }
  return text;
}

// 스트림 결과 정리: 코드 블록 벗기기, [ERROR]/[WARN] 분리
function parseStreamResult(text) {
  const fenced = text.trim().match(/^```[^\n]*\n([\s\S]*?)\n```\s*$/);
  if (fenced) text = fenced[1];
  const errMatch = text.match(/\n*\[ERROR\]\s*(.+)\s*$/);
  if (errMatch) return { text: text.slice(0, errMatch.index), error: errMatch[1] };
  const warnMatch = text.match(/\n*\[WARN\]\s*(.+)\s*$/);
  if (warnMatch) return { text: text.slice(0, warnMatch.index), warning: warnMatch[1] };
  return { text };
}

// 원고 영역에 글을 표시하고 관련 상태를 맞춤
function showArticle(markdown, historyId = currentHistoryId) {
  EL.output.textContent = markdown;
  currentHistoryId = historyId;
  updateCharCount();
  if (!EL.preview.classList.contains("hidden")) updatePreview();
  refreshReviseTargets();
}

// ---------- 1. 트렌드 키워드 ----------
const TRENDS_LIMIT_KR = 50;

function selectKeyword(k, li) {
  EL.keyword.value = k;
  switchInputMode("keyword");
  EL.trendsContainer.querySelectorAll("li.selected").forEach((el) => el.classList.remove("selected"));
  li.classList.add("selected");
  renderTrendNews(k);
  checkDuplicate(k);
}

function togglePick(k, li) {
  if (pickedKeywords.has(k)) {
    pickedKeywords.delete(k);
    li.classList.remove("picked");
  } else {
    if (pickedKeywords.size >= MAX_BATCH) {
      setStatus(EL.trendsStatus, `한 번에 ${MAX_BATCH}개까지 고를 수 있습니다.`, "warning");
      return;
    }
    pickedKeywords.add(k);
    li.classList.add("picked");
  }
  updateBatchBar();
}

function createKeywordList(keywords) {
  const ul = document.createElement("ul");
  ul.className = "keywords";
  keywords.forEach((k) => {
    const li = document.createElement("li");

    const text = document.createElement("button");
    text.type = "button";
    text.className = "keyword-text";
    text.textContent = k;
    text.addEventListener("click", () => (multiPickMode ? togglePick(k, li) : selectKeyword(k, li)));

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

// 고른 키워드의 관련 뉴스 헤드라인
function renderTrendNews(k) {
  const news = trendNews[k] || [];
  EL.trendNews.innerHTML = "";
  EL.trendNews.classList.toggle("hidden", news.length === 0);
  if (!news.length) return;
  const h4 = document.createElement("h4");
  h4.textContent = `‘${k}’ 관련 뉴스`;
  const ul = document.createElement("ul");
  news.forEach((n) => {
    if (!/^https?:\/\//.test(n.url)) return;
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = n.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = n.headline;
    li.appendChild(a);
    if (n.source) {
      const src = document.createElement("span");
      src.className = "news-source";
      src.textContent = n.source;
      li.appendChild(src);
    }
    ul.appendChild(li);
  });
  EL.trendNews.appendChild(h4);
  EL.trendNews.appendChild(ul);
}

EL.fetchTrends?.addEventListener("click", async () => {
  EL.trendsContainer.innerHTML = "";
  EL.trendNews.classList.add("hidden");
  pickedKeywords.clear();
  updateBatchBar();
  setStatus(EL.trendsStatus, "인기 검색어 불러오는 중…", "loading");
  EL.fetchTrends.disabled = true;
  try {
    const regRes = await fetch("/api/regions");
    const regData = parseJsonOrFail(await regRes.text());
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
            return { ...r, google: d.google || [], recommend: d.recommend || [], news: d.news || {} };
          })
      )
    );

    let okCount = 0;
    let recommendOnly = false;
    trendNews = {};
    results.forEach((res) => {
      if (res.status !== "fulfilled") return;
      const { google, recommend, news } = res.value;
      Object.assign(trendNews, news);

      if (google.length) {
        okCount += 1;
        appendKeywordBlock("Google 실시간 검색어", google);
      } else if (recommend.length) {
        // 실시간 검색어를 못 받으면 추천 주제로 대신 채움
        okCount += 1;
        recommendOnly = true;
        appendKeywordBlock("추천 주제", recommend);
      }
    });

    if (okCount === 0) {
      setStatus(EL.trendsStatus, "검색어를 불러오지 못했습니다. 네트워크 연결과 서버 실행 상태를 확인해 주세요.", "error");
      return;
    }
    EL.multiPick.classList.remove("hidden");
    setStatus(
      EL.trendsStatus,
      recommendOnly
        ? "실시간 검색어를 받지 못해 추천 주제를 보여 드립니다. 누르면 키워드로 들어갑니다."
        : "누르면 키워드로 들어갑니다.",
      recommendOnly ? "warning" : ""
    );
  } catch (e) {
    setStatus(EL.trendsStatus, friendlyError(e), "error");
  } finally {
    EL.fetchTrends.disabled = false;
  }
});

// 여러 개 고르기 모드
EL.multiPick?.addEventListener("click", () => {
  multiPickMode = !multiPickMode;
  EL.multiPick.setAttribute("aria-pressed", String(multiPickMode));
  EL.multiPick.textContent = multiPickMode ? "하나씩 고르기" : "여러 개 고르기";
  EL.trendsContainer.classList.toggle("picking", multiPickMode);
  if (!multiPickMode) {
    pickedKeywords.clear();
    EL.trendsContainer.querySelectorAll("li.picked").forEach((el) => el.classList.remove("picked"));
  }
  setStatus(
    EL.trendsStatus,
    multiPickMode ? `연달아 쓸 키워드를 최대 ${MAX_BATCH}개까지 고르세요. 지금 설정한 스타일과 분량으로 씁니다.` : "누르면 키워드로 들어갑니다."
  );
  updateBatchBar();
});

function updateBatchBar() {
  EL.batchBar.classList.toggle("hidden", !multiPickMode);
  EL.batchCount.textContent = `${pickedKeywords.size}개 고름`;
  EL.batchStart.disabled = pickedKeywords.size === 0 || batchRunning;
}

// ---------- 2. 같은 키워드 중복 알림 ----------
let dupTimer = null;
let dupSeq = 0;

function checkDuplicate(keyword) {
  clearTimeout(dupTimer);
  const kw = (keyword || "").trim();
  if (kw.length < 2) {
    EL.dupNotice.classList.add("hidden");
    return;
  }
  const seq = ++dupSeq;
  dupTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/history/check?keyword=${encodeURIComponent(kw)}`);
      const data = parseJsonOrFail(await res.text());
      if (seq !== dupSeq) return; // 그 사이 키워드가 바뀜
      const items = data.items || [];
      EL.dupNotice.innerHTML = "";
      EL.dupNotice.classList.toggle("hidden", items.length === 0);
      if (!items.length) return;
      const text = document.createElement("span");
      text.textContent = `이 키워드로 쓴 글이 ${items.length}편 있습니다. 최근: ${formatDate(items[0].created_at)}`;
      const open = document.createElement("button");
      open.type = "button";
      open.className = "link-btn";
      open.textContent = "열어 보기";
      open.addEventListener("click", () => openHistory(items[0].id));
      EL.dupNotice.append(text, open);
    } catch (_) {
      EL.dupNotice.classList.add("hidden");
    }
  }, 350);
}

EL.keyword?.addEventListener("input", () => checkDuplicate(EL.keyword.value));

// Claude 웹 검색은 '최신 뉴스·검색 결과 반영'이 켜져 있을 때만 의미가 있음
function syncSearchOptions() {
  EL.useClaudeSearch.disabled = !EL.useWebSearch.checked;
}
EL.useWebSearch?.addEventListener("change", syncSearchOptions);

// ---------- 3. 글 생성 (스트리밍) ----------

function getSelectedStyle() {
  for (const radio of EL.styleRadios) {
    if (radio.checked) return radio.value;
  }
  return "정보성";
}

// 현재 설정으로 생성 요청 body 구성. 문제가 있으면 { error } 반환
function buildGenerateRequest(keywordOverride) {
  const common = {
    style: getSelectedStyle(),
    length: getRadioValue("length", "medium"),
    lang: "ko",
    use_emoji: !!EL.useEmoji?.checked,
    use_web_search: !!EL.useWebSearch?.checked,
    use_claude_search: !!EL.useClaudeSearch?.checked,
    include_sources: !!EL.includeSources?.checked,
  };
  const guide = (EL.guide?.value || "").trim();
  if (guide) common.guide = guide;

  if (currentInputMode === "url" && keywordOverride === undefined) {
    const url = (EL.sourceUrl?.value || "").trim();
    if (!url) return { error: "분석할 URL을 입력해 주세요." };
    if (!/^https?:\/\//.test(url)) return { error: "올바른 URL 형식이 아닙니다. (http:// 또는 https://로 시작해야 합니다)" };
    return { endpoint: "/api/generate-from-url", body: withApiKey({ ...common, url }) };
  }

  const kw = (keywordOverride ?? EL.keyword?.value ?? "").trim();
  if (!kw) return { error: "키워드를 입력하거나 트렌드에서 선택해 주세요." };
  const body = { ...common, keyword: kw };
  const referenceUrl = (EL.referenceUrl?.value || "").trim();
  if (referenceUrl && keywordOverride === undefined) body.reference_url = referenceUrl;
  return { endpoint: "/api/generate", body: withApiKey(body) };
}

async function generateArticle() {
  const req = buildGenerateRequest();
  if (req.error) {
    setStatus(EL.generateStatus, req.error, "error");
    return;
  }

  currentAbortController = new AbortController();
  const loadingMsg = currentInputMode === "url" ? "URL을 분석하고 글을 생성하고 있습니다…" : "글을 생성하고 있습니다…";
  setStatus(EL.generateStatus, loadingMsg, "loading");
  EL.generate.disabled = true;
  EL.cancelGenerate?.classList.remove("hidden");
  showArticle("", null);
  EL.output.classList.add("streaming");
  switchTab("source");
  clearMeta();
  saveApiKey();

  try {
    const res = await fetch(`${req.endpoint}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
      signal: currentAbortController.signal,
    });

    if (!res.ok) {
      let errData;
      try { errData = JSON.parse(await res.text()); } catch (_) {}
      throw new Error(errorDetail(errData, "생성에 실패했습니다."));
    }
    const historyId = Number(res.headers.get("X-History-Id")) || null;
    currentHistoryId = historyId;

    const fullText = await readStream(res, (text) => {
      EL.output.textContent = text;
      updateCharCount();
      EL.output.scrollTop = EL.output.scrollHeight;
    });

    const result = parseStreamResult(fullText);
    showArticle(result.text, historyId);
    if (result.error) {
      setStatus(EL.generateStatus, result.error, "error");
    } else if (result.warning) {
      setStatus(EL.generateStatus, result.warning, "warning");
    } else {
      setStatus(EL.generateStatus, "다 썼습니다. ‘티스토리용 복사’로 에디터에 바로 붙여넣을 수 있습니다.", "success");
    }
  } catch (e) {
    if (e.name === "AbortError") {
      setStatus(EL.generateStatus, "생성을 멈췄습니다. 지금까지 쓴 부분은 남아 있습니다.", "warning");
      refreshReviseTargets();
    } else {
      setStatus(EL.generateStatus, friendlyError(e), "error");
    }
  } finally {
    EL.generate.disabled = batchRunning;
    EL.cancelGenerate?.classList.add("hidden");
    currentAbortController = null;
    EL.output.classList.remove("streaming");
    refreshHistory();
  }
}

EL.generate?.addEventListener("click", generateArticle);

EL.cancelGenerate?.addEventListener("click", () => {
  if (currentAbortController) currentAbortController.abort();
});

// ---------- 4. 여러 키워드 연달아 생성 ----------
let batchRunning = false;
let batchAbort = null;

function setBatchRow(row, text, type = "") {
  const status = row.querySelector(".batch-state");
  status.textContent = text;
  status.className = "batch-state " + type;
}

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); reject(new DOMException("aborted", "AbortError")); }, { once: true });
  });
}

// 글 하나 생성. 요청 한도(429)에 걸리면 안내된 시간만큼 기다렸다 다시 시도
async function generateOne(keyword, row) {
  const req = buildGenerateRequest(keyword);
  if (req.error) throw new Error(req.error);
  for (let attempt = 0; attempt < 5; attempt++) {
    setBatchRow(row, "쓰는 중…", "loading");
    const res = await fetch(req.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
      signal: batchAbort.signal,
    });
    const data = parseJsonOrFail(await res.text());
    if (res.status === 429) {
      const seconds = Number(res.headers.get("Retry-After")) || 30;
      setBatchRow(row, `요청 한도 대기 ${seconds}초`, "warning");
      await wait((seconds + 1) * 1000, batchAbort.signal);
      continue;
    }
    if (!res.ok) throw new Error(errorDetail(data, "생성에 실패했습니다."));
    return data;
  }
  throw new Error("요청 한도 때문에 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.");
}

EL.batchStart?.addEventListener("click", async () => {
  const keywords = [...pickedKeywords];
  if (!keywords.length) return;
  batchRunning = true;
  batchAbort = new AbortController();
  EL.generate.disabled = true;
  EL.batchStop.classList.remove("hidden");
  updateBatchBar();
  saveApiKey();

  EL.batchList.innerHTML = "";
  EL.batchList.classList.remove("hidden");
  const rows = keywords.map((k) => {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "batch-keyword";
    name.textContent = k;
    const state = document.createElement("span");
    state.className = "batch-state";
    state.textContent = "기다리는 중";
    li.append(name, state);
    EL.batchList.appendChild(li);
    return li;
  });

  let done = 0;
  for (let i = 0; i < keywords.length; i++) {
    const row = rows[i];
    try {
      const data = await generateOne(keywords[i], row);
      done += 1;
      setBatchRow(row, "다 씀", "success");
      if (data.history_id) {
        const open = document.createElement("button");
        open.type = "button";
        open.className = "link-btn";
        open.textContent = "열기";
        open.addEventListener("click", () => openHistory(data.history_id));
        row.appendChild(open);
      }
      refreshHistory();
    } catch (e) {
      if (e.name === "AbortError") {
        rows.slice(i).forEach((r) => setBatchRow(r, "멈춤", "warning"));
        break;
      }
      setBatchRow(row, friendlyError(e), "error");
    }
  }

  setStatus(EL.trendsStatus, `${keywords.length}개 중 ${done}개를 썼습니다. ‘지난 글’에서 열어 볼 수 있습니다.`, done ? "success" : "error");
  batchRunning = false;
  batchAbort = null;
  EL.generate.disabled = false;
  EL.batchStop.classList.add("hidden");
  updateBatchBar();
});

EL.batchStop?.addEventListener("click", () => batchAbort?.abort());

// ---------- 5. 지난 글 (생성 이력) ----------
let historySearchTimer = null;

async function refreshHistory() {
  const q = (EL.historySearch?.value || "").trim();
  try {
    const res = await fetch(`/api/history?limit=30${q ? `&q=${encodeURIComponent(q)}` : ""}`);
    const data = parseJsonOrFail(await res.text());
    renderHistory(data.items || [], q);
  } catch (_) {
    // 이력은 부가 기능이라 실패해도 조용히 둠
  }
}

function renderHistory(items, query) {
  EL.historyCount.textContent = query ? `${items.length}건` : (items.length ? `${items.length}편` : "");
  EL.historyList.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "history-empty";
    empty.textContent = query ? "검색 결과가 없습니다." : "아직 쓴 글이 없습니다. 글을 생성하면 여기에 쌓입니다.";
    EL.historyList.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const li = document.createElement("li");
    if (item.id === currentHistoryId) li.classList.add("current");

    const open = document.createElement("button");
    open.type = "button";
    open.className = "history-open";
    const title = document.createElement("span");
    title.className = "history-title";
    title.textContent = item.title || item.keyword || item.source_url || "제목 없음";
    const meta = document.createElement("span");
    meta.className = "history-meta";
    meta.textContent = `${formatDate(item.created_at)}  ${item.mode === "url" ? "URL" : item.keyword || ""}`;
    open.append(title, meta);
    open.addEventListener("click", () => openHistory(item.id));

    const del = document.createElement("button");
    del.type = "button";
    del.className = "history-delete";
    del.title = "삭제";
    del.setAttribute("aria-label", `${title.textContent} 삭제`);
    del.textContent = "삭제";
    del.addEventListener("click", () => deleteHistory(item.id, title.textContent));

    li.append(open, del);
    EL.historyList.appendChild(li);
  });
}

async function openHistory(id) {
  try {
    const res = await fetch(`/api/history/${id}`);
    const data = parseJsonOrFail(await res.text());
    if (!res.ok) throw new Error(errorDetail(data, "글을 불러오지 못했습니다."));
    clearMeta();
    showArticle(data.markdown, data.id);
    if (data.mode === "keyword" && data.keyword) {
      switchInputMode("keyword");
      EL.keyword.value = data.keyword;
    }
    setStatus(EL.generateStatus, `${formatDate(data.created_at)}에 쓴 글을 열었습니다.`);
    refreshHistory();
    EL.output.scrollTop = 0;
  } catch (e) {
    notify(friendlyError(e), "error");
  }
}

async function deleteHistory(id, title) {
  if (!confirm(`‘${title}’ 글을 지난 글 목록에서 지울까요?`)) return;
  try {
    const res = await fetch(`/api/history/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(errorDetail(parseJsonOrFail(await res.text()), "지우지 못했습니다."));
    if (id === currentHistoryId) currentHistoryId = null;
    refreshHistory();
  } catch (e) {
    notify(friendlyError(e), "error");
  }
}

EL.historySearch?.addEventListener("input", () => {
  clearTimeout(historySearchTimer);
  historySearchTimer = setTimeout(refreshHistory, 300);
});

// ---------- 6. 글 다듬기 ----------

// ## 소제목 기준으로 섹션 위치 계산. 끝의 해시태그 줄은 섹션에 넣지 않음
function splitSections(md) {
  const lines = md.split("\n");
  let end = lines.length;
  while (end > 0 && !lines[end - 1].trim()) end--;
  if (end > 0 && /^(#[^\s#]+\s*)+$/.test(lines[end - 1].trim())) end--;

  const sections = [];
  for (let i = 0; i < end; i++) {
    if (/^##\s+/.test(lines[i])) {
      if (sections.length) sections[sections.length - 1].end = i;
      sections.push({ title: lines[i].replace(/^##\s+/, "").trim(), start: i, end });
    }
  }
  return { lines, sections };
}

function refreshReviseTargets() {
  const md = EL.output?.textContent || "";
  EL.reviseBar.classList.toggle("hidden", !md.trim());
  const prev = EL.reviseTarget.value;
  EL.reviseTarget.innerHTML = "";
  const whole = document.createElement("option");
  whole.value = "";
  whole.textContent = "글 전체";
  EL.reviseTarget.appendChild(whole);
  splitSections(md).sections.forEach((s, i) => {
    const opt = document.createElement("option");
    opt.value = String(i);
    opt.textContent = `섹션: ${s.title}`;
    EL.reviseTarget.appendChild(opt);
  });
  if ([...EL.reviseTarget.options].some((o) => o.value === prev)) EL.reviseTarget.value = prev;
}

EL.revisePresets.forEach((btn) => {
  btn.addEventListener("click", () => {
    EL.reviseInstruction.value = btn.dataset.revisePreset;
    EL.reviseInstruction.focus();
  });
});

async function reviseArticle() {
  const original = EL.output?.textContent || "";
  const instruction = (EL.reviseInstruction?.value || "").trim();
  if (!original.trim()) return;
  if (!instruction) {
    setStatus(EL.reviseStatus, "어떻게 고칠지 적어 주세요.", "error");
    EL.reviseInstruction.focus();
    return;
  }

  // 고칠 범위: 섹션이면 앞(before) + 새 섹션 + 뒤(after)로 이어 붙임
  const { lines, sections } = splitSections(original);
  const target = EL.reviseTarget.value === "" ? null : sections[Number(EL.reviseTarget.value)];
  let before = "", after = "", section = null;
  if (target) {
    before = lines.slice(0, target.start).join("\n");
    section = lines.slice(target.start, target.end).join("\n").trim();
    after = lines.slice(target.end).join("\n").replace(/^\n+/, "");
  }
  const compose = (text) => {
    if (!target) return text;
    return [before.replace(/\n+$/, ""), text.trim(), after].filter((s) => s !== "").join("\n\n");
  };

  currentAbortController = new AbortController();
  EL.revise.disabled = true;
  EL.generate.disabled = true;
  EL.cancelGenerate?.classList.remove("hidden");
  EL.output.classList.add("streaming");
  switchTab("source");
  clearMeta();
  setStatus(EL.reviseStatus, target ? `‘${target.title}’ 섹션을 고치는 중…` : "글 전체를 고치는 중…", "loading");

  try {
    const res = await fetch("/api/revise/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(withApiKey({ markdown: original, instruction, section })),
      signal: currentAbortController.signal,
    });
    if (!res.ok) {
      let errData;
      try { errData = JSON.parse(await res.text()); } catch (_) {}
      throw new Error(errorDetail(errData, "다듬지 못했습니다."));
    }

    const fullText = await readStream(res, (text) => {
      EL.output.textContent = compose(text);
      updateCharCount();
    });
    const result = parseStreamResult(fullText);
    if (result.error || !result.text.trim()) {
      showArticle(original);
      setStatus(EL.reviseStatus, result.error || "고친 내용이 비어 있어 원래 글을 유지했습니다.", "error");
      return;
    }

    const revised = compose(result.text);
    showArticle(revised);
    if (currentHistoryId) {
      await fetch(`/api/history/${currentHistoryId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown: revised }),
      }).catch(() => {});
      refreshHistory();
    }
    setStatus(EL.reviseStatus, result.warning || "고쳤습니다.", result.warning ? "warning" : "success");
  } catch (e) {
    showArticle(original);
    if (e.name === "AbortError") {
      setStatus(EL.reviseStatus, "다듬기를 멈추고 원래 글로 되돌렸습니다.", "warning");
    } else {
      setStatus(EL.reviseStatus, friendlyError(e), "error");
    }
  } finally {
    EL.revise.disabled = false;
    EL.generate.disabled = batchRunning;
    EL.cancelGenerate?.classList.add("hidden");
    EL.output.classList.remove("streaming");
    currentAbortController = null;
  }
}

EL.revise?.addEventListener("click", reviseArticle);
EL.reviseInstruction?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.isComposing) {
    e.preventDefault();
    reviseArticle();
  }
});

// ---------- 7. 복사 / 저장 / 제목 추천 ----------
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
  clearMeta();
  setStatus(EL.metaStatus, "제목 후보와 메타 설명을 만드는 중…", "loading");
  EL.genMeta.disabled = true;
  try {
    const res = await fetch("/api/meta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(withApiKey({ markdown: md })),
    });
    const data = parseJsonOrFail(await res.text());
    if (!res.ok) throw new Error(errorDetail(data, "생성에 실패했습니다."));
    EL.metaPanel.appendChild(createMetaList("제목 후보", data.titles || []));
    EL.metaPanel.appendChild(createMetaList("메타 설명", [data.meta_description || ""]));
    EL.metaPanel.classList.remove("hidden");
    setStatus(EL.metaStatus, "항목을 클릭하면 복사됩니다.", "success");
  } catch (e) {
    setStatus(EL.metaStatus, friendlyError(e), "error");
  } finally {
    EL.genMeta.disabled = false;
  }
});

EL.downloadMd?.addEventListener("click", async () => {
  const text = EL.output?.textContent || "";
  if (!text) return;
  // 파일명: 글 제목(첫 # 줄) → 키워드 모드면 키워드 → article
  const heading = text.match(/^#\s+(.+)$/m)?.[1] || "";
  const keyword = currentInputMode === "keyword" ? (EL.keyword?.value || "") : "";
  const base = (heading || keyword).replace(/[^\w가-힣\s-]/g, "").trim().slice(0, 40) || "article";
  const filename = `tistory_${base}_${Date.now().toString(36)}`;

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
      notify(`저장하지 못했습니다: ${errorDetail(data, "서버 응답을 확인해 주세요.")}`, "error");
    }
  } catch (e) {
    notify(`저장하지 못했습니다: ${e.message}`, "error");
  }
});

// ---------- 8. 탭 전환 (마크다운 / 미리보기) ----------
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

// ---------- 9. 키보드 단축키 ----------
document.addEventListener("keydown", (e) => {
  // Ctrl+Enter: 글 생성
  if (e.ctrlKey && e.key === "Enter") {
    e.preventDefault();
    if (!EL.generate?.disabled) generateArticle();
  }
  // Escape: 생성·다듬기 취소
  if (e.key === "Escape" && currentAbortController) {
    e.preventDefault();
    currentAbortController.abort();
  }
});

loadStoredApiKey();
syncSearchOptions();
refreshHistory();
// 좁은 화면에서는 원고가 아래로 밀리지 않게 지난 글을 접어 둠
if (window.matchMedia("(max-width: 900px)").matches) {
  document.querySelector(".history")?.removeAttribute("open");
}
