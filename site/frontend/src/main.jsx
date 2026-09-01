import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { api } from "./api.js";
import { Icon, ToastHost } from "./components.jsx";
import { AccountBar, LoginView, MembersPage } from "./account.jsx";
import { ManualEvalPage, ManualAnnotatePage, ManualSummaryPage } from "./manual.jsx";
import {
  BenchmarkDetailPage,
  BenchmarksPage,
  DatasetDetailPage,
  DatasetsPage,
  OverviewPage,
  ReportTemplateDetailPage,
  ReportTemplatesPage,
  TaskDetailPage,
  TaskReportPage,
  TasksPage,
} from "./pages.jsx";

// 使用指南（GitHub Pages 托管的静态单页，见仓库 gh-pages 分支）。侧边栏左下角入口。
const GUIDE_URL = "https://qiankzhang.github.io/ZhiSouAiEvaluate/";

const NAV = [
  { path: "/overview", label: "数据概览", icon: "dashboard" },
  {
    path: "/tasks",
    label: "AI评估中心",
    icon: "list",
    // 默认展开，点击父项可收起/展开（状态记忆在 localStorage）；处于子路由时强制展开
    children: [
      { path: "/datasets", label: "数据集", icon: "database" },
      { path: "/benchmarks", label: "评估基准", icon: "target" },
      { path: "/report-templates", label: "评估报告模板", icon: "file" },
    ],
  },
  { path: "/manual-eval", label: "人工评估中心", icon: "list" },
];

function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/overview";
  return raw.startsWith("/") ? raw : `/${raw}`;
}

// 顶部导航栏的当日模型调用额度提示（API.md：默认 1000 次/天）。每 30s 刷新一次。
function QuotaBadge() {
  const [quota, setQuota] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .get("/api/quota")
        .then((data) => alive && setQuota(data))
        .catch(() => {});
    load();
    const timer = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  if (!quota) return null;
  const over = quota.remaining_calls <= 0;
  return (
    <span
      className={`topbar-quota${over ? " over" : ""}`}
      title={`每日模型调用额度上限 ${quota.limit} 次${over ? "，今日额度已用完" : ""}`}
    >
      今日模型调用额度 {quota.calls} / {quota.limit} 次
    </span>
  );
}

const NAV_COLLAPSED_KEY = "nav-collapsed";

function App() {
  const [route, setRoute] = useState(parseHash());
  // undefined = 会话状态未知（加载中）；null = 未登录；对象 = 已登录
  const [me, setMe] = useState(undefined);
  // 被手动收起的父级导航路径集合（默认空 = 全部展开），记忆在 localStorage
  const [navCollapsed, setNavCollapsed] = useState(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(NAV_COLLAPSED_KEY) || "[]"));
    } catch {
      return new Set();
    }
  });

  function toggleNav(path) {
    setNavCollapsed((prev) => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      try {
        localStorage.setItem(NAV_COLLAPSED_KEY, JSON.stringify([...next]));
      } catch {
        /* ignore storage errors (e.g. private mode) */
      }
      return next;
    });
  }

  useEffect(() => {
    function onHashChange() {
      setRoute(parseHash());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const refreshMe = useCallback(() => {
    api
      .get("/api/auth/me")
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  useEffect(() => {
    refreshMe();
    const onAuthRequired = () => setMe(null);
    window.addEventListener("auth:required", onAuthRequired);
    return () => window.removeEventListener("auth:required", onAuthRequired);
  }, [refreshMe]);

  function navigate(path) {
    window.location.hash = path;
  }

  if (me === undefined) return <div className="login-page" />;
  if (me === null) return <LoginView onLogin={setMe} />;

  const segments = route.split("/").filter(Boolean);
  const section = segments[0] || "overview";
  const detailId = segments[1] || null;
  const subRoute = segments[2] || null;

  let page = <OverviewPage />;
  if (section === "members") {
    page = <MembersPage me={me} />;
  } else if (!me.org) {
    page = (
      <div className="content">
        <div className="empty">
          <div className="empty-title">你尚未加入任何组织</div>
          <div>加入「智搜产品」后即可查看数据集、评估基准与评估任务。请联系组织内成员在「成员管理」中邀请你的账号（{me.account}）。</div>
        </div>
      </div>
    );
  } else if (section === "tasks" && detailId && subRoute === "report") {
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
  } else if (section === "report-templates" && detailId) {
    page = <ReportTemplateDetailPage id={detailId} navigate={navigate} />;
  } else if (section === "report-templates") {
    page = <ReportTemplatesPage navigate={navigate} />;
  } else if (section === "manual-eval" && detailId && subRoute === "summary") {
    page = <ManualSummaryPage id={detailId} navigate={navigate} />;
  } else if (section === "manual-eval" && detailId) {
    page = <ManualAnnotatePage id={detailId} navigate={navigate} />;
  } else if (section === "manual-eval") {
    page = <ManualEvalPage navigate={navigate} />;
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
          {NAV.map((item) => {
            const hasChildren = Boolean(item.children);
            // 处于某个子路由时强制展开，避免“在数据集页却看不到菜单”
            const onChildRoute = hasChildren && item.children.some((c) => route.startsWith(c.path));
            const collapsed = hasChildren && navCollapsed.has(item.path) && !onChildRoute;

            const renderItem = (navItem, isChild) => {
              const blocked = navItem.disabled || !me.org;
              const isActive = route.startsWith(navItem.path);
              const isParent = navItem === item && hasChildren;
              return (
                <button
                  key={navItem.path}
                  className={`nav-item${isChild ? " nav-sub" : ""}${isActive ? " active" : ""}${blocked ? " disabled" : ""}`}
                  onClick={() => {
                    if (blocked) return;
                    navigate(navItem.path);
                    if (isParent) toggleNav(navItem.path);
                  }}
                  disabled={blocked}
                  aria-current={isActive ? "page" : undefined}
                  aria-expanded={isParent ? !collapsed : undefined}
                >
                  <span className="nav-icon">
                    <Icon name={navItem.icon} size={18} />
                  </span>
                  <span>{navItem.label}</span>
                  {navItem.disabled ? <span style={{ fontSize: 11 }}>待开发</span> : null}
                  {isParent ? (
                    <Icon name="chevron" size={14} className={`nav-caret${collapsed ? "" : " open"}`} />
                  ) : null}
                </button>
              );
            };
            return (
              <React.Fragment key={item.path}>
                {renderItem(item, false)}
                {hasChildren && !collapsed ? (
                  <div className="nav-children">
                    {item.children.map((child) => renderItem(child, true))}
                  </div>
                ) : null}
              </React.Fragment>
            );
          })}
        </nav>

        <a className="nav-item nav-guide" href={GUIDE_URL} target="_blank" rel="noopener noreferrer">
          <span className="nav-icon">
            <Icon name="book" size={18} />
          </span>
          <span>使用指南</span>
          <Icon name="external" size={13} className="nav-guide-ext" />
        </a>

        <div className="sidebar-foot">人工定标准 · AI 做执行 · 人工兜置信</div>
      </aside>

      <main className="main">
        <header className="topbar">
          <span className="topbar-title">智搜策略效果评估</span>
          <div className="topbar-right">
            <QuotaBadge />
            <AccountBar me={me} onChange={setMe} navigate={navigate} />
          </div>
        </header>
        {page}
      </main>
      <ToastHost />
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
