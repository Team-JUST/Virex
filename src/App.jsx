import { useState, useEffect, useRef } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import Button from './components/Button.jsx';
import Alert from './components/Alert.jsx';
import Sidebar from './components/Sidebar';
import Home from './pages/Home';
import Recovery from './pages/Recovery';
import Setting from './pages/Settings';
import Information from './pages/Information';
import './styles/App.css';
import RecoveryPauseIcon from './images/recoveryPauseIcon.svg?react';

function App() {
  const navigate = useNavigate();
  const [showStopRecoverPopup, setShowStopRecoverPopup] = useState(false);
  const [pendingPath, setPendingPath] = useState(null);
  const [isDarkMode, setIsDarkMode] = useState(false);

  const openRef = useRef(false);
  useEffect(() => {
    openRef.current = showStopRecoverPopup;
  }, [showStopRecoverPopup]);

    useEffect(() => {
    const onShow = (e) => {
      if (openRef.current) return; 
      setPendingPath(e.detail?.to || null);
      setShowStopRecoverPopup(true);
    };
    window.addEventListener('show-stop-recover', onShow);
    return () => window.removeEventListener('show-stop-recover', onShow);
  }, []);


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
        console.error("[Debug] IPC send failed : ", e);
      }
    }

    // 다크모드 전역 적용
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
    {showStopRecoverPopup && (
      <Alert
        icon={<RecoveryPauseIcon className="recoveryPause-icon" />}
        title="복구 중단 알림"
        isDarkMode={isDarkMode}
        description={
          <>
            영상 복원이 아직 완료되지 않았습니다.<br />
            이 상태에서 다른 화면으로 이동하면 복구가 중단됩니다.<br />
            그래도 이동하시겠습니까?
          </>
        }
      >
        <div className="alert-buttons">
          <Button
            variant="gray"
            onClick={() => {
              setShowStopRecoverPopup(false);
              setPendingPath(null);
            }}
          >
            취소
          </Button>
          <Button
            variant="dark"
            onClick={() => {
              if (pendingPath) navigate(pendingPath);
              setPendingPath(null);
              setShowStopRecoverPopup(false);
            }}
          >
            이동하기
          </Button>
        </div>
      </Alert>
  )}
    </div>
  );
}



export default App;
