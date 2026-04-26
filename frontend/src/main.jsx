import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE =
  import.meta.env.VITE_API_BASE ??
  `${window.location.protocol}//${window.location.hostname}:8000`;

const sections = [
  { key: "interests", label: "관심종목", path: "/api/interests" },
  { key: "interestAreas", label: "관심분야", path: "/api/interest-areas" },
  { key: "holdings", label: "보유종목", path: "/api/holdings" },
  { key: "schedules", label: "스케줄", path: "/api/schedules" },
  { key: "reports", label: "분석 리포트", path: "/api/reports" },
  { key: "sources", label: "뉴스 소스", path: "/api/expert-sources" },
];

const pipelineSections = [
  { key: "newsRaw", label: "news_raw", path: "/api/pipeline/news-raw" },
  { key: "newsRefined", label: "news_refined", path: "/api/pipeline/news-refined" },
  { key: "newsCluster", label: "news_cluster", path: "/api/pipeline/news-cluster" },
  { key: "strategyReports", label: "strategy_report", path: "/api/pipeline/strategy-reports" },
  { key: "pipelineState", label: "pipeline_state", path: "/api/pipeline/state" },
];

function dash(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "-";
  return `${value}${suffix}`;
}

function money(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString();
}

function formatPipelineCell(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.join(", ") || "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function App() {
  const [status, setStatus] = useState("확인 중");
  const [items, setItems] = useState({});
  const [pipelineItems, setPipelineItems] = useState({});
  const [command, setCommand] = useState("");
  const [commandResult, setCommandResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedSchedule, setSelectedSchedule] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);
  const [selectedPipelineRow, setSelectedPipelineRow] = useState(null);
  const [view, setView] = useState("dashboard");
  const [loadWarning, setLoadWarning] = useState("");

  const totalCount = useMemo(
    () =>
      Object.values(items).reduce(
        (sum, value) => sum + (Array.isArray(value) ? value.length : 0),
        0
      ),
    [items]
  );

  async function api(path, options) {
    const response = await fetch(`${API_BASE}${path}`, options);
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      const detail =
        payload && typeof payload === "object" && "detail" in payload
          ? payload.detail
          : `API ${response.status}`;
      throw new Error(String(detail));
    }
    return payload;
  }

  async function safeFetch(path, fallback = []) {
    try {
      const response = await fetch(`${API_BASE}${path}`);
      if (!response.ok) {
        return { ok: false, data: fallback, path, status: response.status };
      }
      return { ok: true, data: await response.json(), path, status: response.status };
    } catch {
      return { ok: false, data: fallback, path, status: "network_error" };
    }
  }

  async function loadAll() {
    setLoading(true);
    try {
      const health = await fetch(`${API_BASE}/api/health`);
      setStatus(health.ok ? "연결됨" : "확인 필요");
      const sectionResults = await Promise.all(
        sections.map((section) => safeFetch(section.path))
      );
      const pipelineResults = await Promise.all(
        pipelineSections.map((section) => safeFetch(section.path))
      );

      const sectionEntries = sections.map((section, index) => [
        section.key,
        sectionResults[index].data,
      ]);
      const pipelineEntries = pipelineSections.map((section, index) => [
        section.key,
        pipelineResults[index].data,
      ]);

      setItems(Object.fromEntries(sectionEntries));
      setPipelineItems(Object.fromEntries(pipelineEntries));

      const failed = [...sectionResults, ...pipelineResults].filter((result) => !result.ok);
      if (failed.length) {
        setLoadWarning(
          `일부 데이터 로딩에 실패했습니다: ${failed
            .map((result) => `${result.path}(${result.status})`)
            .join(", ")}`
        );
      } else {
        setLoadWarning("");
      }
    } catch {
      setStatus("오프라인");
      setLoadWarning("API 연결에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function submitCommand(event) {
    event.preventDefault();
    if (!command.trim()) return;
    setLoading(true);
    try {
      const data = await api("/api/commands", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: command, execute: true }),
      });
      setCommandResult(data.message ?? "처리되었습니다.");
      setCommand("");
      await loadAll();
    } catch {
      setCommandResult("명령 처리에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function runTest(label, action) {
    setLoading(true);
    try {
      const message = await action();
      setCommandResult(`${label}: ${message}`);
      await loadAll();
    } catch {
      setCommandResult(`${label}: 실패했습니다.`);
    } finally {
      setLoading(false);
    }
  }

  async function runSchedule(schedule) {
    setLoading(true);
    try {
      const data = await api(`/api/schedules/${schedule.id}/run`, {
        method: "POST",
      });
      setCommandResult(data.message ?? `${schedule.name}: 실행 완료`);
      await loadAll();
    } catch (error) {
      setCommandResult(`${schedule.name}: 실행에 실패했습니다. ${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function deleteSource(source) {
    setLoading(true);
    try {
      await api(`/api/expert-sources/${source.id}`, { method: "DELETE" });
      setCommandResult(`${source.name}: 뉴스 소스를 삭제했습니다.`);
      await loadAll();
    } catch {
      setCommandResult(`${source.name}: 삭제에 실패했습니다.`);
    } finally {
      setLoading(false);
    }
  }

  async function deleteInterestArea(area) {
    setLoading(true);
    try {
      await api(`/api/interest-areas/${area.id}`, { method: "DELETE" });
      setCommandResult(`${area.name}: 관심분야를 삭제했습니다.`);
      await loadAll();
    } catch {
      setCommandResult(`${area.name}: 삭제에 실패했습니다.`);
    } finally {
      setLoading(false);
    }
  }

  async function runBackfill() {
    setLoading(true);
    try {
      const data = await api("/api/pipeline/backfill", { method: "POST" });
      if (data.status === "skipped" && data.reason === "pipeline_running") {
        setCommandResult("백필이 이미 실행 중입니다. 잠시 후 다시 확인해주세요.");
        setView("pipeline");
        await loadAll();
        return;
      }
      const collect = data.collect?.inserted ?? 0;
      const classify = data.classify?.inserted ?? 0;
      const cluster = data.cluster?.inserted ?? 0;
      setCommandResult(
        `백필 완료: raw ${collect}건, refined ${classify}건, cluster ${cluster}건`
      );
      setView("pipeline");
      await loadAll();
    } catch (error) {
      setCommandResult(`백필 실행에 실패했습니다: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function runE2E(scheduleType = "interest_area_radar_report") {
    setLoading(true);
    try {
      const data = await api(`/api/e2e/run?schedule_type=${encodeURIComponent(scheduleType)}`, {
        method: "POST",
      });
      const reportTitle = data.result?.report?.title ?? data.result?.message ?? "리포트 생성";
      const notificationChannel = data.result?.notification?.channel ?? "알림 정보 없음";
      setCommandResult(`E2E 완료: ${reportTitle} / notification ${notificationChannel}`);
      setView("pipeline");
      await loadAll();
    } catch (error) {
      setCommandResult(`E2E 실행에 실패했습니다: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function clearReports() {
    setLoading(true);
    try {
      const data = await api("/api/reports/clear", { method: "POST" });
      setCommandResult(
        `리포트 삭제 완료: report ${data.deleted_reports}건, strategy_report ${data.deleted_strategy_reports}건`
      );
      await loadAll();
    } catch {
      setCommandResult("리포트 삭제 실행에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  const testActions = [
    {
      label: "알림 테스트",
      run: async () => {
        const data = await api("/api/notifications/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        return `${data.status}`;
      },
    },
  ];

  useEffect(() => {
    loadAll();
  }, []);

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">stock_scheduler</p>
          <h1>뉴스 파이프라인과 투자 리포트를 한 화면에서 확인합니다.</h1>
        </div>
        <div className="status-panel">
          <span>API {status}</span>
          <strong>{totalCount}</strong>
          <small>로딩된 항목</small>
        </div>
      </section>

      <section className="view-switch" aria-label="화면 전환">
        <button
          className={view === "dashboard" ? "tab-button active" : "tab-button"}
          onClick={() => setView("dashboard")}
          disabled={loading}
        >
          대시보드
        </button>
        <button
          className={view === "pipeline" ? "tab-button active" : "tab-button"}
          onClick={() => setView("pipeline")}
          disabled={loading}
        >
          파이프라인 테이블
        </button>
        <button className="tab-button pipeline-action" onClick={runBackfill} disabled={loading}>
          백필 실행
        </button>
        <button className="tab-button danger-tab" onClick={clearReports} disabled={loading}>
          리포트 삭제
        </button>
      </section>

      <form className="command-bar" onSubmit={submitCommand}>
        <input
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          placeholder="삼성전자 160500원 284주 보유"
          aria-label="자연어 명령"
        />
        <button disabled={loading}>{loading ? "처리 중" : "실행"}</button>
      </form>

      {commandResult && <p className="notice">{commandResult}</p>}
      {loadWarning && <p className="notice">{loadWarning}</p>}

      <section className="summary-strip" aria-label="핵심 데이터 요약">
        <SummaryPill
          label="보유종목"
          count={(items.holdings ?? []).length}
          detail={(items.holdings ?? []).slice(0, 2).map((item) => item.name).join(", ") || "데이터 없음"}
        />
        <SummaryPill
          label="관심종목"
          count={(items.interests ?? []).length}
          detail={(items.interests ?? []).slice(0, 2).map((item) => item.name).join(", ") || "데이터 없음"}
        />
        <SummaryPill
          label="관심분야"
          count={(items.interestAreas ?? []).length}
          detail={(items.interestAreas ?? []).slice(0, 2).map((item) => item.name).join(", ") || "데이터 없음"}
        />
        <SummaryPill
          label="뉴스 소스"
          count={(items.sources ?? []).length}
          detail={(items.sources ?? []).slice(0, 2).map((item) => item.name).join(", ") || "데이터 없음"}
        />
      </section>

      <section className="quick-actions" aria-label="바로 실행">
        <button onClick={loadAll} disabled={loading}>
          새로고침
        </button>
        <button onClick={runBackfill} disabled={loading}>
          백필 실행
        </button>
        <button onClick={() => runE2E("interest_area_radar_report")} disabled={loading}>
          관심분야 E2E
        </button>
        <button onClick={() => runE2E("interest_stock_radar_report")} disabled={loading}>
          관심종목 E2E
        </button>
        <button onClick={clearReports} disabled={loading}>
          리포트 삭제
        </button>
        {testActions.map((item) => (
          <button key={item.label} onClick={() => runTest(item.label, item.run)} disabled={loading}>
            {item.label}
          </button>
        ))}
      </section>

      {view === "dashboard" ? (
        <section className="dashboard-grid">
          <HoldingsCard items={items.holdings ?? []} />
          <InterestsCard items={items.interests ?? []} />
          <InterestAreasCard
            items={items.interestAreas ?? []}
            onPrompt={setCommand}
            onDelete={deleteInterestArea}
            loading={loading}
          />
          <SchedulesCard
            items={items.schedules ?? []}
            onSelect={setSelectedSchedule}
            onRun={runSchedule}
            loading={loading}
          />
          <ReportsCard items={items.reports ?? []} onSelect={setSelectedReport} />
          <SourcesCard
            items={items.sources ?? []}
            onPrompt={setCommand}
            onDelete={deleteSource}
            loading={loading}
          />
        </section>
      ) : (
        <section className="pipeline-grid">
          <article className="data-card pipeline-card">
            <header>
              <div>
                <h2>파이프라인 작업</h2>
                <small>백필 실행과 과거 리포트 삭제를 여기서 바로 할 수 있습니다.</small>
              </div>
            </header>
            <div className="pipeline-actions">
              <button onClick={runBackfill} disabled={loading}>
                백필 실행
              </button>
              <button onClick={() => runE2E("interest_area_radar_report")} disabled={loading}>
                관심분야 E2E
              </button>
              <button onClick={() => runE2E("interest_stock_radar_report")} disabled={loading}>
                관심종목 E2E
              </button>
              <button className="danger-action" onClick={clearReports} disabled={loading}>
                과거 리포트 삭제
              </button>
            </div>
          </article>
          <PipelineTableCard
            title="news_raw"
            subtitle="원본 headline 수집 결과"
            rows={pipelineItems.newsRaw ?? []}
            columns={["id", "source", "title", "published_at", "created_at"]}
            onSelectRow={setSelectedPipelineRow}
          />
          <PipelineTableCard
            title="news_refined"
            subtitle="정제/분류 결과"
            rows={pipelineItems.newsRefined ?? []}
            columns={["id", "news_raw_id", "tickers", "sectors", "importance", "sentiment", "classified_at"]}
            onSelectRow={setSelectedPipelineRow}
          />
          <PipelineTableCard
            title="news_cluster"
            subtitle="테마/내러티브 클러스터"
            rows={pipelineItems.newsCluster ?? []}
            columns={["id", "cluster_key", "theme", "tickers", "importance_score", "created_at"]}
            onSelectRow={setSelectedPipelineRow}
          />
          <PipelineTableCard
            title="strategy_report"
            subtitle="최종 전략 리포트 원본"
            rows={pipelineItems.strategyReports ?? []}
            columns={["id", "report_type", "title", "major_signal_detected", "created_at"]}
            onSelectRow={setSelectedPipelineRow}
          />
          <PipelineTableCard
            title="pipeline_state"
            subtitle="체인 실행 상태와 checkpoint"
            rows={pipelineItems.pipelineState ?? []}
            columns={["id", "pipeline_name", "status", "last_cursor", "last_started_at", "last_finished_at"]}
            onSelectRow={setSelectedPipelineRow}
          />
        </section>
      )}

      {selectedSchedule && (
        <ScheduleModal schedule={selectedSchedule} onClose={() => setSelectedSchedule(null)} />
      )}
      {selectedReport && <ReportModal report={selectedReport} onClose={() => setSelectedReport(null)} />}
      {selectedPipelineRow && (
        <PipelineRowModal row={selectedPipelineRow} onClose={() => setSelectedPipelineRow(null)} />
      )}
    </main>
  );
}

function HoldingsCard({ items }) {
  return (
    <article className="data-card wide">
      <header>
        <h2>보유종목</h2>
        <span>{items.length}</span>
      </header>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <strong>
              {item.name} <em>{item.ticker}</em>
            </strong>
            <div className="metric-row">
              <small>현재가 {money(item.current_price)}</small>
              <small>수량 {dash(item.quantity)}</small>
              <small>평단 {money(item.avg_price)}</small>
            </div>
          </li>
        ))}
        {items.length === 0 && <li className="empty">보유종목이 없습니다.</li>}
      </ul>
    </article>
  );
}

function SummaryPill({ label, count, detail }) {
  return (
    <article className="summary-pill">
      <strong>{label}</strong>
      <span>{count}</span>
      <small>{detail}</small>
    </article>
  );
}

function InterestsCard({ items }) {
  return (
    <article className="data-card">
      <header>
        <h2>관심종목</h2>
        <span>{items.length}</span>
      </header>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <strong>
              {item.name} <em>{item.ticker}</em>
            </strong>
            <small>현재가 {money(item.current_price)}</small>
          </li>
        ))}
        {items.length === 0 && <li className="empty">관심종목이 없습니다.</li>}
      </ul>
    </article>
  );
}

function InterestAreasCard({ items, onPrompt, onDelete, loading }) {
  const example =
    "AI 반도체를 관심분야로 추가하고 키워드는 HBM, 온디바이스AI, 연결 종목은 삼성전자와 SK하이닉스";

  return (
    <article className="data-card">
      <header>
        <h2>관심분야</h2>
        <span>{items.length}</span>
      </header>
      <div className="natural-command-help">
        <small>자연어 명령으로 추가할 수 있습니다.</small>
        <button type="button" className="inline-action" onClick={() => onPrompt(example)} disabled={loading}>
          예시 넣기
        </button>
      </div>
      <ul>
        {items.slice(0, 5).map((item) => (
          <li key={item.id} className="source-row">
            <div>
              <strong>{item.name}</strong>
              <small>
                {item.category} · {(item.keywords ?? []).join(", ") || "-"} ·{" "}
                {(item.linked_tickers ?? []).join(", ") || "-"}
              </small>
            </div>
            <button className="danger-action" onClick={() => onDelete(item)} disabled={loading}>
              삭제
            </button>
          </li>
        ))}
        {items.length === 0 && <li className="empty">관심분야가 없습니다.</li>}
      </ul>
    </article>
  );
}

function SchedulesCard({ items, onSelect, onRun, loading }) {
  return (
    <article className="data-card">
      <header>
        <h2>스케줄</h2>
        <span>{items.length}</span>
      </header>
      <ul>
        {items.map((item) => (
          <li key={item.id} className="schedule-row">
            <button className="row-button" onClick={() => onSelect(item)}>
              <strong>{item.name}</strong>
              <small>
                {item.schedule_type} · {item.cron}
              </small>
            </button>
            <button className="inline-action" onClick={() => onRun(item)} disabled={loading}>
              바로 실행
            </button>
          </li>
        ))}
        {items.length === 0 && <li className="empty">스케줄이 없습니다.</li>}
      </ul>
    </article>
  );
}

function ReportsCard({ items, onSelect }) {
  return (
    <article className="data-card wide">
      <header>
        <h2>분석 리포트</h2>
        <span>{items.length}</span>
      </header>
      <ul>
        {items.slice(0, 5).map((item) => (
          <li key={item.id}>
            <button className="row-button" onClick={() => onSelect(item)}>
              <strong>{item.title}</strong>
              <small>
                {item.report_type} · {item.created_at}
              </small>
            </button>
          </li>
        ))}
        {items.length === 0 && <li className="empty">분석 리포트가 없습니다.</li>}
      </ul>
    </article>
  );
}

function SourcesCard({ items, onPrompt, onDelete, loading }) {
  const addExample = "오건영 SNS를 뉴스 소스로 추가";
  const deleteExample = "오건영 Facebook 뉴스 소스 삭제";

  return (
    <article className="data-card">
      <header>
        <h2>뉴스 소스</h2>
        <span>{items.length}</span>
      </header>
      <div className="natural-command-help">
        <small>자연어 명령으로 추가하거나 삭제할 수 있습니다.</small>
        <button type="button" className="inline-action" onClick={() => onPrompt(addExample)} disabled={loading}>
          추가 예시
        </button>
        <button type="button" className="inline-action" onClick={() => onPrompt(deleteExample)} disabled={loading}>
          삭제 예시
        </button>
      </div>
      <ul>
        {items.slice(0, 5).map((item) => (
          <li key={item.id} className="source-row">
            <div>
              <strong>{item.name}</strong>
              <small>
                {item.category} · {item.platform} · {item.enabled ? "활성" : "비활성"}
              </small>
            </div>
            <button className="danger-action" onClick={() => onDelete(item)} disabled={loading}>
              삭제
            </button>
          </li>
        ))}
        {items.length === 0 && <li className="empty">뉴스 소스가 없습니다.</li>}
      </ul>
    </article>
  );
}

function PipelineTableCard({ title, subtitle, rows, columns, onSelectRow }) {
  return (
    <article className="data-card pipeline-card wide">
      <header>
        <div>
          <h2>{title}</h2>
          <small>{subtitle}</small>
        </div>
        <span>{rows.length}</span>
      </header>
      <div className="table-scroll">
        <table className="pipeline-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="empty-cell">
                  데이터가 없습니다.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id ?? JSON.stringify(row)}
                  className={onSelectRow ? "clickable-row" : ""}
                  onClick={onSelectRow ? () => onSelectRow({ title, row }) : undefined}
                >
                  {columns.map((column) => (
                    <td key={column}>{formatPipelineCell(row[column])}</td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function PipelineRowModal({ row, onClose }) {
  const entries = Object.entries(row.row ?? {});
  return (
    <div className="modal-backdrop fullscreen-backdrop" role="presentation" onClick={onClose}>
      <section
        className="modal fullscreen-modal"
        role="dialog"
        aria-modal="true"
        aria-label="파이프라인 행 상세"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <p className="eyebrow">{row.title}</p>
            <h2>행 상세</h2>
            <small>숨겨진 summary, description, payload도 여기서 확인할 수 있습니다.</small>
          </div>
          <button onClick={onClose}>닫기</button>
        </header>
        <div className="pipeline-detail">
          {entries.map(([key, value]) => (
            <div key={key} className="pipeline-detail-row">
              <strong>{key}</strong>
              <pre>{formatDetailValue(value)}</pre>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function formatDetailValue(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function ReportModal({ report, onClose }) {
  return (
    <div className="modal-backdrop fullscreen-backdrop" role="presentation" onClick={onClose}>
      <section
        className="modal fullscreen-modal"
        role="dialog"
        aria-modal="true"
        aria-label="리포트 상세"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <p className="eyebrow">분석 리포트</p>
            <h2>{report.title}</h2>
            <small>
              {report.report_type} · {report.created_at}
            </small>
          </div>
          <button onClick={onClose}>닫기</button>
        </header>
        <MarkdownView markdown={report.markdown ?? ""} />
      </section>
    </div>
  );
}

function ScheduleModal({ schedule, onClose }) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="스케줄 상세"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <h2>{schedule.name}</h2>
          <button onClick={onClose}>닫기</button>
        </header>
        <dl>
          <dt>타입</dt>
          <dd>{schedule.schedule_type}</dd>
          <dt>대상</dt>
          <dd>{schedule.target_type}</dd>
          <dt>종목</dt>
          <dd>{schedule.tickers?.length ? schedule.tickers.join(", ") : "-"}</dd>
          <dt>주기</dt>
          <dd>{schedule.cron}</dd>
          <dt>상태</dt>
          <dd>{schedule.enabled ? "활성" : "비활성"}</dd>
        </dl>
      </section>
    </div>
  );
}

function MarkdownView({ markdown }) {
  const lines = markdown.split(/\r?\n/);
  const blocks = [];
  let paragraph = [];
  let list = [];

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push({ type: "p", text: paragraph.join(" ") });
      paragraph = [];
    }
  }

  function flushList() {
    if (list.length) {
      blocks.push({ type: "ul", items: list });
      list = [];
    }
  }

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: `h${heading[1].length}`, text: heading[2] });
      return;
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      list.push(bullet[1]);
      return;
    }

    flushList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  flushList();

  if (!blocks.length) {
    return <p className="empty">본문이 없습니다.</p>;
  }

  return (
    <div className="markdown-body">
      {blocks.map((block, index) => {
        if (block.type === "ul") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === "h1") return <h1 key={index}>{renderInlineMarkdown(block.text)}</h1>;
        if (block.type === "h2") return <h2 key={index}>{renderInlineMarkdown(block.text)}</h2>;
        if (block.type === "h3") return <h3 key={index}>{renderInlineMarkdown(block.text)}</h3>;
        return <p key={index}>{renderInlineMarkdown(block.text)}</p>;
      })}
    </div>
  );
}

function renderInlineMarkdown(text) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

createRoot(document.getElementById("root")).render(<App />);
