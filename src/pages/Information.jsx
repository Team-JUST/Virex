import React from 'react';
import '../styles/Information.css';

const Information = ({ isDarkMode }) => {
  return (
    <div className={`info_page${isDarkMode ? ' dark-mode' : ''}`}>
      <h1 className={`info_title${isDarkMode ? ' dark-mode' : ''}`}>Information</h1>
      {/* 소프트웨어 정보 */}
      <div className={`info_box${isDarkMode ? ' dark-mode' : ''}`}>
        <h1 className={`info_section_title${isDarkMode ? ' dark-mode' : ''}`}>소프트웨어 정보</h1>
        <table className={`info_table${isDarkMode ? ' dark-mode' : ''}`}>
          <tbody>
            <tr className="stack-divider">
              <th>도구명</th>
              <td>Virex</td>
            </tr>
            <tr>
              <th>버전</th>
              <td>v2.0.0</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* 개발자 정보 */}
      <div className={`info_box${isDarkMode ? ' dark-mode' : ''}`}>
        <h1 className={`info_section_title${isDarkMode ? ' dark-mode' : ''}`}>개발자 정보</h1>
        <table className={`info_table${isDarkMode ? ' dark-mode' : ''}`}>
          <tbody>
            <tr className="stack-divider">
              <th>팀</th>
              <td>JUST</td>
            </tr>
            <tr className="stack-divider">
              <th>개발자</th>
              <td>김세연, 마유진, 최리안</td>
            </tr>
            <tr className="stack-divider">
              <th>문의</th>
              <td>justvx2025@gmail.com</td>
            </tr>
            <tr>
              <th>GitHub</th>
              <td><a href="https://github.com/Team-JUST/Virex" target="_blank" rel="noreferrer" className={isDarkMode ? 'dark-mode' : ''}>https://github.com/Team-JUST/Virex</a></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* 기술 스택 */}
      <div className={`info_box${isDarkMode ? ' dark-mode' : ''}`}>
        <h1 className={`info_section_title${isDarkMode ? ' dark-mode' : ''}`}>스택 정보</h1>
        <table className={`info_table${isDarkMode ? ' dark-mode' : ''}`}>
          <tbody>
            <tr className="stack-divider">
              <th>프론트엔드</th>
              <td>
                <span className="tag">Electron</span>
                <span className="tag">React</span>
                <span className="tag">JavaScript</span>
                <span className="tag">Vite</span>
                <span className="tag">CSS</span>
              </td>
            </tr>
            <tr className="stack-divider">
              <th>백엔드</th>
              <td>
                <span className="tag">Python</span>
                <span className="tag">Node.js</span>
              </td>
            </tr>
            <tr>
              <th>기타 도구</th>
              <td>
                <span className="tag">FFmpeg</span>
                <span className="tag">FFprobe</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Information;
