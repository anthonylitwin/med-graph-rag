<template>
  <nav class="app-nav">
    <RouterLink to="/">
      Chat
    </RouterLink>
    <RouterLink to="/graph">
      Graph
    </RouterLink>
    <RouterLink to="/ingestion">
      Ingestion
    </RouterLink>
  </nav>

  <RouterView />
</template>

<style scoped>
.app-nav {
  padding: 1rem;
  border-bottom: 1px solid #ddd;
  display: flex;
  gap: 1rem;
}
</style>
