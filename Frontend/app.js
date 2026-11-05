/**
 * ================================================================================
 * [파일명] Frontend/app.js
 * [역할] 알약이가 (e-Drug Care) 클라이언트 사이드 비동기 API 컨트롤러 및 UI 상태 관리 모듈
 * ================================================================================
 *
 * [프론트엔드 ➔ 백엔드 아키텍처 호출 흐름 (출발지 ➔ 목적지)]
 * 1. 서버 상태 및 캐시 확인:
 *    - `checkBackendStatus()` ➔ `GET /api/status/`
 *    - 목적지: `Backend/drugs/urls.py` ➔ `Backend/drugs/views.py :: api_status()`
 * 2. 통합 스마트 검색 (검색어 + 다중 낱알 외형 조건):
 *    - `runUnifiedSearch()` ➔ `GET /api/unified-search/?q=...&shapes=...&colors=...`
 *    - 목적지: `Backend/drugs/views.py :: api_unified_search()` ➔ `Backend/drugs/services.py :: unified_drug_search()`
 * 3. 의약품 제품 허가·성분 전문 조회:
 *    - `runPermissionSearch()` ➔ `GET /api/permission-search/?q=...&spclty=...`
 *    - 목적지: `Backend/drugs/views.py :: api_permission_search()` ➔ `Backend/drugs/services.py :: fetch_prmsn_list()`
 * 4. 의약품 카드 클릭 시 3대 OpenAPI 상세 교차 조회:
 *    - `openDetailModal(item)` ➔ `GET /api/drug-detail/?itemSeq=...&itemName=...`
 *    - 목적지: `Backend/drugs/views.py :: api_drug_detail()` ➔ `Backend/drugs/services.py :: enrich_single_drug_detail()`
 * 5. 내 약통 (복약 수첩) 조회 / 추가 / 삭제 및 주성분 중복 점검:
 *    - `loadPillbox()` / `addToPillbox()` / `removeFromPillbox()` ➔ `GET | POST | DELETE /api/pillbox/`
 *    - 목적지: `Backend/drugs/views.py :: api_pillbox()` ➔ `Backend/drugs/models.py :: SavedDrug`
 *
 * [보안 및 모던 JS 적용 사항]
 * - `escapeHtml()`: 모든 동적 텍스트 바인딩 시 HTML 특수문자 이스케이프로 Reflected/Stored XSS 원천 차단
 * - `sanitizeHttpUrl()`: `<img src>` 바인딩 전 `http:` / `https:` 프로토콜만 허용하여 `javascript:` URI 공격 차단
 * - `AbortController`: 연속 검색 클릭 시 이전 진행 중인 네트워크 요청을 즉시 취소하여 레이스 컨디션 방지
 * ================================================================================
 */

const DIRECT_ENDPOINTS = {
    EASY: "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList",
    GRAIN: "https://apis.data.go.kr/1471000/MdcinGrnIdntfcInfoService03/getMdcinGrnIdntfcInfoList03",
    PRMSN_LIST: "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService08/getDrugPrdtPrmsnInq08",
    PRMSN_DTL: "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService08/getDrugPrdtPrmsnDtlInq08",
};

const DEFAULT_STATIC_ENCODED_KEY =
    "s%2FvWNiKH1YndVRu2mPOq7OXAIj%2Byk0M3JTgvN%2B8UVdSFPq8SBR7zuUdG3mxklTrj6WYIiUidSIUwgE8bz09fzQ%3D%3D";

// [수정 가이드] 한 페이지에 표시할 의약품 카드 개수를 12개에서 15개로 바꾸고 싶다면 아래 값을 15로 변경하세요.
const ITEMS_PER_PAGE = 12;

const STANDARD_SHAPES = new Set([
    "원형",
    "타원형",
    "장방형",
    "반원형",
    "삼각형",
    "사각형",
    "마름모형",
    "오각형",
    "육각형",
    "팔각형",
]);

const CHECKBOX_GROUP_IDS = [
    "formCheckGroup",
    "shapeCheckGroup",
    "lineFrontCheckGroup",
    "lineBackCheckGroup",
    "colorCheckGroup",
];

let useDjangoBackend = false;
let unifiedSearchState = { items: [], currentPage: 1 };
let prmsnSearchState = { items: [], currentPage: 1 };

let unifiedAbortController = null;
let prmsnAbortController = null;
let toastTimerId = null;

// DOM 참조 (Frontend/index.html 내 요소 ID와 1:1 매핑)
const brandLogo = document.getElementById("brandLogo");
const pillboxCountBadge = document.getElementById("pillboxCountBadge");
const mPillboxCount = document.getElementById("mPillboxCount");

const tabUnified = document.getElementById("tab-unified");
const searchInput = document.getElementById("searchInput");
const unifiedFieldSelect = document.getElementById("unifiedFieldSelect");
const searchBtn = document.getElementById("searchBtn");

const grainFilterBody = document.getElementById("grainFilterBody");
const activeFilterBadges = document.getElementById("activeFilterBadges");
const resetGrainFilterBtn = document.getElementById("resetGrainFilterBtn");
const toggleGrainFilterBtn = document.getElementById("toggleGrainFilterBtn");
const grainPrintInput = document.getElementById("grainPrintInput");
const grainPrintExact = document.getElementById("grainPrintExact");

const unifiedResultsSection = document.getElementById("unifiedResultsSection");
const unifiedStatsBar = document.getElementById("unifiedStatsBar");
const statusMessage = document.getElementById("statusMessage");
const resultList = document.getElementById("resultList");
const unifiedPagination = document.getElementById("unifiedPagination");

const prmsnSpcltySelect = document.getElementById("prmsnSpcltySelect");
const prmsnSearchInput = document.getElementById("prmsnSearchInput");
const prmsnSearchBtn = document.getElementById("prmsnSearchBtn");
const prmsnStatusMessage = document.getElementById("prmsnStatusMessage");
const prmsnResultList = document.getElementById("prmsnResultList");
const prmsnPagination = document.getElementById("prmsnPagination");

const safetyReportBox = document.getElementById("safetyReportBox");
const pillboxList = document.getElementById("pillboxList");

const detailModal = document.getElementById("detailModal");
const modalBody = document.getElementById("modalBody");
const closeModalBtn = document.getElementById("closeModalBtn");
const toastNotice = document.getElementById("toastNotice");

/**
 * [역할] XSS(교차 사이트 스크립팅) 방지를 위해 문자열 내 HTML 특수문자를 안전하게 이스케이프합니다.
 */
function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

/**
 * [역할] 이미지 URL 등에 `javascript:` 또는 `data:` 스킴이 주입되는 것을 차단하고
 * 오직 안전한 `http:` / `https:` URL만 반환합니다.
 */
function sanitizeHttpUrl(rawUrl) {
    if (!rawUrl) return "";
    const trimmed = String(rawUrl).trim();
    if (!trimmed) return "";
    try {
        const parsed = new URL(trimmed, window.location.origin);
        if (parsed.protocol === "http:" || parsed.protocol === "https:") {
            return parsed.href;
        }
    } catch {
        return "";
    }
    return "";
}

/**
 * [역할] OpenAPI 응답 내 `<![CDATA[...]]>`와 `<ARTICLE title="...">`를 보존하면서 HTML 태그를 제거합니다.
 */
function stripTags(text) {
    if (!text) return "";
    return String(text)
        .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
        .replace(/<(?:SECTION|ARTICLE)\b[^>]*?\btitle="([^"]+)"[^>]*?>/gi, "\n$1\n")
        .replace(/<[^>]*>?/gm, " ")
        .replace(/&nbsp;/g, " ")
        .replace(/[ \t]+/g, " ")
        .trim();
}

function cleanIngredientClient(rawIngr) {
    if (!rawIngr) return "";
    return String(rawIngr).replace(/\[[A-Za-z0-9_-]+\]/g, "").trim();
}

function updatePillboxCount(count) {
    if (pillboxCountBadge) pillboxCountBadge.textContent = String(count);
    if (mPillboxCount) mPillboxCount.textContent = String(count);
}

function showToast(msg) {
    if (!toastNotice) return;
    toastNotice.textContent = msg;
    toastNotice.classList.remove("hidden");
    if (toastTimerId) clearTimeout(toastTimerId);
    toastTimerId = setTimeout(() => {
        toastNotice.classList.add("hidden");
    }, 2600);
}

function showStatus(el, text, color = "#475569") {
    if (!el) return;
    el.textContent = text;
    el.style.color = color;
    el.classList.remove("hidden");
}

function hideStatus(el) {
    if (!el) return;
    el.textContent = "";
    el.classList.add("hidden");
}

// 초기화: 최초 접속 시 메인(홈) 화면 고정 및 백엔드 연동 상태 점검
document.addEventListener("DOMContentLoaded", async () => {
    initTabNavigation();
    initGrainCheckboxGroups();
    initEventListeners();
    resetToHome(false);
    await checkBackendStatus();
});

/**
 * [역할] Django 백엔드 서버 구동 여부를 확인하고 내 약통 개수 및 엔드포인트를 동기화합니다.
 * [연결 백엔드 목적지] GET /api/status/ ➔ Backend/drugs/urls.py ➔ Backend/drugs/views.py :: api_status()
 */
async function checkBackendStatus() {
    try {
        const resp = await fetch("/api/status/", { method: "GET" });
        if (resp.ok) {
            const data = await resp.json();
            useDjangoBackend = true;
            updatePillboxCount(data.pillboxCount ?? 0);

            if (data.endpoints) {
                if (data.endpoints.easy) DIRECT_ENDPOINTS.EASY = `${data.endpoints.easy}/getDrbEasyDrugList`;
                if (data.endpoints.grain) DIRECT_ENDPOINTS.GRAIN = `${data.endpoints.grain}/getMdcinGrnIdntfcInfoList03`;
                if (data.endpoints.permission) {
                    DIRECT_ENDPOINTS.PRMSN_LIST = `${data.endpoints.permission}/getDrugPrdtPrmsnInq08`;
                    DIRECT_ENDPOINTS.PRMSN_DTL = `${data.endpoints.permission}/getDrugPrdtPrmsnDtlInq08`;
                }
            }
            return;
        }
    } catch {
        // 정적 파일 단독 실행 환경 폴백
    }
    useDjangoBackend = false;
    updatePillboxCount(getLocalPillbox().length);
}

/* ==========================================================================
   메인(홈) 화면 복귀 & 탭 네비게이션
   ========================================================================== */
function setGrainFilterExpanded(expanded) {
    grainFilterBody.classList.toggle("collapsed", !expanded);
    toggleGrainFilterBtn.setAttribute("aria-expanded", String(expanded));
    toggleGrainFilterBtn.textContent = expanded ? "외형 조건 접기 ▲" : "외형 조건 펼치기 ▼";
}

function resetGrainFilters() {
    grainPrintInput.value = "";
    grainPrintExact.checked = false;

    CHECKBOX_GROUP_IDS.forEach((groupId) => {
        const groupEl = document.getElementById(groupId);
        if (!groupEl) return;
        groupEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
            cb.checked = cb.dataset.role === "all";
        });
    });

    updateActiveFilterBadges();
}

function resetToHome(scrollTop = true) {
    if (unifiedAbortController) {
        unifiedAbortController.abort();
        unifiedAbortController = null;
    }

    document.querySelectorAll(".nav-btn, .m-nav-btn").forEach((b) => {
        b.classList.toggle("active", b.dataset.tab === "tab-unified");
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === "tab-unified");
    });

    unifiedFieldSelect.value = "itemName";
    searchInput.value = "";
    resetGrainFilters();

    // 홈 모드: 검색창 + 모두 펼쳐진 낱알 식별기만 정중앙에 표시
    tabUnified.classList.add("is-home");
    setGrainFilterExpanded(true);
    toggleGrainFilterBtn.classList.add("hidden");

    unifiedSearchState = { items: [], currentPage: 1 };
    resultList.innerHTML = "";
    hideStatus(statusMessage);
    unifiedStatsBar.classList.add("hidden");
    unifiedPagination.classList.add("hidden");
    unifiedPagination.innerHTML = "";
    unifiedResultsSection.classList.add("hidden");

    if (scrollTop) {
        window.scrollTo({ top: 0, behavior: "smooth" });
    }
}

function initTabNavigation() {
    const allNavBtns = document.querySelectorAll(".nav-btn, .m-nav-btn");
    allNavBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            switchTab(btn.dataset.tab);
        });
    });

    brandLogo?.addEventListener("click", () => {
        resetToHome(true);
    });
    brandLogo?.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            resetToHome(true);
        }
    });
}

async function switchTab(targetId) {
    document.querySelectorAll(".nav-btn, .m-nav-btn").forEach((b) => {
        b.classList.toggle("active", b.dataset.tab === targetId);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === targetId);
    });

    if (targetId === "tab-pillbox") {
        await loadPillbox();
    }
}

/* ==========================================================================
   낱알 식별기 체크박스 다중 선택 & 활성 조건 요약 배지
   ========================================================================== */
function getCheckedValues(groupId) {
    const groupEl = document.getElementById(groupId);
    if (!groupEl) return [];
    return Array.from(
        groupEl.querySelectorAll('input[type="checkbox"]:not([data-role="all"]):checked')
    ).map((cb) => cb.value);
}

function getGrainFilterParams() {
    const forms = getCheckedValues("formCheckGroup");
    const shapes = getCheckedValues("shapeCheckGroup");
    const lineFront = getCheckedValues("lineFrontCheckGroup");
    const lineBack = getCheckedValues("lineBackCheckGroup");
    const colors = getCheckedValues("colorCheckGroup");
    const printText = grainPrintInput.value.trim();
    const printExact = grainPrintExact.checked;

    const hasAppearanceFilter = Boolean(
        forms.length ||
            shapes.length ||
            lineFront.length ||
            lineBack.length ||
            colors.length ||
            printText
    );

    return {
        forms,
        shapes,
        lineFront,
        lineBack,
        colors,
        printText,
        printExact,
        hasAppearanceFilter,
    };
}

function updateActiveFilterBadges() {
    const f = getGrainFilterParams();
    const badges = [];

    if (f.printText) {
        badges.push(`식별문자: ${f.printText}${f.printExact ? "(일치)" : ""}`);
    }
    if (f.forms.length) badges.push(`제형: ${f.forms.join(", ")}`);
    if (f.shapes.length) badges.push(`모양: ${f.shapes.join(", ")}`);
    if (f.colors.length) badges.push(`색상: ${f.colors.join(", ")}`);
    if (f.lineFront.length) badges.push(`분할선[앞]: ${f.lineFront.join(", ")}`);
    if (f.lineBack.length) badges.push(`분할선[뒤]: ${f.lineBack.join(", ")}`);

    activeFilterBadges.innerHTML = badges
        .map((txt) => `<span class="active-filter-tag">${escapeHtml(txt)}</span>`)
        .join("");
}

function initGrainCheckboxGroups() {
    CHECKBOX_GROUP_IDS.forEach((groupId) => {
        const groupEl = document.getElementById(groupId);
        if (!groupEl) return;

        const allBox = groupEl.querySelector('input[data-role="all"]');
        const optionBoxes = Array.from(
            groupEl.querySelectorAll('input[type="checkbox"]:not([data-role="all"])')
        );

        allBox?.addEventListener("change", () => {
            allBox.checked = true;
            optionBoxes.forEach((cb) => {
                cb.checked = false;
            });
            updateActiveFilterBadges();
        });

        optionBoxes.forEach((cb) => {
            cb.addEventListener("change", () => {
                const anyChecked = optionBoxes.some((opt) => opt.checked);
                if (allBox) {
                    allBox.checked = !anyChecked;
                }
                updateActiveFilterBadges();
            });
        });
    });

    grainPrintInput.addEventListener("input", updateActiveFilterBadges);
    grainPrintExact.addEventListener("change", updateActiveFilterBadges);

    resetGrainFilterBtn.addEventListener("click", () => {
        resetGrainFilters();
    });

    toggleGrainFilterBtn.addEventListener("click", () => {
        const isCollapsed = grainFilterBody.classList.contains("collapsed");
        setGrainFilterExpanded(isCollapsed);
    });
}

function bindEnterKey(inputEl, handler) {
    inputEl?.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.isComposing) {
            e.preventDefault();
            handler();
        }
    });
}

function initEventListeners() {
    searchBtn.addEventListener("click", runUnifiedSearch);
    bindEnterKey(searchInput, runUnifiedSearch);
    bindEnterKey(grainPrintInput, runUnifiedSearch);

    prmsnSearchBtn.addEventListener("click", runPermissionSearch);
    bindEnterKey(prmsnSearchInput, runPermissionSearch);

    closeModalBtn.addEventListener("click", () => detailModal.classList.add("hidden"));
    detailModal.addEventListener("click", (e) => {
        if (e.target === detailModal) detailModal.classList.add("hidden");
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !detailModal.classList.contains("hidden")) {
            detailModal.classList.add("hidden");
        }
    });
}

/* ==========================================================================
   공통 페이지네이션 (페이지당 12개, 화살표 + 숫자 네모칸 모두 지원)
   ========================================================================== */
function buildPageItems(totalPages, current) {
    if (totalPages <= 9) {
        return Array.from({ length: totalPages }, (_, i) => i + 1);
    }

    const pages = new Set([1, totalPages]);
    let start = Math.max(2, current - 2);
    let end = Math.min(totalPages - 1, current + 2);

    if (current <= 4) {
        start = 2;
        end = 6;
    } else if (current >= totalPages - 3) {
        start = totalPages - 5;
        end = totalPages - 1;
    }

    for (let p = start; p <= end; p++) {
        pages.add(p);
    }

    const sorted = Array.from(pages).sort((a, b) => a - b);
    const result = [];
    for (let i = 0; i < sorted.length; i++) {
        if (i > 0 && sorted[i] - sorted[i - 1] > 1) {
            result.push("...");
        }
        result.push(sorted[i]);
    }
    return result;
}

function renderPagination(navEl, totalItems, currentPage, onPageSelect) {
    if (!navEl) return;
    if (totalItems <= 0) {
        navEl.innerHTML = "";
        navEl.classList.add("hidden");
        return;
    }

    const totalPages = Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE));
    navEl.innerHTML = "";
    navEl.classList.remove("hidden");

    const fragment = document.createDocumentFragment();

    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "page-btn arrow";
    prevBtn.setAttribute("aria-label", "이전 페이지");
    prevBtn.disabled = currentPage <= 1;
    prevBtn.innerHTML = "&#8249;";
    prevBtn.addEventListener("click", () => {
        if (currentPage > 1) onPageSelect(currentPage - 1);
    });
    fragment.appendChild(prevBtn);

    const pageItems = buildPageItems(totalPages, currentPage);
    pageItems.forEach((entry) => {
        if (entry === "...") {
            const dots = document.createElement("span");
            dots.className = "page-ellipsis";
            dots.textContent = "···";
            fragment.appendChild(dots);
            return;
        }
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `page-btn${entry === currentPage ? " active" : ""}`;
        btn.textContent = String(entry);
        if (entry === currentPage) {
            btn.setAttribute("aria-current", "page");
        }
        btn.addEventListener("click", () => {
            if (entry !== currentPage) onPageSelect(entry);
        });
        fragment.appendChild(btn);
    });

    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "page-btn arrow";
    nextBtn.setAttribute("aria-label", "다음 페이지");
    nextBtn.disabled = currentPage >= totalPages;
    nextBtn.innerHTML = "&#8250;";
    nextBtn.addEventListener("click", () => {
        if (currentPage < totalPages) onPageSelect(currentPage + 1);
    });
    fragment.appendChild(nextBtn);

    navEl.appendChild(fragment);
}

function renderUnifiedPage(page, smoothScroll = true) {
    const total = unifiedSearchState.items.length;
    const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));
    const safePage = Math.max(1, Math.min(page, totalPages));
    unifiedSearchState.currentPage = safePage;

    const startIdx = (safePage - 1) * ITEMS_PER_PAGE;
    const slice = unifiedSearchState.items.slice(startIdx, startIdx + ITEMS_PER_PAGE);

    renderDrugCards(slice, resultList);
    renderPagination(unifiedPagination, total, safePage, (nextPage) => {
        renderUnifiedPage(nextPage, true);
    });

    if (smoothScroll) {
        unifiedResultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

function renderPrmsnPage(page, smoothScroll = true) {
    const total = prmsnSearchState.items.length;
    const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));
    const safePage = Math.max(1, Math.min(page, totalPages));
    prmsnSearchState.currentPage = safePage;

    const startIdx = (safePage - 1) * ITEMS_PER_PAGE;
    const slice = prmsnSearchState.items.slice(startIdx, startIdx + ITEMS_PER_PAGE);

    renderDrugCards(slice, prmsnResultList);
    renderPagination(prmsnPagination, total, safePage, (nextPage) => {
        renderPrmsnPage(nextPage, true);
    });

    if (smoothScroll) {
        prmsnResultList.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

/* ==========================================================================
   [탭 1] 통합 스마트 검색 (검색어 + 낱알 외형 조건 통합)
   - 연결 백엔드 목적지: GET /api/unified-search/ ➔ Backend/drugs/views.py :: api_unified_search()
   ========================================================================== */
async function runUnifiedSearch() {
    const keyword = searchInput.value.trim();
    const field = unifiedFieldSelect.value;
    const filters = getGrainFilterParams();

    if (!keyword && !filters.hasAppearanceFilter) {
        showToast("검색어를 입력하거나 알약 외형 조건을 하나 이상 선택해 주세요.");
        return;
    }

    if (unifiedAbortController) unifiedAbortController.abort();
    unifiedAbortController = new AbortController();
    const { signal } = unifiedAbortController;

    tabUnified.classList.remove("is-home");
    toggleGrainFilterBtn.classList.remove("hidden");
    setGrainFilterExpanded(false);
    unifiedResultsSection.classList.remove("hidden");

    resultList.innerHTML = "";
    unifiedPagination.innerHTML = "";
    unifiedPagination.classList.add("hidden");
    unifiedStatsBar.classList.add("hidden");
    showStatus(statusMessage, "의약품 정보를 검색하고 있습니다...", "#2563eb");

    try {
        let items = [];
        let counts = { mergedCount: 0, easyTotal: 0, grainTotal: 0, prmsnTotal: 0 };

        if (useDjangoBackend) {
            const params = new URLSearchParams({
                q: keyword,
                field,
                rows: "60",
            });
            if (filters.shapes.length) params.set("shapes", filters.shapes.join(","));
            if (filters.colors.length) params.set("colors", filters.colors.join(","));
            if (filters.forms.length) params.set("forms", filters.forms.join(","));
            if (filters.lineFront.length) params.set("lineFront", filters.lineFront.join(","));
            if (filters.lineBack.length) params.set("lineBack", filters.lineBack.join(","));
            if (filters.printText) params.set("print", filters.printText);
            if (filters.printExact) params.set("printExact", "1");

            const resp = await fetch(`/api/unified-search/?${params.toString()}`, { signal });
            if (!resp.ok) throw new Error(`서버 응답 오류 (${resp.status})`);
            const data = await resp.json();
            items = data.items || [];
            counts = data.counts || counts;
        } else {
            const res = await directUnifiedSearch(keyword, field, filters, signal);
            items = res.items;
            counts = res.counts;
        }

        document.getElementById("statMergedCount").textContent = `${counts.mergedCount}건`;
        document.getElementById("statEasyCount").textContent = `${counts.easyTotal}건`;
        document.getElementById("statGrainCount").textContent = `${counts.grainTotal}건`;
        document.getElementById("statPrmsnCount").textContent = `${counts.prmsnTotal}건`;
        unifiedStatsBar.classList.remove("hidden");

        unifiedSearchState = { items, currentPage: 1 };

        if (items.length === 0) {
            showStatus(
                statusMessage,
                "선택하신 조건과 일치하는 의약품이 없습니다. 검색어 또는 외형 조건을 변경해 보세요.",
                "#64748b"
            );
            return;
        }

        hideStatus(statusMessage);
        renderUnifiedPage(1, false);
    } catch (err) {
        if (err.name === "AbortError") return;
        console.error(err);
        showStatus(statusMessage, `조회 중 오류가 발생했습니다: ${err.message}`, "#dc2626");
    }
}

/* ==========================================================================
   [탭 2] 의약품 제품 허가·주성분 전문 조회
   - 연결 백엔드 목적지: GET /api/permission-search/ ➔ Backend/drugs/views.py :: api_permission_search()
   ========================================================================== */
async function runPermissionSearch() {
    const keyword = prmsnSearchInput.value.trim();
    const spclty = prmsnSpcltySelect.value;

    if (!keyword && spclty === "전체") {
        showToast("조회할 품목명을 입력하거나 전문·일반 구분을 선택해 주세요.");
        return;
    }

    if (prmsnAbortController) prmsnAbortController.abort();
    prmsnAbortController = new AbortController();
    const { signal } = prmsnAbortController;

    prmsnResultList.innerHTML = "";
    prmsnPagination.innerHTML = "";
    prmsnPagination.classList.add("hidden");
    showStatus(prmsnStatusMessage, "의약품 허가 정보를 조회하고 있습니다...", "#2563eb");

    try {
        let items = [];

        if (useDjangoBackend) {
            const params = new URLSearchParams({ q: keyword, spclty });
            const resp = await fetch(`/api/permission-search/?${params.toString()}`, { signal });
            if (!resp.ok) throw new Error(`서버 오류 (${resp.status})`);
            const data = await resp.json();
            items = data.items || [];
        } else {
            const extra = { item_name: keyword, numOfRows: 60, pageNo: 1 };
            if (spclty !== "전체") extra.spclty_pblc = spclty;
            const raw = await fetchDirectApi(DIRECT_ENDPOINTS.PRMSN_LIST, extra, signal);
            items = raw.items.map((r) => ({
                itemSeq: r.ITEM_SEQ || "",
                itemName: r.ITEM_NAME || "",
                itemEngName: r.ITEM_ENG_NAME || "",
                entpName: r.ENTP_NAME || "",
                itemPermitDate: r.ITEM_PERMIT_DATE || "",
                etcOtcName: r.SPCLTY_PBLC || "",
                className: r.PRDUCT_TYPE || "",
                itemIngrName: cleanIngredientClient(r.ITEM_INGR_NAME || ""),
                itemImage: r.BIG_PRDT_IMG_URL || "",
                ediCode: r.EDI_CODE || "",
            }));
        }

        prmsnSearchState = { items, currentPage: 1 };

        if (items.length === 0) {
            showStatus(
                prmsnStatusMessage,
                "조건에 해당하는 의약품 허가 정보가 없습니다.",
                "#64748b"
            );
            return;
        }

        hideStatus(prmsnStatusMessage);
        renderPrmsnPage(1, false);
    } catch (err) {
        if (err.name === "AbortError") return;
        console.error(err);
        showStatus(prmsnStatusMessage, `허가 정보 조회 실패: ${err.message}`, "#dc2626");
    }
}

/* ==========================================================================
   공통 의약품 카드 렌더링
   ========================================================================== */
function buildFallbackGraphicHtml(imprintLabel, subLabel) {
    return `
        <div class="pill-graphic-fallback">
            <div class="pill-shape-badge">${escapeHtml(imprintLabel)}</div>
            <span>${escapeHtml(subLabel)}</span>
        </div>
    `;
}

function renderDrugCards(items, container, isPillbox = false) {
    container.innerHTML = "";
    const fragment = document.createDocumentFragment();

    items.forEach((item) => {
        const card = document.createElement("div");
        card.className = "card";

        const safeImageUrl = sanitizeHttpUrl(item.itemImage);
        const imprintFront = item.printFront || "";
        const imprintBack = item.printBack || "";
        const imprintLabel = [imprintFront, imprintBack].filter(Boolean).join(" / ") || "각인 없음";
        const fallbackSubLabel = `${item.drugShape || "의약품"} · ${item.colorClass1 || "표준제형"}`;

        const imageMarkup = safeImageUrl
            ? `<img src="${escapeHtml(safeImageUrl)}" alt="${escapeHtml(item.itemName)}" class="card-img" loading="lazy">`
            : buildFallbackGraphicHtml(imprintLabel, fallbackSubLabel);

        const otcClass = (item.etcOtcName || "").includes("전문") ? "special" : "general";
        const otcText = item.etcOtcName || "의약품";

        const metaChips = [];
        if (item.drugShape) {
            metaChips.push(`<span class="meta-chip">${escapeHtml(item.drugShape)}</span>`);
        }
        if (item.colorClass1) {
            metaChips.push(`<span class="meta-chip">${escapeHtml(item.colorClass1)}</span>`);
        }
        if (imprintFront || imprintBack) {
            metaChips.push(`<span class="meta-chip imprint">각인: ${escapeHtml(imprintLabel)}</span>`);
        }
        if (item.className) {
            metaChips.push(`<span class="meta-chip">${escapeHtml(item.className)}</span>`);
        }

        const summaryText =
            stripTags(item.efcyQesitm) ||
            (item.itemIngrName ? `주성분: ${cleanIngredientClient(item.itemIngrName)}` : "") ||
            item.chart ||
            "상세 카드를 클릭하여 효능·복용법·성분·외형 정보를 확인하세요.";

        card.innerHTML = `
            <div class="card-img-wrap">
                <div class="card-badges-top">
                    <span class="otc-badge ${otcClass}">${escapeHtml(otcText)}</span>
                </div>
                ${imageMarkup}
            </div>
            <div class="card-body">
                <span class="card-corp">${escapeHtml(item.entpName || "제조사 미표기")} ${
                    item.itemSeq ? `· #${escapeHtml(item.itemSeq)}` : ""
                }</span>
                <h3 class="card-title">${escapeHtml(item.itemName)}</h3>
                ${metaChips.length ? `<div class="grain-meta-chips">${metaChips.slice(0, 4).join("")}</div>` : ""}
                <p class="card-efcy">${escapeHtml(summaryText)}</p>
                <div class="card-footer-actions">
                    <span style="font-size:0.76rem; color:#64748b; font-weight:600;">
                        ${isPillbox ? `${escapeHtml(item.dosageTime || "복용중")}` : "상세보기 →"}
                    </span>
                    ${
                        isPillbox
                            ? `<button type="button" class="btn-pillbox-del" data-del="1">약통에서 삭제</button>`
                            : `<button type="button" class="btn-pillbox-add" data-add="1">+ 내 약통 담기</button>`
                    }
                </div>
            </div>
        `;

        const imgEl = card.querySelector(".card-img");
        if (imgEl) {
            imgEl.addEventListener("error", () => {
                const wrap = card.querySelector(".card-img-wrap");
                imgEl.remove();
                wrap?.insertAdjacentHTML(
                    "beforeend",
                    buildFallbackGraphicHtml(imprintLabel, "실물 이미지 준비중")
                );
            });
        }

        card.addEventListener("click", (e) => {
            if (e.target.closest("[data-add]")) {
                e.stopPropagation();
                addToPillbox(item);
                return;
            }
            if (e.target.closest("[data-del]")) {
                e.stopPropagation();
                removeFromPillbox(item);
                return;
            }
            openDetailModal(item);
        });

        fragment.appendChild(card);
    });

    container.appendChild(fragment);
}

/* ==========================================================================
   의약품 상세 정보 모달
   - 연결 백엔드 목적지: GET /api/drug-detail/ ➔ Backend/drugs/views.py :: api_drug_detail()
     ➔ Backend/drugs/services.py :: enrich_single_drug_detail()
   ========================================================================== */
async function openDetailModal(initialItem) {
    detailModal.classList.remove("hidden");
    modalBody.innerHTML = `
        <div class="modal-loading">
            <p>상세 정보를 불러오는 중입니다...</p>
        </div>
    `;

    let item = { ...initialItem };
    try {
        if (useDjangoBackend) {
            const params = new URLSearchParams({
                itemSeq: initialItem.itemSeq || "",
                itemName: initialItem.itemName || "",
            });
            const resp = await fetch(`/api/drug-detail/?${params.toString()}`);
            if (resp.ok) {
                const enriched = await resp.json();
                for (const [k, v] of Object.entries(enriched)) {
                    if (
                        v !== "" &&
                        v !== null &&
                        v !== undefined &&
                        !(Array.isArray(v) && v.length === 0)
                    ) {
                        item[k] = v;
                    }
                }
            }
        } else {
            const enriched = await directEnrichDrugDetail(initialItem);
            for (const [k, v] of Object.entries(enriched)) {
                if (v) item[k] = v;
            }
        }
    } catch (e) {
        console.warn("상세 보강 조회 실패, 기본 데이터 표시:", e);
    }

    const safeImageUrl = sanitizeHttpUrl(item.itemImage);
    const imprintFront = item.printFront || "-";
    const imprintBack = item.printBack || "-";

    modalBody.innerHTML = `
        <div class="modal-header-top">
            <div class="modal-img-box">
                ${
                    safeImageUrl
                        ? `<img src="${escapeHtml(safeImageUrl)}" alt="${escapeHtml(item.itemName)}" class="modal-img">`
                        : buildFallbackGraphicHtml(`${imprintFront} / ${imprintBack}`, "실물 사진 없음")
                }
            </div>
            <div class="modal-title-area">
                <div style="margin-bottom:6px;">
                    <span class="otc-badge ${(item.etcOtcName || "").includes("전문") ? "special" : "general"}">
                        ${escapeHtml(item.etcOtcName || "의약품")}
                    </span>
                </div>
                <h2 id="modalDialogTitle" class="modal-title">${escapeHtml(item.itemName)}</h2>
                ${
                    item.itemEngName
                        ? `<p style="font-size:0.84rem; color:#64748b; margin-bottom:4px;">${escapeHtml(item.itemEngName)}</p>`
                        : ""
                }
                <p class="modal-corp">
                    제조/수입사: <b>${escapeHtml(item.entpName || "-")}</b> | 품목기준코드: <b>${escapeHtml(item.itemSeq || "-")}</b>
                </p>
                <div style="margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;">
                    <button type="button" id="modalAddPillboxBtn" class="primary-btn" style="padding:9px 16px; border-radius:9px; font-size:0.85rem;">
                        내 약통에 추가하기
                    </button>
                </div>
            </div>
        </div>

        <div class="modal-tabs">
            <button type="button" class="m-tab-btn active" data-mtab="mtab-easy">복약 안내</button>
            <button type="button" class="m-tab-btn" data-mtab="mtab-grain">외형·식별 정보</button>
            <button type="button" class="m-tab-btn" data-mtab="mtab-prmsn">성분·허가 정보</button>
        </div>

        <div id="mtab-easy" class="m-tab-pane active">
            <div class="detail-section">
                <h4>효능 및 효과</h4>
                <p>${escapeHtml(
                    stripTags(item.efcyQesitm) || "약효분류: " + (item.className || "정보 없음")
                )}</p>
            </div>
            <div class="detail-section">
                <h4>용법 및 용량 (복용법)</h4>
                <p>${escapeHtml(
                    stripTags(item.useMethodQesitm) ||
                        "전문의약품이거나 별도 첨부문서 참조가 필요한 품목입니다. 의사·약사의 복약지도에 따라 복용하십시오."
                )}</p>
            </div>
            ${
                item.atpnWarnQesitm
                    ? `<div class="detail-section" style="border-color:#fecaca; background:#fef2f2;">
                         <h4 style="color:#dc2626;">복용 전 필수 경고</h4>
                         <p style="color:#991b1b; font-weight:600;">${escapeHtml(stripTags(item.atpnWarnQesitm))}</p>
                       </div>`
                    : ""
            }
            <div class="detail-section">
                <h4>사용상 주의사항</h4>
                <p>${escapeHtml(stripTags(item.atpnQesitm) || "복용 전 첨부문서의 금기사항을 반드시 확인하십시오.")}</p>
            </div>
            ${
                item.intrcQesitm
                    ? `<div class="detail-section">
                         <h4>병용 주의 (함께 복용 시 주의할 약·음식)</h4>
                         <p>${escapeHtml(stripTags(item.intrcQesitm))}</p>
                       </div>`
                    : ""
            }
            ${
                item.seQesitm
                    ? `<div class="detail-section">
                         <h4>발생 가능한 이상반응·부작용</h4>
                         <p>${escapeHtml(stripTags(item.seQesitm))}</p>
                       </div>`
                    : ""
            }
            <div class="detail-section">
                <h4>가정 내 보관 방법</h4>
                <p>${escapeHtml(
                    stripTags(item.depositMethodQesitm) ||
                        item.storageMethod ||
                        "직사광선을 피하고 서늘한 실온에 어린이 손이 닿지 않는 곳에 보관하십시오."
                )}</p>
            </div>
        </div>

        <div id="mtab-grain" class="m-tab-pane">
            <div class="spec-grid">
                <div class="spec-item">
                    <span>성상 (외형 설명)</span>
                    <strong>${escapeHtml(item.chart || "정보 없음")}</strong>
                </div>
                <div class="spec-item">
                    <span>의약품 모양 / 제형</span>
                    <strong>${escapeHtml(item.drugShape || "-")} / ${escapeHtml(item.formCodeName || "-")}</strong>
                </div>
                <div class="spec-item">
                    <span>색상 (앞 / 뒤)</span>
                    <strong>${escapeHtml(item.colorClass1 || "-")} ${
                        item.colorClass2 ? `/ ${escapeHtml(item.colorClass2)}` : ""
                    }</strong>
                </div>
                <div class="spec-item">
                    <span>식별 표시 각인 (앞 / 뒤)</span>
                    <strong style="color:#2563eb;">앞: ${escapeHtml(imprintFront)} &nbsp;|&nbsp; 뒤: ${escapeHtml(imprintBack)}</strong>
                </div>
                <div class="spec-item">
                    <span>분할선 (앞 / 뒤)</span>
                    <strong>앞: ${escapeHtml(item.lineFront || "없음")} &nbsp;|&nbsp; 뒤: ${escapeHtml(item.lineBack || "없음")}</strong>
                </div>
                <div class="spec-item">
                    <span>실측 크기 (장축 × 단축 × 두께)</span>
                    <strong>${escapeHtml(item.lengLong || "-")} mm × ${escapeHtml(item.lengShort || "-")} mm × ${escapeHtml(item.thick || "-")} mm</strong>
                </div>
            </div>
        </div>

        <div id="mtab-prmsn" class="m-tab-pane">
            <div class="spec-grid">
                <div class="spec-item">
                    <span>전문 / 일반의약품 구분</span>
                    <strong>${escapeHtml(item.etcOtcName || "-")}</strong>
                </div>
                <div class="spec-item">
                    <span>약효분류</span>
                    <strong>${escapeHtml(item.className || "-")}</strong>
                </div>
                <div class="spec-item">
                    <span>주성분명 (영문/한글)</span>
                    <strong>${escapeHtml(cleanIngredientClient(item.itemIngrName) || "-")}</strong>
                </div>
                <div class="spec-item">
                    <span>품목허가일자 / 유효기간</span>
                    <strong>허가일: ${escapeHtml(item.itemPermitDate || "-")} / 유효기간: ${escapeHtml(item.validTerm || "-")}</strong>
                </div>
                <div class="spec-item">
                    <span>공식 저장방법</span>
                    <strong>${escapeHtml(item.storageMethod || stripTags(item.depositMethodQesitm) || "-")}</strong>
                </div>
                <div class="spec-item">
                    <span>보험코드(EDI) / ATC코드</span>
                    <strong>EDI: ${escapeHtml(item.ediCode || "-")} / ATC: ${escapeHtml(item.atcCode || "-")}</strong>
                </div>
            </div>
            ${
                item.materialName
                    ? `<div class="detail-section">
                         <h4>원료성분 및 분량</h4>
                         <p>${escapeHtml(String(item.materialName).replaceAll("|", " · "))}</p>
                       </div>`
                    : ""
            }
            ${
                item.barCode
                    ? `<div class="detail-section">
                         <h4>표준 바코드</h4>
                         <p>${escapeHtml(item.barCode)}</p>
                       </div>`
                    : ""
            }
        </div>
    `;

    const modalImg = modalBody.querySelector(".modal-img");
    if (modalImg) {
        modalImg.addEventListener("error", () => {
            const box = modalBody.querySelector(".modal-img-box");
            modalImg.remove();
            box?.insertAdjacentHTML(
                "beforeend",
                buildFallbackGraphicHtml(`${imprintFront} / ${imprintBack}`, "실물 사진 없음")
            );
        });
    }

    modalBody.querySelectorAll(".m-tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            modalBody.querySelectorAll(".m-tab-btn").forEach((b) => b.classList.remove("active"));
            modalBody.querySelectorAll(".m-tab-pane").forEach((p) => p.classList.remove("active"));
            btn.classList.add("active");
            document.getElementById(btn.dataset.mtab)?.classList.add("active");
        });
    });

    document.getElementById("modalAddPillboxBtn")?.addEventListener("click", () => {
        addToPillbox(item);
    });
}

/* ==========================================================================
   [탭 3] 내 약통 (복약 수첩) & 성분 중복 안전 점검
   - 연결 백엔드 목적지: GET | POST | DELETE /api/pillbox/ ➔ Backend/drugs/views.py :: api_pillbox()
   ========================================================================== */
function getLocalPillbox() {
    try {
        return JSON.parse(localStorage.getItem("edrugs_pillbox") || "[]");
    } catch {
        return [];
    }
}

function saveLocalPillbox(list) {
    localStorage.setItem("edrugs_pillbox", JSON.stringify(list));
    updatePillboxCount(list.length);
}

function buildClientSafetyReport(items) {
    const ingrMap = new Map();
    for (const d of items) {
        const raw = cleanIngredientClient(d.itemIngrName || "");
        const parts = raw
            .replaceAll("|", "/")
            .replaceAll(",", "/")
            .replaceAll(";", "/")
            .split("/")
            .map((p) => p.trim())
            .filter(Boolean);
        for (const ingr of parts) {
            const key = ingr.toLowerCase();
            if (!ingrMap.has(key)) ingrMap.set(key, { name: ingr, drugs: [] });
            const entry = ingrMap.get(key);
            if (!entry.drugs.includes(d.itemName)) entry.drugs.push(d.itemName);
        }
    }
    const duplicates = Array.from(ingrMap.values())
        .filter((v) => v.drugs.length >= 2)
        .map((v) => ({ ingredient: v.name, drugs: v.drugs }));
    return {
        totalSaved: items.length,
        duplicateIngredients: duplicates,
        hasDuplicateRisk: duplicates.length > 0,
    };
}

async function addToPillbox(item) {
    const dosageTime = prompt(
        `'${item.itemName}'의 복용 시간대 또는 메모를 입력해 주세요:`,
        "아침·저녁 식후 30분"
    );
    if (dosageTime === null) return;

    const payload = {
        itemSeq: item.itemSeq || item.itemName,
        itemName: item.itemName,
        entpName: item.entpName || "",
        itemImage: sanitizeHttpUrl(item.itemImage),
        etcOtcName: item.etcOtcName || "",
        className: item.className || "",
        itemIngrName: cleanIngredientClient(item.itemIngrName || ""),
        efcyQesitm: stripTags(item.efcyQesitm || ""),
        useMethodQesitm: stripTags(item.useMethodQesitm || ""),
        atpnQesitm: stripTags(item.atpnWarnQesitm || item.intrcQesitm || item.atpnQesitm || ""),
        dosageTime: dosageTime || "수시 복용",
    };

    if (useDjangoBackend) {
        try {
            const resp = await fetch("/api/pillbox/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (resp.ok) {
                const data = await resp.json();
                updatePillboxCount(data.pillboxCount ?? 0);
                showToast(`'${item.itemName}'이(가) 내 약통에 저장되었습니다.`);
                return;
            }
        } catch (e) {
            console.warn(e);
        }
    }

    const list = getLocalPillbox().filter((x) => x.itemName !== payload.itemName);
    list.unshift({ ...payload, id: Date.now() });
    saveLocalPillbox(list);
    showToast(`'${item.itemName}'이(가) 내 약통에 저장되었습니다.`);
}

async function removeFromPillbox(item) {
    if (useDjangoBackend && item.id) {
        await fetch(`/api/pillbox/?id=${encodeURIComponent(item.id)}`, { method: "DELETE" });
    } else {
        const list = getLocalPillbox().filter((x) => x.itemName !== item.itemName);
        saveLocalPillbox(list);
    }
    showToast("내 약통에서 삭제되었습니다.");
    await loadPillbox();
}

async function loadPillbox() {
    pillboxList.innerHTML = "";
    let items = [];
    let safetyReport = {
        totalSaved: 0,
        duplicateIngredients: [],
        hasDuplicateRisk: false,
        warnings: [],
    };

    if (useDjangoBackend) {
        try {
            const resp = await fetch("/api/pillbox/");
            if (resp.ok) {
                const data = await resp.json();
                items = data.items || [];
                safetyReport = data.safetyReport || safetyReport;
                updatePillboxCount(items.length);
            }
        } catch (e) {
            console.warn(e);
        }
    } else {
        items = getLocalPillbox();
        safetyReport = buildClientSafetyReport(items);
        updatePillboxCount(items.length);
    }

    if (items.length === 0) {
        safetyReportBox.innerHTML = `
            <div class="safety-alert safe">
                <strong>아직 내 약통에 등록된 의약품이 없습니다.</strong><br>
                통합 검색 결과에서 복용 중인 약의 <b>[+ 내 약통 담기]</b> 버튼을 누르면 주성분 중복 여부와 병용 주의사항을 자동으로 분석해 드립니다.
            </div>
        `;
        return;
    }

    let dupHtml = "";
    if (safetyReport.hasDuplicateRisk && safetyReport.duplicateIngredients.length > 0) {
        dupHtml = safetyReport.duplicateIngredients
            .map(
                (d) =>
                    `<div class="safety-alert warn">
                        <strong>주성분 중복 복용 주의: [${escapeHtml(d.ingredient)}]</strong><br>
                        현재 내 약통에 담긴 <b>${escapeHtml(d.drugs.join(", "))}</b>에 동일한 주성분이 포함되어 있습니다. 과량 복용 위험이 있으니 약사 또는 의사와 상담하세요!
                    </div>`
            )
            .join("");
    } else {
        dupHtml = `
            <div class="safety-alert safe">
                <strong>주성분 중복 점검 결과: 안전 (총 ${items.length}개 의약품 보관 중)</strong><br>
                현재 내 약통에 담긴 의약품 간에 중복된 주성분이 발견되지 않았습니다. 각 의약품의 복용 시간대와 주의사항을 확인하세요.
            </div>
        `;
    }

    safetyReportBox.innerHTML = dupHtml;
    renderDrugCards(items, pillboxList, true);
}

/* ==========================================================================
   정적 호스팅 단독 실행 폴백 함수
   ========================================================================== */
function getStaticEncodedKey() {
    const stored = localStorage.getItem("edrugs_public_api_key") || "";
    if (stored.trim()) {
        return stored.trim();
    }
    return DEFAULT_STATIC_ENCODED_KEY;
}

function normalizeDirectItems(rawItems) {
    if (!rawItems) return [];
    if (Array.isArray(rawItems)) return rawItems;
    if (typeof rawItems === "object") {
        if ("item" in rawItems) {
            const sub = rawItems.item;
            if (!sub) return [];
            return Array.isArray(sub) ? sub : [sub];
        }
        return [rawItems];
    }
    return [];
}

async function fetchDirectApi(baseUrl, params = {}, signal = undefined) {
    const encodedKey = getStaticEncodedKey();
    const query = Object.entries(params)
        .filter(([_, v]) => v !== "" && v !== undefined && v !== null)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join("&");
    const url = `${baseUrl}?serviceKey=${encodedKey}&type=json${query ? `&${query}` : ""}`;
    const resp = await fetch(url, { signal });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const text = await resp.text();
    if (text.trim().startsWith("{")) {
        const json = JSON.parse(text);
        const body = json.body || json.response?.body || {};
        return {
            totalCount: Number(body.totalCount || 0),
            items: normalizeDirectItems(body.items),
        };
    }
    return { totalCount: 0, items: [] };
}

function mapGrainItem(g) {
    return {
        itemSeq: g.ITEM_SEQ || "",
        itemName: g.ITEM_NAME || "",
        entpName: g.ENTP_NAME || "",
        chart: g.CHART || "",
        itemImage: g.ITEM_IMAGE || "",
        printFront: g.PRINT_FRONT || "",
        printBack: g.PRINT_BACK || "",
        drugShape: g.DRUG_SHAPE || "",
        colorClass1: g.COLOR_CLASS1 || "",
        colorClass2: g.COLOR_CLASS2 || "",
        lineFront: g.LINE_FRONT || "",
        lineBack: g.LINE_BACK || "",
        lengLong: g.LENG_LONG || "",
        lengShort: g.LENG_SHORT || "",
        thick: g.THICK || "",
        className: g.CLASS_NAME || "",
        etcOtcName: g.ETC_OTC_NAME || "",
        formCodeName: g.FORM_CODE_NAME || "",
        itemEngName: g.ITEM_ENG_NAME || "",
        ediCode: g.EDI_CODE || "",
        sources: ["낱알식별"],
    };
}

function matchLineSideClient(rawLine, selected) {
    const val = (rawLine || "").trim();
    return selected.some((opt) => {
        if (opt === "없음") return val === "" || val === "없음";
        if (opt === "+") return val.includes("+");
        if (opt === "-") return val.includes("-");
        if (opt === "기타") {
            return val !== "" && val !== "없음" && !val.includes("+") && !val.includes("-");
        }
        return false;
    });
}

function matchFormClient(formCodeName, chart, selected) {
    const fc = (formCodeName || "").trim();
    const ch = (chart || "").trim();
    if (!fc && !ch) return false;

    return selected.some((opt) => {
        if (opt === "정제") {
            return (
                (fc.includes("정") &&
                    !fc.includes("캡슐") &&
                    !fc.includes("필름제") &&
                    !fc.includes("붕해필름")) ||
                (!fc && ch.includes("정") && !ch.includes("캡슐"))
            );
        }
        if (opt === "경질캡슐") return fc.includes("경질") || ch.includes("경질");
        if (opt === "연질캡슐") return fc.includes("연질") || ch.includes("연질");
        if (opt === "구강붕해필름") {
            return (
                fc.includes("구강붕해") ||
                fc.includes("붕해필름") ||
                fc.includes("필름제") ||
                ch.includes("구강붕해") ||
                ch.includes("필름제")
            );
        }
        return fc.includes(opt) || ch.includes(opt);
    });
}

function matchesAppearanceClient(item, filters) {
    if (!filters.hasAppearanceFilter) return true;

    const hasGrain =
        (item.sources || []).includes("낱알식별") ||
        Boolean(item.drugShape || item.colorClass1 || item.formCodeName);
    if (!hasGrain) return false;

    if (filters.shapes.length) {
        const ds = (item.drugShape || "").trim();
        if (!ds) return false;
        const ok = filters.shapes.some((s) =>
            s === "기타" ? ds === "기타" || !STANDARD_SHAPES.has(ds) : ds === s
        );
        if (!ok) return false;
    }

    if (filters.colors.length) {
        const combined = `${item.colorClass1 || ""} ${item.colorClass2 || ""}`.trim();
        if (!combined || !filters.colors.some((c) => combined.includes(c))) return false;
    }

    if (filters.forms.length) {
        if (!matchFormClient(item.formCodeName, item.chart, filters.forms)) return false;
    }

    if (filters.lineFront.length) {
        if (!matchLineSideClient(item.lineFront, filters.lineFront)) return false;
    }

    if (filters.lineBack.length) {
        if (!matchLineSideClient(item.lineBack, filters.lineBack)) return false;
    }

    if (filters.printText) {
        const pt = filters.printText.toLowerCase();
        const pf = (item.printFront || "").trim().toLowerCase();
        const pb = (item.printBack || "").trim().toLowerCase();
        if (filters.printExact) {
            if (pf !== pt && pb !== pt) return false;
        } else if (!pf.includes(pt) && !pb.includes(pt)) {
            return false;
        }
    }

    return true;
}

async function directUnifiedSearch(keyword, field, filters, signal) {
    if (!keyword && filters.hasAppearanceFilter) {
        const raw = await fetchDirectApi(
            DIRECT_ENDPOINTS.GRAIN,
            { numOfRows: 100, pageNo: 1 },
            signal
        );
        const items = raw.items
            .map(mapGrainItem)
            .filter((item) => matchesAppearanceClient(item, filters));
        return {
            items,
            counts: {
                mergedCount: items.length,
                easyTotal: 0,
                grainTotal: items.length,
                prmsnTotal: 0,
            },
        };
    }

    const easyParams = { pageNo: 1, numOfRows: 60 };
    if (field === "efcy") easyParams.efcyQesitm = keyword;
    else if (field === "entp") easyParams.entpName = keyword;
    else easyParams.itemName = keyword;

    const grainParams = { pageNo: 1, numOfRows: 60 };
    const prmsnParams = { pageNo: 1, numOfRows: 60 };
    if (field === "entp") {
        grainParams.entp_name = keyword;
        prmsnParams.entp_name = keyword;
    } else {
        grainParams.item_name = keyword;
        prmsnParams.item_name = keyword;
    }

    const [easyRes, grainRes, prmsnRes] = await Promise.allSettled([
        fetchDirectApi(DIRECT_ENDPOINTS.EASY, easyParams, signal),
        field === "efcy"
            ? Promise.resolve({ totalCount: 0, items: [] })
            : fetchDirectApi(DIRECT_ENDPOINTS.GRAIN, grainParams, signal),
        field === "efcy"
            ? Promise.resolve({ totalCount: 0, items: [] })
            : fetchDirectApi(DIRECT_ENDPOINTS.PRMSN_LIST, prmsnParams, signal),
    ]);

    const easy = easyRes.status === "fulfilled" ? easyRes.value : { totalCount: 0, items: [] };
    const grain = grainRes.status === "fulfilled" ? grainRes.value : { totalCount: 0, items: [] };
    const prmsn = prmsnRes.status === "fulfilled" ? prmsnRes.value : { totalCount: 0, items: [] };

    const map = new Map();
    easy.items.forEach((e) => {
        const key = e.itemSeq || e.itemName;
        map.set(key, {
            itemSeq: e.itemSeq || "",
            itemName: e.itemName || "",
            entpName: e.entpName || "",
            itemImage: e.itemImage || "",
            efcyQesitm: e.efcyQesitm || "",
            useMethodQesitm: e.useMethodQesitm || "",
            atpnWarnQesitm: e.atpnWarnQesitm || "",
            atpnQesitm: e.atpnQesitm || "",
            intrcQesitm: e.intrcQesitm || "",
            seQesitm: e.seQesitm || "",
            depositMethodQesitm: e.depositMethodQesitm || "",
            sources: ["e약은요"],
        });
    });

    grain.items.forEach((g) => {
        const key = g.ITEM_SEQ || g.ITEM_NAME;
        const prev = map.get(key) || { sources: [] };
        const mapped = mapGrainItem(g);
        map.set(key, {
            ...mapped,
            ...prev,
            itemImage: prev.itemImage || mapped.itemImage,
            chart: mapped.chart,
            drugShape: mapped.drugShape,
            colorClass1: mapped.colorClass1,
            colorClass2: mapped.colorClass2,
            printFront: mapped.printFront,
            printBack: mapped.printBack,
            lineFront: mapped.lineFront,
            lineBack: mapped.lineBack,
            formCodeName: mapped.formCodeName,
            etcOtcName: mapped.etcOtcName,
            className: mapped.className,
            sources: Array.from(new Set([...(prev.sources || []), "낱알식별"])),
        });
    });

    prmsn.items.forEach((p) => {
        const key = p.ITEM_SEQ || p.ITEM_NAME;
        const prev = map.get(key) || {
            itemSeq: p.ITEM_SEQ,
            itemName: p.ITEM_NAME,
            entpName: p.ENTP_NAME,
            sources: [],
        };
        map.set(key, {
            ...prev,
            itemEngName: p.ITEM_ENG_NAME || prev.itemEngName || "",
            etcOtcName: p.SPCLTY_PBLC || prev.etcOtcName || "",
            className: p.PRDUCT_TYPE || prev.className || "",
            itemIngrName: cleanIngredientClient(p.ITEM_INGR_NAME) || prev.itemIngrName || "",
            itemPermitDate: p.ITEM_PERMIT_DATE || prev.itemPermitDate || "",
            itemImage: prev.itemImage || p.BIG_PRDT_IMG_URL || "",
            sources: Array.from(new Set([...(prev.sources || []), "허가정보"])),
        });
    });

    let items = Array.from(map.values());
    if (filters.hasAppearanceFilter) {
        items = items.filter((item) => matchesAppearanceClient(item, filters));
        return {
            items,
            counts: {
                mergedCount: items.length,
                easyTotal: items.filter((r) => (r.sources || []).includes("e약은요")).length,
                grainTotal: items.filter((r) => (r.sources || []).includes("낱알식별")).length,
                prmsnTotal: items.filter((r) => (r.sources || []).includes("허가정보")).length,
            },
        };
    }

    return {
        items,
        counts: {
            mergedCount: items.length,
            easyTotal: easy.totalCount,
            grainTotal: grain.totalCount,
            prmsnTotal: prmsn.totalCount,
        },
    };
}

async function directEnrichDrugDetail(item) {
    const dtlParams = { numOfRows: 1 };
    if (item.itemSeq) dtlParams.item_seq = item.itemSeq;
    else if (item.itemName) dtlParams.item_name = item.itemName.split("(")[0].trim();

    const dtlRes = await fetchDirectApi(DIRECT_ENDPOINTS.PRMSN_DTL, dtlParams);
    if (dtlRes.items && dtlRes.items[0]) {
        const d = dtlRes.items[0];
        return {
            validTerm: d.VALID_TERM || "",
            storageMethod: d.STORAGE_METHOD || "",
            materialName: d.MATERIAL_NAME || "",
            barCode: d.BAR_CODE || "",
            itemIngrName:
                cleanIngredientClient(item.itemIngrName) ||
                cleanIngredientClient(d.MAIN_ITEM_INGR) ||
                "",
            efcyQesitm: item.efcyQesitm || stripTags(d.EE_DOC_DATA || "").slice(0, 1200),
            useMethodQesitm: item.useMethodQesitm || stripTags(d.UD_DOC_DATA || "").slice(0, 1200),
            atpnQesitm: item.atpnQesitm || stripTags(d.NB_DOC_DATA || "").slice(0, 1500),
        };
    }
    return {};
}
