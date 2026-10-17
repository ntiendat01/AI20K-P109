import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { Icon } from "./Icon";
import { LoadingState } from "./ui";
import { roleConfig } from "./config";

export function LoginPage() {
  const { session, loading, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Wait for stored credentials to be checked before redirecting. Otherwise a
  // stale local session can send the user away from the login form briefly.
  if (loading) return <LoadingState label="Đang kiểm tra phiên đăng nhập…" />;
  if (session) return <Navigate to={roleConfig[session.user.role].home} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const authenticated = await login(email, password);
      navigate(roleConfig[authenticated.user.role].home, { replace: true });
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Không thể đăng nhập.");
    } finally {
      setSubmitting(false);
    }
  };

  const useDemo = (role: "procurement" | "manager") => {
    if (role === "procurement") { setEmail("anhnm@dotcom.vn"); setPassword("Purchase123!"); }
    else { setEmail("quanghuy@dotcom.vn"); setPassword("Manager123!"); }
  };

  return <main className="login-layout">
    <section className="login-panel"><div className="login-card">
      <div className="brand"><span className="brand-mark"><Icon name="brand" /></span><span>DotCom</span></div>
      <p className="section-kicker">Nền tảng quản lý thu mua</p>
      <h1>Đăng nhập hệ thống</h1>
      <p className="subtitle">Tạo đề nghị mua hàng, đối chiếu báo giá và theo dõi các quyết định.</p>
      <form onSubmit={submit}>
        <label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="ten@dotcom.vn" required />
        <label htmlFor="password">Mật khẩu</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Nhập mật khẩu" required />
        <button className="primary" type="submit" disabled={submitting}>{submitting ? "Đang xác thực…" : "Đăng nhập"}</button>
        <p className="error" role="alert">{error}</p>
      </form>
      <div className="demo-box"><div><strong>Tài khoản dùng thử</strong><span>Chọn vai trò để điền thông tin đăng nhập.</span></div>
        <div className="demo-row"><span>Nhân viên phụ trách mua sắm</span><button type="button" onClick={() => useDemo("procurement")}>Dùng tài khoản này <Icon name="arrow-right" className="button-icon" /></button></div>
        <div className="demo-row"><span>Quản lý phê duyệt</span><button type="button" onClick={() => useDemo("manager")}>Dùng tài khoản này <Icon name="arrow-right" className="button-icon" /></button></div>
      </div>
    </div></section>
    <aside className="hero"><div className="hero-content"><h2>Mọi đề nghị đều có đường đi rõ ràng.</h2><p>Tập trung đề nghị, báo giá và quyết định trong cùng một quy trình. AI hỗ trợ xử lý, con người xác nhận kết quả.</p><div className="hero-flow" aria-label="Quy trình xử lý đề nghị mua hàng"><span className="flow-node"><i>01</i>Đề nghị mua hàng</span><span className="flow-line" /><span className="flow-node"><i>02</i>Báo giá</span><span className="flow-line" /><span className="flow-node"><i>03</i>Phê duyệt</span></div><div className="hero-note"><span /> Theo dõi trạng thái của từng Đề nghị mua hàng</div></div></aside>
  </main>;
}
