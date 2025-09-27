import React, { useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import '../styles/Sidebar.css';

import LogoIcon from '../images/logo.svg?react';
import HomeIcon from '../images/home.svg?react';
import RecoveryIcon from '../images/recovery.svg?react';
import SettingIcon from '../images/setting.svg?react';
import InfoIcon from '../images/information.svg?react';

const Sidebar = ({ isDarkMode }) => {
  const location = useLocation();
  const navigate = useNavigate();

  const handleNav = (e, to) => {
  e.preventDefault();
  const g = window.__recoverGuard;
  const isOnRecovery = location.pathname === '/recovery' || location.pathname === '/fileUpload';
  const isRecoveryMenu = to === '/fileUpload';

  if (isOnRecovery && isRecoveryMenu && g?.isRecovering && Number(g.progress) < 100) {
    return;
  }
  if (g?.isRecovering && Number(g.progress) < 100) {
    window.dispatchEvent(new CustomEvent('show-stop-recover', { detail: { to } }));
    return;
  }
  navigate(to);
  };

  // 다크모드 동기화
  useEffect(() => {
    if (isDarkMode) document.body.classList.add('dark-mode');
    else document.body.classList.remove('dark-mode');
  }, [isDarkMode]);

  const navItems = [
    { path: '/', label: 'HOME', icon: HomeIcon, alt: 'HOME 아이콘' },
    { path: '/fileUpload', label: 'Recovery', icon: RecoveryIcon, alt: 'Recovery 아이콘' },
    { path: '/setting', label: 'Setting', icon: SettingIcon, alt: 'Setting 아이콘' },
    { path: '/information', label: 'Information', icon: InfoIcon, alt: 'Information 아이콘' },
  ];

  return (
    <div id="sidebar" className={`container${isDarkMode ? ' dark-mode' : ''}`}>
      <div className="menu_box">
        <div className="logo_section">
          <LogoIcon className="logo_icon" alt="앱로고" />
          <span className="logo_text">Virex</span>
        </div>
        <div className="menu_title_section">
          <div className="menu_title">MENU</div>
          <div className="menu_divider" />
        </div>
        <ul className="menu_list">
          {navItems.map(({ path, label, icon, alt }) => {
            const g = window.__recoverGuard;
            const isRecovering = g?.isRecovering && Number(g.progress) < 100;
            const isRecoveryMenu = path === '/fileUpload';
            const disabled = isRecoveryMenu && isRecovering;
            return (
              <li key={path}>
                <Link
                  to={path}
                  onClick={disabled ? (e) => e.preventDefault() : (e) => handleNav(e, path)}
                  className={`menu_item${location.pathname === path ? ' active' : ''}${disabled ? ' disabled' : ''}`}
                  style={disabled ? { pointerEvents: 'none', cursor: 'not-allowed' } : {}}
                  tabIndex={disabled ? -1 : 0}
                  aria-disabled={disabled}
                >
                  {React.createElement(icon, { className: 'menu_icon', alt })}
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
};

export default Sidebar;
