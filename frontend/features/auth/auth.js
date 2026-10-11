import { API_ROOT, storageKey, roleConfig } from "../../config/constants.js";
import { icon } from "../../core/icons.js";
import { setSession, getSession } from "../../core/session.js";
import { displayDashboard } from "../../core/router.js";

export function displayLogin() {
  const app = document.querySelector("#app");
  app.innerHTML = `
    <section class="login-layout">
      <section class="login-panel">
        <div class="login-card">
          <div class="brand"><span class="brand-mark" aria-hidden="true">${icon("brand")}</span><span>DotCom</span><small>OPS</small></div>
          <p class="section-kicker">Không gian mua sắm</p>
          <h1>Vào ca,<br />xử lý đúng việc.</h1>
          <p class="subtitle">Đăng nhập để tạo đề nghị mua, đối chiếu báo giá và theo dõi từng quyết định.</p>
          <form id="login-form">
            <label for="email">Email công việc</label>
            <input id="email" name="email" type="email" autocomplete="email" placeholder="name@vinuni.edu.vn" required />
            <label for="password">Mật khẩu</label>
            <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Nhập mật khẩu" required />
            <button class="primary" type="submit">Đăng nhập</button>
            <p class="error" id="login-error" role="alert"></p>
          </form>
          <div class="demo-box">
            <div><strong>Chế độ trình diễn</strong><span>Chọn vai trò để xem đúng khu vực làm việc.</span></div>
            <div class="demo-row"><span>Nhân viên mua sắm</span><button data-demo="procurement" type="button">Dùng tài khoản này <b>→</b></button></div>
            <div class="demo-row"><span>Quản lý duyệt</span><button data-demo="manager" type="button">Dùng tài khoản này <b>→</b></button></div>
          </div>
        </div>
      </section>
      <aside class="hero">
        <div class="hero-content">
          <div class="eyebrow">Procurement control board</div>
          <h2>Mọi đề nghị đều có đường đi rõ ràng.</h2>
          <p>Đưa nhu cầu, báo giá và quyết định vào cùng một luồng kiểm soát. AI hỗ trợ xử lý; con người xác nhận kết quả.</p>
          <div class="hero-flow" aria-label="Luồng xử lý đề nghị mua"><span class="flow-node"><i>01</i>Đề nghị mua</span><span class="flow-line"></span><span class="flow-node"><i>02</i>Báo giá</span><span class="flow-line"></span><span class="flow-node"><i>03</i>Phê duyệt</span></div>
          <div class="hero-note"><span></span> Truy vết trạng thái theo từng PR</div>
        </div>
      </aside>
    </section>`;

  document.querySelector("#login-form").addEventListener("submit", submitLogin);
  document.querySelectorAll("[data-demo]").forEach((button) => button.addEventListener("click", () => {
    const isProcurement = button.dataset.demo === "procurement";
    document.querySelector("#email").value = isProcurement ? "purchasing@vinuni.edu.vn" : "manager@vinuni.edu.vn";
    document.querySelector("#password").value = isProcurement ? "Purchase123!" : "Manager123!";
    document.querySelector("#login-form").requestSubmit();
  }));
}

async function submitLogin(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const error = document.querySelector("#login-error");
  const button = event.currentTarget.querySelector("button[type=submit]");
  error.textContent = "";
  button.disabled = true;
  button.textContent = "Đang xác thực…";
  try {
    const response = await fetch(`${API_ROOT}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(form)) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Không thể đăng nhập.");
    setSession(data);
    window.location.hash = `#/${roleConfig[data.user.role].home}`;
    displayDashboard(data);
  } catch (exception) {
    error.textContent = exception.message;
  } finally {
    button.disabled = false;
    button.textContent = "Đăng nhập";
  }
}

export async function logout(session) {
  try { await fetch(`${API_ROOT}/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${session.access_token}` } }); } finally {
    localStorage.removeItem(storageKey);
    history.replaceState(null, "", window.location.pathname);
    displayLogin();
  }
}

export async function restoreSession() {
  const session = getSession();
  if (!session?.access_token) return displayLogin();
  try {
    const response = await fetch(`${API_ROOT}/auth/session`, { headers: { Authorization: `Bearer ${session.access_token}` } });
    if (!response.ok) throw new Error();
    session.user = await response.json();
    setSession(session);
    displayDashboard(session);
  } catch { localStorage.removeItem(storageKey); displayLogin(); }
}
