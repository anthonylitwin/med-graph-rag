import { createRouter, createWebHistory } from 'vue-router'
import HomePage from './routes/HomePage.vue'
import ChatPage from './routes/ChatPage.vue'
import GraphPage from './routes/GraphPage.vue'
import IngestionPage from './routes/IngestionPage.vue'
import AdministrationPage from './routes/AdministrationPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomePage },
    { path: '/chat', component: ChatPage },
    { path: '/graph', component: GraphPage },
    { path: '/ingestion', component: IngestionPage },
    { path: '/administration', component: AdministrationPage },
  ],
})

export default router
