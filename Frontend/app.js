/**
 * [역할] 알약이가 프론트엔드 배색 테마·검색·모달·내 약통(CRUD) 비동기 컨트롤러
 * [경로] Frontend/index.html (<script defer>) -> Backend/drugs/views.py (/api/*) -> DOM 렌더링
 * [수정] 페이지당 카드 표시 개수를 바꾸려면 아래 PAGE_SIZE 상수를 조정하세요.
 */

const PAGE_SIZE = 12;
const THEME_STORAGE_KEY = "edrugs-theme";
const VALID_THEMES = new Set(["forest", "navy", "walnut", "plum"]);

const CHAPTER_TITLES = {
    "tab-unified": "통합 의약품 및 낱알 외형 탐색",
    "tab-permission": "식약처 품목허가 · 주성분 색인",
    "tab-pillbox": "내 약통 관리 및 주성분 중복 점검",
};

const FILTER_GROUPS = [
    { key: "forms", id: "formCheckGroup", label: "제형" },
    { key: "lineFront", id: "lineFrontCheckGroup", label: "앞분할" },
    { key: "lineBack", id: "lineBackCheckGroup", label: "뒤분할" },
    { key: "shapes", id: "shapeCheckGroup", label: "모양" },
    { key: "colors", id: "colorCheckGroup", label: "색상" },
];

let unifiedItemsCache = [];
let prmsnItemsCache = [];
let unifiedAbortController = null;
let prmsnAbortController = null;
let detailAbortController = null;
let pillboxModalState = { mode: "create", item: null };
let toastTimer = null;

/**
 * [역할] innerHTML 없이 안전한 DOM 요소를 생성해 XSS 싱크를 원천 차단합니다.
 * [경로] 렌더 함수 전체 -> el() -> HTMLElement 반환
 * [수정] 커스텀 data-* 속성이 필요하면 attrs.dataset 객체로 전달하세요.
 */
function el(tag, attrs = null, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
        for (const [key, val] of Object.entries(attrs)) {
            if (val === null || val === undefined || val === false) continue;
            if (key === "className") {
                node.className = val;
            } else if (key === "text") {
                node.textContent = String(val);
            } else if (key === "dataset" && typeof val === "object") {
                for (const [dKey, dVal] of Object.entries(val)) {
                    node.dataset[dKey] = String(dVal);
                }
            } else if (key.startsWith("on") && typeof val === "function") {
                node.addEventListener(key.slice(2).toLowerCase(), val);
            } else if (val === true) {
                node.setAttribute(key, "");
            } else {
                node.setAttribute(key, String(val));
            }
        }
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
}

/**
 * [역할] 선택한 깔맞춤 배색 테마를 <html data-theme>에 반영하고 로컬 스토리지에 보존합니다.
 * [경로] 우측 하단 .theme-swatch-circle 클릭 / 초기 로드 -> applyTheme()
 * [수정] 새 테마를 추가하려면 style.css에 토큰을 정의하고 VALID_THEMES에 키를 추가하세요.
 */
function applyTheme(themeName, persist = true) {
    const safeTheme = VALID_THEMES.has(themeName) ? themeName : "forest";
    document.documentElement.dataset.theme = safeTheme;

    document.querySelectorAll(".theme-swatch-circle[data-theme-choice]").forEach((btn) => {
        const isActive = btn.dataset.themeChoice === safeTheme;
        btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    });

    if (persist) {
        try {
            window.localStorage.setItem(THEME_STORAGE_KEY, safeTheme);
        } catch {
            /* 사설 브라우징 등 저장소 제한 환경 무시 */
        }
    }
}

/**
 * [역할] 우측 하단 반반 동그라미 테마 버튼 이벤트를 연결하고 이전 선택 테마를 복원합니다.
 * [경로] DOMContentLoaded -> initThemeSwitcher() -> applyTheme()
 * [수정] 기본 시작 테마를 바꾸려면 fallback 문자열("forest")을 수정하세요.
 */
function initThemeSwitcher() {
    let saved = "forest";
    try {
        saved = window.localStorage.getItem(THEME_STORAGE_KEY) || "forest";
    } catch {
        saved = "forest";
    }
    applyTheme(saved, false);

    document.querySelectorAll(".theme-swatch-circle[data-theme-choice]").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (btn.dataset.themeChoice) {
                applyTheme(btn.dataset.themeChoice, true);
            }
        });
    });
}

/**
 * [역할] 외부 이미지 URL이 안전한 http/https 스킴인지 검증합니다.
 * [경로] createDossierCard / renderDetailModalContent -> sanitizeUrl() -> 안전한 URL 또는 ""
 * [수정] 특정 도메인만 허용하려면 parsed.hostname 화이트리스트 조건을 추가하세요.
 */
function sanitizeUrl(rawUrl) {
    if (!rawUrl || typeof rawUrl !== "string") return "";
    const trimmed = rawUrl.trim();
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
 * [역할] Django가 발급한 csrftoken 쿠키 값을 읽어 상태 변경 API 헤더에 전달합니다.
 * [경로] apiJson() -> getCsrfToken() -> document.cookie 조회
 * [수정] settings.py에서 CSRF_COOKIE_NAME을 변경한 경우 name 상수를 동일하게 맞추세요.
 */
function getCsrfToken() {
    const name = "csrftoken=";
    const parts = document.cookie ? document.cookie.split(";") : [];
    for (const rawPart of parts) {
        const part = rawPart.trim();
        if (part.startsWith(name)) {
            return decodeURIComponent(part.slice(name.length));
        }
    }
    return "";
}

/**
 * [역할] 공통 JSON Fetch 래퍼 (CSRF 토큰 자동 첨부 및 HTTP 오류 메시지 표준화)
 * [경로] 모든 프론트엔드 API 호출 -> apiJson() -> Backend/drugs/views.py
 * [수정] 요청 타임아웃을 추가하려면 AbortSignal.any와 AbortSignal.timeout을 결합하세요.
 */
async function apiJson(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = {
        Accept: "application/json",
        ...(options.headers || {}),
    };
    if (method !== "GET" && method !== "HEAD") {
        headers["X-CSRFToken"] = getCsrfToken();
    }
    if (options.body && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }

    const res = await fetch(url, {
        credentials: "same-origin",
        ...options,
        method,
        headers,
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(data.error || `요청 처리 중 오류가 발생했습니다. (HTTP ${res.status})`);
    }
    return data;
}

/**
 * [역할] 화면 우측 하단 테마 버튼 위에 짧은 상태 알림 토스트를 띄웁니다.
 * [경로] 내 약통 등록·수정·삭제 완료 시 -> showToast() -> #toastNotice
 * [수정] 표시 유지 시간을 바꾸려면 setTimeout의 2600(ms) 값을 조정하세요.
 */
function showToast(message) {
    const banner = document.getElementById("toastNotice");
    if (!banner) return;
    banner.textContent = message;
    banner.classList.remove("hidden");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
        banner.classList.add("hidden");
    }, 2600);
}

/**
 * [역할] 상태 안내 배너(#statusMessage, #prmsnStatusMessage)의 표시 여부와 오류 스타일을 갱신합니다.
 * [경로] runUnifiedSearch / runPermissionSearch -> setBannerState()
 * [수정] 오류 색상을 조정하려면 style.css의 .state-banner.is-error 규칙을 수정하세요.
 */
function setBannerState(elementId, message, isError = false) {
    const banner = document.getElementById(elementId);
    if (!banner) return;
    if (!message) {
        banner.textContent = "";
        banner.classList.add("hidden");
        banner.classList.remove("is-error");
        return;
    }
    banner.textContent = message;
    banner.classList.remove("hidden");
    banner.classList.toggle("is-error", Boolean(isError));
}

/**
 * [역할] 좌측 레일 및 모바일 하단 도크의 내 약통 개수 배지를 동기화합니다.
 * [경로] syncPillboxStatus / api_pillbox 응답 -> updatePillboxBadges()
 * [수정] 배지 요소를 추가한 경우 아래 배열에 ID를 추가하세요.
 */
function updatePillboxBadges(count) {
    const safeCount = Number.isFinite(Number(count)) ? Number(count) : 0;
    for (const id of ["pillboxCountBadge", "mPillboxCount"]) {
        const node = document.getElementById(id);
        if (node) node.textContent = String(safeCount);
    }
}

/**
 * [역할] 초기 진입 시 내 약통 보관 건수를 동기화하고 빈 캐시 DB 시드를 트리거합니다.
 * [경로] DOMContentLoaded -> syncPillboxStatus() -> GET /api/status/
 * [수정] 초기 로드 시 추가 상태값이 필요하면 응답 처리 로직을 확장하세요.
 */
async function syncPillboxStatus() {
    try {
        const data = await apiJson("/api/status/");
        updatePillboxBadges(data.pillboxCount ?? 0);
    } catch {
        /* 네트워크 미연결 시 기본 배지 값(0) 유지 */
    }
}

/**
 * [역할] 3개 메뉴 탭 전환 및 상단 워크벤치 제목을 갱신합니다.
 * [경로] 좌측 .nav-btn / 모바일 .m-nav-btn 클릭 -> switchTab() -> 탭 활성화
 * [수정] 새 탭 추가 시 CHAPTER_TITLES 객체에 제목을 등록하세요.
 */
function switchTab(targetId) {
    document.querySelectorAll(".nav-btn, .m-nav-btn").forEach((btn) => {
        const isCurrent = btn.dataset.tab === targetId;
        btn.classList.toggle("active", isCurrent);
        if (isCurrent) {
            btn.setAttribute("aria-current", "page");
        } else {
            btn.removeAttribute("aria-current");
        }
    });

    document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === targetId);
    });

    const titleText = CHAPTER_TITLES[targetId];
    const heading = document.getElementById("workspaceHeading");
    if (titleText && heading) {
        heading.textContent = titleText;
    }

    if (targetId === "tab-pillbox") {
        loadPillbox();
    }
}

/**
 * [역할] 특정 외형 조건 그룹에서 선택된 체크박스 값 배열을 반환합니다 ('전체' 선택 시 빈 배열).
 * [경로] updateActiveFilterBadges / runUnifiedSearch -> getCheckedValues()
 * [수정] 단일 선택 모드로 바꾸려면 initCheckGroups()의 체크 해제 로직을 조정하세요.
 */
function getCheckedValues(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return [];
    const allBox = container.querySelector('input[data-role="all"]');
    if (allBox && allBox.checked) return [];
    return Array.from(
        container.querySelectorAll('input[type="checkbox"]:not([data-role="all"]):checked')
    ).map((cb) => cb.value);
}

/**
 * [역할] 활성화된 낱알 외형 조건 요약 배지(#activeFilterBadges)를 실시간 렌더링합니다.
 * [경로] 체크박스 변경 / 각인 입력 -> updateActiveFilterBadges()
 * [수정] 배지 표기 형식을 바꾸려면 tags 문자열 포맷을 수정하세요.
 */
function updateActiveFilterBadges() {
    const badgeWrap = document.getElementById("activeFilterBadges");
    if (!badgeWrap) return;

    const tags = [];
    const printVal = (document.getElementById("grainPrintInput")?.value || "").trim();
    const isExact = Boolean(document.getElementById("grainPrintExact")?.checked);
    if (printVal) {
        tags.push(`각인: ${printVal}${isExact ? " (정확일치)" : ""}`);
    }

    for (const group of FILTER_GROUPS) {
        const vals = getCheckedValues(group.id);
        if (vals.length > 0) {
            tags.push(`${group.label}: ${vals.join("·")}`);
        }
    }

    badgeWrap.replaceChildren(
        ...tags.map((label) => el("span", { className: "active-filter-tag", text: label }))
    );
}

/**
 * [역할] 낱알 외형 매트릭스의 '전체' 체크박스와 개별 조건 체크박스 간 상호 배타 상태를 관리합니다.
 * [경로] DOMContentLoaded -> initCheckGroups() -> 각 fieldset change 이벤트 바인딩
 * [수정] 조건 그룹 추가 시 상단 FILTER_GROUPS 배열에 항목을 추가하세요.
 */
function initCheckGroups() {
    for (const group of FILTER_GROUPS) {
        const container = document.getElementById(group.id);
        if (!container) continue;

        container.addEventListener("change", (e) => {
            const target = e.target;
            if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") return;

            const allBox = container.querySelector('input[data-role="all"]');
            const itemBoxes = Array.from(
                container.querySelectorAll('input[type="checkbox"]:not([data-role="all"])')
            );

            if (target.dataset.role === "all") {
                if (target.checked) {
                    itemBoxes.forEach((cb) => {
                        cb.checked = false;
                    });
                } else if (!itemBoxes.some((cb) => cb.checked)) {
                    target.checked = true;
                }
            } else {
                const anyChecked = itemBoxes.some((cb) => cb.checked);
                if (allBox) allBox.checked = !anyChecked;
            }
            updateActiveFilterBadges();
        });
    }

    document.getElementById("grainPrintInput")?.addEventListener("input", updateActiveFilterBadges);
    document.getElementById("grainPrintExact")?.addEventListener("change", updateActiveFilterBadges);
}

/**
 * [역할] 모든 낱알 외형 체크박스와 각인 입력값을 초기 상태('전체')로 되돌립니다.
 * [경로] #resetGrainFilterBtn / resetToHome -> resetGrainFilters()
 * [수정] 기본 선택값을 바꾸려면 해당 input을 찾아 checked = true로 설정하세요.
 */
function resetGrainFilters() {
    for (const group of FILTER_GROUPS) {
        const container = document.getElementById(group.id);
        if (!container) continue;
        container.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
            cb.checked = cb.dataset.role === "all";
        });
    }
    const printInput = document.getElementById("grainPrintInput");
    const printExact = document.getElementById("grainPrintExact");
    if (printInput) printInput.value = "";
    if (printExact) printExact.checked = false;
    updateActiveFilterBadges();
}

/**
 * [역할] 외형 조건판 접기·펼치기 상태를 전환합니다.
 * [경로] #toggleGrainFilterBtn 클릭 -> setGrainPanelExpanded()
 * [수정] 초기 접힘 상태를 원하면 DOMContentLoaded에서 setGrainPanelExpanded(false)를 호출하세요.
 */
function setGrainPanelExpanded(expanded) {
    const body = document.getElementById("grainFilterBody");
    const toggleBtn = document.getElementById("toggleGrainFilterBtn");
    if (!body || !toggleBtn) return;
    body.classList.toggle("collapsed", !expanded);
    toggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
    toggleBtn.textContent = expanded ? "외형 조건판 접기" : "외형 조건판 펼치기";
}

/**
 * [역할] 좌측 상단 브랜드 클릭 시 통합 탐색 초기 상태로 복귀합니다.
 * [경로] #brandLogo 클릭 -> resetToHome()
 * [수정] 초기화 시 포커스 대상을 바꾸려면 마지막 focus() 호출 요소를 변경하세요.
 */
function resetToHome() {
    if (unifiedAbortController) unifiedAbortController.abort();
    switchTab("tab-unified");

    const searchInput = document.getElementById("searchInput");
    const fieldSelect = document.getElementById("unifiedFieldSelect");
    if (searchInput) searchInput.value = "";
    if (fieldSelect) fieldSelect.value = "itemName";

    resetGrainFilters();
    setGrainPanelExpanded(true);

    unifiedItemsCache = [];
    document.getElementById("unifiedResultsSection")?.classList.add("hidden");
    document.getElementById("unifiedStatsBar")?.classList.add("hidden");
    document.getElementById("unifiedPagination")?.classList.add("hidden");
    document.getElementById("resultList")?.replaceChildren();
    setBannerState("statusMessage", "");

    window.scrollTo({ top: 0, behavior: "smooth" });
    searchInput?.focus();
}

/**
 * [역할] 이미지가 없거나 로드 실패 시 알약 각인·형상을 도식화한 대체 미디어 박스를 생성합니다.
 * [경로] createDossierCard / renderDetailModalContent -> createFallbackMedia()
 * [수정] 대체 박스 문구를 바꾸려면 diagramText / captionText 조합을 수정하세요.
 */
function createFallbackMedia(item) {
    const imprints = [item.printFront, item.printBack].filter(Boolean).join(" | ");
    const diagramText = imprints || item.drugShape || item.etcOtcName || "이미지 없음";
    const captionText =
        [item.colorClass1, item.formCodeName].filter(Boolean).join(" · ") || "식별 도식";

    return el(
        "div",
        { className: "media" },
        el("span", { className: "imprint-diagram", text: diagramText }),
        el("span", { className: "media-caption", text: captionText })
    );
}

/**
 * [역할] 단일 의약품 도시에(Dossier) 카드를 생성합니다 (스트레치드 상세 트리거 + 독립 액션 버튼).
 * [경로] renderPaginatedCards / loadPillbox -> createDossierCard() -> .dossier-card 반환
 * [수정] 카드 노출 항목을 추가하려면 .spec-chip-row 또는 .dossier-summary 생성부를 수정하세요.
 */
function createDossierCard(item, isPillbox = false) {
    const safeImg = sanitizeUrl(item.itemImage);
    let mediaNode;

    if (safeImg) {
        mediaNode = el("img", {
            className: "dossier-photo",
            src: safeImg,
            alt: `${item.itemName || "의약품"} 외형 이미지`,
            width: 132,
            height: 106,
            loading: "lazy",
            decoding: "async",
        });
        mediaNode.addEventListener(
            "error",
            () => {
                mediaNode.replaceWith(createFallbackMedia(item));
            },
            { once: true }
        );
    } else {
        mediaNode = createFallbackMedia(item);
    }

    const etcLabel = item.etcOtcName || "분류 미상";
    const isSpecial = etcLabel.includes("전문");

    const headerNode = el(
        "header",
        null,
        el(
            "div",
            { className: "dossier-meta-line" },
            el("span", {
                className: `rx-tag ${isSpecial ? "special" : "general"}`,
                text: etcLabel,
            }),
            el("span", { text: item.entpName || "제조사 미상" }),
            item.itemSeq ? el("span", { className: "seq-code", text: `#${item.itemSeq}` }) : null
        ),
        el(
            "h3",
            { className: "dossier-title" },
            el("button", {
                type: "button",
                className: "card-trigger",
                text: item.itemName || "품목명 미상",
                onClick: () => openDetailModal(item),
            })
        )
    );

    const specChips = [];
    if (item.className) {
        specChips.push(el("span", { className: "spec-chip", text: item.className }));
    }
    const shapeColor = [item.drugShape, item.colorClass1, item.colorClass2]
        .filter(Boolean)
        .join(" · ");
    if (shapeColor) {
        specChips.push(el("span", { className: "spec-chip", text: shapeColor }));
    }
    const imprintText = [item.printFront, item.printBack].filter(Boolean).join(" | ");
    if (imprintText) {
        specChips.push(
            el("span", { className: "spec-chip imprint", text: `각인 ${imprintText}` })
        );
    }
    if (item.ediCode) {
        specChips.push(el("span", { className: "spec-chip", text: `EDI ${item.ediCode}` }));
    }

    const summaryStr =
        item.efcyQesitm ||
        (item.itemIngrName
            ? `주성분: ${item.itemIngrName}`
            : "카드를 선택하면 효능·용법·외형·허가 통합 명세서를 조회합니다.");

    const pillboxNote = isPillbox
        ? el(
              "div",
              { className: "pillbox-note-box" },
              el("span", {
                  className: "pillbox-dosage-line",
                  text: `복용 시간 · ${item.dosageTime || "시간대 미지정"}`,
              }),
              el("span", {
                  className: "pillbox-memo-line",
                  text: item.memo
                      ? `메모 · ${item.memo}`
                      : `개인 메모 없음${item.createdAt ? ` · 등록 ${item.createdAt}` : ""}`,
              })
          )
        : null;

    const bodyNode = el(
        "div",
        { className: "dossier-body" },
        specChips.length > 0 ? el("div", { className: "spec-chip-row" }, specChips) : null,
        el("p", { className: "dossier-summary", text: summaryStr }),
        pillboxNote
    );

    const sourceCaption =
        Array.isArray(item.sources) && item.sources.length > 0
            ? `데이터 · ${item.sources.join(" + ")}`
            : isPillbox
              ? `등록일 · ${item.createdAt || "-"}`
              : "식약처 공공데이터";

    const actionButtons = isPillbox
        ? [
              el("button", {
                  type: "button",
                  className: "btn-card-action",
                  text: "복용·메모 수정",
                  onClick: () => openPillboxModal(item, "edit"),
              }),
              el("button", {
                  type: "button",
                  className: "btn-danger",
                  text: "삭제",
                  onClick: () => removeFromPillbox(item),
              }),
          ]
        : [
              el("button", {
                  type: "button",
                  className: "btn-card-action",
                  text: "+ 내 약통 등록",
                  onClick: () => openPillboxModal(item, "create"),
              }),
          ];

    const footerNode = el(
        "footer",
        null,
        el("span", { className: "source-caption", text: sourceCaption }),
        el("div", { className: "card-action-group" }, actionButtons)
    );

    return el("article", { className: "dossier-card" }, mediaNode, headerNode, bodyNode, footerNode);
}

/**
 * [역할] 검색 결과 배열을 PAGE_SIZE 단위로 분할 렌더링하고 페이지 이동 버튼을 구성합니다.
 * [경로] runUnifiedSearch / runPermissionSearch -> renderPaginatedCards()
 * [수정] 페이지 버튼 노출 범위를 조정하려면 startPage / endPage 오프셋(2)을 수정하세요.
 */
function renderPaginatedCards(items, listContainer, paginationContainer, page = 1) {
    if (!listContainer) return;
    if (!Array.isArray(items) || items.length === 0) {
        listContainer.replaceChildren();
        paginationContainer?.classList.add("hidden");
        paginationContainer?.replaceChildren();
        return;
    }

    const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
    const safePage = Math.min(Math.max(1, page), totalPages);
    const slice = items.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

    listContainer.replaceChildren(...slice.map((item) => createDossierCard(item, false)));

    if (!paginationContainer) return;
    if (totalPages <= 1) {
        paginationContainer.classList.add("hidden");
        paginationContainer.replaceChildren();
        return;
    }

    const goPage = (nextPage) => {
        renderPaginatedCards(items, listContainer, paginationContainer, nextPage);
        listContainer.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    const buttons = [];
    buttons.push(
        el("button", {
            type: "button",
            className: "page-btn",
            text: "이전",
            disabled: safePage === 1,
            onClick: () => goPage(safePage - 1),
        })
    );

    const startPage = Math.max(1, safePage - 2);
    const endPage = Math.min(totalPages, safePage + 2);

    if (startPage > 1) {
        buttons.push(
            el("button", {
                type: "button",
                className: "page-btn",
                text: "1",
                onClick: () => goPage(1),
            })
        );
        if (startPage > 2) {
            buttons.push(el("span", { className: "page-ellipsis", text: "…" }));
        }
    }

    for (let p = startPage; p <= endPage; p += 1) {
        buttons.push(
            el("button", {
                type: "button",
                className: `page-btn${p === safePage ? " active" : ""}`,
                text: String(p),
                "aria-current": p === safePage ? "page" : false,
                onClick: () => goPage(p),
            })
        );
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            buttons.push(el("span", { className: "page-ellipsis", text: "…" }));
        }
        buttons.push(
            el("button", {
                type: "button",
                className: "page-btn",
                text: String(totalPages),
                onClick: () => goPage(totalPages),
            })
        );
    }

    buttons.push(
        el("button", {
            type: "button",
            className: "page-btn",
            text: "다음",
            disabled: safePage === totalPages,
            onClick: () => goPage(safePage + 1),
        })
    );

    paginationContainer.replaceChildren(...buttons);
    paginationContainer.classList.remove("hidden");
}

/**
 * [역할] 검색어와 낱알 외형 다중 조건을 조합해 식약처 3종 통합 검색 API를 호출합니다.
 * [경로] #unifiedSearchForm submit -> runUnifiedSearch() -> GET /api/unified-search/
 * [수정] 기본 조회 건수를 늘리려면 params.set("rows", "80") 파라미터를 추가하세요.
 */
async function runUnifiedSearch() {
    const keyword = (document.getElementById("searchInput")?.value || "").trim();
    const field = document.getElementById("unifiedFieldSelect")?.value || "itemName";
    const printVal = (document.getElementById("grainPrintInput")?.value || "").trim();
    const printExact = Boolean(document.getElementById("grainPrintExact")?.checked);

    const shapes = getCheckedValues("shapeCheckGroup");
    const colors = getCheckedValues("colorCheckGroup");
    const forms = getCheckedValues("formCheckGroup");
    const lineFront = getCheckedValues("lineFrontCheckGroup");
    const lineBack = getCheckedValues("lineBackCheckGroup");

    const hasAppearance =
        shapes.length > 0 ||
        colors.length > 0 ||
        forms.length > 0 ||
        lineFront.length > 0 ||
        lineBack.length > 0 ||
        Boolean(printVal);

    const resultsSection = document.getElementById("unifiedResultsSection");
    const statsBar = document.getElementById("unifiedStatsBar");
    const resultList = document.getElementById("resultList");
    const pagination = document.getElementById("unifiedPagination");

    resultsSection?.classList.remove("hidden");

    if (!keyword && !hasAppearance) {
        statsBar?.classList.add("hidden");
        resultList?.replaceChildren();
        pagination?.classList.add("hidden");
        setBannerState(
            "statusMessage",
            "검색어를 입력하거나 아래 낱알 외형 식별 매트릭스에서 모양·색상·각인 조건을 1개 이상 선택해 주세요.",
            true
        );
        return;
    }

    if (unifiedAbortController) unifiedAbortController.abort();
    unifiedAbortController = new AbortController();

    setBannerState("statusMessage", "식약처 공공데이터 3종 및 로컬 외형 캐시를 교차 조회하고 있습니다...");
    statsBar?.classList.add("hidden");
    resultList?.replaceChildren();
    pagination?.classList.add("hidden");

    const params = new URLSearchParams();
    if (keyword) params.set("q", keyword);
    params.set("field", field);
    if (shapes.length) params.set("shapes", shapes.join(","));
    if (colors.length) params.set("colors", colors.join(","));
    if (forms.length) params.set("forms", forms.join(","));
    if (lineFront.length) params.set("lineFront", lineFront.join(","));
    if (lineBack.length) params.set("lineBack", lineBack.join(","));
    if (printVal) params.set("print", printVal);
    if (printExact) params.set("printExact", "1");

    try {
        const data = await apiJson(`/api/unified-search/?${params.toString()}`, {
            signal: unifiedAbortController.signal,
        });

        unifiedItemsCache = Array.isArray(data.items) ? data.items : [];
        const counts = data.counts || {};

        const setStat = (id, num) => {
            const node = document.getElementById(id);
            if (node) node.textContent = `${Number(num || 0).toLocaleString()}건`;
        };
        setStat("statMergedCount", counts.mergedCount ?? unifiedItemsCache.length);
        setStat("statEasyCount", counts.easyTotal ?? 0);
        setStat("statGrainCount", counts.grainTotal ?? 0);
        setStat("statPrmsnCount", counts.prmsnTotal ?? 0);
        statsBar?.classList.remove("hidden");

        if (unifiedItemsCache.length === 0) {
            setBannerState(
                "statusMessage",
                "선택한 검색어 및 외형 조건과 일치하는 의약품을 찾지 못했습니다. 조건을 일부 해제해 다시 조회해 보세요."
            );
        } else {
            setBannerState("statusMessage", "");
            renderPaginatedCards(unifiedItemsCache, resultList, pagination, 1);
        }
    } catch (err) {
        if (err.name === "AbortError") return;
        setBannerState("statusMessage", err.message || "통합 검색 중 오류가 발생했습니다.", true);
    }
}

/**
 * [역할] 전문·일반 구분 및 품목명·제조사 기준으로 식약처 허가 원장을 조회합니다.
 * [경로] #prmsnSearchForm submit -> runPermissionSearch() -> GET /api/permission-search/
 * [수정] 검색 기준 옵션을 늘리려면 index.html의 #prmsnFieldSelect와 views.py를 함께 수정하세요.
 */
async function runPermissionSearch() {
    const keyword = (document.getElementById("prmsnSearchInput")?.value || "").trim();
    const spclty = document.getElementById("prmsnSpcltySelect")?.value || "전체";
    const field = document.getElementById("prmsnFieldSelect")?.value || "item_name";

    const listEl = document.getElementById("prmsnResultList");
    const paginationEl = document.getElementById("prmsnPagination");

    if (!keyword && spclty === "전체") {
        listEl?.replaceChildren();
        paginationEl?.classList.add("hidden");
        setBannerState(
            "prmsnStatusMessage",
            "품목명·제조사 키워드를 입력하거나 전문·일반 구분을 선택해 주세요.",
            true
        );
        return;
    }

    if (prmsnAbortController) prmsnAbortController.abort();
    prmsnAbortController = new AbortController();

    setBannerState("prmsnStatusMessage", "식약처 의약품 제품 허가 원장을 조회하고 있습니다...");
    listEl?.replaceChildren();
    paginationEl?.classList.add("hidden");

    const params = new URLSearchParams({
        q: keyword,
        spclty,
        field,
    });

    try {
        const data = await apiJson(`/api/permission-search/?${params.toString()}`, {
            signal: prmsnAbortController.signal,
        });
        prmsnItemsCache = Array.isArray(data.items) ? data.items : [];

        if (prmsnItemsCache.length === 0) {
            setBannerState("prmsnStatusMessage", "조건에 해당하는 품목허가 데이터가 없습니다.");
            return;
        }

        setBannerState(
            "prmsnStatusMessage",
            `식약처 전체 허가 원장 ${Number(data.totalCount || prmsnItemsCache.length).toLocaleString()}건 중 상위 ${prmsnItemsCache.length}건을 표시합니다.`
        );
        renderPaginatedCards(prmsnItemsCache, listEl, paginationEl, 1);
    } catch (err) {
        if (err.name === "AbortError") return;
        setBannerState("prmsnStatusMessage", err.message || "허가 조회 중 오류가 발생했습니다.", true);
    }
}

/**
 * [역할] 상세 모달 내부의 규격 정의 항목(<div class="spec-ledger-item">)을 생성합니다.
 * [경로] renderDetailModalContent() -> specItem()
 * [수정] 빈 값 대체 문구를 바꾸려면 fallback 기본값("-")을 수정하세요.
 */
function specItem(label, value, fallback = "-") {
    const textVal =
        value !== null && value !== undefined && String(value).trim() !== ""
            ? String(value)
            : fallback;
    return el(
        "div",
        { className: "spec-ledger-item" },
        el("dt", { text: label }),
        el("dd", { text: textVal })
    );
}

/**
 * [역할] 상세 모달 내부의 서술형 텍스트 블록(.monograph-block)을 생성합니다.
 * [경로] renderDetailModalContent() -> monographBlock()
 * [수정] 주의사항 강조 여부를 바꾸려면 isCritical 인자를 조정하세요.
 */
function monographBlock(title, content, fallbackText, isCritical = false) {
    return el(
        "section",
        { className: `monograph-block${isCritical ? " critical" : ""}` },
        el("h3", { text: title }),
        el("p", { text: content && String(content).trim() ? String(content) : fallbackText })
    );
}

/**
 * [역할] 병합된 3-in-1 의약품 상세 데이터를 네이티브 <dialog id="detailModal"> 본문에 렌더링합니다.
 * [경로] openDetailModal() -> renderDetailModalContent() -> #modalBody 갱신
 * [수정] 모달 탭 순서를 바꾸려면 tabDefs 배열과 panes 순서를 함께 변경하세요.
 */
function renderDetailModalContent(merged) {
    const modalBody = document.getElementById("modalBody");
    if (!modalBody) return;

    const safeImg = sanitizeUrl(merged.itemImage);
    const frameNode = el("div", { className: "modal-specimen-frame" });
    if (safeImg) {
        const img = el("img", {
            src: safeImg,
            alt: `${merged.itemName || "의약품"} 상세 외형 사진`,
            width: 172,
            height: 120,
        });
        img.addEventListener(
            "error",
            () => {
                frameNode.replaceChildren(createFallbackMedia(merged));
            },
            { once: true }
        );
        frameNode.append(img);
    } else {
        frameNode.append(createFallbackMedia(merged));
    }

    const etcLabel = merged.etcOtcName || "분류 미상";
    const isSpecial = etcLabel.includes("전문");

    const heroNode = el(
        "div",
        { className: "modal-hero" },
        frameNode,
        el(
            "div",
            { className: "modal-summary-col" },
            el(
                "div",
                { className: "dossier-meta-line" },
                el("span", {
                    className: `rx-tag ${isSpecial ? "special" : "general"}`,
                    text: etcLabel,
                }),
                merged.itemSeq ? el("span", { className: "seq-code", text: `#${merged.itemSeq}` }) : null,
                merged.cancelName
                    ? el("span", { className: "seq-code", text: `상태: ${merged.cancelName}` })
                    : null
            ),
            el("h2", {
                id: "modalDialogTitle",
                className: "modal-drug-title",
                text: merged.itemName || "의약품 상세 명세",
            }),
            merged.itemEngName
                ? el("p", { className: "modal-eng-title", text: merged.itemEngName })
                : null,
            el("p", {
                className: "modal-corp-meta",
                text: [merged.entpName || "제조사 미상", merged.className]
                    .filter(Boolean)
                    .join(" · "),
            }),
            el(
                "div",
                { className: "modal-hero-actions" },
                el("button", {
                    type: "button",
                    className: "btn-outline",
                    text: "+ 내 약통에 등록",
                    onClick: () => openPillboxModal(merged, "create"),
                })
            )
        )
    );

    const warnCombined = [merged.atpnWarnQesitm, merged.atpnQesitm]
        .filter((v) => v && String(v).trim())
        .join("\n\n");

    const easyPane = el(
        "div",
        {
            id: "mtab-easy",
            className: "m-tab-pane active",
            role: "tabpanel",
            "aria-labelledby": "mtab-btn-easy",
        },
        monographBlock(
            "효능 · 효과",
            merged.efcyQesitm,
            "식약처 복약 요약·허가상세 문서가 등록되어 있지 않거나 허가가 만료·취하된 품목입니다. 낱알 외형 규격 및 품목허가 탭을 함께 확인하세요."
        ),
        monographBlock(
            "용법 · 용량",
            merged.useMethodQesitm,
            "처방전 또는 약사 복약지도에 따라 정해진 용법·용량을 준수하세요."
        ),
        monographBlock(
            "복약 경고 및 주의사항",
            warnCombined,
            "별도로 기재된 경고 문구가 없습니다.",
            Boolean(warnCombined)
        ),
        merged.intrcQesitm
            ? monographBlock("병용 · 음식 상호작용 주의", merged.intrcQesitm, "-", true)
            : null,
        merged.seQesitm ? monographBlock("보고된 이상반응 (부작용)", merged.seQesitm, "-") : null,
        monographBlock(
            "보관 및 취급 방법",
            merged.depositMethodQesitm || merged.storageMethod,
            "직사광선을 피하고 서늘하고 건조한 곳에 어린이 손이 닿지 않게 보관하세요."
        )
    );

    const dimensions = [
        merged.lengLong ? `장축 ${merged.lengLong}mm` : "",
        merged.lengShort ? `단축 ${merged.lengShort}mm` : "",
        merged.thick ? `두께 ${merged.thick}mm` : "",
    ]
        .filter(Boolean)
        .join(" × ");

    const grainPane = el(
        "div",
        {
            id: "mtab-grain",
            className: "m-tab-pane",
            role: "tabpanel",
            "aria-labelledby": "mtab-btn-grain",
            hidden: true,
        },
        el(
            "dl",
            { className: "spec-ledger-grid" },
            specItem("의약품 기하 모양", merged.drugShape),
            specItem("제형 구분", merged.formCodeName),
            specItem(
                "표면 색상 (앞 / 뒤)",
                [merged.colorClass1, merged.colorClass2].filter(Boolean).join(" / ")
            ),
            specItem(
                "식별 각인 문자 (앞 / 뒤)",
                [merged.printFront, merged.printBack].filter(Boolean).join(" / ")
            ),
            specItem(
                "분할선 (앞 / 뒤)",
                [merged.lineFront, merged.lineBack].filter(Boolean).join(" / ")
            ),
            specItem("물리 규격 (mm)", dimensions)
        ),
        merged.chart ? monographBlock("외형 성상 설명", merged.chart, "-") : null
    );

    const prmsnPane = el(
        "div",
        {
            id: "mtab-prmsn",
            className: "m-tab-pane",
            role: "tabpanel",
            "aria-labelledby": "mtab-btn-prmsn",
            hidden: true,
        },
        el(
            "dl",
            { className: "spec-ledger-grid" },
            specItem("품목기준코드", merged.itemSeq),
            specItem("전문 · 일반 구분", merged.etcOtcName),
            specItem("주성분 수", merged.itemIngrCnt ? `${merged.itemIngrCnt}종` : "-"),
            specItem("품목허가일", merged.itemPermitDate),
            specItem("보험 EDI 코드", merged.ediCode),
            specItem(
                "유효기간 · 포장단위",
                [merged.validTerm, merged.packUnit].filter(Boolean).join(" / ") ||
                    [merged.induty, merged.bizrno].filter(Boolean).join(" / ")
            )
        ),
        monographBlock(
            "주성분 명세",
            merged.itemIngrName || merged.materialName,
            "주성분 상세 정보가 등록되어 있지 않습니다."
        )
    );

    const panes = [easyPane, grainPane, prmsnPane];
    const tabDefs = [
        { id: "mtab-btn-easy", target: "mtab-easy", label: "01 복약 안내" },
        { id: "mtab-btn-grain", target: "mtab-grain", label: "02 낱알 외형 규격" },
        { id: "mtab-btn-prmsn", target: "mtab-prmsn", label: "03 품목허가 · 성분" },
    ];

    let tabButtons = [];
    const activateTab = (nextIdx, moveFocus = false) => {
        tabButtons.forEach((btn, i) => {
            const isActive = i === nextIdx;
            btn.classList.toggle("active", isActive);
            btn.setAttribute("aria-selected", isActive ? "true" : "false");
            btn.setAttribute("tabindex", isActive ? "0" : "-1");
            if (isActive && moveFocus) {
                btn.focus();
            }
        });
        panes.forEach((pane, i) => {
            const isActive = i === nextIdx;
            pane.classList.toggle("active", isActive);
            pane.hidden = !isActive;
        });
    };

    tabButtons = tabDefs.map((def, idx) =>
        el("button", {
            id: def.id,
            type: "button",
            role: "tab",
            "aria-selected": idx === 0 ? "true" : "false",
            "aria-controls": def.target,
            tabindex: idx === 0 ? "0" : "-1",
            className: `m-tab-btn${idx === 0 ? " active" : ""}`,
            text: def.label,
            onClick: () => activateTab(idx, false),
            onKeydown: (e) => {
                let targetIdx = null;
                if (e.key === "ArrowRight") targetIdx = (idx + 1) % tabDefs.length;
                else if (e.key === "ArrowLeft") targetIdx = (idx - 1 + tabDefs.length) % tabDefs.length;
                else if (e.key === "Home") targetIdx = 0;
                else if (e.key === "End") targetIdx = tabDefs.length - 1;
                if (targetIdx !== null) {
                    e.preventDefault();
                    activateTab(targetIdx, true);
                }
            },
        })
    );

    const tabBar = el(
        "div",
        {
            className: "monograph-tabs",
            role: "tablist",
            "aria-label": "의약품 상세 정보 구분",
        },
        tabButtons
    );
    modalBody.replaceChildren(heroNode, tabBar, ...panes);
}

/**
 * [역할] 의약품 카드 클릭 시 네이티브 상세 모달을 열고 3대 API 실시간 병합 정보를 로드합니다.
 * [경로] .card-trigger 클릭 -> openDetailModal() -> GET /api/drug-detail/
 * [수정] 모달 초기 탭을 바꾸려면 renderDetailModalContent()의 active 인덱스를 변경하세요.
 */
async function openDetailModal(initialItem) {
    const dialog = document.getElementById("detailModal");
    const modalBody = document.getElementById("modalBody");
    if (!dialog || !modalBody) return;

    if (detailAbortController) detailAbortController.abort();
    detailAbortController = new AbortController();

    modalBody.replaceChildren(
        el("h2", {
            id: "modalDialogTitle",
            className: "modal-drug-title",
            text: initialItem.itemName || "의약품 상세 조회",
        }),
        el("p", {
            className: "state-banner",
            text: "식약처 공공데이터에서 복약안내·외형·허가 상세 명세를 병합하고 있습니다...",
        })
    );

    if (!dialog.open) {
        dialog.showModal();
    }

    const params = new URLSearchParams({
        itemSeq: initialItem.itemSeq || "",
        itemName: initialItem.itemName || "",
    });

    try {
        const enriched = await apiJson(`/api/drug-detail/?${params.toString()}`, {
            signal: detailAbortController.signal,
        });
        const merged = { ...initialItem };
        for (const [k, v] of Object.entries(enriched)) {
            if (v !== "" && v !== null && v !== undefined) {
                merged[k] = v;
            }
        }
        renderDetailModalContent(merged);
    } catch (err) {
        if (err.name === "AbortError") return;
        renderDetailModalContent(initialItem);
    }
}

/**
 * [역할] 내 약통 등록(Create) 또는 복용시간·메모 수정(Update) 전용 모달을 엽니다.
 * [경로] '+ 내 약통 등록' / '복용·메모 수정' 버튼 클릭 -> openPillboxModal()
 * [수정] 기본 복용 시간대 문구를 바꾸려면 dosageInput 기본값을 수정하세요.
 */
function openPillboxModal(item, mode = "create") {
    const dialog = document.getElementById("pillboxModal");
    if (!dialog) return;

    pillboxModalState = { mode, item };

    const modeLabel = document.getElementById("pillboxDialogModeLabel");
    const titleEl = document.getElementById("pillboxDialogTitle");
    const metaEl = document.getElementById("pillboxTargetMeta");
    const dosageInput = document.getElementById("pillboxDosageInput");
    const memoInput = document.getElementById("pillboxMemoInput");
    const submitBtn = document.getElementById("pillboxSubmitBtn");

    if (modeLabel) {
        modeLabel.textContent =
            mode === "edit" ? "내 약통 복용 시간 · 메모 수정" : "내 약통 신규 복약 기록 등록";
    }
    if (titleEl) titleEl.textContent = item.itemName || "의약품 복약 설정";
    if (metaEl) {
        metaEl.textContent =
            [
                item.entpName || "제조사 미상",
                item.etcOtcName || "",
                item.itemIngrName ? `주성분: ${item.itemIngrName}` : "",
            ]
                .filter(Boolean)
                .join(" · ");
    }
    if (dosageInput) {
        dosageInput.value = item.dosageTime || "아침·저녁 식후 30분";
    }
    if (memoInput) {
        memoInput.value = item.memo || "";
    }
    if (submitBtn) {
        submitBtn.textContent = mode === "edit" ? "수정 내용 저장" : "약통에 저장";
    }

    if (!dialog.open) {
        dialog.showModal();
    }
    dosageInput?.focus();
}

/**
 * [역할] 내 약통 폼 제출 시 POST(신규 등록) 또는 PATCH(복용시간·메모 수정) 요청을 처리합니다.
 * [경로] #pillboxForm submit -> handlePillboxSubmit() -> POST/PATCH /api/pillbox/
 * [수정] 추가 입력 필드를 저장하려면 payload 객체와 Backend/drugs/views.py를 함께 수정하세요.
 */
async function handlePillboxSubmit(e) {
    e.preventDefault();
    const { mode, item } = pillboxModalState;
    if (!item) return;

    const dosageInput = document.getElementById("pillboxDosageInput");
    const memoInput = document.getElementById("pillboxMemoInput");
    const submitBtn = document.getElementById("pillboxSubmitBtn");
    const dialog = document.getElementById("pillboxModal");

    const dosageTime = (dosageInput?.value || "").trim() || "아침·저녁 식후 30분";
    const memo = (memoInput?.value || "").trim();

    if (submitBtn) submitBtn.disabled = true;

    try {
        const isEdit = mode === "edit";
        const payload = isEdit
            ? {
                  id: item.id,
                  itemSeq: item.itemSeq || "",
                  dosageTime,
                  memo,
              }
            : {
                  ...item,
                  dosageTime,
                  memo,
              };

        const data = await apiJson("/api/pillbox/", {
            method: isEdit ? "PATCH" : "POST",
            body: JSON.stringify(payload),
        });

        updatePillboxBadges(data.pillboxCount ?? 0);
        dialog?.close("saved");
        showToast(data.message || (isEdit ? "복용 정보가 수정되었습니다." : "내 약통에 등록되었습니다."));

        const pillboxTabActive = document
            .getElementById("tab-pillbox")
            ?.classList.contains("active");
        if (pillboxTabActive) {
            await loadPillbox();
        }
    } catch (err) {
        showToast(err.message || "약통 저장 중 오류가 발생했습니다.");
    } finally {
        if (submitBtn) submitBtn.disabled = false;
    }
}

/**
 * [역할] 내 약통에서 선택한 의약품 레코드를 삭제(DELETE)합니다.
 * [경로] 내 약통 카드 '삭제' 버튼 -> removeFromPillbox() -> DELETE /api/pillbox/
 * [수정] 삭제 전 확인 창을 띄우려면 상단에 window.confirm 조건을 추가하세요.
 */
async function removeFromPillbox(item) {
    const params = new URLSearchParams();
    if (item.id !== undefined && item.id !== null) params.set("id", String(item.id));
    if (item.itemSeq) params.set("itemSeq", String(item.itemSeq));

    try {
        const data = await apiJson(`/api/pillbox/?${params.toString()}`, {
            method: "DELETE",
        });
        updatePillboxBadges(data.pillboxCount ?? 0);
        showToast("내 약통에서 삭제되었습니다.");
        await loadPillbox();
    } catch (err) {
        showToast(err.message || "삭제 처리 중 오류가 발생했습니다.");
    }
}

/**
 * [역할] 보관 약품 간 주성분 중복 위험 경고 및 핵심 복약 주의 요약을 렌더링합니다.
 * [경로] loadPillbox() -> renderSafetyReport() -> #safetyReportBox
 * [수정] 주의사항 요약 노출 개수를 바꾸려면 warnings.slice(0, 5) 숫자를 변경하세요.
 */
function renderSafetyReport(report) {
    const safetyBox = document.getElementById("safetyReportBox");
    if (!safetyBox) return;

    const totalSaved = Number(report?.totalSaved || 0);
    if (totalSaved === 0) {
        safetyBox.replaceChildren(
            el(
                "div",
                { className: "safety-card" },
                el("h2", { text: "내 약통이 비어 있습니다" }),
                el("p", {
                    text: "통합 약품 탐색(01) 또는 허가·성분 색인(02) 탭에서 복용 중인 약의 '+ 내 약통 등록' 버튼을 누르면 주성분 중복 여부와 주의사항을 자동으로 분석합니다.",
                })
            )
        );
        return;
    }

    const blocks = [];
    if (report.hasDuplicateRisk && Array.isArray(report.duplicateIngredients)) {
        const dupParagraphs = report.duplicateIngredients.map((dup) =>
            el("p", {
                text: `중복 주성분 [${dup.ingredient}] — 해당 약품: ${(dup.drugs || []).join(", ")}`,
            })
        );
        blocks.push(
            el(
                "div",
                { className: "safety-card warn" },
                el("h2", {
                    text: `주성분 중복 복용 주의 (${report.duplicateIngredients.length}건 감지)`,
                }),
                ...dupParagraphs,
                el("p", {
                    text: "동일 주성분이 포함된 의약품을 함께 복용하면 일일 최대 허용량을 초과할 수 있으므로 의사·약사와 상담하시기 바랍니다.",
                })
            )
        );
    } else {
        blocks.push(
            el(
                "div",
                { className: "safety-card safe" },
                el("h2", {
                    text: `주성분 중복 안전 점검 완료 (보관 약품 ${totalSaved}종)`,
                }),
                el("p", {
                    text: "현재 보관 중인 의약품 사이에 겹치는 주성분이 발견되지 않았습니다. 개별 약품의 복용 시간과 주의사항을 확인하세요.",
                })
            )
        );
    }

    const warnings = Array.isArray(report.warnings) ? report.warnings.slice(0, 5) : [];
    if (warnings.length > 0) {
        blocks.push(
            el(
                "div",
                { className: "caution-digest" },
                el("h3", { text: "보관 약품별 핵심 복약 주의 요약" }),
                el(
                    "ul",
                    { className: "caution-list" },
                    warnings.map((w) =>
                        el("li", { text: `[${w.itemName}] ${w.warnSummary}` })
                    )
                )
            )
        );
    }

    safetyBox.replaceChildren(...blocks);
}

/**
 * [역할] 내 약통 목록(GET /api/pillbox/)과 주성분 중복 안전 리포트를 불러와 화면에 그립니다.
 * [경로] switchTab('tab-pillbox') / CRUD 완료 후 -> loadPillbox()
 * [수정] 정렬 순서를 바꾸려면 Backend/drugs/models.py SavedDrug.Meta.ordering을 수정하세요.
 */
async function loadPillbox() {
    const listEl = document.getElementById("pillboxList");
    if (!listEl) return;

    try {
        const data = await apiJson("/api/pillbox/");
        const items = Array.isArray(data.items) ? data.items : [];
        updatePillboxBadges(items.length);
        renderSafetyReport(data.safetyReport || { totalSaved: items.length });
        listEl.replaceChildren(...items.map((item) => createDossierCard(item, true)));
    } catch (err) {
        const safetyBox = document.getElementById("safetyReportBox");
        safetyBox?.replaceChildren(
            el(
                "div",
                { className: "safety-card warn" },
                el("h2", { text: "내 약통 조회 오류" }),
                el("p", { text: err.message || "데이터를 불러오지 못했습니다." })
            )
        );
    }
}

/**
 * [역할] 구형 브라우저를 위한 <dialog closedby="any"> 바깥 배경 클릭 닫기 폴백 및 returnValue 초기화
 * [경로] DOMContentLoaded -> initDialogs() -> #detailModal, #pillboxModal 이벤트 등록
 * [수정] 바깥 클릭으로 닫히지 않게 하려면 index.html에서 closedby 속성을 "closerequest"로 변경하세요.
 */
function initDialogs() {
    const dialogs = document.querySelectorAll("dialog.clinical-dialog");
    dialogs.forEach((dialog) => {
        dialog.addEventListener("close", () => {
            dialog.returnValue = "";
        });
    });

    if (!("closedBy" in HTMLDialogElement.prototype)) {
        document.querySelectorAll('dialog[closedby="any"]').forEach((dialog) => {
            let pressedOutside = false;
            dialog.addEventListener("pointerdown", (e) => {
                if (e.target !== dialog) {
                    pressedOutside = false;
                    return;
                }
                const rect = dialog.getBoundingClientRect();
                pressedOutside =
                    e.clientX < rect.left ||
                    e.clientX > rect.right ||
                    e.clientY < rect.top ||
                    e.clientY > rect.bottom;
            });
            dialog.addEventListener("pointerup", (e) => {
                if (!pressedOutside || e.target !== dialog) return;
                const rect = dialog.getBoundingClientRect();
                const releasedOutside =
                    e.clientX < rect.left ||
                    e.clientX > rect.right ||
                    e.clientY < rect.top ||
                    e.clientY > rect.bottom;
                if (releasedOutside) {
                    dialog.close("dismiss");
                }
                pressedOutside = false;
            });
        });
    }
}

document.addEventListener("DOMContentLoaded", () => {
    initThemeSwitcher();
    initCheckGroups();
    initDialogs();
    syncPillboxStatus();

    document.getElementById("brandLogo")?.addEventListener("click", resetToHome);

    document.querySelectorAll(".nav-btn, .m-nav-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (btn.dataset.tab) switchTab(btn.dataset.tab);
        });
    });

    document.getElementById("toggleGrainFilterBtn")?.addEventListener("click", () => {
        const body = document.getElementById("grainFilterBody");
        const willExpand = Boolean(body?.classList.contains("collapsed"));
        setGrainPanelExpanded(willExpand);
    });

    document.getElementById("resetGrainFilterBtn")?.addEventListener("click", () => {
        resetGrainFilters();
    });

    document.getElementById("unifiedSearchForm")?.addEventListener("submit", (e) => {
        e.preventDefault();
        runUnifiedSearch();
    });

    document.getElementById("prmsnSearchForm")?.addEventListener("submit", (e) => {
        e.preventDefault();
        runPermissionSearch();
    });

    document.getElementById("pillboxForm")?.addEventListener("submit", handlePillboxSubmit);

    document.getElementById("pillboxCancelBtn")?.addEventListener("click", () => {
        document.getElementById("pillboxModal")?.close("cancel");
    });

    document.querySelectorAll(".preset-chip[data-preset]").forEach((chip) => {
        chip.addEventListener("click", () => {
            const dosageInput = document.getElementById("pillboxDosageInput");
            if (dosageInput && chip.dataset.preset) {
                dosageInput.value = chip.dataset.preset;
                dosageInput.focus();
            }
        });
    });
});
