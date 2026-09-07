import {
  createContext,
  type FormEvent,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { LockKeyhole } from "lucide-react";
import {
  fetchAuthSession,
  fetchAuthStatus,
  loginWithPassword,
  logoutSession,
  registerOwner,
  type AuthUser,
} from "./services/authApi";

type AuthContextValue = {
  user: AuthUser;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthGate");
  return value;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);
  const [setupRequired, setSetupRequired] = useState(false);

  useEffect(() => {
    let active = true;
    fetchAuthSession()
      .then((session) => active && setUser(session.user))
      .catch(async () => {
        if (!active) return;
        setUser(null);
        try {
          const status = await fetchAuthStatus();
          if (active) setSetupRequired(status.setup_required);
        } catch {
          if (active) setSetupRequired(false);
        }
      })
      .finally(() => active && setChecking(false));
    const handleUnauthorized = () => setUser(null);
    window.addEventListener("findesk:unauthorized", handleUnauthorized);
    return () => {
      active = false;
      window.removeEventListener("findesk:unauthorized", handleUnauthorized);
    };
  }, []);

  if (checking) {
    return <div className="auth-loading" aria-label="正在检查登录状态" />;
  }
  if (!user) {
    return setupRequired ? (
      <RegistrationScreen onAuthenticated={setUser} />
    ) : (
      <LoginScreen onAuthenticated={setUser} />
    );
  }
  return (
    <AuthContext.Provider
      value={{
        user,
        logout: async () => {
          await logoutSession();
          setUser(null);
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

function RegistrationScreen({
  onAuthenticated,
}: {
  onAuthenticated: (user: AuthUser) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [setupToken, setSetupToken] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password !== confirmation) {
      setError("两次输入的密码不一致");
      return;
    }
    setSubmitting(true);
    try {
      const session = await registerOwner(email, password, setupToken);
      onAuthenticated(session.user);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "初始化失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="register-title">
        <div className="auth-brand"><span>F</span><strong>FinDesk</strong></div>
        <div className="auth-icon"><LockKeyhole /></div>
        <p className="auth-eyebrow">ONE-TIME OWNER SETUP</p>
        <h1 id="register-title">创建你的管理员账号</h1>
        <p className="auth-intro">这是一次性初始化。创建成功后，注册入口会自动关闭。</p>
        <form onSubmit={submit} className="auth-form">
          <label>
            <span>登录邮箱</span>
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required autoFocus />
          </label>
          <label>
            <span>密码（至少 12 位）</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required />
          </label>
          <label>
            <span>确认密码</span>
            <input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} required />
          </label>
          <label>
            <span>服务器初始化码</span>
            <input type="password" value={setupToken} onChange={(event) => setSetupToken(event.target.value)} autoComplete="one-time-code" minLength={16} required />
          </label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button type="submit" disabled={submitting}>{submitting ? "正在创建…" : "创建并登录"}</button>
        </form>
        <p className="auth-footnote">初始化码只用于创建第一个账号，不是日常登录密码。</p>
      </section>
    </main>
  );
}

function LoginScreen({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const session = await loginWithPassword(email, password);
      onAuthenticated(session.user);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="auth-brand"><span>F</span><strong>FinDesk</strong></div>
        <div className="auth-icon"><LockKeyhole /></div>
        <p className="auth-eyebrow">PRIVATE FINANCE WORKSPACE</p>
        <h1 id="auth-title">登录你的财务工作台</h1>
        <p className="auth-intro">账单、财务档案与 CFO 对话仅对已验证用户开放。</p>
        <form onSubmit={submit} className="auth-form">
          <label>
            <span>邮箱</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
              autoFocus
            />
          </label>
          <label>
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button type="submit" disabled={submitting}>
            {submitting ? "正在验证…" : "安全登录"}
          </button>
        </form>
        <p className="auth-footnote">FinDesk 不会通过此页面索取银行密码或支付验证码。</p>
      </section>
    </main>
  );
}
