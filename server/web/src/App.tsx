import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Toast } from './components/Toast'
import { Workspace } from './pages/Workspace'
import { Settings } from './pages/Settings'
import { Sessions } from './pages/Sessions'

export function App() {
  return (
    <BrowserRouter>
      <Toast />
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Workspace />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/sessions" element={<Sessions />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
