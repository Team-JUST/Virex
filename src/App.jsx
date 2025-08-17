import { useState, useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Home from './pages/Home';
import Recovery from './pages/Recovery';
import Setting from './pages/Settings';
import Information from './pages/Information';
import './styles/App.css';

function App() {
  const [isDarkMode, setIsDarkMode] = useState(false);

  // Electron 윈도우 배경 동적 변경
  useEffect(() => {
    // Electron 쪽 메시지 전달
    if (window.electron && window.electron.ipcRenderer) {
      window.electron.ipcRenderer.send('set-dark-mode', isDarkMode);
    } else if (window.require) {
      try {
        const { ipcRenderer } = window.require('electron');
        ipcRenderer.send('set-dark-mode', isDarkMode);
      } catch (e) {
        console.error('IPC 전송 실패:', e);
      }
    }

    // CSS 다크모드 전역 적용
    if (isDarkMode) {
      document.documentElement.classList.add('dark-mode');
    } else {
      document.documentElement.classList.remove('dark-mode');
    }
  }, [isDarkMode]);

  return (
    <div className={`container${isDarkMode ? ' dark-mode' : ''}`}>
      <Sidebar />
      <main className="app_main">
        <Routes>
          <Route path="/" element={<Home isDarkMode={isDarkMode} />} />
          <Route path="/fileUpload" element={<Recovery isDarkMode={isDarkMode} />} />
          <Route path="/recovery" element={<Recovery isDarkMode={isDarkMode} />} />
          <Route path="/setting" element={<Setting isDarkMode={isDarkMode} setIsDarkMode={setIsDarkMode} />} />
          <Route path="/information" element={<Information isDarkMode={isDarkMode} />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
