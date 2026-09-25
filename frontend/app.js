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

async function api(path, opt) {
  const response = await fetch(path, opt);
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "요청 오류";
    throw Error(detail);
  }
  return data;
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

function top(title, items, cls, rows) {
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
    top("오늘의 종합 수혜주 TOP 10", data?.top10?.beneficiaries || [], "benefit", rows) +
    top("오늘의 종합 피해주 TOP 10", data?.top10?.losers || [], "loss", rows);

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

$("#collect").onclick = async () => {
  try {
    const data = await api("api/collect", { method: "POST" });
    toast(`${data.fetched}개 신규 기사 · 한국 ${data.universe?.kospi + data.universe?.kosdaq || 0}종목 · 미국 ${data.universe?.us || 0}종목`);
    await load();
  } catch (error) {
    toast(error.message);
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
