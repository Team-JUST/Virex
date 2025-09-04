import React, { useRef, useState, useEffect, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import Stepbar from '../components/Stepbar.jsx';
import Box from '../components/Box.jsx';
import Button from '../components/Button.jsx';
import Alert from '../components/Alert.jsx';
import Badge from '../components/Badge.jsx';
import Loading from '../components/Loading.jsx';
import '../styles/Stepbar.css';
import '../styles/Recovery.css';
import '../styles/Button.css';
import '../styles/Alert.css';
import alertIcon from '../images/alert_file.svg';
import drivingIcon from '../images/driving.svg';
import parkingIcon from '../images/parking.svg';
import eventIcon from '../images/event.svg';
import deletedIcon from '../images/deleted.svg';
import downloadIcon from '../images/download.svg';
import basicIcon from '../images/information_t.svg';
import integrityIcon from '../images/integrity.svg';
import slackIcon from '../images/slack.svg';
import structureIcon from '../images/struc.svg';
import recoveryPauseIcon from '../images/recoveryPauseIcon.svg';
import replayIcon from '../images/view_replay.svg';
import pauseIcon from '../images/view_pause.svg';
import fullscreenIcon from '../images/view_fullscreen.svg';
import integrityGreen from '../images/integrity_g.svg';
import integrityRed from '../images/integrity_r.svg';
import completeIcon from '../images/complete.svg';
import storageFullIcon from '../images/storageFullIcon.svg';
import { useNavigate } from 'react-router-dom';

const Recovery = ({ isDarkMode }) => {

// 1) 화면 제어 상태 정의
  const [showTabGuardPopup, setShowTabGuardPopup] = useState(false);
  const [isRecovering, setIsRecovering] = useState(false);
  const [progress, setProgress] = useState(0);
  const prevIsRecovering = useRef(isRecovering);
  const [showDiskFullAlert, setShowDiskFullAlert] = useState(false);
  const navigate = useNavigate();
  const rollbackRef = useRef(() => {});

  rollbackRef.current = () => {
    setIsRecovering(false);
    setProgress(0);
    setRecoveredFiles?.([]);
    setRecoveryDone?.(false);
    setSelectedAnalysisFile?.(null);
    setSlackVideoSrc?.(null);
    setShowDiskFullAlert?.(false);
    navigate('/recovery'); // 또는 setView('upload')
  };

  function rollbackToFirst() {
    rollbackRef.current();
  }

// 2) 복원 진행률 관련 이펙트
  useEffect(() => {
    window.__recoverGuard = { isRecovering, progress };
    console.log("[Debug] export from Recovery : ", { isRecovering, progress });
  }, [isRecovering, progress]);

  useEffect(() => {
    if (!isRecovering) return;

    if (progress >= 100) {
      setIsRecovering(false);
      setRecoveryDone(true); 
    }
  }, [isRecovering, progress]);

  useEffect(() => {
    return () => {
      setShowTabGuardPopup(false);
    };
  }, []);

// 3) 입력/팝업/선택 파일/카운트 등 입력·파일·다운로드 상태
  const inputRef = useRef(null);
  const [showStopRecoverPopup, setShowStopRecoverPopup] = useState(false);
  const [pendingTab, setPendingTab] = useState(null);

  const [showAlert, setShowAlert] = useState(false);
  const [recoveryDone, setRecoveryDone] = useState(false);
  const [showDownloadPopup, setShowDownloadPopup] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const [selectedFile, setSelectedFile] = useState(null);
  const [saveFrames, setSaveFrames] = useState(false);
  const [selectedPath, setSelectedPath] = useState("");

  const [currentCount, setCurrentCount] = useState(0);
  const [totalFiles, setTotalFiles] = useState(0);

  const [showSlackPopup, setShowSlackPopup] = useState(false);

  const [results, setResults] = useState([]);
  const [openGroups, setOpenGroups] = useState({});

  const [tempOutputDir, setTempOutputDir] = useState(null);


// 4) 결과 목록 → 카테고리 그룹핑 유틸/파생값
  function groupByCategory(list) {
    return list.reduce((acc, file) => {
      const cat = file.path.split(/[/\\]/)[1] || 'unknown'
      if (!acc[cat]) acc[cat] = []
      acc[cat].push(file)
      return acc
    }, {})
  }
  const groupedResults = useMemo(() => groupByCategory(results), [results])

// 5) 분석 선택/탭/다운로드 완료 등 결과 뷰 상태
  const [selectedAnalysisFile, setSelectedAnalysisFile] = useState(null);
  const [activeTab, setActiveTab] = useState('basic');
  const [showComplete, setShowComplete] = useState(false);
  const [showDownloadAlert, setShowDownloadAlert] = useState(false);

// 6) 라우팅/초기파일 자동시작 상태
  const location = useLocation();
  const initialFile = location.state?.e01File || null;
  const autoStart = location.state?.autoStart || false;

// 7) 슬랙 영상 소스 등 슬랙 관련 상태
  const [slackVideoSrc, setSlackVideoSrc] = useState('');

// 8) 공통 유틸 (단위/코덱 포맷)
  const bytesToMB = (bytes) => (bytes / 1024 / 1024).toFixed(1) + ' MB';

  const formatCodec = (codec) =>
    codec
      .toUpperCase()
      .replace(/^([HE]\d{3,4})$/, (m) => m[0] + '.' + m.slice(1));

// 9) 결과/분석 파일 파생값 및 슬랙 지표
  const analysis = useMemo(
    () => results.find(f => f.name === selectedAnalysisFile)?.analysis,
    [results, selectedAnalysisFile]
  );

  const selectedResultFile = useMemo(
    () => results.find(f => f.name === selectedAnalysisFile),
    [results, selectedAnalysisFile]
  );

  const slack_info = selectedResultFile?.slack_info ?? { slack_rate: 0 };
  const safeSlackRate = slack_info.slack_rate ?? 0;

  const slackPercent = safeSlackRate <= 1
    ? (safeSlackRate * 100).toFixed(0)
    : safeSlackRate.toFixed(0);

  const validPercent = (100 - safeSlackRate * 100).toFixed(1);

// 10) 진행률 변화 시 뷰 전환 로직
  useEffect(() => {
    if (progress >= 100) {
      setIsRecovering(false);
      setRecoveryDone(true);
    }

    setHistory(prev => [...prev, 'result']);
    setView('result');

  }, [progress]);

// 11) 카테고리 아이콘 매핑 및 아이콘 선택 헬퍼
  const categoryIcons = {
    driving: drivingIcon,
    parking: parkingIcon,
    event: eventIcon,
    slack: slackIcon,
    deleted: deletedIcon,
  };

  const specialCategoryMap = {
    shock: 'event',
  };

  const getCategoryIcon = (category) => {
    const cat = category.toLowerCase();
    for (const [match, iconKey] of Object.entries(specialCategoryMap)) {
      if (cat.includes(match)) {
        return categoryIcons[iconKey];
      }
    }
    const prefix = Object.keys(categoryIcons).find((k) =>
      cat.startsWith(k)
    );
    return prefix ? categoryIcons[prefix] : slackIcon;
  };

  // 12) 메인 IPC: 진행률/완료 리스너 등록
  useEffect(() => {
    console.log("[Debug] onProgress useEffect : mounted");
    const offProg = window.api.onProgress(({ processed, total }) => {
      console.log("[Debug] progress event : processed " + processed + " of " + total);
      setTotalFiles(total);
      setProgress(Math.floor((processed / total) * 100));
    });
    const offDone = window.api.onDone(() => {
      console.log("[Debug] recovery done event : completed");
      setProgress(100);
      setIsRecovering(false);
      setRecoveryDone(true);
    });
    return () => { offProg(); offDone(); };
  }, []);

// 13) 결과 수신 리스너
  useEffect(() => {
    console.log("[Debug] onResults listener : registered");
    const off = window.api.onResults(data => {
      console.log("[Debug] onResults data : ", data);
      if (data.error) setResultError(data.error);
      else setResults(data);
    });
    return off;
  }, []);

// 14) 분석 경로/다운로드 로그·에러 리스너
  useEffect(() => {
    const offPath = window.api.onAnalysisPath(path => {
      console.log("[Debug] analysis path : ", path);
      setTempOutputDir(path);
    });
    return () => offPath();
  }, []);

  useEffect(() => {
    const offLog = window.api.onDownloadLog(line => {
      console.log("[Debug] download log : ", line);
    });
    const offErr = window.api.onDownloadError(err => {
      console.error("[Debug] download error : ", err);
    });
    const offDownloadComplete = window.api.onDownloadComplete(() => {
      console.log("[Debug] download completed");
      setIsDownloading(false);
      setShowComplete(true);
    });
    return () => {
      offLog();
      offErr();
      offDownloadComplete();
    };
  }, []);

// 15) 복원 자동 시작 트리거
  useEffect(() => {
    if (isRecovering && selectedFile) {
      window.api.startRecovery(selectedFile.path).catch((err) => {
        const msg = String(err?.message || err);
        console.warn("[Recovery] startRecovery failed:", msg);

        if (msg.includes("disk_full")) {
          setShowDiskFullAlert(true);   // ✅ 팝업 띄우기
          rollbackToFirst();          // ✅ 초기화
        } else {
          // TODO: 그 외 에러 처리 (원하면 일반 에러 팝업 따로)
        }
      });
    }
  }, [isRecovering, selectedFile]);

  useEffect(() => {
    if (autoStart && initialFile) {
      handleFile(initialFile);
    }
  }, [autoStart, initialFile]);

// 16) 파일/다운로드 등 핸들러
  const handleFile = (file) => {
  if (!file.name.toLowerCase().endsWith('.e01')) {
    setShowAlert(true);
    return;
  }
  setSelectedFile(file);
  setShowAlert(false);
  setIsRecovering(true);     // ← 시작
  setRecoveryDone(false);
  setProgress(0);            // ← 0으로 리셋
  setTotalFiles(0);
};

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) handleFile(file);
  };

  const handleClick = async () => {
    const filePath = await window.api.openE01File();
    if (filePath) {
      const parts = filePath.split(/[/\\]/);
      const fileName = parts[parts.length - 1];
      handleFile({ path: filePath, name: fileName });
    }
  };

  const startRecovery = () => {
    if (!selectedFile) return;
    setShowRange(false);
    setIsRecovering(true);
    setCurrentCount(0);
    setProgress(0);
    setTotalFiles(300);
  };

  const toggleGroup = (cat) =>
    setOpenGroups(prev => ({ ...prev, [cat]: !prev[cat] }))

  const confirmDownload = () => {
    console.log("[Debug] final save path : ", selectedPath);
  };

  const handleDownload = () => {
    setShowDownloadPopup(true);
  };

  const closeDownloadPopup = () => {
    setShowDownloadPopup(false); 
  };

  const handleInvalidFile = () => {
    setShowAlert(true);
  };

  const handleDownloadClick = () => {
    setShowDownloadPopup(true);
  };

  const handleFolderSelect = async () => {
    const result = await window.api.openDirectory();
    if (!result.canceled && result.filePaths.length > 0) {
      setSelectedPath(result.filePaths[0]);
    }
  };

  // 다운로드 백엔드
  const handleDownloadConfirm = async () => {
    if (!selectedFile || !tempOutputDir || !selectedPath) {
      alert('다운로드 경로 또는 임시 폴더가 올바르지 않습니다.');
      return;
    }

    const choice = saveFrames ? 'both' : 'video';

    try {
      setShowDownloadPopup(false);
      setIsDownloading(true);
      
      await window.api.runDownload({
        e01Path: tempOutputDir,
        choice,
        downloadDir: selectedPath
      });

      // 다운로드 완료는 onDownloadComplete 이벤트에서 처리
    } catch (err) {
      console.error("[Debug] download failed : ", err);
      setIsDownloading(false);
    }
  };

  const handleDownloadCancel = () => {
    setShowDownloadPopup(false);
  };

  const handleFileClick = (filename) => {
    setSelectedAnalysisFile(filename);
    setActiveTab('basic');
    setHistory(prev => [...prev, 'parser']);
    setView('parser');
  };

  const handlePathSelect = async () => {
    const dir = await window.api.selectFolder();
    if (dir) {
      console.log("[Debug] selected folder : ", dir);
      setSelectedPath(dir);
    }
  };

// 17) 스텝바 계산
  let currentStep = 0;

  if (recoveryDone) {
    currentStep = 3;
  } else if (isRecovering) {
    currentStep = 1;
  } else if (recoveryDone) {
    currentStep = 2;
  } else {
    currentStep = 0;
  }

// 18) 파서 뷰어 DOM 세팅(useEffect)
  useEffect(() => {
    if (!selectedAnalysisFile) return;

    const waitForDOMAndSetup = () => {
      const video = document.getElementById('parser-video');
      const playPauseBtn = document.getElementById('playPauseBtn');
      const playPauseIcon = document.getElementById('playPauseIcon');
      const replayBtn = document.getElementById('replayBtn');
      const fullscreenBtn = document.getElementById('fullscreenBtn');
      const progressBar = document.getElementById('progressBar');
      const timeText = document.getElementById('timeText');

      if (!video || !playPauseBtn || !replayBtn || !fullscreenBtn || !progressBar || !timeText || !playPauseIcon) {
        console.warn("[Debug] video or control element : not ready, retrying");
        requestAnimationFrame(waitForDOMAndSetup);
        return;
      }

      fullscreenBtn.onclick = () => {
        if (!document.fullscreenElement) {
          // 전체화면 진입
          if (video.requestFullscreen) {
            video.requestFullscreen().catch(err => {
              console.error("[Debug] fullscreen enter failed : ", err);
            });
          } else if (video.webkitRequestFullscreen) {
            video.webkitRequestFullscreen();
          } else if (video.msRequestFullscreen) {
            video.msRequestFullscreen();
          }
        } else {
          // 전체화면 종료
          if (document.exitFullscreen) {
            document.exitFullscreen();
          } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
          } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
          }
        }
      };

      playPauseBtn.onclick = () => {
        if (video.paused) {
          video.play();
          playPauseIcon.src = 'view_pause.svg';
        } else {
          video.pause();
          playPauseIcon.src = 'view_play.svg';
        }
      };
      playPauseBtn.onclick = () => {
        if (video.paused) {
          video.play();
          playPauseIcon.style.filter = 'none';
        } else {
          video.pause();
          playPauseIcon.style.filter = 'grayscale(100%) brightness(0.8)';
        }
      };

      replayBtn.onclick = () => {
        video.currentTime = 0;
        video.play();
        playPauseIcon.style.filter = 'none';
      };

      fullscreenBtn.onclick = () => {
        if (video.requestFullscreen) video.requestFullscreen();
      };
      replayBtn.onclick = () => {
        video.currentTime = 0;
        video.play();
      };

      video.ontimeupdate = () => {
        progressBar.value = video.currentTime;
        timeText.textContent = `${formatTime(video.currentTime)} / ${formatTime(video.duration)}`;
      };

      progressBar.oninput = () => {
        video.currentTime = progressBar.value;
      };

      video.onloadedmetadata = () => {
        progressBar.max = video.duration;
      };

      function formatTime(seconds) {
        const min = Math.floor(seconds / 60).toString().padStart(2, '0');
        const sec = Math.floor(seconds % 60).toString().padStart(2, '0');
        return `${min}:${sec}`;
      }
    };

    requestAnimationFrame(waitForDOMAndSetup);
  }, [selectedAnalysisFile]); // selectedAnalysisFile이 변경될 때마다 실행

// 19) 다운로드 완료 후 복원 재시작 핸들러
    const startRecoveryFromDownload = () => {
      setShowDownloadPopup(false);
      setShowComplete(false);
      setIsRecovering(true);
      setCurrentCount(0);
      setProgress(0);
      setTotalFiles(300);
    };

// 20) 화면 전환/탭 가드 네비게이션
    const [view, setView] = useState('upload');
    const [history, setHistory] = useState(['upload']);

    const handleBack = () => {
      if (history.length > 1) {
        const newHistory = [...history];
        newHistory.pop();
        const prevView = newHistory[newHistory.length - 1];
        setHistory(newHistory);
        setView(prevView);

        if (prevView === 'upload') {
          setIsRecovering(false);
          setRecoveryDone(false);
          setShowComplete(false);
          setSelectedAnalysisFile(null);
        } else if (prevView === 'recovering') {
          setIsRecovering(true);
          setRecoveryDone(false);
          setShowComplete(false);
          setSelectedAnalysisFile(null);
        } else if (prevView === 'result') {
          setIsRecovering(false);
          setRecoveryDone(true);
          setShowComplete(false);
          setSelectedAnalysisFile(null);
        } else if (prevView === 'parser') {
          setIsRecovering(false);
          setRecoveryDone(true);
          setShowComplete(false);
        }
      }
    };

    const handleTabClick = (tab) => {
      if (isRecovering && progress < 100) {
        setPendingTab(tab);
        setShowTabGuardPopup(true);
        return;
      }
      setActiveTab(tab);
    };

    const confirmTabMove = () => {
      if (pendingTab) setActiveTab(pendingTab);
      setPendingTab(null);
      setShowTabGuardPopup(false);
    };

    const cancelTabMove = () => {
      setShowTabGuardPopup(false);
      setPendingTab(null);
    };

  // 21) 디스크 용량 부족 이벤트 수신 → Alert 띄우고 롤백
  useEffect(() => {
      if (!window.api?.onDiskFull) return;
      const off = window.api.onDiskFull(() => {
        setShowDiskFullAlert(true);
        rollbackToFirst();  
      });
      return () => { try { off && off(); } catch {} };
    }, []);

  return (
    <div className={`recovery-page ${isDarkMode ? 'dark-mode' : ''}`}>
      <Stepbar currentStep={currentStep} isDarkMode={isDarkMode} />
      <Box isDarkMode={isDarkMode}>
        {showComplete ? (
          <>
          {/* 결과 화면 */}
            <h1 className="upload-title">Result</h1>
            <div className="recovery-complete-area">
              <div style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                flexDirection: 'column',
              }}>
                <img src={completeIcon} alt="완료 아이콘" style={{ width: '100px', margin: '3rem 0', marginTop: '6rem' }} />
              </div>
              <p style={{ textAlign: 'center', fontSize: '1rem' }}>
                선택된 경로에 복원된 영상이 저장되었습니다.
              </p>
              <div style={{ display: 'flex', justifyContent: 'center', marginTop: '1.5rem' }}>
                <Button variant="dark" onClick={() => navigate('/')}>홈으로</Button>
              </div>
            </div>
          </>
        ) : isDownloading ? (
          <>
          {/* 다운로드 진행 화면 */}
            <h1 className="upload-title">Download</h1>
            <p className="recovery-desc-left">잠시만 기다려 주세요… 영상을 다운로드하고 있어요</p>

            <div className="recovery-file-box">
              <div className="recovery-file-left">
                <Badge label="다운로드 중" />
                <span className="file-name">{selectedFile?.name}</span>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "center" }}>
              <Loading text="Downloading..." />
            </div>
          </>
        ) : isRecovering ? (
          <>
          {/* 분석 진행 화면 */}
            <h1 className="upload-title">File Recovery</h1>
            <p className="recovery-desc-left">잠시만 기다려 주세요… 영상을 복원하고 있어요</p>

            <div className="recovery-file-box">
              <div className="recovery-file-left">
                <Badge label="진행중" />
                <span className="file-name">{selectedFile?.name}</span>
              </div>
              <button className="close-btn" onClick={() => setIsRecovering(false)}>✕</button>
            </div>
            <div style={{ display: "flex", justifyContent: "center" }}>
              <Loading />
            </div>
            <div className="progress-bar-wrapper">
              <div className="progress-bar-track">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${progress}%`, transition: 'width 0.6s ease' }}
                />
              </div>
              <div className="progress-bar-text">
                {progress}%
              </div>
              
            </div>
          </>
        ) : !isRecovering && !recoveryDone ? (
          <>
          {/* 파일 업로드 후 복원 중 화면 */}
            <h1 className="upload-title">File Upload</h1>
            <p className="upload-subtitle">E01 파일을 업로드 해주세요</p>
            <div
              className="dropzone"
              id="dadDrop"
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={handleClick}
            >
              <p className="dropzone-title">복구할 블랙박스 이미지(E01) 선택</p>
              <p className="dropzone-desc">
                E01 파일을 드래그 앤 드롭하거나 클릭하여 선택하세요<br />
                분할된 E01 파일(.E01, E02, E03 ...)을 자동으로 인식합니다
              </p>

              <input
                type="file"
                id="dadFile"
                accept=".E01"
                ref={inputRef}
                onChange={handleFileChange}
                hidden
              />
              <Button variant="gray">
                ⭱ <span>업로드</span>
              </Button>
            </div>
          </>

        
        ) : recoveryDone ? (
          selectedAnalysisFile ? (
            <>
              <h1 className="upload-title">Result</h1>

              <div className="recovery-file-box">
                <span className="file-name">{selectedAnalysisFile}</span>
                <div className="recovery-file-controls">
                  {selectedAnalysisFile.toLowerCase().endsWith('.avi') && (
                    <>
                      <Badge label="전방" onClick={() => {}} />
                      <Badge label="후방" onClick={() => {}} />
                      <Badge label="사이드" onClick={() => {}} />
                    </>
                  )}
                  <button className="close-btn" onClick={handleBack}>✕</button>
                </div>
              </div>

              <div className="result-scroll-area">
                {/* 뷰 */}
                <div className="video-container">
                  <video
                    id="parser-video"
                    preload="metadata"
                    controls
                    style={{
                      width: '100%',
                      maxWidth: '1200px',
                      height: 'auto',
                      backgroundColor: 'white',
                    }}
                    src={
                      results.find(f => f.name === selectedAnalysisFile)?.origin_video
                        ? `file:///${results
                          .find(f => f.name === selectedAnalysisFile)
                          .origin_video.replace(/\\/g, '/')}`
                        : ''
                    }
                  ></video>

                  <div className="parser-controls">
                    <button id="replayBtn">
                      <img src={replayIcon} alt="Replay" />
                    </button>
                    <button
                      id="playPauseBtn"
                      style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                    >
                      <img
                        id="playPauseIcon"
                        src={pauseIcon}
                        alt="Pause"
                        style={{
                          width: '30px',
                          transition: 'filter 0.2s',
                          filter: 'none', 
                        }}
                      />
                    </button>

                    <input type="range" id="progressBar" min="0" defaultValue="0" step="0.01" />
                    <span id="timeText">00:00 / 00:00</span>
                    <button id="fullscreenBtn">
                      <img src={fullscreenIcon} alt="Fullscreen" />
                    </button>
                  </div>
                </div>

                {/* 분석 화면 */}
                <div className="parser-tabs">
                  <button
                    className={`parser-tab-button ${activeTab === 'basic' ? 'active' : ''}`}
                    onClick={() => handleTabClick('basic')}
                  >
                    <img src={basicIcon} alt="기본 정보" />
                    <span>기본 정보</span>
                  </button>
                  <button
                    className={`parser-tab-button ${activeTab === 'integrity' ? 'active' : ''}`}
                    onClick={() => handleTabClick('integrity')}
                  >
                    <img src={integrityIcon} alt="무결성 검사" />
                    <span>무결성 검사</span>
                  </button>
                  <button
                    className={`parser-tab-button ${activeTab === 'slack' ? 'active' : ''}`}
                    onClick={() => handleTabClick('slack')}
                  >
                    <img src={slackIcon} alt="슬랙 정보" />
                    <span>슬랙 정보</span>
                  </button>
                  <button
                    className={`parser-tab-button ${activeTab === 'structure' ? 'active' : ''}`}
                    onClick={() => handleTabClick('structure')}
                  >
                    <img src={structureIcon} alt="구조 정보" />
                    <span>구조 정보</span>
                  </button>
                </div>

              {/* 분석 파서 */}
                <div className={`parser-tab-content ${activeTab === 'basic' ? 'active' : ''}`}>
                  <div className="parser-info-table">
                    <div className="parser-info-row">
                      <span className="parser-info-label">파일 포맷</span>
                      <span className="parser-info-value">{analysis.basic.format}</span>
                    </div>

                    <div className="parser-info-row">
                      <span className="parser-info-label">복구 시간</span>
                      <span className="parser-info-value">{analysis.basic.timestamps.created}</span>
                    </div>

                    <div className="parser-info-row">
                      <span className="parser-info-label">파일 크기</span>
                      <span className="parser-info-value">
                        {bytesToMB(analysis.basic.file_size)}
                      </span>
                    </div>
                    <div className="parser-info-row">
                      <span className="parser-info-label">비디오 코덱</span>
                      <span className="parser-info-value">
                        {formatCodec(analysis.basic.video_metadata.codec)}
                      </span>
                    </div>
                    <div className="parser-info-row">
                      <span className="parser-info-label">해상도</span>
                      <span className="parser-info-value">
                        {analysis.basic.video_metadata.width}×{analysis.basic.video_metadata.height}
                      </span>
                    </div>
                    <div className="parser-info-row">
                      <span className="parser-info-label">프레임 레이트</span>
                      <span className="parser-info-value">
                        {Math.round(analysis.basic.video_metadata.frame_rate)} fps
                      </span>
                    </div>
                  </div>
                </div>

                <div className={`parser-tab-content ${activeTab === 'integrity' ? 'active' : ''}`}>
                  <div className="parser-info-table">
                    <div className="parser-info-row">
                      <span className="parser-info-label">전체 상태</span>
                      <span className="parser-info-value">
                        <img
                          src={analysis.integrity.damaged ? integrityRed : integrityGreen}
                          alt={analysis.integrity.damaged ? "손상" : "정상"}
                          className="status-icon"
                        />
                        <span className={`status-text ${analysis.integrity.damaged ? 'red' : 'green'}`}>
                          {analysis.integrity.damaged ? '손상됨' : '정상'}
                        </span>
                      </span>
                    </div>
                    {analysis.integrity.damaged && analysis.integrity.reasons.length > 0 && (
                      <div className="parser-info-row">
                        <span className="parser-info-label">손상 사유</span>
                        <span className="parser-info-value">
                          <ul className="reason-list">
                            {analysis.integrity.reasons.map((reason, idx) => (
                              <li key={idx}>{reason}</li>
                            ))}
                          </ul>
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className={`parser-tab-content ${activeTab === 'slack' ? 'active' : ''}`}>
                  <div className="parser-info-table">
                    <div className="parser-info-row">
                      <span className="parser-info-label">슬랙 비율</span>
                      <span className="parser-info-value">{slackPercent} %</span>
                    </div>
                    <div className="parser-info-row">
                      <span className="parser-info-label">유효 데이터 비율</span>
                      <span className="parser-info-value">
                        {100 - slackPercent} %
                      </span>
                    </div>
                    <div className="parser-info-row">
                      <span className="parser-info-label">데이터 분포</span>
                    </div>
                    <div className="data-bar-wrapper">
                      <div
                        className="data-bar-used"
                        style={{
                          width: `${100 - slackPercent}%`
                        }}
                      />
                    </div>
                  </div>
                </div>

                <div className={`parser-tab-content ${activeTab === 'structure' ? 'active' : ''}`}>
                  <div className="parser-structure">
                    <h4>{analysis.structure.type.toUpperCase()} Structure</h4>
                    <pre className="structure-pre">
                      {analysis.structure.structure.join('\n')}
                    </pre>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <>
              {/* 복원 결과 리스트 */}
              <h1 className="upload-title">Result</h1>
              <div className="recovery-file-box">
                <span className="result-recovery-text">복원된 파일 목록</span>
              </div>
              <div className="result-wrapper">

                <p className="result-summary">
                  총 {results.length}개의 파일, 용량{' '}
                  {bytesToMB(
                    results.reduce((sum, f) => sum + f.size, 0)
                  )}
                </p>

                <div className="result-scroll-area" style={{ position: 'relative' }}>
                  {Object.entries(groupedResults).map(([category, files]) => (
                    <div className="result-group" key={category}>

                      <div
                        className={`result-group-header ${openGroups[category] ? 'open' : ''}`}
                        onClick={() => toggleGroup(category)}
                      >
                        <span className="result-group-toggle" />
                        <img
                          className="result-group-icon"
                          src={getCategoryIcon(category)}
                          alt={`${category} icon`}
                        />
                        {category} ({files.length})
                      </div>

                      {openGroups[category] && (
                        <div className="result-file-list">
                          {files.map((file) => {
                            const mb = bytesToMB(file.size);
                            const rawRate = file.slack_info.slack_rate;
                            const slackRatePercent =
                              rawRate <= 1
                                ? (rawRate * 100).toFixed(0)
                                : rawRate.toFixed(0);

                            return (
                              <div className="result-file-item" key={file.path}>
                                <div className="result-file-info">
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <button
                                      className="text-button"
                                      onClick={() => handleFileClick(file.name)}
                                    >
                                      {file.name}
                                    </button>
                                    {slackRatePercent > 0 && (
                                      <Badge
                                        label="슬랙"
                                        onClick={() => {
                                          const slackPath = file.slack_info?.output_path;
                                          if (!slackPath) {
                                            return;
                                          }

                                          const formatted = `file:///${slackPath.replace(/\\/g, '/')}`;
                                          console.log("[Debug] slack video path : ", formatted);

                                          setSlackVideoSrc(formatted);  // 슬랙 영상 경로 저장
                                          setShowSlackPopup(true);   
                                        }}
                                        style={{ cursor: 'pointer' }}
                                      />
                                    )}
                                  </div>
                                  <br />
                                  {mb} ・ 슬랙비율: {slackRatePercent} %
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div
                  style={{
                    position: 'absolute',
                    bottom: '1.5rem',
                    right: '4rem',
                    display: 'flex',
                    justifyContent: 'flex-end',
                  }}
                >
                  <Button variant="dark" onClick={handleDownload}>
                    다운로드
                  </Button>
                </div>
              </div>
            </>
          )
        ) : null
        }
      </Box>

    {/* Alert 조건문 */}
      {showAlert && (
        <Alert
          icon={alertIcon}
          title="파일 형식 오류"
          isDarkMode={isDarkMode}
          description={
            <>
              선택한 파일은 E01 이미지 형식이 아닙니다<br />
              해당 도구는 .E01 형식만 지원됩니다<br />
              올바른 파일을 다시 선택해 주세요
            </>
          }
        >
          <Button variant="dark" onClick={() => setShowAlert(false)}>다시 선택</Button>
        </Alert>
      )}

      {showTabGuardPopup && (
        <Alert
          icon={recoveryPauseIcon}
          title="탭 전환 경고"
          isDarkMode={isDarkMode}
          description={
            <>
              영상 복원이 아직 완료되지 않았습니다.<br />
              이 상태에서 탭을 이동하면 복구가 중단됩니다.<br />
              계속 이동하시겠습니까?
            </>
          }
        >
          <div
            className="alert-buttons"
            style={{ marginTop: '1rem', display: 'flex', gap: '10px' }}
          >
            <Button variant="gray" onClick={cancelTabMove}>취소</Button>
            <Button variant="dark" onClick={confirmTabMove}>이동하기</Button>
          </div>
        </Alert>
      )}

      {showSlackPopup && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            backgroundColor: 'rgba(0, 0, 0, 0.85)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 9999,
          }}
        >
          <div style={{ position: 'absolute', top: '20px', right: '30px' }}>
            <Button variant="gray" onClick={() => setShowSlackPopup(false)}>
              닫기
            </Button>
          </div>
          <video
            preload="metadata"
            controls
            style={{
              width: '90vw',
              height: '80vh',
              backgroundColor: 'black',
              borderRadius: '12px',
            }}
            src={slackVideoSrc} 
          />
        </div>
      )}

      {showDiskFullAlert && (
        <Alert
          icon={storageFullIcon}
          title="용량 부족 알림"
          isDarkMode={isDarkMode}
          description={
            <>
              복원 영상을 저장할 드라이브에 용량이 부족합니다<br />
              용량을 비우고 다시 시도해주세요
            </>
          }
        >
          <Button variant="dark" onClick={() => setShowDiskFullAlert(false)}>확인</Button>

        </Alert>
      )}


      {showDownloadPopup && (
        <Alert
          icon={downloadIcon}
          title="다운로드 옵션"
          isDarkMode={isDarkMode}
          description={
            <div className={`download-popup-wide ${isDarkMode ? 'dark-mode' : ''}`}>
              <p>
                영상과 함께 각 프레임 이미지를 ZIP으로 다운받으시겠습니까?
              </p>
              <div className="download-options" style={{ margin: '1rem 0' }}>
                <label style={{ marginRight: '1rem' }}>
                  <input
                    type="radio"
                    name="saveFrames"
                    checked={saveFrames === true}
                    onChange={() => setSaveFrames(true)}
                  /> 예
                </label>
                <label>
                  <input
                    type="radio"
                    name="saveFrames"
                    checked={saveFrames === false}
                    onChange={() => setSaveFrames(false)}
                  /> 아니요
                </label>
              </div>
              <div
                className="path-box"
                style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}
              >
                <input
                  type="text"
                  value={selectedPath}
                  readOnly
                  className={`custom-path-input ${isDarkMode ? 'dark-mode' : ''}`}
                  style={{ flex: 1 }}
                  placeholder="경로를 지정해주세요"
                />
                <Button variant="gray" onClick={handlePathSelect}>
                  경로 지정
                </Button>
              </div>
            </div>
          }
        >
          <div
            className="alert-buttons"
            style={{ marginTop: '1rem', display: 'flex', gap: '10px' }}
          >
            <Button variant="gray" onClick={handleDownloadCancel}>이전</Button>
            <Button variant="dark" onClick={handleDownloadConfirm}>완료</Button>
          </div>
        </Alert>
      )}
    </div>
  );
}
export default Recovery;