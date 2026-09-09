import {
  createContext,
  type FormEvent,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
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
        <AuthStory />
        <div className="auth-panel">
          <p className="auth-eyebrow">首次使用</p>
          <h1 id="register-title">创建管理员账号</h1>
          <p className="auth-intro">只需初始化一次，完成后注册入口会自动关闭。</p>
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
            <button type="submit" disabled={submitting}><span>{submitting ? "正在创建…" : "创建并登录"}</span><ArrowRight /></button>
          </form>
          <p className="auth-footnote"><ShieldCheck /> 初始化码只用于创建第一个账号，不是日常登录密码。</p>
        </div>
      </section>
    </main>
  );
}

function AuthStory() {
  return (
    <aside className="auth-story">
      <div className="auth-brand"><span>F</span><strong>FinDesk</strong></div>
      <div className="auth-story-copy">
        <p>PERSONAL FINANCE DESK</p>
        <h2>财务压力，<br />应该被算清楚。</h2>
        <span>把账单、债务和下一步计划放在同一个清晰的视图里。</span>
      </div>
      <div className="auth-story-points">
        <div><span>01</span><strong>看清每天的钱去了哪里</strong></div>
        <div><span>02</span><strong>提前发现还款资金缺口</strong></div>
        <div><span>03</span><strong>和个人 CFO 讨论下一步</strong></div>
      </div>
    </aside>
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
        <AuthStory />
        <div className="auth-panel">
          <p className="auth-eyebrow">欢迎回来</p>
          <h1 id="auth-title">登录你的财务工作台</h1>
          <p className="auth-intro">继续查看你的现金流、账单和计划。</p>
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
              <span>{submitting ? "正在验证…" : "安全登录"}</span><ArrowRight />
            </button>
          </form>
          <p className="auth-footnote"><ShieldCheck /> FinDesk 不会索取银行密码或支付验证码。</p>
        </div>
      </section>
    </main>
  );
}
