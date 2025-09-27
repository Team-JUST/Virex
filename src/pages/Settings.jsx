import React, { useState } from 'react';
import '../styles/Setting.css';
import Button from '../components/Button';

const Settings = ({ isDarkMode, setIsDarkMode }) => {
  const [notificationsOn, setNotificationsOn] = useState(true);

  const handlePathChange = () => {
    const fakePath = 'C:\\Users\\Retato\\Recovered'; // 테스트용
    setSavePath(fakePath);
  };

  const [showCacheMessage, setShowCacheMessage] = useState(false);

  const handleCacheClear = async () => {
    if (window.api?.clearCache) {
      await window.api.clearCache();
    }
    setShowCacheMessage(true);
    setTimeout(() => setShowCacheMessage(false), 4000);
  };

  const handleNotificationToggle = () => {
    const newValue = !notificationsOn;
    setNotificationsOn(newValue);
    window.api?.setNotifications(newValue);
  };

  return (
    <div className={`settings_page ${isDarkMode ? 'dark-mode' : ''}`}>
      <h1 className="settings_title">Setting</h1>
      <p className="settings_desc">Virex 애플리케이션의 설정을 관리하세요</p>

      {/* 테마 설정 */}
      <div className="settings_box setting-row">
        <div className="setting-text">
          <h2 className="settings_box_title">테마 설정</h2>
          <p className="settings_box_desc">다크 모드를 활성화하거나 비활성화합니다</p>
        </div>
        <div className="setting-action">
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={isDarkMode}
              onChange={() => setIsDarkMode(!isDarkMode)}
            />
            <span className="slider"></span>
          </label>
        </div>
      </div>

      {/* 캐시 삭제 */}
      <div className="settings_box setting-row">
        <div className="setting-text">
          <h2 className="settings_box_title">
            캐시 삭제
            {showCacheMessage && (
              <span className="cache-inline-msg">캐시 파일이 삭제되었습니다</span>
            )}
          </h2>
          <p className="settings_box_desc">임시 캐시 파일을 정리하여 저장 공간을 확보합니다.</p>
        </div>
        <div className="setting-action">
          <Button variant="dark" onClick={handleCacheClear}>캐시 삭제</Button>
        </div>
      </div>

      {/* 알림 설정 */}
      <div className="settings_box setting-row">
        <div className="setting-text">
          <h2 className="settings_box_title">알림 설정</h2>
          <p className="settings_box_desc">복구 완료 등의 주요 이벤트에 대한 알림을 받습니다</p>
        </div>
        <div className="setting-action">
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={notificationsOn}
              onChange={handleNotificationToggle}
            />
            <span className="slider"></span>
          </label>
        </div>
      </div>

    </div>
  );
};

export default Settings;
