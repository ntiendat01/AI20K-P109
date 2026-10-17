import { useEffect, useRef, useState } from "react";
import { useAuth } from "../AuthProvider";
import { Icon } from "../Icon";

type SettingsTab = "extraction" | "matching" | "evaluation" | "approval" | "ai";

interface SynonymPair {
  id: string;
  source: string;
  target: string;
}

interface SystemSettingsState {
  // Extraction & OCR
  confidenceThreshold: number; // 60 - 90%, default 80
  highConfidenceThreshold: number; // default 95
  defaultCurrency: string; // VND, USD, EUR
  defaultVatRate: number; // 0, 8, 10
  autoHighlightBbox: boolean;
  autoScrollPdf: boolean;

  // Matching
  autoMatchThreshold: number; // default 90%
  suggestThreshold: number; // default 70%
  minNameScore: number; // default 55%
  synonyms: SynonymPair[];

  // Evaluation (Manager only)
  deviationThreshold: number; // default 15%
  minQuotationsRequired: number; // default 2
  weightTco: number; // default 50%
  weightLeadTime: number; // default 25%
  weightWarranty: number; // default 15%
  weightPayment: number; // default 10%

  // Approval (Manager only)
  budgetOverrunAlertPct: number; // default 10%
  poCodePrefix: string; // default PO-{YYYYMMDD}-{SEQ}
  approvalSlaHours: number; // default 24h
  requireRejectionReason: boolean;
  minRejectionChars: number; // default 20

  // AI Engine (Manager only)
  llmModel: string; // "gpt-6-luna", "qwen2.5:7b", "gemini-3.5-flash"
  reasoningEffort: string; // "none", "low", "medium", "high"
  decisionPromptDirective: string;
}

const DEFAULT_SETTINGS: SystemSettingsState = {
  confidenceThreshold: 80,
  highConfidenceThreshold: 95,
  defaultCurrency: "VND",
  defaultVatRate: 10,
  autoHighlightBbox: true,
  autoScrollPdf: true,

  autoMatchThreshold: 90,
  suggestThreshold: 70,
  minNameScore: 55,
  synonyms: [
    { id: "1", source: "laptop", target: "máy tính xách tay" },
    { id: "2", source: "chuột quang", target: "chuột máy tính" },
    { id: "3", source: "cái", target: "chiếc" },
  ],

  deviationThreshold: 15,
  minQuotationsRequired: 2,
  weightTco: 50,
  weightLeadTime: 25,
  weightWarranty: 15,
  weightPayment: 10,

  budgetOverrunAlertPct: 10,
  poCodePrefix: "PO-{YYYYMMDD}-{SEQ}",
  approvalSlaHours: 24,
  requireRejectionReason: true,
  minRejectionChars: 20,

  llmModel: "gpt-6-luna",
  reasoningEffort: "none",
  decisionPromptDirective: "Ưu tiên giải pháp tối ưu TCO và nhà cung cấp cam kết thời gian bảo hành chính hãng từ 24 tháng trở lên.",
};

const STORAGE_KEY = "dotcom_system_settings_v1";

import { apiRequest } from "../api";

function backendToFrontend(b: any): SystemSettingsState {
  return {
    confidenceThreshold: Math.round((b.confidence_threshold ?? 0.8) * 100),
    highConfidenceThreshold: Math.round((b.high_confidence_threshold ?? 0.95) * 100),
    defaultCurrency: b.default_currency || "VND",
    defaultVatRate: Math.round((b.default_vat_rate ?? 0.1) * 100),
    autoHighlightBbox: b.auto_highlight_bbox ?? true,
    autoScrollPdf: b.auto_scroll_pdf ?? true,

    autoMatchThreshold: Math.round((b.auto_match_threshold ?? 0.9) * 100),
    suggestThreshold: Math.round((b.suggest_threshold ?? 0.7) * 100),
    minNameScore: Math.round((b.min_name_score ?? 0.55) * 100),
    synonyms: b.synonyms || [],

    deviationThreshold: Math.round((b.deviation_threshold ?? 0.15) * 100),
    minQuotationsRequired: b.min_quotations_required ?? 2,
    weightTco: b.weight_tco ?? 50,
    weightLeadTime: b.weight_lead_time ?? 25,
    weightWarranty: b.weight_warranty ?? 15,
    weightPayment: b.weight_payment ?? 10,

    budgetOverrunAlertPct: b.budget_overrun_alert_pct ?? 10,
    poCodePrefix: b.po_code_prefix || "PO-{YYYYMMDD}-{SEQ}",
    approvalSlaHours: b.approval_sla_hours ?? 24,
    requireRejectionReason: b.require_rejection_reason ?? true,
    minRejectionChars: b.min_rejection_chars ?? 20,

    llmModel: b.llm_model || "gpt-6-luna",
    reasoningEffort: b.reasoning_effort || "none",
    decisionPromptDirective: b.decision_prompt_directive || "",
  };
}

function frontendToBackend(f: SystemSettingsState): any {
  return {
    confidence_threshold: f.confidenceThreshold / 100,
    high_confidence_threshold: f.highConfidenceThreshold / 100,
    default_currency: f.defaultCurrency,
    default_vat_rate: f.defaultVatRate / 100,
    auto_highlight_bbox: f.autoHighlightBbox,
    auto_scroll_pdf: f.autoScrollPdf,

    auto_match_threshold: f.autoMatchThreshold / 100,
    suggest_threshold: f.suggestThreshold / 100,
    min_name_score: f.minNameScore / 100,
    synonyms: f.synonyms,

    deviation_threshold: f.deviationThreshold / 100,
    min_quotations_required: f.minQuotationsRequired,
    weight_tco: f.weightTco,
    weight_lead_time: f.weightLeadTime,
    weight_warranty: f.weightWarranty,
    weight_payment: f.weightPayment,

    budget_overrun_alert_pct: f.budgetOverrunAlertPct,
    po_code_prefix: f.poCodePrefix,
    approval_sla_hours: f.approvalSlaHours,
    require_rejection_reason: f.requireRejectionReason,
    min_rejection_chars: f.minRejectionChars,

    llm_model: f.llmModel,
    reasoning_effort: f.reasoningEffort,
    decision_prompt_directive: f.decisionPromptDirective,
  };
}

interface BoundedNumberFieldProps {
  id: string;
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}

function BoundedNumberField({ id, label, hint, value, min, max, step, disabled = false, onChange }: BoundedNumberFieldProps) {
  const [draftValue, setDraftValue] = useState(String(value));

  useEffect(() => setDraftValue(String(value)), [value]);

  const normalizeValue = (nextValue: number) => {
    const boundedValue = Math.min(max, Math.max(min, nextValue));
    return Math.min(max, Math.max(min, min + Math.round((boundedValue - min) / step) * step));
  };

  const updateValue = (nextValue: number) => {
    const normalizedValue = normalizeValue(nextValue);
    setDraftValue(String(normalizedValue));
    onChange(normalizedValue);
  };

  return (
    <div className="setting-item">
      <label htmlFor={id}>
        <strong>{label}</strong>
        <span className="setting-hint">{hint}</span>
      </label>
      <div className="bounded-number-control">
        <input
          id={id}
          type="number"
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          value={draftValue}
          onChange={(event) => {
            const nextDraftValue = event.target.value;
            setDraftValue(nextDraftValue);
            if (nextDraftValue === "") return;
            const parsedValue = Number(nextDraftValue);
            if (Number.isFinite(parsedValue) && parsedValue >= min && parsedValue <= max) onChange(parsedValue);
          }}
          onBlur={() => {
            if (draftValue === "") {
              setDraftValue(String(value));
              return;
            }
            const parsedValue = Number(draftValue);
            if (Number.isFinite(parsedValue)) updateValue(parsedValue);
            else setDraftValue(String(value));
          }}
        />
        <span className="bounded-number-suffix">%</span>
        <div className="bounded-number-stepper" aria-label={`Điều chỉnh ${label}`}>
          <button type="button" disabled={disabled} aria-label={`Tăng ${label}`} onClick={() => updateValue(value + step)}>+</button>
          <button type="button" disabled={disabled} aria-label={`Giảm ${label}`} onClick={() => updateValue(value - step)}>−</button>
        </div>
      </div>
    </div>
  );
}

export function SettingsPage() {
  const { session } = useAuth();
  const currentRole = session?.user.role || "procurement";
  const isManager = currentRole === "manager";

  const [activeTab, setActiveTab] = useState<SettingsTab>("extraction");
  const tabsRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const checkScroll = () => {
    if (!tabsRef.current) return;
    const { scrollLeft, scrollWidth, clientWidth } = tabsRef.current;
    setCanScrollLeft(scrollLeft > 4);
    setCanScrollRight(scrollLeft + clientWidth < scrollWidth - 4);
  };

  useEffect(() => {
    checkScroll();
    const timer = setTimeout(checkScroll, 100);
    const onResize = () => checkScroll();
    window.addEventListener("resize", onResize);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  const handleScrollTabs = (direction: "left" | "right") => {
    if (!tabsRef.current) return;
    const offset = direction === "left" ? -240 : 240;
    tabsRef.current.scrollBy({ left: offset, behavior: "smooth" });
    setTimeout(checkScroll, 300);
  };

  const [settings, setSettings] = useState<SystemSettingsState>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  });

  const [saveToast, setSaveToast] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newSynonym, setNewSynonym] = useState({ source: "", target: "" });
  const weightTotal = settings.weightTco + settings.weightLeadTime + settings.weightWarranty + settings.weightPayment;
  const matchingThresholdsValid = settings.suggestThreshold < settings.autoMatchThreshold;

  // Fetch settings from server on mount
  useEffect(() => {
    if (!session) return;
    apiRequest<any>("/settings", session)
      .then((data) => {
        if (data) {
          const loaded = backendToFrontend(data);
          setSettings(loaded);
          localStorage.setItem(STORAGE_KEY, JSON.stringify(loaded));
        }
      })
      .catch(() => {
        // Fallback to local storage if API is not yet reachable
      });
  }, [session]);

  const handleSave = async () => {
    if (!matchingThresholdsValid || (isManager && weightTotal !== 100)) {
      setActiveTab(matchingThresholdsValid ? "evaluation" : "matching");
      return;
    }
    setSaving(true);
    try {
      if (session) {
        const payload = frontendToBackend(settings);
        const savedData = await apiRequest<any>("/settings", session, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (savedData) {
          setSettings(backendToFrontend(savedData));
        }
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
      setSaveToast(true);
      setTimeout(() => setSaveToast(false), 4000);
    } catch (e: any) {
      alert("Lỗi khi lưu cấu hình: " + (e?.message || "Không xác định"));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (window.confirm("Bạn có chắc chắn muốn khôi phục tất cả thông số về mặc định?")) {
      setSettings(DEFAULT_SETTINGS);
      localStorage.removeItem(STORAGE_KEY);
      if (session) {
        try {
          await apiRequest<any>("/settings", session, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(frontendToBackend(DEFAULT_SETTINGS)),
          });
        } catch {
          // ignore error on reset
        }
      }
      setSaveToast(true);
      setTimeout(() => setSaveToast(false), 3000);
    }
  };

  const addSynonym = () => {
    if (!newSynonym.source.trim() || !newSynonym.target.trim()) return;
    setSettings((prev) => ({
      ...prev,
      synonyms: [
        ...prev.synonyms,
        { id: Date.now().toString(), source: newSynonym.source.trim(), target: newSynonym.target.trim() },
      ],
    }));
    setNewSynonym({ source: "", target: "" });
  };

  const removeSynonym = (id: string) => {
    setSettings((prev) => ({
      ...prev,
      synonyms: prev.synonyms.filter((item) => item.id !== id),
    }));
  };

  return (
    <div className="settings-container">
      {saveToast && (
        <div className="settings-toast-banner">
          <Icon name="check" />
          <span><strong>Đã lưu thay đổi thành công!</strong> Các thông số mới sẽ được áp dụng trong lượt xử lý và phân tích tiếp theo.</span>
        </div>
      )}

      {/* Main Settings Tabs with Arrow Navigation & Hidden Scrollbar */}
      <div className="settings-tabs-wrapper">
        {canScrollLeft && (
          <button
            type="button"
            className="settings-tabs-arrow-btn left"
            onClick={() => handleScrollTabs("left")}
            aria-label="Cuộn sang trái"
            title="Cuộn sang trái"
          >
            <Icon name="chevron-left" />
          </button>
        )}
        <div className="settings-tabs-bar" ref={tabsRef} onScroll={checkScroll}>
          <button
            type="button"
            className={`settings-tab-btn ${activeTab === "extraction" ? "active" : ""}`}
            onClick={() => setActiveTab("extraction")}
          >
            <Icon name="file-text" /> Bóc tách OCR & Dữ liệu
          </button>
          <button
            type="button"
            className={`settings-tab-btn ${activeTab === "matching" ? "active" : ""}`}
            onClick={() => setActiveTab("matching")}
          >
            <Icon name="sliders" /> Khớp sản phẩm & Từ điển
          </button>
          <button
            type="button"
            className={`settings-tab-btn ${activeTab === "evaluation" ? "active" : ""}`}
            onClick={() => setActiveTab("evaluation")}
          >
            <Icon name="trending-up" /> Tiêu chuẩn so sánh {!isManager && <Icon name="lock" className="tab-lock" />}
          </button>
          <button
            type="button"
            className={`settings-tab-btn ${activeTab === "approval" ? "active" : ""}`}
            onClick={() => setActiveTab("approval")}
          >
            <Icon name="shield" /> Ngân sách & Phê duyệt {!isManager && <Icon name="lock" className="tab-lock" />}
          </button>
          <button
            type="button"
            className={`settings-tab-btn ${activeTab === "ai" ? "active" : ""}`}
            onClick={() => setActiveTab("ai")}
          >
            <Icon name="cpu" /> Mô hình AI & Prompt {!isManager && <Icon name="lock" className="tab-lock" />}
          </button>
        </div>
        {canScrollRight && (
          <button
            type="button"
            className="settings-tabs-arrow-btn right"
            onClick={() => handleScrollTabs("right")}
            aria-label="Cuộn sang phải"
            title="Cuộn sang phải"
          >
            <Icon name="chevron-right" />
          </button>
        )}
      </div>

      {/* Tab 1: OCR & Data Extraction */}
      {activeTab === "extraction" && (
        <>
        <div className="settings-section-card">
          <div className="section-title-row">
            <div>
              <h3>Cấu hình bóc tách tài liệu & OCR</h3>
              <p>Tùy chỉnh ngưỡng tin cậy và dữ liệu mặc định khi bóc tách báo giá nhà cung cấp.</p>
            </div>
            <span className="permission-badge editable">Cả 2 vai trò có thể chỉnh</span>
          </div>

          <div className="settings-grid threshold-settings-grid">
            <BoundedNumberField
              id="confidence-threshold"
              label="Ngưỡng tin cậy cảnh báo OCR"
              hint="Dưới ngưỡng này, dữ liệu cần được xác nhận thủ công."
              value={settings.confidenceThreshold}
              min={isManager ? 50 : 60}
              max={isManager ? 95 : 90}
              step={5}
              onChange={(confidenceThreshold) => setSettings({ ...settings, confidenceThreshold })}
            />
            <BoundedNumberField
              id="high-confidence-threshold"
              label="Ngưỡng độ tin cậy cao"
              hint="Từ ngưỡng này trở lên, dữ liệu được đánh dấu tin cậy cao."
              value={settings.highConfidenceThreshold}
              min={85}
              max={99}
              step={1}
              onChange={(highConfidenceThreshold) => setSettings({ ...settings, highConfidenceThreshold })}
            />
          </div>

          <div className="confidence-preview" aria-live="polite">
            <h4>Ví dụ trạng thái theo ngưỡng</h4>
            <div className="confidence-preview-grid">
              <div className="confidence-preview-item warning">
                <span className="confidence-preview-mark" aria-hidden="true">!</span>
                <div><strong>Cần kiểm tra</strong><span>Độ tin cậy: {Math.max(0, settings.confidenceThreshold - 2)}% (dưới {settings.confidenceThreshold}%)</span></div>
              </div>
              <div className="confidence-preview-item success">
                <span className="confidence-preview-mark" aria-hidden="true">✓</span>
                <div><strong>Tin cậy cao</strong><span>Độ tin cậy: {Math.min(100, settings.highConfidenceThreshold + 1)}% (từ {settings.highConfidenceThreshold}% trở lên)</span></div>
              </div>
            </div>
          </div>

          <div className="settings-grid extraction-defaults-grid">
            <div className="setting-item">
              <label htmlFor="default-currency">
                <strong>Đơn vị tiền tệ ngầm định</strong>
                <span className="setting-hint">Áp dụng khi tài liệu báo giá không ghi rõ loại tiền</span>
              </label>
              <select
                id="default-currency"
                value={settings.defaultCurrency}
                onChange={(e) => setSettings({ ...settings, defaultCurrency: e.target.value })}
              >
                <option value="VND">VND (Việt Nam Đồng)</option>
                <option value="USD">USD (Đô la Mỹ)</option>
                <option value="EUR">EUR (Euro)</option>
              </select>
            </div>

            <div className="setting-item">
              <label htmlFor="default-vat">
                <strong>Thuế suất VAT ngầm định (%)</strong>
                <span className="setting-hint">Tự động áp dụng khi báo giá chưa bóc tách được dòng thuế VAT</span>
              </label>
              <select
                id="default-vat"
                value={settings.defaultVatRate}
                onChange={(e) => setSettings({ ...settings, defaultVatRate: Number(e.target.value) })}
              >
                <option value={0}>0% (Không chịu thuế / Miễn thuế)</option>
                <option value={8}>8% (Nghị định giảm thuế)</option>
                <option value={10}>10% (Thuế suất chuẩn)</option>
              </select>
            </div>
          </div>
        </div>

        <div className="settings-section-card pdf-settings-card">
          <div className="section-title-row">
            <div>
              <h3>Tương tác với tài liệu PDF</h3>
              <p>Thiết lập cách hệ thống hiển thị và di chuyển đến dữ liệu trên tài liệu gốc.</p>
            </div>
          </div>
          <div className="pdf-settings-grid">
            <label className="pdf-setting-row">
              <span className="pdf-setting-copy">
                <strong>Tự động làm nổi bật vị trí dữ liệu</strong>
                <span>Hiển thị vùng dữ liệu đã bóc tách trên tài liệu PDF.</span>
              </span>
              <input
                className="pdf-setting-checkbox"
                type="checkbox"
                checked={settings.autoHighlightBbox}
                onChange={(event) => setSettings({ ...settings, autoHighlightBbox: event.target.checked })}
                aria-label="Tự động làm nổi bật vị trí dữ liệu"
              />
              <span className="pdf-setting-switch" aria-hidden="true" />
            </label>
            <label className="pdf-setting-row">
              <span className="pdf-setting-copy">
                <strong>Tự cuộn đến trường đang chọn</strong>
                <span>Tự động cuộn đến vị trí dữ liệu đang được chọn trong tài liệu.</span>
              </span>
              <input
                className="pdf-setting-checkbox"
                type="checkbox"
                checked={settings.autoScrollPdf}
                onChange={(event) => setSettings({ ...settings, autoScrollPdf: event.target.checked })}
                aria-label="Tự cuộn đến trường đang chọn"
              />
              <span className="pdf-setting-switch" aria-hidden="true" />
            </label>
          </div>
        </div>
        </>
      )}

      {/* Tab 2: Product Matching & Synonyms */}
      {activeTab === "matching" && (
        <div className="settings-section-card">
          <div className="section-title-row">
            <div>
              <h3>Cấu hình thuật toán khớp sản phẩm (Fuzzy Matching)</h3>
              <p>Điều chỉnh độ nhạy khi ghép nối tên sản phẩm trên Báo giá với danh mục trong Yêu cầu mua sắm (PR)</p>
            </div>
            <span className="permission-badge editable">Cả 2 vai trò có thể chỉnh</span>
          </div>

          <div className="settings-grid matching-threshold-grid">
            <BoundedNumberField
              id="auto-match-threshold"
              label="Ngưỡng tự động ghép đôi"
              hint="Từ mức này, hệ thống tự ghép cặp sản phẩm."
              value={settings.autoMatchThreshold}
              min={80}
              max={98}
              step={2}
              onChange={(autoMatchThreshold) => setSettings({ ...settings, autoMatchThreshold })}
            />
            <BoundedNumberField
              id="suggest-threshold"
              label="Ngưỡng gợi ý ứng viên"
              hint="Từ mức này đến dưới ngưỡng tự động, hệ thống sẽ gợi ý cặp sản phẩm."
              value={settings.suggestThreshold}
              min={50}
              max={85}
              step={5}
              onChange={(suggestThreshold) => setSettings({ ...settings, suggestThreshold })}
            />
          </div>

          <div className="matching-preview" aria-live="polite">
            <h4>Hành động theo điểm tương đồng</h4>
            <div className="matching-bands">
              <div className="matching-band automatic"><strong>Tự động ghép</strong><span>Từ {settings.autoMatchThreshold}% trở lên</span></div>
              <div className="matching-band suggested"><strong>Đưa vào danh sách gợi ý</strong><span>Từ {settings.suggestThreshold}% đến dưới {settings.autoMatchThreshold}%</span></div>
              <div className="matching-band manual"><strong>Kiểm tra thủ công</strong><span>Dưới {settings.suggestThreshold}%</span></div>
            </div>
            {!matchingThresholdsValid && (
              <p className="settings-validation-message" role="alert">Ngưỡng gợi ý phải thấp hơn ngưỡng tự động ghép để các mức điểm không chồng lấn.</p>
            )}
          </div>

          {/* Synonym Dictionary Management */}
          <div className="synonyms-management">
            <h4>Từ điển từ đồng nghĩa & Viết tắt ngành hàng</h4>
            <p className="setting-hint">Hệ thống sẽ chuẩn hóa các từ này trước khi tính điểm tương đồng, giúp tỷ lệ khớp tăng đáng kể.</p>

            <div className="synonym-add-row">
              <input
                type="text"
                placeholder="Từ trên báo giá (VD: laptop, đĩa cứng)"
                value={newSynonym.source}
                onChange={(e) => setNewSynonym({ ...newSynonym, source: e.target.value })}
              />
              <span className="synonym-arrow">➔</span>
              <input
                type="text"
                placeholder="Chuẩn hóa theo PR (VD: máy tính xách tay, ổ cứng)"
                value={newSynonym.target}
                onChange={(e) => setNewSynonym({ ...newSynonym, target: e.target.value })}
              />
              <button type="button" className="inline-primary" onClick={addSynonym}>
                <Icon name="plus" className="button-icon" /> Thêm từ
              </button>
            </div>

            <table className="synonyms-table">
              <thead>
                <tr>
                  <th>Từ trên Báo giá</th>
                  <th>Từ chuẩn hóa (PR)</th>
                  <th style={{ width: "80px", textAlign: "center" }}>Xóa</th>
                </tr>
              </thead>
              <tbody>
                {settings.synonyms.map((pair) => (
                  <tr key={pair.id}>
                    <td><code>{pair.source}</code></td>
                    <td><code>{pair.target}</code></td>
                    <td style={{ textAlign: "center" }}>
                      <button
                        type="button"
                        className="table-action remove"
                        onClick={() => removeSynonym(pair.id)}
                        title="Xóa cặp từ"
                      >
                        <Icon name="close" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Evaluation Criteria */}
      {activeTab === "evaluation" && (
        <div className="settings-section-card">
          <div className="section-title-row">
            <div>
              <h3>Tiêu chuẩn đánh giá & Ma trận so sánh nhà cung cấp</h3>
              <p>Quy định các tiêu chuẩn kỹ thuật để AI Agent xếp hạng và chọn phương án tối ưu (Bước 4 & 5)</p>
            </div>
            <span className={`permission-badge ${isManager ? "editable" : "locked"}`}>
              {isManager ? "Quản lý có quyền chỉnh sửa" : "🔒 Chỉ đọc (Chỉ Quản lý được sửa)"}
            </span>
          </div>

          {!isManager && (
            <div className="settings-lock-notice">
              <Icon name="lock" />
              <span>Các thông số này ảnh hưởng trực tiếp đến kết quả xếp hạng và quyết định chọn thầu. Chỉ tài khoản cấp Quản lý mới có quyền điều chỉnh.</span>
            </div>
          )}

          <div className="settings-grid">
            <BoundedNumberField
              id="deviation-threshold"
              label="Ngưỡng cảnh báo sai lệch giá thị trường"
              hint="Cảnh báo khi đơn giá lệch quá mức này so với giá trung bình."
              value={settings.deviationThreshold}
              min={5}
              max={30}
              step={1}
              disabled={!isManager}
              onChange={(deviationThreshold) => setSettings({ ...settings, deviationThreshold })}
            />

            <div className="setting-item">
              <label htmlFor="min-quotes">
                <strong>Số lượng báo giá tối thiểu bắt buộc</strong>
                <span className="setting-hint">Hệ thống sẽ chặn chuyển sang Bước 4 nếu chưa đủ số lượng báo giá hợp lệ</span>
              </label>
              <select
                id="min-quotes"
                disabled={!isManager}
                value={settings.minQuotationsRequired}
                onChange={(e) => setSettings({ ...settings, minQuotationsRequired: Number(e.target.value) })}
              >
                <option value={2}>Tối thiểu 02 báo giá (Đơn hàng thông thường)</option>
                <option value={3}>Tối thiểu 03 báo giá (Chuẩn chào hàng cạnh tranh)</option>
                <option value={4}>Tối thiểu 04 báo giá (Gói thầu lớn)</option>
              </select>
            </div>
          </div>

          <div className="weights-distribution-card">
            <div className="weights-heading-row">
              <div>
                <h4>Phân bổ trọng số chấm điểm nhà cung cấp</h4>
                <p>Điều chỉnh mức ảnh hưởng của từng tiêu chí. Tổng trọng số cần bằng 100%.</p>
              </div>
              <div className={`weights-total ${weightTotal === 100 ? "valid" : "invalid"}`} role="status" aria-live="polite">
                <span>Tổng trọng số</span>
                <strong>{weightTotal}%</strong>
                <span>{weightTotal === 100 ? "Đã cân bằng" : "Cần bằng 100% để lưu"}</span>
              </div>
            </div>
            <div className="weights-bar">
              <div style={{ width: `${settings.weightTco}%`, background: "#147dab" }} title={`TCO: ${settings.weightTco}%`}>
                TCO ({settings.weightTco}%)
              </div>
              <div style={{ width: `${settings.weightLeadTime}%`, background: "#16836a" }} title={`Tiến độ: ${settings.weightLeadTime}%`}>
                Giao hàng ({settings.weightLeadTime}%)
              </div>
              <div style={{ width: `${settings.weightWarranty}%`, background: "#f59e0b" }} title={`Bảo hành: ${settings.weightWarranty}%`}>
                Bảo hành ({settings.weightWarranty}%)
              </div>
              <div style={{ width: `${settings.weightPayment}%`, background: "#7558d9" }} title={`Công nợ: ${settings.weightPayment}%`}>
                Công nợ ({settings.weightPayment}%)
              </div>
            </div>

            <div className="weights-inputs-grid">
              <BoundedNumberField
                id="weight-tco"
                label="Tổng chi phí TCO"
                hint="Khoảng cho phép: 20–70%."
                value={settings.weightTco}
                min={20}
                max={70}
                step={5}
                disabled={!isManager}
                onChange={(weightTco) => setSettings({ ...settings, weightTco })}
              />
              <BoundedNumberField
                id="weight-lead-time"
                label="Tiến độ giao hàng"
                hint="Khoảng cho phép: 10–40%."
                value={settings.weightLeadTime}
                min={10}
                max={40}
                step={5}
                disabled={!isManager}
                onChange={(weightLeadTime) => setSettings({ ...settings, weightLeadTime })}
              />
              <BoundedNumberField
                id="weight-warranty"
                label="Thời gian bảo hành"
                hint="Khoảng cho phép: 5–30%."
                value={settings.weightWarranty}
                min={5}
                max={30}
                step={5}
                disabled={!isManager}
                onChange={(weightWarranty) => setSettings({ ...settings, weightWarranty })}
              />
              <BoundedNumberField
                id="weight-payment"
                label="Điều khoản công nợ"
                hint="Khoảng cho phép: 5–25%."
                value={settings.weightPayment}
                min={5}
                max={25}
                step={5}
                disabled={!isManager}
                onChange={(weightPayment) => setSettings({ ...settings, weightPayment })}
              />
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Approval & Budget Policies */}
      {activeTab === "approval" && (
        <div className="settings-section-card">
          <div className="section-title-row">
            <div>
              <h3>Chính sách phê duyệt & Kiểm soát ngân sách</h3>
              <p>Thiết lập quy tắc tài chính, cảnh báo vượt dự toán và quy trình sinh Đơn mua hàng (PO)</p>
            </div>
            <span className={`permission-badge ${isManager ? "editable" : "locked"}`}>
              {isManager ? "Quản lý có quyền chỉnh sửa" : "🔒 Chỉ đọc (Chỉ Quản lý được sửa)"}
            </span>
          </div>

          {!isManager && (
            <div className="settings-lock-notice">
              <Icon name="lock" />
              <span>Chính sách kiểm soát ngân sách và quy tắc duyệt chỉ dành cho Cấp Quản lý. Nhân viên xem ở chế độ chỉ đọc để nắm quy định.</span>
            </div>
          )}

          <div className="settings-grid">
            <BoundedNumberField
              id="budget-overrun-threshold"
              label="Ngưỡng vượt ngân sách PR cần giải trình"
              hint="Khi phương án vượt dự toán quá mức này, hồ sơ sẽ cần giải trình đặc biệt."
              value={settings.budgetOverrunAlertPct}
              min={0}
              max={25}
              step={1}
              disabled={!isManager}
              onChange={(budgetOverrunAlertPct) => setSettings({ ...settings, budgetOverrunAlertPct })}
            />

            <div className="setting-item">
              <label htmlFor="po-prefix">
                <strong>Định dạng sinh mã Đơn đặt hàng (PO) tự động</strong>
                <span className="setting-hint">Mã PO tự động tạo sau khi Quản lý bấm Phê duyệt</span>
              </label>
              <input
                id="po-prefix"
                type="text"
                disabled={!isManager}
                value={settings.poCodePrefix}
                onChange={(e) => setSettings({ ...settings, poCodePrefix: e.target.value })}
              />
              <span className="slider-range-hint">Biến hỗ trợ: {"{YYYY}"}, {"{MM}"}, {"{DD}"}, {"{SEQ}"}</span>
            </div>

            <div className="setting-item">
              <label htmlFor="sla-hours">
                <strong>SLA thời gian cam kết phê duyệt</strong>
                <span className="setting-hint">Thời gian tối đa để Quản lý phản hồi trước khi gửi cảnh báo nhắc nhở</span>
              </label>
              <select
                id="sla-hours"
                disabled={!isManager}
                value={settings.approvalSlaHours}
                onChange={(e) => setSettings({ ...settings, approvalSlaHours: Number(e.target.value) })}
              >
                <option value={12}>12 giờ làm việc</option>
                <option value={24}>24 giờ làm việc (1 ngày)</option>
                <option value={48}>48 giờ làm việc (2 ngày)</option>
                <option value={72}>72 giờ làm việc (3 ngày)</option>
              </select>
            </div>

            <div className="setting-item approval-toggle-setting">
              <label className="toggle-item approval-toggle-item">
                <input
                  type="checkbox"
                  disabled={!isManager}
                  checked={settings.requireRejectionReason}
                  onChange={(e) => setSettings({ ...settings, requireRejectionReason: e.target.checked })}
                />
                <div>
                  <strong>Bắt buộc nhập lý do khi Từ chối đề nghị</strong>
                  <span>Không cho phép từ chối mà không có nhận xét chỉ đạo cho nhân viên</span>
                </div>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Tab 5: AI Engine & System */}
      {activeTab === "ai" && (
        <div className="settings-section-card">
          <div className="section-title-row">
            <div>
              <h3>Mô hình AI & Chỉ đạo lập luận đề xuất</h3>
              <p>Quản lý cấu hình LLM Model, độ sâu suy luận và tiêu chí chỉ đạo đặc thù cho doanh nghiệp</p>
            </div>
            <span className={`permission-badge ${isManager ? "editable" : "locked"}`}>
              {isManager ? "Toàn quyền quản trị" : "🔒 Khóa đối với nhân viên"}
            </span>
          </div>

          {!isManager && (
            <div className="settings-lock-notice">
              <Icon name="lock" />
              <span>Phân hệ này chứa các tham số kỹ thuật về mô hình ngôn ngữ và tài nguyên API. Chỉ Quản trị viên / Quản lý mới có quyền xem và cấu hình.</span>
            </div>
          )}

          <div className="settings-grid">
            <div className="setting-item">
              <label htmlFor="llm-model">
                <strong>Mô hình AI chủ đạo (Decision Support LLM)</strong>
                <span className="setting-hint">Mô hình phân tích dữ liệu, tổng hợp ma trận và tạo tờ trình đề xuất</span>
              </label>
              <select
                id="llm-model"
                disabled={!isManager}
                value={settings.llmModel}
                onChange={(e) => setSettings({ ...settings, llmModel: e.target.value })}
              >
                <option value="gpt-6-luna">GPT-6 Luna (OpenAI Production Default - Tối ưu lập luận)</option>
                <option value="qwen2.5:7b">Qwen 2.5 7B (Local Model - Tối ưu chi phí)</option>
                <option value="qwen/qwen3.8-27b:free">Qwen 3.8 27B (OpenRouter Free Tier)</option>
                <option value="gemini-3.5-flash">Gemini 3.5 Flash (Google AI)</option>
              </select>
            </div>

            <div className="setting-item">
              <label htmlFor="reasoning-effort">
                <strong>Mức độ suy luận (Reasoning Effort)</strong>
                <span className="setting-hint">Độ sâu kiểm tra chéo các điều khoản phụ phí và điều kiện giao hàng</span>
              </label>
              <select
                id="reasoning-effort"
                disabled={!isManager}
                value={settings.reasoningEffort}
                onChange={(e) => setSettings({ ...settings, reasoningEffort: e.target.value })}
              >
                <option value="none">None (Nhanh nhất - Phù hợp PR đơn giản)</option>
                <option value="low">Low (Kiểm tra cơ bản)</option>
                <option value="medium">Medium (Đề xuất tiêu chuẩn)</option>
                <option value="high">High (Phân tích chi tiết điều khoản rủi ro)</option>
              </select>
            </div>
          </div>

          <div className="ai-prompt-panel">
            <div className="setting-item">
              <label htmlFor="prompt-directive">
                <strong>Chỉ đạo ưu tiên cho AI khi lập đề xuất</strong>
                <span className="setting-hint">Nội dung này sẽ được bổ sung vào system prompt của AI khi sinh tờ trình so sánh</span>
              </label>
              <textarea
                id="prompt-directive"
                className="ai-directive-textarea"
                rows={4}
                disabled={!isManager}
                value={settings.decisionPromptDirective}
                onChange={(e) => setSettings({ ...settings, decisionPromptDirective: e.target.value })}
                placeholder="Nhập chỉ đạo riêng của doanh nghiệp..."
              />
            </div>
          </div>
        </div>
      )}

      {/* Action Bar Footer */}
      <div className="settings-footer-actions">
        {!matchingThresholdsValid && activeTab !== "matching" && (
          <span className="settings-footer-validation" role="status">Hãy chỉnh ngưỡng gợi ý trước khi lưu.</span>
        )}
        {isManager && weightTotal !== 100 && activeTab !== "evaluation" && (
          <span className="settings-footer-validation" role="status">Tổng trọng số {weightTotal}%; cần bằng 100% để lưu.</span>
        )}
        <button type="button" className="secondary" disabled={saving} onClick={handleReset}>
          Khôi phục mặc định
        </button>
        <button
          type="button"
          className="inline-primary"
          disabled={saving || !matchingThresholdsValid || (isManager && weightTotal !== 100)}
          onClick={handleSave}
        >
          <Icon name="check" className="button-icon" /> {saving ? "Đang lưu cấu hình…" : "Lưu thay đổi cấu hình"}
        </button>
      </div>
    </div>
  );
}
