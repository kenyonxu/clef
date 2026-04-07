import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Workspace } from './pages/Workspace'
import { Settings } from './pages/Settings'
import { Sessions } from './pages/Sessions'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Workspace />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/sessions" element={<Sessions />} />
      </Routes>
    </BrowserRouter>
  )
}
