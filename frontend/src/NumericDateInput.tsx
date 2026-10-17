import { useRef } from "react";

type NumericDateInputProps = {
  value: string;
  onChange: (value: string) => void;
  min?: string;
  required?: boolean;
};

export function NumericDateInput({ value, onChange, min, required }: NumericDateInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [year, month, day] = value.slice(0, 10).split("-");
  const display = year && month && day ? `${day}/${month}/${year}` : "dd/mm/yyyy";

  return <div className="numeric-date-input" onClick={() => inputRef.current?.showPicker?.()}>
    <input ref={inputRef} type="date" lang="vi" value={value} min={min} required={required} onChange={(event) => onChange(event.target.value)} />
    <span className={`numeric-date-display${value ? "" : " placeholder"}`} aria-hidden="true">{display}</span>
  </div>;
}
