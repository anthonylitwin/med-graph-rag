<template>
  <header class="app-shell-header">
    <RouterLink
      class="brand"
      to="/"
    >
      <span class="brand-mark">MG</span>
      <span>
        <strong>MedGraphRAG</strong>
        <small>Biomedical QA workbench</small>
      </span>
    </RouterLink>

    <nav
      class="app-nav"
      aria-label="Primary navigation"
    >
      <RouterLink to="/">
        Home
      </RouterLink>
      <RouterLink to="/chat">
        Chat
      </RouterLink>
      <RouterLink to="/graph">
        Graph
      </RouterLink>
      <RouterLink to="/ingestion">
        Ingestion
      </RouterLink>
      <RouterLink to="/administration">
        Administration
      </RouterLink>
    </nav>
  </header>

  <RouterView />
</template>

<style scoped>
.app-shell-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 86%, transparent);
  padding: 14px 24px;
  backdrop-filter: blur(14px);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: fit-content;
  color: var(--text-h);
  text-decoration: none;
}

.brand-mark {
  display: inline-grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: #fff;
  font-size: 13px;
  font-weight: 900;
}

.brand strong,
.brand small {
  display: block;
}

.brand strong {
  line-height: 1.1;
}

.brand small {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.2;
}

.app-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.app-nav a {
  border: 1px solid transparent;
  border-radius: 999px;
  color: var(--text);
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  padding: 10px 12px;
  text-decoration: none;
  transition:
    background 160ms ease,
    border-color 160ms ease,
    color 160ms ease;
}

.app-nav a:hover {
  border-color: var(--border-strong);
  color: var(--text-h);
}

.app-nav a.router-link-exact-active {
  border-color: var(--accent-border);
  background: var(--accent-bg);
  color: var(--accent);
}

@media (max-width: 760px) {
  .app-shell-header {
    align-items: flex-start;
    flex-direction: column;
    padding: 12px 16px;
  }

  .app-nav {
    justify-content: flex-start;
    width: 100%;
  }
}
</style>
