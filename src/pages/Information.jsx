import React from 'react';
import '../styles/Information.css';

const Information = ({ isDarkMode }) => {
  return (
    <div className={`info_page${isDarkMode ? ' dark-mode' : ''}`}>
      <h1 className={`info_title${isDarkMode ? ' dark-mode' : ''}`}>Information</h1>
      {/* 소프트웨어 정보 */}
      <div className={`info_box${isDarkMode ? ' dark-mode' : ''}`}>
        <h1 className={`info_section_title${isDarkMode ? ' dark-mode' : ''}`}>  소프트웨어 정보</h1>
        <table className={`info_table${isDarkMode ? ' dark-mode' : ''}`}>
          <tbody>
            <tr className="stack-divider">
              <th>제품명</th>
              <td>Virex</td>
            </tr>
            <tr className="stack-divider">
              <th>버전</th>
              <td>v1.0.0</td>
            </tr>
            <tr>
              <th>출시일</th>
              <td>2025년 8월 20일</td>
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
              <th>문의</th> 
              <td>seyeon680895@gmail.com</td>
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
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Information;
