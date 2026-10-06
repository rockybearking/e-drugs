// 식약처 의약품개요정보 API 엔드포인트
const TARGET_API = "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList";

// 전달해주신 정확한 Encoding 일반 인증키
const SERVICE_KEY = "s%2FvWNiKH1YndVRu2mPOq7OXAIj%2Byk0M3JTgvN%2B8UVdSFPq8SBR7zuUdG3mxklTrj6WYIiUidSIUwgE8bz09fzQ%3D%3D";

// DOM 요소 참조
const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const resultList = document.getElementById("resultList");
const statusMessage = document.getElementById("statusMessage");
const detailModal = document.getElementById("detailModal");
const modalBody = document.getElementById("modalBody");
const closeModalBtn = document.getElementById("closeModalBtn");

// 이벤트 리스너 등록
searchBtn.addEventListener("click", searchDrugs);
searchInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") searchDrugs();
});
closeModalBtn.addEventListener("click", () => {
    detailModal.classList.add("hidden");
});

// 검색 실행 함수
async function searchDrugs() {
    const keyword = searchInput.value.trim();
    if (!keyword) {
        alert("검색할 약 이름을 입력해 주세요.");
        return;
    }

    resultList.innerHTML = "";
    statusMessage.style.color = "#2563eb";
    statusMessage.textContent = `'${keyword}' 검색 중입니다...`;

    try {
        // 식약처 API 호출 (이미 인코딩된 SERVICE_KEY는 encodeURIComponent를 거치지 않고 직접 결합)
        const requestUrl = `${TARGET_API}?serviceKey=${SERVICE_KEY}&itemName=${encodeURIComponent(keyword)}&pageNo=1&numOfRows=20`;

        const response = await fetch(requestUrl);
        if (!response.ok) {
            throw new Error(`서버 응답 오류 (HTTP ${response.status})`);
        }

        const rawText = await response.text();
        let items = [];
        let totalCount = 0;

        // XML 및 JSON 응답 자동 판별
        if (rawText.trim().startsWith("<")) {
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(rawText, "text/xml");

            // 식약처 게이트웨이 인증/서비스 오류 처리
            const returnAuthMsg = xmlDoc.querySelector("returnAuthMsg")?.textContent;
            const returnReasonCode = xmlDoc.querySelector("returnReasonCode")?.textContent;
            const errMsg = xmlDoc.querySelector("errMsg")?.textContent;
            const resultCode = xmlDoc.querySelector("resultCode")?.textContent;
            const resultMsg = xmlDoc.querySelector("resultMsg")?.textContent;

            if (returnAuthMsg || returnReasonCode) {
                throw new Error(`인증 오류 [코드 ${returnReasonCode}]: ${returnAuthMsg || errMsg}`);
            }

            if (resultCode && resultCode !== "00") {
                throw new Error(`조회 실패 [코드 ${resultCode}]: ${resultMsg}`);
            }

            totalCount = xmlDoc.querySelector("totalCount")?.textContent || "0";
            const xmlItems = xmlDoc.querySelectorAll("item");

            xmlItems.forEach((node) => {
                items.push({
                    itemName: node.querySelector("itemName")?.textContent || "",
                    entpName: node.querySelector("entpName")?.textContent || "",
                    itemSeq: node.querySelector("itemSeq")?.textContent || "",
                    efcyQesitm: node.querySelector("efcyQesitm")?.textContent || "",
                    useMethodQesitm: node.querySelector("useMethodQesitm")?.textContent || "",
                    atpnWarnQesitm: node.querySelector("atpnWarnQesitm")?.textContent || "",
                    atpnQesitm: node.querySelector("atpnQesitm")?.textContent || "",
                    intrcQesitm: node.querySelector("intrcQesitm")?.textContent || "",
                    seQesitm: node.querySelector("seQesitm")?.textContent || "",
                    depositMethodQesitm: node.querySelector("depositMethodQesitm")?.textContent || "",
                    itemImage: node.querySelector("itemImage")?.textContent || "",
                });
            });
        } else {
            const json = JSON.parse(rawText);
            const body = json.body || json.response?.body;
            if (!body) throw new Error("응답 본문 구조가 올바르지 않습니다.");

            totalCount = body.totalCount || 0;
            const rawItems = body.items || [];
            items = Array.isArray(rawItems) ? rawItems : [rawItems];
        }

        if (items.length === 0) {
            statusMessage.style.color = "#64748b";
            statusMessage.textContent = `'${keyword}'에 대한 검색 결과가 없습니다.`;
            return;
        }

        statusMessage.style.color = "#16a34a";
        statusMessage.textContent = `총 ${totalCount}건 중 상위 ${items.length}건을 표시합니다.`;
        renderCards(items);

    } catch (error) {
        console.error("API 요청 실패 상세:", error);
        statusMessage.style.color = "#dc2626";
        statusMessage.innerHTML = `${error.message}`;
    }
}

// 태그 제거 함수
function stripTags(text) {
    if (!text) return "정보 없음";
    return text.replace(/<[^>]*>?/gm, "").trim();
}

// 검색 결과 카드 렌더링
function renderCards(items) {
    resultList.innerHTML = "";

    items.forEach((item) => {
        const card = document.createElement("div");
        card.className = "card";

        // 낱알 이미지 표시 (이미지가 없거나 깨졌을 경우 대체 표시)
        const hasImage = item.itemImage && item.itemImage.trim() !== "";
        const imageMarkup = hasImage
            ? `<img src="${item.itemImage}" alt="${item.itemName}" class="card-img" onerror="this.parentElement.innerHTML='<span class=\\'card-img-placeholder\\'>이미지 준비중</span>';">`
            : `<span class="card-img-placeholder">약 이미지 없음</span>`;

        card.innerHTML = `
      <div class="card-img-wrap">
        ${imageMarkup}
      </div>
      <div class="card-body">
        <span class="card-corp">${item.entpName || "제조사 미표기"}</span>
        <h3 class="card-title">${item.itemName}</h3>
        <p class="card-efcy">${stripTags(item.efcyQesitm)}</p>
      </div>
    `;

        card.addEventListener("click", () => openDetailModal(item));
        resultList.appendChild(card);
    });
}

// 상세 정보 모달 오픈
function openDetailModal(item) {
    const hasImage = item.itemImage && item.itemImage.trim() !== "";

    modalBody.innerHTML = `
    ${hasImage ? `<div class="modal-img-wrap"><img src="${item.itemImage}" alt="${item.itemName}" class="modal-img"></div>` : ""}
    <h2 class="modal-title">${item.itemName}</h2>
    <p class="modal-corp">업체명: ${item.entpName || "-"} | 품목기준코드: ${item.itemSeq || "-"}</p>
    
    <div class="detail-section">
      <h4>📌 효능 및 효과</h4>
      <p>${stripTags(item.efcyQesitm)}</p>
    </div>

    <div class="detail-section">
      <h4>📌 복용법 (용법·용량)</h4>
      <p>${stripTags(item.useMethodQesitm)}</p>
    </div>

    ${item.atpnWarnQesitm ? `
    <div class="detail-section">
      <h4>⚠️ 주의사항 경고</h4>
      <p style="color: #dc2626; font-weight: 500;">${stripTags(item.atpnWarnQesitm)}</p>
    </div>` : ""}

    <div class="detail-section">
      <h4>⚠️ 사용상 주의사항</h4>
      <p>${stripTags(item.atpnQesitm)}</p>
    </div>

    ${item.intrcQesitm ? `
    <div class="detail-section">
      <h4>💊 상호작용 (주의할 약·음식)</h4>
      <p>${stripTags(item.intrcQesitm)}</p>
    </div>` : ""}

    ${item.seQesitm ? `
    <div class="detail-section">
      <h4>🚨 이상반응 및 부작용</h4>
      <p>${stripTags(item.seQesitm)}</p>
    </div>` : ""}

    <div class="detail-section">
      <h4>📦 보관법</h4>
      <p>${stripTags(item.depositMethodQesitm)}</p>
    </div>
  `;

    detailModal.classList.remove("hidden");
}