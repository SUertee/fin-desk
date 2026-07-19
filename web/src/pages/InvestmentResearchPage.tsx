import { useEffect, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  BriefcaseBusiness,
  ChevronRight,
  CircleDollarSign,
  FileSearch,
  FlaskConical,
  LineChart,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

import { useI18n } from "../i18n";
import {
  createScenario,
  fetchInstrumentResearch,
  fetchScenario,
  fetchScenarios,
  fetchScenarioValuation,
  fetchWatchlist,
  followInstrument,
  replaceScenarioPositions,
  unfollowInstrument,
} from "../services/investmentResearchApi";
import type {
  InstrumentResearchSnapshot,
  InvestmentScenario,
  InvestmentScenarioDetail,
  MarketAssetType,
  ScenarioValuation,
  WatchlistItem,
} from "../services/investmentResearchApi";


type ResearchTab = "research" | "scenario";

type InvestmentResearchPageProps = {
  userId: string;
  onAskCfo: (question: string) => void;
};

function formatMoney(amount: string | number, currency: string): string {
  const parsed = Number(amount);
  if (!Number.isFinite(parsed)) return `— ${currency}`;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(parsed);
}

function compactDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function PriceSparkline({ snapshot }: { snapshot: InstrumentResearchSnapshot }) {
  const values = snapshot.history.bars
    .map((bar) => Number(bar.close.amount))
    .filter(Number.isFinite);
  if (values.length < 2) {
    return (
      <div className="research-chart-empty">
        <LineChart />
        <span>No price history returned for this range.</span>
      </div>
    );
  }
  const width = 720;
  const height = 210;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const path = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 30) - 15;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="research-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Price history">
        <defs>
          <linearGradient id="research-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#4d7c70" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#4d7c70" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={`${path} L${width},${height} L0,${height} Z`} fill="url(#research-fill)" />
        <path d={path} fill="none" stroke="#315f54" strokeWidth="4" strokeLinecap="round" />
      </svg>
      <div className="research-chart-axis">
        <span>{snapshot.history.date_from}</span>
        <span>{snapshot.history.date_to}</span>
      </div>
    </div>
  );
}

export function InvestmentResearchPage({
  userId,
  onAskCfo,
}: InvestmentResearchPageProps) {
  const { lang } = useI18n();
  const [tab, setTab] = useState<ResearchTab>("research");
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [scenarios, setScenarios] = useState<InvestmentScenario[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedAssetType, setSelectedAssetType] = useState<MarketAssetType>("equity");
  const [snapshot, setSnapshot] = useState<InstrumentResearchSnapshot | null>(null);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [scenarioDetail, setScenarioDetail] = useState<InvestmentScenarioDetail | null>(null);
  const [valuation, setValuation] = useState<ScenarioValuation | null>(null);
  const [symbolInput, setSymbolInput] = useState("");
  const [assetTypeInput, setAssetTypeInput] = useState<MarketAssetType>("equity");
  const [scenarioName, setScenarioName] = useState("");
  const [scenarioCash, setScenarioCash] = useState("");
  const [positionSymbol, setPositionSymbol] = useState("");
  const [positionQuantity, setPositionQuantity] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const loadCollections = async () => {
    setLoading(true);
    setError(null);
    try {
      const [watchlistItems, scenarioItems] = await Promise.all([
        fetchWatchlist(userId),
        fetchScenarios(userId),
      ]);
      setWatchlist(watchlistItems);
      setScenarios(scenarioItems);
    } catch (caught: any) {
      setError(caught?.message ?? "Unable to load investment research.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadCollections();
  }, [userId]);

  const loadResearch = async (symbol: string, assetType: MarketAssetType) => {
    setSelectedSymbol(symbol);
    setSelectedAssetType(assetType);
    setSnapshot(null);
    setDetailLoading(true);
    setError(null);
    try {
      setSnapshot(await fetchInstrumentResearch(userId, symbol, assetType));
    } catch (caught: any) {
      setError(caught?.message ?? "Unable to load instrument research.");
    } finally {
      setDetailLoading(false);
    }
  };

  const addToWatchlist = async () => {
    const symbol = symbolInput.trim().toUpperCase();
    if (!symbol) return;
    setSaving(true);
    setError(null);
    try {
      await followInstrument(userId, symbol, assetTypeInput);
      setSymbolInput("");
      await loadCollections();
      await loadResearch(symbol, assetTypeInput);
    } catch (caught: any) {
      setError(caught?.message ?? "Unable to follow instrument.");
    } finally {
      setSaving(false);
    }
  };

  const removeFromWatchlist = async (item: WatchlistItem) => {
    setSaving(true);
    setError(null);
    try {
      await unfollowInstrument(userId, item.symbol, item.asset_type);
      if (selectedSymbol === item.symbol && selectedAssetType === item.asset_type) {
        setSelectedSymbol(null);
        setSnapshot(null);
      }
      await loadCollections();
    } catch (caught: any) {
      setError(caught?.message ?? "Unable to remove instrument.");
    } finally {
      setSaving(false);
    }
  };

  const loadScenario = async (scenarioId: string) => {
    setSelectedScenarioId(scenarioId);
    setScenarioDetail(null);
    setValuation(null);
    setDetailLoading(true);
    setError(null);
    try {
      const [detail, result] = await Promise.all([
        fetchScenario(userId, scenarioId),
        fetchScenarioValuation(userId, scenarioId),
      ]);
      setScenarioDetail(detail);
      setValuation(result);
    } catch (caught: any) {
      setError(caught?.message ?? "Unable to load scenario.");
    } finally {
      setDetailLoading(false);
    }
  };

  const addScenario = async () => {
    const name = scenarioName.trim();
    if (!name) return;
    const cash = scenarioCash.trim() ? Number(scenarioCash) : null;
    if (cash !== null && (!Number.isFinite(cash) || cash < 0)) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createScenario(userId, {
        name,
        reporting_currency: "CNY",
        starting_cash_amount: cash,
      });
      setScenarioName("");
      setScenarioCash("");
      await loadCollections();
      await loadScenario(created.scenario_id);
    } catch (caught: any) {
      setError(caught?.message ?? "Unable to create scenario.");
    } finally {
      setSaving(false);
    }
  };

  const savePositions = async (
    next: Array<{ symbol: string; asset_type: MarketAssetType; quantity: number }>
  ) => {
    if (!selectedScenarioId) return;
    setSaving(true);
    setError(null);
    try {
      await replaceScenarioPositions(userId, selectedScenarioId, next);
      setPositionSymbol("");
      setPositionQuantity("");
      await loadScenario(selectedScenarioId);
      await loadCollections();
    } catch (caught: any) {
      setError(caught?.message ?? "Unable to update scenario positions.");
    } finally {
      setSaving(false);
    }
  };

  const addPosition = async () => {
    const symbol = positionSymbol.trim().toUpperCase();
    const quantity = Number(positionQuantity);
    if (!scenarioDetail || !symbol || !Number.isFinite(quantity) || quantity <= 0) return;
    const existing = scenarioDetail.positions.map((item) => ({
      symbol: item.symbol,
      asset_type: item.asset_type,
      quantity: Number(item.quantity),
    }));
    const withoutDuplicate = existing.filter((item) => item.symbol !== symbol);
    await savePositions([
      ...withoutDuplicate,
      { symbol, asset_type: "equity", quantity },
    ]);
  };

  const removePosition = async (symbol: string, assetType: MarketAssetType) => {
    if (!scenarioDetail) return;
    await savePositions(
      scenarioDetail.positions
        .filter((item) => item.symbol !== symbol || item.asset_type !== assetType)
        .map((item) => ({
          symbol: item.symbol,
          asset_type: item.asset_type,
          quantity: Number(item.quantity),
        }))
    );
  };

  return (
    <main className="research-shell">
      <header className="research-page-head">
        <div>
          <div className="research-eyebrow">
            <BookOpenCheck /> {lang === "zh" ? "只读市场研究" : "READ-ONLY MARKET RESEARCH"}
          </div>
          <h1>{lang === "zh" ? "投资研究室" : "Investment Research"}</h1>
          <p>
            {lang === "zh"
              ? "关注标的、核对来源，并在不连接真实资金的前提下构建假设场景。"
              : "Follow instruments, inspect sourced evidence, and model scenarios without connecting real capital."}
          </p>
        </div>
        <div className="research-safety-badge">
          <ShieldCheck />
          <span>{lang === "zh" ? "不下单 · 不执行交易" : "No orders · No trade execution"}</span>
        </div>
      </header>

      <div className="research-tabs" role="tablist">
        <button
          type="button"
          className={tab === "research" ? "active" : ""}
          aria-selected={tab === "research"}
          onClick={() => setTab("research")}
        >
          <FileSearch /> {lang === "zh" ? "标的研究" : "Research"}
        </button>
        <button
          type="button"
          className={tab === "scenario" ? "active" : ""}
          aria-selected={tab === "scenario"}
          onClick={() => setTab("scenario")}
        >
          <FlaskConical /> {lang === "zh" ? "假设场景" : "Scenario Lab"}
        </button>
      </div>

      {error && (
        <div className="research-error">
          <span>{error}</span>
          <button type="button" onClick={() => void loadCollections()}>
            <RefreshCw /> Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="research-loading"><LoaderCircle /> Loading research workspace…</div>
      ) : tab === "research" ? (
        <section className="research-layout">
          <aside className="research-rail">
            <div className="research-rail-head">
              <div>
                <span>{lang === "zh" ? "关注列表" : "Watchlist"}</span>
                <small>{watchlist.length} instruments</small>
              </div>
            </div>
            <div className="research-add-row">
              <input
                value={symbolInput}
                onChange={(event) => setSymbolInput(event.target.value)}
                placeholder="AAPL"
                aria-label="Symbol"
              />
              <select
                value={assetTypeInput}
                onChange={(event) => setAssetTypeInput(event.target.value as MarketAssetType)}
                aria-label="Asset type"
              >
                <option value="equity">Stock</option>
                <option value="etf">ETF</option>
              </select>
              <button
                type="button"
                onClick={() => void addToWatchlist()}
                disabled={saving}
                aria-label={lang === "zh" ? "添加关注标的" : "Add instrument"}
              >
                <Plus />
              </button>
            </div>
            <div className="research-watchlist">
              {watchlist.length === 0 ? (
                <div className="research-rail-empty">
                  {lang === "zh" ? "还没有关注标的。" : "No followed instruments yet."}
                </div>
              ) : (
                watchlist.map((item) => (
                  <div
                    key={`${item.symbol}:${item.asset_type}`}
                    className={`research-watch-row${
                      selectedSymbol === item.symbol && selectedAssetType === item.asset_type
                        ? " active"
                        : ""
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => void loadResearch(item.symbol, item.asset_type)}
                    >
                      <span>{item.symbol}</span>
                      <small>{item.asset_type.toUpperCase()}</small>
                      <ChevronRight />
                    </button>
                    <button
                      type="button"
                      className="research-remove"
                      onClick={() => void removeFromWatchlist(item)}
                      aria-label={`Remove ${item.symbol}`}
                    >
                      <X />
                    </button>
                  </div>
                ))
              )}
            </div>
          </aside>

          <div className="research-canvas">
            {detailLoading ? (
              <div className="research-loading"><LoaderCircle /> Loading sourced market data…</div>
            ) : snapshot ? (
              <>
                <div className="research-instrument-head">
                  <div className="research-symbol-mark">{snapshot.symbol.slice(0, 2)}</div>
                  <div>
                    <span>{snapshot.profile.venue || snapshot.asset_type.toUpperCase()}</span>
                    <h2>{snapshot.profile.name}</h2>
                    <small>{snapshot.symbol} · {snapshot.profile.currency}</small>
                  </div>
                  <div className="research-head-actions">
                    <button type="button" onClick={() => setEvidenceOpen(true)}>
                      <BookOpenCheck /> {snapshot.evidence.length} sources
                    </button>
                    <button
                      type="button"
                      className="research-primary"
                      onClick={() =>
                        onAskCfo(
                          lang === "zh"
                            ? `请基于已获取的证据分析股票标的 ${snapshot.symbol}，说明风险、数据边界和需要进一步核对的事项。`
                            : `Review stock symbol ${snapshot.symbol} using the sourced evidence. Explain the risks, data boundaries, and what needs further verification.`
                        )
                      }
                    >
                      Ask CFO <ArrowRight />
                    </button>
                  </div>
                </div>

                <div className="research-metric-grid">
                  <article className="research-price-card">
                    <span>{lang === "zh" ? "最近行情" : "Latest quote"}</span>
                    <strong>
                      {snapshot.quote
                        ? formatMoney(snapshot.quote.price.amount, snapshot.quote.price.currency)
                        : "Unavailable"}
                    </strong>
                    <small>
                      {snapshot.quote
                        ? `${snapshot.quote.timestamp_basis === "provider_time" ? "Provider time" : "Retrieval time"} · ${compactDate(snapshot.quote.quote_as_of)}`
                        : "No current price was returned"}
                    </small>
                  </article>
                  <article>
                    <span>{lang === "zh" ? "行业" : "Sector"}</span>
                    <strong>{snapshot.profile.sector || "Not reported"}</strong>
                    <small>{snapshot.profile.industry || "Provider profile"}</small>
                  </article>
                  <article>
                    <span>{lang === "zh" ? "市场" : "Market"}</span>
                    <strong>{snapshot.profile.venue || "—"}</strong>
                    <small>{snapshot.profile.country || "Country unavailable"}</small>
                  </article>
                </div>

                <article className="research-chart-card">
                  <header>
                    <div>
                      <span>{lang === "zh" ? "价格历史" : "Price history"}</span>
                      <h3>{snapshot.history.date_from} — {snapshot.history.date_to}</h3>
                    </div>
                    <small>{snapshot.history.provider}</small>
                  </header>
                  <PriceSparkline snapshot={snapshot} />
                </article>

                <div className="research-limitations">
                  <ShieldCheck />
                  <div>
                    <strong>{lang === "zh" ? "研究边界" : "Research boundaries"}</strong>
                    {snapshot.limitations.map((item) => <span key={item}>{item}</span>)}
                  </div>
                </div>
              </>
            ) : (
              <div className="research-empty-state">
                <div className="research-empty-orbit"><LineChart /></div>
                <span>{lang === "zh" ? "从一个标的开始" : "Start with one instrument"}</span>
                <h2>
                  {lang === "zh"
                    ? "输入股票代码或 ETF 代码，建立你的第一份有来源的研究卡片。"
                    : "Add a stock or ETF symbol to build your first sourced research brief."}
                </h2>
                <p>
                  {lang === "zh"
                    ? "这里不会显示虚构行情，也不会连接真实资金。"
                    : "This workspace never fabricates prices or connects real capital."}
                </p>
              </div>
            )}
          </div>
        </section>
      ) : (
        <section className="research-layout">
          <aside className="research-rail">
            <div className="research-rail-head">
              <div>
                <span>{lang === "zh" ? "场景档案" : "Scenario files"}</span>
                <small>Hypothetical only</small>
              </div>
            </div>
            <div className="research-scenario-form">
              <input
                value={scenarioName}
                onChange={(event) => setScenarioName(event.target.value)}
                placeholder={lang === "zh" ? "场景名称" : "Scenario name"}
                aria-label={lang === "zh" ? "场景名称" : "Scenario name"}
              />
              <input
                value={scenarioCash}
                onChange={(event) => setScenarioCash(event.target.value)}
                inputMode="decimal"
                placeholder={lang === "zh" ? "研究预算 CNY（可选）" : "Research budget CNY (optional)"}
                aria-label={lang === "zh" ? "研究预算" : "Research budget"}
              />
              <button type="button" onClick={() => void addScenario()} disabled={saving}>
                <Plus /> {lang === "zh" ? "新建场景" : "New scenario"}
              </button>
            </div>
            <div className="research-watchlist">
              {scenarios.length === 0 ? (
                <div className="research-rail-empty">No scenarios yet.</div>
              ) : (
                scenarios.map((item) => (
                  <div
                    key={item.scenario_id}
                    className={`research-watch-row${selectedScenarioId === item.scenario_id ? " active" : ""}`}
                  >
                    <button type="button" onClick={() => void loadScenario(item.scenario_id)}>
                      <span>{item.name}</span>
                      <small>{item.starting_cash ? formatMoney(item.starting_cash.amount, item.starting_cash.currency) : "No budget"}</small>
                      <ChevronRight />
                    </button>
                  </div>
                ))
              )}
            </div>
          </aside>

          <div className="research-canvas">
            {detailLoading ? (
              <div className="research-loading"><LoaderCircle /> Valuing hypothetical positions…</div>
            ) : scenarioDetail && valuation ? (
              <>
                <div className="research-instrument-head">
                  <div className="research-symbol-mark scenario"><FlaskConical /></div>
                  <div>
                    <span>HYPOTHETICAL SCENARIO</span>
                    <h2>{scenarioDetail.scenario.name}</h2>
                    <small>{scenarioDetail.scenario.reporting_currency} reporting currency</small>
                  </div>
                  <div className="research-head-actions">
                    <button
                      type="button"
                      className="research-primary"
                      onClick={() =>
                        onAskCfo(
                          lang === "zh"
                            ? `请审阅我的假设投资场景“${scenarioDetail.scenario.name}”，只讨论风险与证据边界，不提供交易指令。`
                            : `Review my hypothetical investment scenario "${scenarioDetail.scenario.name}". Discuss only risks and evidence boundaries, without trade instructions.`
                        )
                      }
                    >
                      Ask CFO <ArrowRight />
                    </button>
                  </div>
                </div>

                <div className="scenario-summary-grid">
                  <article>
                    <CircleDollarSign />
                    <span>{lang === "zh" ? "研究预算" : "Research budget"}</span>
                    <strong>
                      {scenarioDetail.scenario.starting_cash
                        ? formatMoney(
                            scenarioDetail.scenario.starting_cash.amount,
                            scenarioDetail.scenario.starting_cash.currency
                          )
                        : "Not configured"}
                    </strong>
                  </article>
                  <article>
                    <BarChart3 />
                    <span>{lang === "zh" ? "可完整估值" : "Valuation coverage"}</span>
                    <strong>{valuation.coverage.reporting_position_count} / {valuation.coverage.position_count}</strong>
                  </article>
                  <article className={valuation.overallocated_amount ? "risk" : ""}>
                    <BriefcaseBusiness />
                    <span>{lang === "zh" ? "场景估值" : "Scenario value"}</span>
                    <strong>
                      {valuation.reporting_total
                        ? formatMoney(valuation.reporting_total.amount, valuation.reporting_total.currency)
                        : valuation.status === "empty"
                          ? "No positions"
                          : "Partial"}
                    </strong>
                  </article>
                </div>

                <div className="scenario-workbench">
                  <section>
                    <header>
                      <div>
                        <span>{lang === "zh" ? "假设仓位" : "Hypothetical positions"}</span>
                        <small>Not brokerage holdings</small>
                      </div>
                    </header>
                    <div className="scenario-position-add">
                      <input
                        value={positionSymbol}
                        onChange={(event) => setPositionSymbol(event.target.value)}
                        placeholder="AAPL"
                        aria-label={lang === "zh" ? "假设仓位代码" : "Position symbol"}
                      />
                      <input
                        value={positionQuantity}
                        onChange={(event) => setPositionQuantity(event.target.value)}
                        inputMode="decimal"
                        placeholder="Quantity"
                        aria-label={lang === "zh" ? "假设数量" : "Hypothetical quantity"}
                      />
                      <button type="button" onClick={() => void addPosition()} disabled={saving}>
                        <Plus /> Add
                      </button>
                    </div>
                    <div className="scenario-position-list">
                      {scenarioDetail.positions.length === 0 ? (
                        <div className="research-rail-empty">Add a hypothetical position to begin.</div>
                      ) : (
                        scenarioDetail.positions.map((item) => {
                          const priced = valuation.positions.find(
                            (value) => value.symbol === item.symbol && value.asset_type === item.asset_type
                          );
                          return (
                            <div key={`${item.symbol}:${item.asset_type}`}>
                              <div><strong>{item.symbol}</strong><small>{item.quantity} units · {item.asset_type}</small></div>
                              <span>
                                {priced?.reporting_market_value
                                  ? formatMoney(
                                      priced.reporting_market_value.amount,
                                      priced.reporting_market_value.currency
                                    )
                                  : priced?.native_market_value
                                    ? `${formatMoney(priced.native_market_value.amount, priced.native_market_value.currency)} native`
                                    : "Quote unavailable"}
                              </span>
                              <button
                                type="button"
                                onClick={() => void removePosition(item.symbol, item.asset_type)}
                                aria-label={`Remove ${item.symbol}`}
                              >
                                <Trash2 />
                              </button>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </section>
                  <section className="scenario-risk-panel">
                    <header>
                      <div><span>{lang === "zh" ? "风控检查" : "Risk checks"}</span><small>Deterministic policy</small></div>
                    </header>
                    {valuation.risk.findings.length === 0 ? (
                      <div className="scenario-risk-clear"><ShieldCheck /> No configured risk rule was triggered.</div>
                    ) : (
                      <div className="scenario-risk-list">
                        {valuation.risk.findings.map((finding, index) => (
                          <article key={`${finding.code}:${index}`} className={finding.severity}>
                            <span>{finding.severity}</span>
                            <strong>{finding.title}</strong>
                            <p>{finding.detail}</p>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>
                </div>

                <div className="research-limitations scenario-note">
                  <FlaskConical />
                  <div>
                    <strong>{lang === "zh" ? "场景说明" : "Scenario notice"}</strong>
                    {valuation.limitations.map((item) => <span key={item}>{item}</span>)}
                  </div>
                </div>
              </>
            ) : (
              <div className="research-empty-state">
                <div className="research-empty-orbit"><FlaskConical /></div>
                <span>{lang === "zh" ? "先验证想法，再谈模拟交易" : "Validate assumptions before paper trading"}</span>
                <h2>
                  {lang === "zh"
                    ? "创建一个不连接券商、不使用真实资金的研究场景。"
                    : "Create a research scenario with no brokerage connection and no real capital."}
                </h2>
                <p>
                  {lang === "zh"
                    ? "FinDesk 会保留原币金额、汇率快照和缺失证据。"
                    : "FinDesk preserves native values, exchange-rate snapshots, and missing evidence."}
                </p>
              </div>
            )}
          </div>
        </section>
      )}

      {evidenceOpen && snapshot && (
        <div className="research-drawer-backdrop" onMouseDown={() => setEvidenceOpen(false)}>
          <aside className="research-drawer" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span>EVIDENCE</span><h3>{snapshot.symbol} sources</h3></div>
              <button
                type="button"
                onClick={() => setEvidenceOpen(false)}
                aria-label={lang === "zh" ? "关闭证据来源" : "Close evidence"}
              >
                <X />
              </button>
            </header>
            <div className="research-drawer-body">
              {snapshot.evidence.map((item) => (
                <article key={`${item.kind}:${item.source}:${item.as_of}`}>
                  <div><span>{item.kind}</span><BookOpenCheck /></div>
                  <strong>{item.source}</strong>
                  <p>{item.description}</p>
                  <small>As of {compactDate(item.as_of)}</small>
                </article>
              ))}
              <div className="research-drawer-boundary">
                <ShieldCheck />
                <p>Reference data supports research only. It is not an executable quote or trade instruction.</p>
              </div>
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}
