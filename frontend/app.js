const $ = (s) => document.querySelector(s);
let state = {};

const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const toast = (text) => {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2300);
};

const APP_BASE = "/stock50-7/";
const FRONTEND_VERSION = "20260925-7";
console.info("stock50 frontend v5 loaded");

async function api(path, opt = {}) {
  const cleanPath = String(path || "").replace(/^\/+/, "");
  const url = APP_BASE + cleanPath;

  const {
    timeoutMs = 12000,
    ...fetchOpt
  } = opt;

  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    timeoutMs
  );

  try {
    const response = await fetch(url, {
      cache: "no-store",
      ...fetchOpt,
      signal: controller.signal,
    });

    let data = {};

    try {
      data = await response.json();
    } catch (_) {}

    if (!response.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : `서버 응답 오류 HTTP ${response.status}`;

      throw Error(detail);
    }

    return data;

  } catch (error) {

    if (error?.name === "AbortError") {
      throw Error(
        `서버 응답시간 초과 (${Math.round(timeoutMs / 1000)}초)`
      );
    }

    throw error;

  } finally {
    clearTimeout(timer);
  }
}

function formatKoreanDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return esc(value);
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

function articleDetails(item, rows) {
  const map = new Map((rows || []).map((row) => [Number(row.article_id), row]));
  const linked = (item.article_ids || [])
    .map((id) => map.get(Number(id)))
    .filter(Boolean);

  if (!linked.length) {
    return `<span class="rank-count">기사 ${item.articles || 0}건</span>`;
  }

  return `
    <details class="rank-details">
      <summary>기사 ${linked.length}건</summary>
      <div class="rank-article-list">
        ${linked.map((article, index) => `
          <div class="rank-article-item">
            <div class="rank-article-title">
              <b>${index + 1}. ${esc(article.title)}</b>
              <span>${esc(article.confidence)} · 중요도 ${esc(article.importance)}</span>
            </div>
            <ul>
              ${(article.summary || []).map((line) => `<li>${esc(line)}</li>`).join("")}
            </ul>
            ${article.url ? `<a target="_blank" rel="noopener" href="${esc(article.url)}">한국경제 원문 ↗</a>` : ""}
          </div>
        `).join("")}
      </div>
    </details>`;
}

function renderTopCard(title, items, cls, rows) {
  return `
    <article class="top-card ${cls}">
      <h2>${title}</h2>
      ${items.length ? items.map((item, index) => `
        <div class="rank">
          <b>${index + 1}</b>
          <div class="rank-copy">
            <div class="rank-stock">
              <b>${esc(item.name)}</b>
              <small>${esc(item.code)}${item.market ? ` · ${esc(item.market)}` : ""}</small>
            </div>
            <div class="rank-meta">
              ${articleDetails(item, rows)}
              <span>· HIGH ${esc(item.high)} · ${esc(item.reason)}</span>
            </div>
          </div>
          <span class="score">${item.score > 0 ? "+" : ""}${esc(item.score)}</span>
        </div>
      `).join("") : '<p class="muted">저장된 분석 결과가 없습니다.</p>'}
    </article>`;
}

function renderAnalysis(data) {
  const rows = data?.articles || [];
  $("#analysisCount").textContent = rows.length;
  $("#top").innerHTML =
    renderTopCard("오늘의 종합 수혜주 TOP 10", data?.top10?.beneficiaries || [], "benefit", rows) +
    renderTopCard("오늘의 종합 피해주 TOP 10", data?.top10?.losers || [], "loss", rows);

  $("#analyses").innerHTML = rows.length
    ? rows.map((article, index) => `
      <article class="article">
        <span class="badge">${index + 1}. 분석완료 · ${esc(article.confidence)}</span>
        <h3>${esc(article.title)}</h3>
        <div class="article-date">${formatKoreanDate(article.published_at)}</div>
        <ul>${(article.summary || []).map((line) => `<li>${esc(line)}</li>`).join("")}</ul>
        ${(article.impacts || []).map((stock) => `
          <div class="impact">
            <b>${stock.side === "beneficiaries" ? "수혜" : "피해"}</b>
            ${esc(stock.name)} <small>${esc(stock.code)} · ${esc(stock.market)}</small>
            ${stock.side === "beneficiaries" ? "+" : "-"}${esc(stock.impact)}
            — ${esc(stock.reason)}
          </div>
        `).join("")}
        <a target="_blank" rel="noopener" href="${esc(article.url)}">한국경제 원문 ↗</a>
      </article>
    `).join("")
    : '<p class="muted">AI 분석 전에는 요약을 만들지 않습니다.</p>';
}

function render() {
  const candidates = state.candidates || [];
  const articleCount = Number.isFinite(Number(state.article_count))
    ? Number(state.article_count)
    : (state.articles || []).length;
  $("#status").textContent = `수집 ${articleCount}개 · AI 후보 ${candidates.length}개 · 분석기사 ${state.latest?.articles?.length || 0}개`;

  $("#candidates").innerHTML = candidates.map((article) => `
    <tr>
      <td><input class="pick" type="checkbox" value="${article.id}" checked></td>
      <td>${esc(article.importance_score)}</td>
      <td class="date-cell">${formatKoreanDate(article.published_at)}</td>
      <td>${esc(article.section || "-")}</td>
      <td>${esc(article.title)}</td>
      <td>${esc(article.snippet || "")}</td>
      <td><a target="_blank" rel="noopener" href="${esc(article.url)}">원문</a></td>
    </tr>
  `).join("");

  const snapshots = $("#snapshots");
  snapshots.innerHTML = '<option value="">현재 분석</option>' +
    (state.snapshots || []).map((x) => `
      <option value="${x.id}">${formatKoreanDate(x.analysis_time)}</option>
    `).join("");

  renderAnalysis(state.latest);
}

async function load() {
  const status = $("#status");
  try {
    const started = performance.now();
    state = await api("api/state");
    render();
    const elapsed = (performance.now() - started) / 1000;
    if (elapsed > 2.0) {
      console.info(`api/state loaded in ${elapsed.toFixed(2)}s`);
    }
  } catch (error) {
    status.textContent = `기사 데이터 로딩 실패: ${error.message}`;
    toast(`기사 데이터 로딩 실패: ${error.message}`);
    console.error(error);
  }
}

load();
resumeCollectionProgress();



// STOCK50_REAL_PROGRESS_FRONTEND

function ensureCollectProgress() {

  let box = $("#collectProgressBox");

  if (box) return box;

  box = document.createElement("div");
  box.id = "collectProgressBox";
  box.hidden = true;

  box.style.marginTop = "10px";
  box.style.padding = "11px 13px";
  box.style.background = "#fff";
  box.style.border = "1px solid #d9ddd5";
  box.style.borderRadius = "7px";
  box.style.maxWidth = "600px";

  box.innerHTML = `
    <div style="
      display:flex;
      justify-content:space-between;
      gap:16px;
      align-items:center;
      margin-bottom:7px;
      font-size:13px;
    ">
      <strong id="collectProgressTitle">
        기사 수집 준비 중…
      </strong>

      <span id="collectElapsed">
        0초
      </span>
    </div>

    <progress
      id="collectProgressBar"
      style="
        width:100%;
        height:13px;
      "
    ></progress>

    <div
      id="collectProgressText"
      style="
        margin-top:7px;
        color:#667174;
        font-size:12px;
      "
    ></div>
  `;

  $("#status").insertAdjacentElement(
    "afterend",
    box
  );

  return box;
}


function collectElapsedSeconds(progress) {

  if (!progress?.started_at)
    return 0;

  const started =
    new Date(progress.started_at);

  if (Number.isNaN(started.getTime()))
    return 0;

  return Math.max(
    0,
    Math.floor(
      (Date.now() - started.getTime())
      / 1000
    )
  );
}


function renderCollectProgress(progress) {

  const box =
    ensureCollectProgress();

  const title =
    $("#collectProgressTitle");

  const text =
    $("#collectProgressText");

  const elapsed =
    $("#collectElapsed");

  const bar =
    $("#collectProgressBar");

  box.hidden = false;

  elapsed.textContent =
    `${collectElapsedSeconds(progress)}초`;

  const current =
    Number(progress?.current || 0);

  const total =
    Number(progress?.total || 0);

  if (
    progress?.stage === "articles"
    &&
    total > 0
  ) {

    const percent =
      Math.round(
        current * 100 / total
      );

    bar.max = total;
    bar.value = current;

    title.textContent =
      `기사 처리 중… ${current}/${total} (${percent}%)`;

    text.textContent =
      progress.message
      || `${current}/${total} 기사 처리 중`;

    return;
  }


  if (
    progress?.stage === "saving"
  ) {

    if (total > 0) {
      bar.max = total;
      bar.value = total;
    }

    title.textContent =
      "수집 결과 저장 중…";

    text.textContent =
      progress.message
      || "기사 데이터를 저장하고 있습니다.";

    return;
  }


  if (
    progress?.stage === "done"
  ) {

    bar.max = 100;
    bar.value = 100;

    title.textContent =
      "기사 수집 완료";

    text.textContent =
      progress.message
      || "기사 수집이 완료되었습니다.";

    return;
  }


  if (
    progress?.stage === "error"
  ) {

    bar.removeAttribute("value");
    bar.removeAttribute("max");

    title.textContent =
      "기사 수집 실패";

    text.textContent =
      progress.error
      || progress.message
      || "수집 오류";

    return;
  }


  // 로그인/Universe/피드 단계는
  // 전체 작업량을 아직 알 수 없으므로
  // 가짜 퍼센트를 표시하지 않는다.
  bar.removeAttribute("value");
  bar.removeAttribute("max");

  const labels = {
    universe:
      "종목 데이터 확인 중…",
    login:
      "한국경제 로그인 확인 중…",
    feeds:
      "한국경제 뉴스 피드 확인 중…",
    idle:
      "기사 수집 준비 중…",
  };

  title.textContent =
    labels[progress?.stage]
    || "기사 수집 준비 중…";

  text.textContent =
    progress?.message || "";
}


async function getCollectProgress() {

  return await api(
    "api/collect/status"
  );
}


let collectProgressTimer = null;


function stopCollectProgressPolling() {

  if (collectProgressTimer) {
    clearInterval(
      collectProgressTimer
    );

    collectProgressTimer = null;
  }
}


function startCollectProgressPolling() {

  stopCollectProgressPolling();

  const poll = async () => {

    try {

      const progress =
        await getCollectProgress();

      renderCollectProgress(
        progress
      );

      if (!progress.running) {

        stopCollectProgressPolling();

        $("#collect").disabled =
          false;

        $("#collect").textContent =
          "새로 수집";
      }

    } catch (error) {

      console.error(
        "진행상태 조회 실패:",
        error
      );
    }
  };

  poll();

  collectProgressTimer =
    setInterval(
      poll,
      500
    );
}


async function startCollectionRequest() {

  const response = await fetch(
    APP_BASE + "api/collect",
    {
      method: "POST",
      cache: "no-store",
    }
  );

  let data = {};

  try {
    data = await response.json();
  } catch (_) {}

  if (!response.ok) {

    const detail =
      typeof data.detail === "string"
        ? data.detail
        : `서버 응답 오류 HTTP ${response.status}`;

    throw Error(detail);
  }

  return data;
}


async function resumeCollectionProgress() {

  try {

    const progress =
      await getCollectProgress();

    if (progress.running) {

      $("#collect").disabled =
        true;

      $("#collect").textContent =
        "수집 중…";

      renderCollectProgress(
        progress
      );

      startCollectProgressPolling();
    }

  } catch (_) {
  }
}


$("#collect").onclick = async () => {

  const button =
    $("#collect");

  if (button.disabled)
    return;

  button.disabled = true;
  button.textContent =
    "수집 중…";

  const box =
    ensureCollectProgress();

  box.hidden = false;

  renderCollectProgress({
    running: true,
    stage: "universe",
    current: 0,
    total: 0,
    message:
      "수집 작업을 시작하고 있습니다.",
  });

  startCollectProgressPolling();

  try {

    const data =
      await startCollectionRequest();

    const finalProgress =
      await getCollectProgress();

    renderCollectProgress(
      finalProgress
    );

    toast(
      `${data.fetched || 0}개 신규 기사 · `
      + `${data.processed || 0}개 처리 완료`
    );

    await load();

    setTimeout(
      () => {
        box.hidden = true;
      },
      3000
    );

  } catch (error) {

    let progress = null;

    try {
      progress =
        await getCollectProgress();
    } catch (_) {}

    if (
      progress
      &&
      progress.stage === "error"
    ) {

      renderCollectProgress(
        progress
      );

    } else {

      renderCollectProgress({
        running: false,
        stage: "error",
        error: error.message,
      });
    }

    toast(
      `수집 오류: ${error.message}`
    );

  } finally {

    stopCollectProgressPolling();

    button.disabled = false;
    button.textContent =
      "새로 수집";
  }
};


function choose(n) {
  document.querySelectorAll(".pick").forEach((x, i) => { x.checked = i < n; });
}

document.querySelectorAll("[data-count]").forEach((button) => {
  button.onclick = () => choose(Number(button.dataset.count));
});
$("#all").onclick = () => choose(9999);
$("#none").onclick = () => choose(0);

$("#copy").onclick = async () => {
  const ids = [...document.querySelectorAll(".pick:checked")].map((x) => Number(x.value));
  try {
    const data = await api("api/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    await navigator.clipboard.writeText(data.text);
    toast(`AI 분석용 자료 복사 완료 · ${data.analysis_request_id}`);
  } catch (error) {
    toast(error.message);
  }
};

$("#openModal").onclick = () => $("#modal").showModal();

async function submit(save) {
  const validation = $("#validation");
  validation.style.color = "";
  try {
    const data = await api(`api/analysis/${save ? "save" : "validate"}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw: $("#raw").value }),
    });
    validation.textContent = save
      ? "저장되었습니다."
      : `검증 완료: ${data.data.articles.length}개 기사`;
    if (save) {
      $("#modal").close();
      toast("분석 snapshot을 저장했습니다");
      await load();
    }
  } catch (error) {
    validation.textContent = error.message;
    validation.style.color = "#c33";
  }
}

$("#validate").onclick = () => submit(false);
$("#save").onclick = () => submit(true);

$("#snapshots").onchange = async (event) => {
  if (event.target.value) {
    renderAnalysis(await api(`api/snapshot/${event.target.value}`));
  } else {
    renderAnalysis(state.latest);
  }
};
