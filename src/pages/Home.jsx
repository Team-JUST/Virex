import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import '../styles/Home.css';
import '../styles/Button.css';
import Button from '../components/Button.jsx';
import DriveIcon from '../images/drive.svg?react';
import FolderIcon from '../images/folder.svg?react';
import FileIcon from '../images/file.svg?react';

function bytesToGB(n) {
  if (!n || n <= 0) return '0 GB';
  return `${(n / (1024 ** 3)).toFixed(1)} GB`;
}

function normalizePath(p) {
  if (!p) return '';
  return p.replace(/\\+$/, '').toLowerCase();
}

function formatDrivePath(folderPath, mountPath) {
  if (!folderPath) return '';
  if (mountPath && folderPath.startsWith(mountPath)) {
    const driveLetterMatch = mountPath.match(/^([A-Z]):/i);
    const driveText = driveLetterMatch ? `${driveLetterMatch[1].toUpperCase()}: 드라이브` : mountPath;
    const rest = folderPath.slice(mountPath.length).replace(/^\\+/, '');
    return rest ? `${driveText}\\${rest}` : driveText;
  }
  return folderPath;
}

function DriveCard({ drive, onClick }) {
  const { size, free } = drive;
  const used = size > 0 ? size - free : 0;
  const usedPercent = size > 0 ? Math.round((used / size) * 100) : 0;

  const sizeText =
    size > 0
      ? `${bytesToGB(used)} / ${bytesToGB(size)}`
      : '정보 없음';

  return (
    <div
      className="drive_card"
      onClick={() => onClick(drive.mount)}
      title={drive.mount}
    >
      <div className="info">
        <div className="drive_title">
          <DriveIcon className="drive_icon" />
          <strong>{drive.label || drive.mount}</strong>
        </div>
        <div>
          <div>{sizeText}</div>
          <div className="bar">
            <div
              className="bar_fill"
              style={{ width: `${usedPercent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function ExplorerView({
  mountPath,
  currentPath,
  entries,
  selectedFile,
  onBack,
  onSelectDrive,
  onOpenDir,
  onSelectFile,
  isDarkMode,
}) {
  const displayPath = formatDrivePath(currentPath, mountPath);
  const canBack = normalizePath(currentPath) !== normalizePath(mountPath);

  const navigate = useNavigate();

  const handleStart = () => {
    navigate('/recovery', {
      state: {
        autoStart: true,
        file: selectedFile
      }
    });
  };

  return (
    <div id="explorer" className={isDarkMode ? 'dark-mode' : ''}>
      <div className={`drive_category ${isDarkMode ? 'dark-mode' : ''}`}>
        <div className="drive_header">
          <div className="drive_header_left">
            <DriveIcon className="drive_icon" />
            <span className="drive_path_text">{displayPath}</span>
          </div>
          <div className="drive_controls">
            {canBack && (
              <Button variant="gray" onClick={onBack}>
                뒤로 가기
              </Button>
            )}

            <Button variant="dark" onClick={onSelectDrive}>
              드라이브 선택
            </Button>
          </div>
        </div>

        <div className="folder_wrapper">
          <div className="folder_list">
            {entries.map((entry) => (
              <div
                key={entry.path}
                className="folder_item"
                onClick={() => (entry.isDirectory 
                  ? onOpenDir(entry.path) 
                  : typeof onSelectFile === 'function' && onSelectFile(entry))}
                style={{ fontWeight: entry.isDirectory ? 'bold' : 'normal', cursor: 'pointer' }}
              >
                {entry.isDirectory ? (
                  <FolderIcon className="folder_icon" />
                ) : (
                  <FileIcon className="file_icon" />
                )}
                <span>{entry.name}</span>
                {entry.isSupported && entry.size ? (
                  <span className="file_size">({bytesToGB(entry.size)})</span>
                ) : null}
              </div>
            ))}
          </div>

          <div id="selected_file_info">
            {selectedFile && (
              <div className="selected_box">
                <h4 style={{ marginLeft: '10px' }}>선택된 파일</h4>
                <p style={{ marginLeft: '10px' }}><strong>파일명:</strong> {selectedFile.name}</p>
                <p style={{ marginLeft: '10px' }}><strong>크기:</strong> {bytesToGB(selectedFile.size)}</p>
                <p style={{ marginLeft: '10px' }}><strong>경로:</strong> {selectedFile.path}</p>
                <Button
                  variant="dark"
                  onClick={handleStart}
                  disabled={!selectedFile || !selectedFile.path || !selectedFile.name}
                >
                  복원 시작
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function DriveSection({ title, drives, onDriveClick }) {
  if (!drives.length) return null;
  return (
    <div className="drive_wrapper">
      <div className="drive_category">
        <h2>{title}</h2>
        <div className="drive_list">
          {drives.map((drive) => (
            <DriveCard key={drive.id} drive={drive} onClick={onDriveClick} />
          ))}
        </div>
      </div>
    </div>
  );
}

const Home = ({ isDarkMode }) => {
  const [drives, setDrives] = useState([]);
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [mountPath, setMountPath] = useState('');

  useEffect(() => {
    window.api.getDrives().then(setDrives);
    const unsubscribe = window.api.onDrivesUpdated(setDrives);
    return () => typeof unsubscribe === 'function' && unsubscribe();
  }, []);

  const categorized = useMemo(() => {
    return {
      internal: drives.filter((d) => d.kind === 'internal'),
      external: drives.filter((d) => d.kind === 'external'),
      removable: drives.filter((d) => d.kind === 'removable'),
    };
  }, [drives]);

  const loadFolder = useCallback(async (folderPath) => {
    setCurrentPath(folderPath);
    setSelectedFile(null);
    const raw = await window.api.readFolder(folderPath);
    raw.sort((a, b) => {
      if (a.isDirectory && !b.isDirectory) return -1;
      if (!a.isDirectory && b.isDirectory) return 1;
      return a.name.localeCompare(b.name);
    });
    setEntries(raw.filter((e) => e.isDirectory || e.isSupported));
  }, []);

  const handleDriveClick = (mount) => {
    setMountPath(mount);
    loadFolder(mount);
  };

  const handleBack = () => {
    if (!currentPath || currentPath === mountPath) return;
    const cut = currentPath.substring(0, currentPath.lastIndexOf('\\'));
    const parent = !cut || /^[A-Z]:$/i.test(cut) ? mountPath : cut;
    loadFolder(parent);
  };

  const handleSelectDrive = () => {
    setCurrentPath('');
    setEntries([]);
    setMountPath('');
  };

  const handleOpenDir = (p) => loadFolder(p);
  const handleSelectFile = (entry) => setSelectedFile(entry);

  return (
    <div className={`main_content ${isDarkMode ? 'dark-mode' : ''}`}>
      {!mountPath && (
        <>
          <h1 className={`home_title${isDarkMode ? ' dark-mode' : ''}`}>드라이브를 선택해 복원을 시작하세요</h1>

          <div className={`drive_wrapper${isDarkMode ? ' dark-mode' : ''}`}>
            <DriveSection
              title="내장 드라이브"
              drives={categorized.internal}
              onDriveClick={handleDriveClick}
            />
            <DriveSection
              title="외장 드라이브"
              drives={categorized.external}
              onDriveClick={handleDriveClick}
            />
            <DriveSection
              title="이동식 드라이브"
              drives={categorized.removable}
              onDriveClick={handleDriveClick}
            />
          </div>
        </>
      )}

      {mountPath && (
        <ExplorerView
          mountPath={mountPath}
          currentPath={currentPath}
          entries={entries}
          selectedFile={selectedFile}
          onBack={handleBack}
          onSelectDrive={handleSelectDrive}
          onOpenDir={handleOpenDir}
          onSelectFile={handleSelectFile}
          isDarkMode={isDarkMode}
        />
      )}
    </div>
  );
};

export default Home;
