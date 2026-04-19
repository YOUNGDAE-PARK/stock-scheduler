import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? `${window.location.protocol}//${window.location.hostname}:8000`;

const sections = [
  { key: "interests", label: "관심종목", path: "/api/interests" },
  { key: "interestAreas", label: "관심분야", path: "/api/interest-areas" },
  { key: "holdings", label: "보유종목", path: "/api/holdings" },
  { key: "schedules", label: "스케줄", path: "/api/schedules" },
  { key: "reports", label: "분석 리포트", path: "/api/reports" },
  { key: "sources", label: "경제뉴스 소스", path: "/api/expert-sources" }
];

function dash(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "-";
  return `${value}${suffix}`;
}

function money(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString();
}

function App() {
  const [status, setStatus] = useState("확인 중");
  const [items, setItems] = useState({});
  const [command, setCommand] = useState("");
  const [commandResult, setCommandResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedSchedule, setSelectedSchedule] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);

  const totalCount = useMemo(
    () => Object.values(items).reduce((sum, value) => sum + (Array.isArray(value) ? value.length : 0), 0),
    [items]
  );

  async function api(path, options) {
    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) throw new Error(`API ${response.status}`);
    return response.json();
  }

  async function loadAll() {
    setLoading(true);
    try {
      const health = await fetch(`${API_BASE}/api/health`);
      setStatus(health.ok ? "연결됨" : "확인 필요");
      const entries = await Promise.all(
        sections.map(async (section) => {
          const response = await fetch(`${API_BASE}${section.path}`);
          return [section.key, response.ok ? await response.json() : []];
        })
      );
      setItems(Object.fromEntries(entries));
    } catch {
      setStatus("오프라인");
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
        body: JSON.stringify({ text: command, execute: true })
      });
      setCommandResult(data.message ?? "처리했습니다.");
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
      const data = await api(`/api/schedules/${schedule.id}/run`, { method: "POST" });
      setCommandResult(data.message ?? `${schedule.name}: 실행 완료`);
      await loadAll();
    } catch {
      setCommandResult(`${schedule.name}: 실행에 실패했습니다.`);
    } finally {
      setLoading(false);
    }
  }

  async function deleteSource(source) {
    setLoading(true);
    try {
      await api(`/api/expert-sources/${source.id}`, { method: "DELETE" });
      setCommandResult(`${source.name}: 경제뉴스 소스 삭제 완료`);
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
      setCommandResult(`${area.name}: 관심분야 삭제 완료`);
      await loadAll();
    } catch {
      setCommandResult(`${area.name}: 삭제에 실패했습니다.`);
    } finally {
      setLoading(false);
    }
  }

  const testActions = [
    {
      label: "관심종목 테스트",
      run: async () => {
        const data = await api("/api/interests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ticker: "005930", market: "KR", name: "삼성전자", tags: ["테스트"] })
        });
        return `${data.name} 추가`;
      }
    },
    {
      label: "보유종목 테스트",
      run: async () => {
        const data = await api("/api/holdings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ticker: "TSLA", market: "US", name: "Tesla", quantity: 1, avg_price: 180 })
        });
        return `${data.name} 1주 추가`;
      }
    },
    {
      label: "분석 테스트",
      run: async () => {
        const data = await api("/api/analysis/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target: { ticker: "005930", market: "KR", name: "삼성전자" } })
        });
        return `${data.status}`;
      }
    },
    {
      label: "알림 테스트",
      run: async () => {
        const data = await api("/api/notifications/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        return `${data.status}`;
      }
    }
  ];

  useEffect(() => {
    loadAll();
  }, []);

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">stock_scheduler</p>
          <h1>오늘 볼 종목과 알림을 한 번에.</h1>
        </div>
        <div className="status-panel">
          <span>API {status}</span>
          <strong>{totalCount}</strong>
          <small>저장된 항목</small>
        </div>
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

      <section className="quick-actions" aria-label="스케줄 없이 테스트">
        <button onClick={loadAll} disabled={loading}>새로고침</button>
        {testActions.map((item) => (
          <button key={item.label} onClick={() => runTest(item.label, item.run)} disabled={loading}>
            {item.label}
          </button>
        ))}
      </section>

      <section className="dashboard-grid">
        <HoldingsCard items={items.holdings ?? []} />
        <InterestsCard items={items.interests ?? []} />
        <InterestAreasCard
          items={items.interestAreas ?? []}
          onPrompt={setCommand}
          onDelete={deleteInterestArea}
          loading={loading}
        />
        <SchedulesCard items={items.schedules ?? []} onSelect={setSelectedSchedule} onRun={runSchedule} loading={loading} />
        <ReportsCard items={items.reports ?? []} onSelect={setSelectedReport} />
        <SourcesCard
          items={items.sources ?? []}
          onPrompt={setCommand}
          onDelete={deleteSource}
          loading={loading}
        />
      </section>

      {selectedSchedule && (
        <ScheduleModal schedule={selectedSchedule} onClose={() => setSelectedSchedule(null)} />
      )}
      {selectedReport && (
        <ReportModal report={selectedReport} onClose={() => setSelectedReport(null)} />
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
            <strong>{item.name} <em>{item.ticker}</em></strong>
            <div className="metric-row">
              <small>현재주가 {money(item.current_price)}</small>
              <small>수량 {dash(item.quantity)}</small>
              <small>갯수 {dash(item.quantity, item.quantity ? "주" : "")}</small>
              <small>평균 {money(item.avg_price)}</small>
            </div>
          </li>
        ))}
        {items.length === 0 && <li className="empty">보유종목이 없습니다.</li>}
      </ul>
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
            <strong>{item.name} <em>{item.ticker}</em></strong>
            <small>현재주가 {money(item.current_price)}</small>
          </li>
        ))}
        {items.length === 0 && <li className="empty">관심종목이 없습니다.</li>}
      </ul>
    </article>
  );
}

function InterestAreasCard({ items, onPrompt, onDelete, loading }) {
  const example = "AI 반도체를 관심분야로 추가하고 키워드는 HBM, 온디바이스 AI, 연결 종목은 삼성전자와 SK하이닉스";
  return (
    <article className="data-card">
      <header>
        <h2>관심분야</h2>
        <span>{items.length}</span>
      </header>
      <div className="natural-command-help">
        <small>자연어 명령으로 추가합니다.</small>
        <button type="button" className="inline-action" onClick={() => onPrompt(example)} disabled={loading}>
          예시 입력
        </button>
      </div>
      <ul>
        {items.slice(0, 5).map((item) => (
          <li key={item.id} className="source-row">
            <div>
              <strong>{item.name}</strong>
              <small>{item.category} · {(item.keywords ?? []).join(", ") || "-"} · {(item.linked_tickers ?? []).join(", ") || "-"}</small>
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
              <small>{item.cron}</small>
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
              <small>{item.report_type} · {item.created_at}</small>
            </button>
          </li>
        ))}
        {items.length === 0 && <li className="empty">분석 리포트가 없습니다.</li>}
      </ul>
    </article>
  );
}

function SourcesCard({ items, onPrompt, onDelete, loading }) {
  const addExample = "오건영 SNS를 경제뉴스 참고소스로 추가";
  const deleteExample = "오건영 Facebook 경제뉴스 소스 삭제";
  return (
    <article className="data-card">
      <header>
        <h2>경제뉴스 소스</h2>
        <span>{items.length}</span>
      </header>
      <div className="natural-command-help">
        <small>자연어 명령으로 추가하거나 삭제합니다.</small>
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
              <small>{item.category} · {item.platform} · {item.enabled ? "활성" : "비활성"}</small>
            </div>
            <button className="danger-action" onClick={() => onDelete(item)} disabled={loading}>
              삭제
            </button>
          </li>
        ))}
        {items.length === 0 && <li className="empty">경제뉴스 소스가 없습니다.</li>}
      </ul>
    </article>
  );
}

function ReportModal({ report, onClose }) {
  return (
    <div className="modal-backdrop fullscreen-backdrop" role="presentation" onClick={onClose}>
      <section
        className="modal fullscreen-modal"
        role="dialog"
        aria-modal="true"
        aria-label="분석 리포트 상세"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <p className="eyebrow">분석 리포트</p>
            <h2>{report.title}</h2>
            <small>{report.report_type} · {report.created_at}</small>
          </div>
          <button onClick={onClose}>닫기</button>
        </header>
        <MarkdownView markdown={report.markdown ?? ""} />
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

function ScheduleModal({ schedule, onClose }) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="modal" role="dialog" aria-modal="true" aria-label="스케줄 상세" onClick={(event) => event.stopPropagation()}>
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

createRoot(document.getElementById("root")).render(<App />);
