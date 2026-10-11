/**
 * Native number inputs increment/decrement while focused when the mouse wheel
 * moves over them. Release focus so the wheel continues to scroll the page
 * without changing a value the buyer may not have noticed.
 */
export function releaseNumberInputOnWheel(event) {
  const input = event.target;
  if (input?.tagName !== "INPUT" || input.type !== "number") return;
  input.blur();
}

export function installNumberInputWheelGuard(root = document) {
  root.addEventListener("wheel", releaseNumberInputOnWheel, { capture: true, passive: true });
}
