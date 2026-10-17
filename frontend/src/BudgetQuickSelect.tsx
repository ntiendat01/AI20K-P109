import { useState, type FocusEvent, type KeyboardEvent } from "react";

const budgetOptions = [
  { label: "100 Triệu", value: "100000000" },
  { label: "500 Triệu", value: "500000000" },
  { label: "1 Tỷ", value: "1000000000" },
];

type BudgetQuickSelectProps = {
  id: string;
  value: string;
  onChange: (value: string) => void;
};

export function BudgetQuickSelect({ id, value, onChange }: BudgetQuickSelectProps) {
  const [open, setOpen] = useState(false);
  const closeOnBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
  };
  const closeOnEscape = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") setOpen(false);
  };

  return <div className="budget-quick-select" onBlur={closeOnBlur} onKeyDown={closeOnEscape}>
    <input id={id} type="number" min="1" step="0.01" value={value} onChange={(event) => onChange(event.target.value)} onFocus={() => setOpen(true)} onClick={() => setOpen(true)} aria-expanded={open} aria-controls={`${id}-options`} aria-haspopup="menu" required />
    {open && <div className="budget-quick-menu" id={`${id}-options`} role="menu" aria-label="Ngân sách nhanh">
      {budgetOptions.map((option) => <button key={option.value} type="button" role="menuitem" className="budget-quick-option" onMouseDown={(event) => event.preventDefault()} onClick={() => { onChange(option.value); setOpen(false); }}>{option.label}</button>)}
    </div>}
  </div>;
}
