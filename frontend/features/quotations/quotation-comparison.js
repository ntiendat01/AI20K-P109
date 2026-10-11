import { requestApi } from "../../core/api.js";
import { escapeHtml, formatComparisonMoney } from "../../utils/formatting.js";

const comparableStatuses = new Set(["auto_matched", "manual_matched"]);
const statusCopy = {
  auto_matched: "Tự động ghép",
  suggested: "Cần xác nhận",
  unmatched: "Chưa khớp",
  manual_matched: "Đã ghép",
  rejected: "Tách riêng",
};

export function quotationMatchItemId(quotationId, itemIndex) {
  return `${quotationId}:item:${itemIndex}`;
}

export function isQuotationReviewComplete(quotations) {
  return quotations.length > 0 && quotations.every((quotation) => quotation.status === "confirmed");
}

function matchStatus(match) {
  return String(match?.status || match?.best_match?.status || "unmatched").toLocaleLowerCase();
}

function isComparable(match) {
  return comparableStatuses.has(matchStatus(match));
}

function confidence(match) {
  const score = Number(match?.best_match?.score);
  return Number.isFinite(score) ? `${Math.round(score * 100)}%` : "";
}

function matchingResultsByItemId(matchResults) {
  return new Map((matchResults?.results || []).map((result) => [result.quote_item_id, result]));
}

function supplierColumns(quotations) {
  const nameCounts = quotations.reduce((counts, quotation) => {
    counts[quotation.supplier_name] = (counts[quotation.supplier_name] || 0) + 1;
    return counts;
  }, {});
  const indexes = {};
  return quotations.map((quotation) => {
    indexes[quotation.supplier_name] = (indexes[quotation.supplier_name] || 0) + 1;
    const suffix = nameCounts[quotation.supplier_name] > 1 ? ` ${indexes[quotation.supplier_name]}` : "";
    return { ...quotation, label: `${quotation.supplier_name}${suffix}` };
  });
}

function groupKey(match, itemId) {
  const status = matchStatus(match);
  const candidate = match?.best_match;
  if (["auto_matched", "suggested", "manual_matched"].includes(status) && candidate?.pr_item_id) {
    return `pr:${candidate.pr_item_id}`;
  }
  return `quote:${itemId}`;
}

export function FuzzyMatchActionCell(offer) {
  const { quotationId, itemId, item, match } = offer;
  const status = matchStatus(match);
  const candidate = match?.best_match;
  const sourceName = escapeHtml(item.product_name || "—");
  const score = confidence(match);
  const statusLabel = `${statusCopy[status] || status}${score ? ` · ${score}` : ""}`;
  const data = `data-fuzzy-match data-quote-id="${escapeHtml(quotationId)}" data-item-id="${escapeHtml(itemId)}"`;
  const source = `<small class="comparison-source-name">Tên báo giá: ${sourceName}</small>`;

  if (status === "suggested" && candidate) {
    return `<div class="fuzzy-match-cell suggested" ${data}><span class="fuzzy-match-status ${status}">${statusLabel}</span>${source}<div class="fuzzy-match-actions"><button class="secondary" type="button" data-fuzzy-action="CONFIRM" data-pr-item-id="${escapeHtml(candidate.pr_item_id)}">Gộp</button><button class="secondary" type="button" data-fuzzy-action="REJECT">Tách riêng</button></div></div>`;
  }

  if (status === "unmatched") {
    const options = [...new Map((match?.candidates || []).map((itemCandidate) => [itemCandidate.pr_item_id, itemCandidate])).values()]
      .map((itemCandidate) => `<option value="${escapeHtml(itemCandidate.pr_item_id)}">${escapeHtml(itemCandidate.pr_item_name)}${Number.isFinite(Number(itemCandidate.score)) ? ` · ${Math.round(Number(itemCandidate.score) * 100)}%` : ""}</option>`)
      .join("");
    return `<div class="fuzzy-match-cell unmatched" ${data}><span class="fuzzy-match-status ${status}">${statusLabel}</span>${source}${options ? `<div class="fuzzy-match-actions"><label class="visually-hidden">Chọn mặt hàng PR cho ${sourceName}</label><select data-manual-pr-item><option value="">Chọn mặt hàng PR…</option>${options}</select><button class="secondary" type="button" data-fuzzy-action="MAP_TO_NEW">Ghép</button></div>` : ""}</div>`;
  }

  return `<div class="fuzzy-match-cell ${escapeHtml(status)}" ${data}><span class="fuzzy-match-status ${escapeHtml(status)}">${escapeHtml(statusLabel)}</span>${source}</div>`;
}

function buildProducts(columns, matchResults) {
  const matches = matchingResultsByItemId(matchResults);
  const products = new Map();
  columns.forEach((quotation) => quotation.items.forEach((item, itemIndex) => {
    const itemId = quotationMatchItemId(quotation.id, itemIndex);
    const match = matches.get(itemId);
    const candidate = match?.best_match;
    const key = groupKey(match, itemId);
    if (!products.has(key)) {
      products.set(key, {
        name: candidate?.pr_item_name || item.product_name,
        unit: item.unit,
        quantity: item.quantity,
        offers: {},
        searchTerms: [candidate?.pr_item_name, item.product_name, item.product_code].filter(Boolean),
      });
    }
    const product = products.get(key);
    product.searchTerms.push(item.product_name, item.product_code);
    product.offers[quotation.id] = { quotationId: quotation.id, itemId, item, match };
  }));
  return products;
}

function matchingTotal(productRows, quotationId) {
  return productRows.reduce((total, product) => {
    const offer = product.offers[quotationId];
    return total + (offer && isComparable(offer.match) ? Number(offer.item.line_total) || 0 : 0);
  }, 0);
}

export function renderQuotationComparison(quotations, matchResults = null) {
  // A comparison is an auditable output of the review step. Do not expose
  // partial or OCR-only values while a buyer still has quotations to confirm.
  if (!isQuotationReviewComplete(quotations)) return "";
  const columns = supplierColumns(quotations);
  const products = buildProducts(columns, matchResults);
  if (!products.size) return "";
  const productRows = [...products.values()];

  const rows = productRows.map((product, index) => {
    const comparableOffers = Object.values(product.offers).filter((offer) => isComparable(offer.match));
    const prices = comparableOffers.map((offer) => Number(offer.item.unit_price)).filter(Number.isFinite);
    const lowest = prices.length ? Math.min(...prices) : null;
    const cells = columns.map((quotation) => {
      const offer = product.offers[quotation.id];
      if (!offer) return `<td data-quote-column="${quotation.id}">—</td><td data-quote-column="${quotation.id}">—</td>`;
      const best = lowest !== null && isComparable(offer.match) && Number(offer.item.unit_price) === lowest ? "best-price" : "";
      return `<td class="${best}" data-quote-column="${quotation.id}"><strong>${formatComparisonMoney(offer.item.unit_price)}</strong>${FuzzyMatchActionCell(offer)}</td><td class="${best}" data-quote-column="${quotation.id}">${formatComparisonMoney(offer.item.line_total)}</td>`;
    }).join("");
    const searchable = product.searchTerms.join(" ").toLocaleLowerCase();
    return `<tr data-comparison-row data-searchable="${escapeHtml(searchable)}"><td>${index + 1}</td><th scope="row">${escapeHtml(product.name || "—")}</th><td>${escapeHtml(product.unit || "—")}</td><td>${escapeHtml(product.quantity ?? "—")}</td>${cells}</tr>`;
  }).join("");
  const supplierHeadings = columns.map((quotation) => `<th colspan="2" scope="colgroup" data-quote-column="${quotation.id}">${escapeHtml(quotation.label)}<small class="comparison-status ${quotation.status}">${quotation.status === "confirmed" ? "Đã xác nhận" : "Chưa xác nhận"}</small></th>`).join("");
  const priceHeadings = columns.map((quotation) => `<th scope="col" data-quote-column="${quotation.id}">Đơn giá</th><th scope="col" data-quote-column="${quotation.id}">Tổng cộng</th>`).join("");
  const totals = columns.map((quotation) => `<td colspan="2" data-quote-column="${quotation.id}">${formatComparisonMoney(matchingTotal(productRows, quotation.id))}</td>`).join("");
  const chips = columns.map((quotation) => `<button class="supplier-chip" type="button" aria-pressed="true" data-supplier-toggle="${quotation.id}"><span aria-hidden="true">◉</span>${escapeHtml(quotation.label)}</button>`).join("");
  const commercialRows = columns.map((quotation) => `<tr><th scope="row">${escapeHtml(quotation.label)}</th><td>${escapeHtml(quotation.delivery_time || "—")}</td><td>${escapeHtml(quotation.payment_terms || "—")}</td><td>${escapeHtml(quotation.warranty || "—")}</td></tr>`).join("");

  return `<section class="comparison-panel" aria-labelledby="quote-comparison-title"><div class="comparison-heading"><div><p class="section-kicker">Đối chiếu fuzzy matching</p><h3 id="quote-comparison-title" tabindex="-1">Bảng so sánh báo giá</h3><p>Tên hàng theo mặt hàng PR do fuzzy matching chọn. Giá tốt nhất và tổng chỉ tính các dòng đã ghép.</p></div><span><b data-comparison-count>${products.size}</b> mặt hàng</span></div><p class="fuzzy-match-error error" data-fuzzy-match-error role="alert"></p><div class="comparison-toolbar"><label class="comparison-search"><span aria-hidden="true">⌕</span><input type="search" placeholder="Tìm theo tên mặt hàng PR hoặc tên báo giá…" data-comparison-search /></label><div class="supplier-chips" aria-label="Lọc nhà cung cấp">${chips}</div></div><div class="comparison-scroll"><table class="comparison-table"><thead><tr><th rowspan="2" scope="col">L/I</th><th rowspan="2" scope="col">Mặt hàng PR</th><th rowspan="2" scope="col">Đơn vị</th><th rowspan="2" scope="col">SL</th>${supplierHeadings}</tr><tr>${priceHeadings}</tr></thead><tbody>${rows}</tbody><tfoot><tr><th colspan="4" scope="row">TỔNG ĐÃ GHÉP</th>${totals}</tr></tfoot></table></div></section><section class="commercial-panel"><h3>Đánh giá thương mại</h3><div class="comparison-scroll"><table class="commercial-table"><thead><tr><th>Nhà cung cấp</th><th>Thời gian giao hàng</th><th>Điều khoản thanh toán</th><th>Bảo hành</th></tr></thead><tbody>${commercialRows}</tbody></table></div></section>`;
}

function applyMatchAction(matchResults, itemId, action, prItemId) {
  const match = matchingResultsByItemId(matchResults).get(itemId);
  if (!match) return;
  if (action === "REJECT") {
    match.status = "rejected";
    match.best_match = null;
    return;
  }
  const candidate = (match.candidates || []).find((itemCandidate) => itemCandidate.pr_item_id === prItemId) || match.best_match;
  if (!candidate) return;
  match.status = "manual_matched";
  match.best_match = { ...candidate, status: "manual_matched" };
}

export function bindQuotationComparison(content, options = {}) {
  const search = content.querySelector("[data-comparison-search]");
  const rows = [...content.querySelectorAll("[data-comparison-row]")];
  const count = content.querySelector("[data-comparison-count]");
  search?.addEventListener("input", () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const matches = !query || row.dataset.searchable.includes(query);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    if (count) count.textContent = visible;
  });
  content.querySelectorAll("[data-supplier-toggle]").forEach((button) => button.addEventListener("click", () => {
    const id = button.dataset.supplierToggle;
    const enabled = button.getAttribute("aria-pressed") !== "false";
    button.setAttribute("aria-pressed", String(!enabled));
    content.querySelectorAll("[data-quote-column]").forEach((cell) => {
      if (cell.dataset.quoteColumn === id) cell.hidden = enabled;
    });
  }));
  content.querySelectorAll("[data-fuzzy-action]").forEach((button) => button.addEventListener("click", async () => {
    const cell = button.closest("[data-fuzzy-match]");
    const action = button.dataset.fuzzyAction;
    const itemId = cell?.dataset.itemId;
    const quotationId = cell?.dataset.quoteId;
    const prItemId = action === "MAP_TO_NEW"
      ? cell?.querySelector("[data-manual-pr-item]")?.value
      : button.dataset.prItemId;
    const error = content.querySelector("[data-fuzzy-match-error]");
    if (!itemId || !quotationId || !action || (action !== "REJECT" && !prItemId)) {
      if (error) error.textContent = "Chọn mặt hàng PR trước khi ghép.";
      return;
    }
    if (!options.session || !options.matchResults) return;
    button.disabled = true;
    if (error) error.textContent = "";
    try {
      await requestApi(`/quotations/${encodeURIComponent(quotationId)}/items/${encodeURIComponent(itemId)}/confirm-match`, options.session, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pr_item_id: prItemId || null, action }),
      });
      applyMatchAction(options.matchResults, itemId, action, prItemId);
      options.onMatchUpdated?.();
    } catch (requestError) {
      if (error) error.textContent = requestError.message;
      button.disabled = false;
    }
  }));
}
