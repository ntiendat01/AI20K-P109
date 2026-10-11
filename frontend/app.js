import { restoreSession } from "./features/auth/auth.js";
import { installNumberInputWheelGuard } from "./core/number-input-wheel.js";

window.addEventListener("hashchange", restoreSession);
installNumberInputWheelGuard();
restoreSession();
