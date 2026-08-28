import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { Icon, ToastHost } from "./components.jsx";
import {
  BenchmarkDetailPage,
  BenchmarksPage,
  DatasetDetailPage,
  DatasetsPage,
  OverviewPage,
  TaskDetailPage,
  TaskReportPage,
  TasksPage,
} from "./pages.jsx";

const NAV = [
  { path: "/overview", label: "数据概览", icon: "dashboard" },
  { path: "/tasks", label: "评估中心", icon: "list" },
  { path: "/datasets", label: "数据集", icon: "database" },
  { path: "/benchmarks", label: "评估基准", icon: "target" },
  { path: "/datasources", label: "数据源连接", icon: "database", disabled: true },
];

function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/overview";
  return raw.startsWith("/") ? raw : `/${raw}`;
}

function App() {
  const [route, setRoute] = useState(parseHash());

  useEffect(() => {
    function onHashChange() {
      setRoute(parseHash());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function navigate(path) {
    window.location.hash = path;
  }

  const segments = route.split("/").filter(Boolean);
  const section = segments[0] || "overview";
  const detailId = segments[1] || null;
  const subRoute = segments[2] || null;

  let page = <OverviewPage />;
  if (section === "tasks" && detailId && subRoute === "report") {
    page = <TaskReportPage id={detailId} navigate={navigate} />;
  } else if (section === "tasks" && detailId) {
    page = <TaskDetailPage id={detailId} navigate={navigate} />;
  } else if (section === "tasks") {
    page = <TasksPage navigate={navigate} />;
  } else if (section === "datasets" && detailId) {
    page = <DatasetDetailPage id={detailId} navigate={navigate} />;
  } else if (section === "datasets") {
    page = <DatasetsPage navigate={navigate} />;
  } else if (section === "benchmarks" && detailId) {
    page = <BenchmarkDetailPage id={detailId} navigate={navigate} />;
  } else if (section === "benchmarks") {
    page = <BenchmarksPage navigate={navigate} />;
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="chart" size={18} />
          </div>
          <div>
            <div className="brand-name">智搜评估</div>
            <div className="brand-sub">策略效果评估平台</div>
          </div>
        </div>

        <nav className="nav">
          <div className="nav-label">工作台</div>
          {NAV.map((item) => (
            <button
              key={item.path}
              className={`nav-item${route.startsWith(item.path) ? " active" : ""}${item.disabled ? " disabled" : ""}`}
              onClick={() => !item.disabled && navigate(item.path)}
              disabled={item.disabled}
              aria-current={route.startsWith(item.path) ? "page" : undefined}
            >
              <span className="nav-icon">
                <Icon name={item.icon} size={18} />
              </span>
              <span>{item.label}</span>
              {item.disabled ? <span style={{ fontSize: 11 }}>待开发</span> : null}
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">人工定标准 · AI 做执行 · 人工兜置信</div>
      </aside>

      <main className="main">
        <header className="topbar">
          <span className="topbar-title">智搜策略效果评估</span>
          <div className="topbar-user">
            <span className="avatar">孙</span>
            <span>孙颖</span>
          </div>
        </header>
        {page}
      </main>
      <ToastHost />
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
