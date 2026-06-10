import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Placeholder from './pages/Placeholder'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Placeholder title="Dashboard" />} />
        <Route path="chart" element={<Placeholder title="Chart" />} />
        <Route path="research" element={<Placeholder title="Research" />} />
        <Route path="backtest" element={<Placeholder title="Backtest" />} />
        <Route path="paper" element={<Placeholder title="Paper Trading" />} />
        <Route path="portfolio" element={<Placeholder title="Portfolio" />} />
        <Route path="settings" element={<Placeholder title="Settings" />} />
      </Route>
    </Routes>
  )
}
