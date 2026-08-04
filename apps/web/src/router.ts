import { createRouter, createWebHistory } from 'vue-router'
import ChatPage from './routes/ChatPage.vue'
import GraphPage from './routes/GraphPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: ChatPage },
    { path: '/graph', component: GraphPage },
  ],
})

export default router
