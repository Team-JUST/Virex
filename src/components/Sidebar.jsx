import React, { useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import '../styles/Sidebar.css';

import LogoIcon from '../images/logo.svg';
import HomeIcon from '../images/home.svg';
import RecoveryIcon from '../images/recovery.svg';
import SettingIcon from '../images/setting.svg';
import InfoIcon from '../images/information.svg';

const Sidebar = ({ isDarkMode }) => {
  const location = useLocation();
  const navigate = useNavigate();

  const handleNav = (e, to) => {
  e.preventDefault();
  const g = window.__recoverGuard;
  const isOnRecovery =
  location.pathname === '/recovery' || location.pathname === '/fileUpload';

  if (isOnRecovery && g?.isRecovering && Number(g.progress) < 100) {
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
          <img src={LogoIcon} alt="앱로고" className="logo_icon" />
          <span className="logo_text">Virex</span>
        </div>
        <div className="menu_title_section">
          <div className="menu_title">MENU</div>
          <div className="menu_divider" />
        </div>
        <ul className="menu_list">
          {navItems.map(({ path, label, icon, alt }) => (
            <li key={path}>
              <Link
                to={path}
                onClick={(e) => handleNav(e, path)}  
                className={`menu_item${location.pathname === path ? ' active' : ''}`}
              >
                <img src={icon} alt={alt} className="menu_icon" />
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default Sidebar;
