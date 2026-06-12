import { Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import Layout from './components/Layout'
import AlertsPage from './pages/AlertsPage'
import BacktestPage from './pages/BacktestPage'
import ChartPage from './pages/ChartPage'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import PaperPage from './pages/PaperPage'
import PortfolioPage from './pages/PortfolioPage'
import ResearchPage from './pages/ResearchPage'
import SettingsPage from './pages/SettingsPage'
import { useAuthStore } from './stores/auth'

export default function App() {
  const token = useAuthStore((s) => s.token)
  const authQuery = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
  })

  if (authQuery.data?.auth_enabled && !token) {
    return <LoginPage />
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="chart" element={<ChartPage />} />
        <Route path="research" element={<ResearchPage />} />
        <Route path="backtest" element={<BacktestPage />} />
        <Route path="paper" element={<PaperPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="portfolio" element={<PortfolioPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
