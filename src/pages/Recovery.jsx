import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useSessionStore } from '../session.js';

import Stepbar from '../components/Stepbar.jsx';
import Box from '../components/Box.jsx';
import Button from '../components/Button.jsx';
import Alert from '../components/Alert.jsx';
import Badge from '../components/Badge.jsx';
import Loading from '../components/Loading.jsx';
import VolBadge from '../components/Vol_Badge.jsx';

import '../styles/Stepbar.css';
import '../styles/Recovery.css';
import '../styles/Button.css';
import '../styles/Alert.css';

import AlertIcon from '../images/alert_file.svg?react';
import DrivingIcon from '../images/driving.svg?react';
import DownloadIcon from '../images/download.svg?react';
import BasicIcon from '../images/information_t.svg?react';
import IntegrityIcon from '../images/integrity.svg?react';
import SlackIcon from '../images/slack.svg?react';
import StructureIcon from '../images/struc.svg?react';
import RecoveryPauseIcon from '../images/recoveryPauseIcon.svg?react';
import ResetIcon from '../images/resetIcon.svg?react';
import IntegrityGreen from '../images/integrity_g.svg?react';
import IntegrityRed from '../images/integrity_r.svg?react';
import CompleteIcon from '../images/complete.svg?react';
import StorageFullIcon from '../images/storageFullIcon.svg?react';


const Recovery = ({ isDarkMode }) => {

// 0) 세션 스토어 훅
const { session, startSession, patchSession, resetSession } = useSessionStore();

const [showRange, setShowRange] = useState(false);

const selectedFile = session.file;
const setSelectedFile = (file) => patchSession({ file });

const [resultError, setResultError] = useState(null);

const progress = session.progress;
const setProgress = (v) => patchSession({ progress: v });

const isRecovering = session.isRecovering;
const setIsRecovering = (v) => patchSession({ isRecovering: v });

const recoveryDone = session.recoveryDone;
const setRecoveryDone = (v) => patchSession({ recoveryDone: v });

const results = Array.isArray(session.results) ? session.results : [];
const setResults = (arr) => patchSession({ results: Array.isArray(arr) ? arr : [] });

const tempOutputDir = session.tempOutputDir;
const setTempOutputDir = (p) => patchSession({ tempOutputDir: p });

const selectedAnalysisFile = session.selectedAnalysisFile;
const setSelectedAnalysisFile = (n) => patchSession({ selectedAnalysisFile: n });

const activeTab = session.activeTab;
const setActiveTab = (t) => patchSession({ activeTab: t });

const selectedFilesForDownload = session.selectedFilesForDownload;
const setSelectedFilesForDownload = (arr) => patchSession({ selectedFilesForDownload: arr });

const selectedPath = session.selectedPath;
const setSelectedPath = (p) => patchSession({ selectedPath: p });

const saveFrames = session.saveFrames;
const setSaveFrames = (b) => patchSession({ saveFrames: b });

const openGroups = session.openGroups || {};
const setOpenGroups = (next) => patchSession({ openGroups: next });

// 볼륨 슬랙 변수 정의
const [volumeSlack, setVolumeSlack] = useState([]);
const volumeSlackCount = volumeSlack?.length || 0;
const volumeSlackBytes = (volumeSlack || []).reduce((s, f) => s + Number(f.size || 0), 0);
const CARVED_TITLE = 'Volume & Partition Unallocated Space';
const totalCount = results.length + volumeSlackCount;
const [isDiskImage, setIsDiskImage] = useState(false);


// 1) 화면 제어 상태 정의
  const startedRef = useRef(false);      
  const diskFullHandledRef = useRef(false); 
  const [showTabGuardPopup, setShowTabGuardPopup] = useState(false);
  const prevIsRecovering = useRef(isRecovering);
  const [showDiskFullAlert, setShowDiskFullAlert] = useState(false);
  const navigate = useNavigate();
  const [selectAll, setSelectAll] = useState(false);

  const recoveryDoneRef = useRef(recoveryDone);
  const selectedAnalysisFileRef = useRef(selectedAnalysisFile);


  useEffect(() => { recoveryDoneRef.current = recoveryDone; }, [recoveryDone]);
  useEffect(() => { selectedAnalysisFileRef.current = selectedAnalysisFile; }, [selectedAnalysisFile]);
  const [view, setView] = useState('upload');
  const [history, setHistory] = useState(['upload']);
  const viewRef = useRef('upload');

  useEffect(() => { viewRef.current = view; }, [view]);
    
  const rollbackRef = useRef(() => {});
  const [selectedChannel, setSelectedChannel] = useState(null);

  rollbackRef.current = () => {
    resetSession();
    setShowDiskFullAlert(false);
    navigate('/recovery');
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
  const [showDownloadPopup, setShowDownloadPopup] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const [currentCount, setCurrentCount] = useState(0);
  const [totalFiles, setTotalFiles] = useState(0);

// 3-1) 오디오 재생 상태
  const audioRef = useRef(null);
  const [currentAudio, setCurrentAudio] = useState(null);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      try {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
      } catch {}
    }
    audioRef.current = null;
    setIsAudioPlaying(false);
    setCurrentAudio(null);
  }, []);

  useEffect(() => () => stopAudio(), [stopAudio]);

// 4) 결과 목록 → 카테고리 그룹핑 유틸/파생값
  function groupByCategory(list) {
    return list.reduce((acc, file) => {
     // file.category가 있으면 우선 사용
      const cat = file.category || file.path.split(/[/\\]/)[1] || 'unknown';
      if (!acc[cat]) acc[cat] = []
      acc[cat].push(file)
      return acc
    }, {})
  };

  // 4-1) 결과 목록 -> JDR 채널별로 그룹핑
  const groupedResults = useMemo(() => {
    const regularGroups = groupByCategory(results);

    if ((volumeSlack?.length || 0) > 0) {
      regularGroups[CARVED_TITLE] = volumeSlack;
    }

    return regularGroups;
  }, [results, volumeSlack]);

  useEffect(() => {
    if (!volumeSlack?.length) return;
    if (openGroups?.[CARVED_TITLE]) return;
    setOpenGroups({ ...openGroups, [CARVED_TITLE]: true });
  }, [volumeSlack?.length, openGroups, CARVED_TITLE]);

// 5) 분석 선택/탭/다운로드 완료 등 결과 뷰 상태
  const [showComplete, setShowComplete] = useState(false);
  const [showDownloadAlert, setShowDownloadAlert] = useState(false);
  const [resultsLoading, setResultsLoading] = useState(false);

  // 복원 완료 → 결과화면 진입 트리거
  useEffect(() => {
    if (recoveryDone && !selectedAnalysisFile) {
      if (results.length === 0) setResultsLoading(true);
    }
  }, [recoveryDone, selectedAnalysisFile, results.length]);

// 6) 라우팅/초기파일 자동시작 상태
  const location = useLocation();
  const initialFile = location.state?.file || null;
  const autoStart = location.state?.autoStart || false;

// 7) 슬랙 영상 소스 등 슬랙 관련 상태
  const [showSlackPopup, setShowSlackPopup] = useState(false);
  const [selectedSlackFile, setSelectedSlackFile] = useState(null);
  const [slackChannel, setSlackChannel] = useState(null);
  const [slackMedia, setSlackMedia] = useState({ type: null, src: '', fallback: null });

// 8) 공통 유틸 (단위/코덱 포맷)
  const bytesToUnit = (bytes) => {
    let n = Number(bytes) || 0;
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++;}
    const decimals = i === 0 ? 0 : 1;
    const label = `${n.toFixed(decimals)} ${units[i]}`;
    return label.replace('.0', ' ');
  };

  const unitToBytes = (label) => {
    if (typeof label === 'number') return label;
    if (typeof label !== 'string') return 0;
    const m = label.trim().match(/^([\d.]+)\s*(B|KB|MB|GB|TB)$/i);
    if (!m) return 0;
    const n = parseFloat(m[1]);
    const u = m[2].toUpperCase();
    const mul = u === 'TB' ? 1024**4 : u === 'GB' ? 1024**3 : u === 'MB' ? 1024**2 : u === 'KB' ? 1024 : 1;
    return Math.floor(n * mul);
  };

  const basename = (p) => {
    if (!p) return '';
    const s = String(p);
    const parts = s.split(/[\\/]/); 
    return parts[parts.length - 1] || '';
  };

  const formatCodec = (codec) =>
    codec
      .toUpperCase()
      .replace(/^([HE]\d{3,4})$/, (m) => m[0] + '.' + m.slice(1));

  const toFileUrl = (p) => (p ? `file:///${encodeURI(String(p).replace(/\\/g, '/'))}` : '');

  async function listCarvedFromFS(baseDir) {
    try {
      if (!baseDir) return [];
      const list = await window.api.listCarvedDir(baseDir);
      return Array.isArray(list) ? list : [];
    } catch (e) {
      console.warn('[Debug] listCarvedFromFS failed:', e);
      return [];
    }
  }

  const getSlackForChannel = (file, ch) => {
    const info = file?.channels?.[ch];
    if (!info || !info.recovered) return null;
    const v = info.video_path ? toFileUrl(info.video_path) : null;
    const i = info.image_path ? toFileUrl(info.image_path) : null;
    if (info.is_image_fallback && i) return { type: 'image', src: i, fallback: v || null };
    if (v) return { type: 'video', src: v, fallback: i || null };
    if (i) return { type: 'image', src: i, fallback: null };
    return null;
  };

  const getSlackForMp4 = (file) => {
    const s = file?.slack_info;
    if (!s || !s.recovered) return null;

    const v = s.video_path ? toFileUrl(s.video_path) : null;
    const i = s.image_path ? toFileUrl(s.image_path) : null;
    
    if (s.is_image_fallback && i) return { type: 'image', src: i, fallback: v || null };
    if (v) return { type: 'video', src: v, fallback: i || null };
    if (i) return { type: 'image', src: i, fallback: null };
    return null;
  };

// 9) 결과/분석 파일 파생값 및 슬랙 지표
  const analysis = useMemo(
    () => results.find((f) => f.name === selectedAnalysisFile)?.analysis,
    [results, selectedAnalysisFile]
  );

  const selectedResultFile = useMemo(
    () => results.find((f) => f.name === selectedAnalysisFile),
    [results, selectedAnalysisFile]
  );

  const availableChannels = useMemo(() => {
    const f = selectedResultFile;
    if (!f || !f.channels) return [];
    return ['front','rear','side'].filter((ch) => !!f.channels?.[ch]?.merged_video_path);
  }, [selectedResultFile]);

  const currentVideoSrc = useMemo(() => {
    const f = selectedResultFile;
    if (!f) return '';
    const isAVIorJDR = f.name?.toLowerCase().endsWith('.avi') || f.name?.toLowerCase().endsWith('.jdr');
    if (isAVIorJDR) {
      // selectedChannel이 없으면 front를 기본값으로 사용
      const ch = selectedChannel || (f.channels?.front ? 'front' : null);
      if (ch && f.channels?.[ch]) {
        return toFileUrl(f.channels[ch].merged_video_path || '');
      }
    }

    const isDamaged = Boolean(f?.analysis?.integrity?.damaged);
    const isRecovered = Boolean(f?.slack_info?.recovered);
    if (isDamaged && isRecovered) {
      return toFileUrl(f.slack_info?.video_path || f.origin_video || '');
    }
    return toFileUrl(f.origin_video || '');
  }, [selectedResultFile, selectedChannel]);

  const slack_info = selectedResultFile?.slack_info ?? { recovered: false, slack_size: '0 B', slack_rate: 0,  };
  const totalBytes = unitToBytes(selectedResultFile?.size || '0 B');
  const lowerCaseName = selectedResultFile?.name?.toLowerCase() || '';
  const isAVI = lowerCaseName.endsWith('.avi')
  const isJDR = lowerCaseName.endsWith('.jdr');
  const isMP4 = lowerCaseName.endsWith('.mp4');
  const isMultiChannel = isAVI || isJDR;
  const isDamagedAndRecovered = Boolean(analysis?.integrity?.damaged && slack_info?.recovered && isMP4);

  const multiChannelSlackBytes = isMultiChannel && selectedResultFile?.channels
    ? Object.values(selectedResultFile.channels)
        .filter(Boolean)
        .reduce((sum, ch) => sum + (ch?.slack_size ? unitToBytes(ch.slack_size) : 0), 0)
    : 0;
  
  let slackBytes = 0;
  let slackLabel = '0 B';

  if (isMultiChannel) {
    slackBytes = multiChannelSlackBytes;
    slackLabel = bytesToUnit(slackBytes);
  } else {
    if (slack_info?.slack_size && typeof slack_info.slack_size === 'string') {
      slackBytes = unitToBytes(slack_info.slack_size);
      slackLabel = bytesToUnit(slackBytes);
    } else {
      const r = Number(slack_info?.slack_rate ?? 0);
      const ratePct = Number.isFinite(r) ? (r <= 1 ? r * 100 : r) : 0;
      slackBytes = totalBytes ? Math.round(totalBytes * (ratePct / 100)) : 0;
      slackLabel = bytesToUnit(slackBytes);
    }
  }
  
  slackBytes = Math.min(Math.max(slackBytes, 0), totalBytes);
  const usedBytes = Math.max(totalBytes - slackBytes, 0);

  const totalLabel = bytesToUnit(totalBytes);
  const usedLabel = bytesToUnit(usedBytes);

  const slackPercent = (() => {
    if (!totalBytes) return 0;
    if (isMultiChannel) {
      const p = (slackBytes / totalBytes) * 100;
      return p > 0 && p < 1 ? 1 : Math.round(p);
    }
    const r = Number(slack_info?.slack_rate ?? 0);
    const pct = Number.isFinite(r) ? (r <= 1 ? r * 100 : r) : (slackBytes / totalBytes) * 100;
    return pct > 0 && pct < 1 ? 1 : Math.round(pct);
  })();

// 11) 카테고리 아이콘 매핑 및 아이콘 선택 헬퍼
  const categoryIcons = {
    driving: DrivingIcon,
    slack: SlackIcon,
  };

  const getCategoryIcon = (category) => {
    if (!category) return DrivingIcon;

    if (category === CARVED_TITLE || category.toLowerCase().includes('slack')) {
      return SlackIcon;
    }

    return DrivingIcon;
  };

  // 12) 메인 IPC: 진행률/완료 리스너 등록
  useEffect(() => {
    console.log("[Debug] onProgress useEffect : mounted");
    const offProg = window.api.onProgress(({ processed, total }) => {
      console.log("[Debug] progress event : processed " + processed + " of " + total);
      setTotalFiles(total);
      const pct = total > 0 ? Math.floor((processed / total) * 100) : 0;
      setProgress(pct);
    });
    const offDone = window.api.onDone(() => {
      console.log("[Debug] recovery done event : completed");
      setProgress(100);
      setIsRecovering(false);
      setRecoveryDone(true);
    });
    const offCancelled = window.api.onCancelled?.(() => {
      resetSession();
      setShowComplete(false);
      setSelectedAnalysisFile(null);
      setIsRecovering(false);
      setRecoveryDone(false);
      setProgress(0);
      setView('upload');
      setHistory(['upload']);
    })
    return () => { offProg(); offDone(); offCancelled?.(); };
  }, []);

// 13) 결과 수신 리스너
useEffect(() => {
  const off = window.api.onResults(data => {
    if (data.error) {
      setResultError(data.error);
      setResultsLoading(false);
      return;
    }
    setResults(data);
    setResultsLoading(false);

    const hasResults = Array.isArray(data) && data.length > 0;
    if (!hasResults) return;

    if (!recoveryDoneRef.current) setRecoveryDone(true);

    // 파서 화면에 있으면 덮어쓰지 않기
    if (!selectedAnalysisFileRef.current && viewRef.current !== 'parser') {
      setView('result');
      setHistory(prev => prev[prev.length - 1] === 'result' ? prev : [...prev, 'result']);
    }
  });
  return off;
}, []);

// 14) 분석 경로/다운로드 로그·에러 리스너
  useEffect(() => {
    const offPath = window.api.onAnalysisPath(async (dir) => {
      console.log("[Debug] analysis path :", dir);
      setTempOutputDir(dir);

      if (!isDiskImage) {
        setVolumeSlack([]);
        return;
    }

      try {
        let list = [];

        // 1) carved_index.json 먼저 시도
        const idx = await window.api.readCarvedIndex(dir).catch(() => null);
        if (idx?.items?.length) {
          list = (idx.items || []).flatMap(it => {
            const rebuilt = (it.rebuilt || [])
              .filter(x => (x?.ok !== false) && (x?.rebuilt || x?.raw))
              .map(x => ({
                name: basename(x.rebuilt || x.raw),
                path: (x.rebuilt || x.raw),
                size: Number(x?.probe?.format?.size || 0),
                _remuxFailed: !x?.rebuilt || !x?.ok
              }));

            const jdr = (it.jdr || [])
              .filter(x => x?.ok && x?.rebuilt)
              .map(x => ({
                name: basename(x.rebuilt),
                path: x.rebuilt,
                size: Number(x?.probe?.format?.size || 0),
              }));

            return [...rebuilt, ...jdr];
          });
        }

        // 2) JSON이 비었으면 carved/ 폴더 직접 스캔 (dir 보정)
        if (!list.length) {
          const baseForCarved = /[\\/](?:carved)$/i.test(String(dir))
            ? String(dir).replace(/[\\/](?:carved)$/i, '')
            : dir;

          console.log('[Debug] carved_index empty → fallback to FS scan');
          console.log('[Debug] listCarvedFromFS base =', baseForCarved);

          list = await listCarvedFromFS(baseForCarved);
        }

        console.log('[Debug] carved list (final) :', list.length);

        // 상태 반영
        setVolumeSlack(list.map(it => ({ ...it, category: CARVED_TITLE })));
        setResultsLoading(false);

        // carved 있으면 결과 화면 열고 그룹 오픈
        if (list.length > 0) {
          setRecoveryDone(true);
          if (viewRef.current !== 'parser') {
            setView('result');
            setHistory(prev => prev[prev.length - 1] === 'result' ? prev : [...prev, 'result']);
          }
          if (!openGroups?.[CARVED_TITLE]) {
            setOpenGroups({ ...openGroups, [CARVED_TITLE]: true });
          }
        }
      } catch (e) {
        console.warn("[Debug] readCarvedIndex/listCarvedFromFS failed:", e);
        setVolumeSlack([]);
        setResultsLoading(false);
      }
    });

    return () => offPath();
  }, [isDiskImage]);

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
      if (startedRef.current) return;
      startedRef.current = true;

      window.api.startRecovery(selectedFile.path).catch((err) => {
        const msg = String(err?.message || err);
        console.warn("[Recovery] startRecovery failed:", msg);

        if (msg.includes("disk_full")) {
          if (!diskFullHandledRef.current) {
            diskFullHandledRef.current = true;
            setShowDiskFullAlert(true);
          }
        }
        setIsRecovering(false);
        startedRef.current = false;
      });
    }
  }, [isRecovering, selectedFile]);

  useEffect(() => {
    if (autoStart && initialFile) {
      handleFile(initialFile);
    }
  }, [autoStart, initialFile]);

  useEffect(() => {
    if (!isRecovering || recoveryDone) {
      startedRef.current = false;
    }
  }, [isRecovering, recoveryDone]);

// 16) 파일/다운로드 등 핸들러
  // 16-1) 오디오 재생 핸들러
  // 오디오 재생 (문자열 path 또는 {path: "..."} 모두 지원)
  const handleAudioPlay = (audioType, file) => {
    // AVI는 channels.audio, MP4는 slack_info.audio 구조 사용
    const isMP4File = file?.name?.toLowerCase().endsWith('.mp4');
    const hasAudio = isMP4File 
      ? file?.slack_info?.audio?.[audioType]
      : file?.channels?.audio?.[audioType];
    
    if (!hasAudio || !audioType) {
      return;
    }

    // AVI와 MP4의 오디오 데이터 구조 통일 처리
    const raw = isMP4File 
      ? file.slack_info.audio[audioType] 
      : file.channels.audio[audioType];
    
    if (!raw) return;

    // audio 데이터 형태: { path: '...' } 또는 문자열 직접
    const realPath = typeof raw === 'string' ? raw : raw.path;
    if (!realPath) return;

    const audioPath = toFileUrl(realPath);
    console.debug('[Audio] 요청 재생', { file: file.name, audioType, audioPath });

    // 이미 동일한 오디오 재생 중이면 토글(정지)
    if (
      currentAudio?.type === audioType &&
      currentAudio?.file?.name === file?.name &&
      isAudioPlaying
    ) {
      console.debug('[Audio] 동일 소스 → 정지');
      stopAudio();
      return;
    }

    // 기존 다른 오디오 정지
    if (audioRef.current) {
      stopAudio();
    }

    // 새 오디오 객체 생성
    try {
      const audioEl = new Audio(audioPath);
      audioRef.current = audioEl;
      setCurrentAudio({ type: audioType, file });

      audioEl.onplay = () => {
        setIsAudioPlaying(true);
      };
      audioEl.onpause = () => {
        // 사용자가 수동 pause 한 경우
        setIsAudioPlaying(false);
      };
      audioEl.onended = () => {
        console.debug('[Audio] 재생 종료 이벤트');
        stopAudio();
      };
      audioEl.onerror = (e) => {
        console.error('[Audio] 재생 오류', e);
        stopAudio();
      };

      audioEl.play().catch(err => {
        console.error('[Audio] play() 실패', err);
        stopAudio();
      });
    } catch (err) {
      console.error('[Audio] Audio 객체 생성 실패', err);
      stopAudio();
    }
  };

  const handleFile = (file) => {
    const lower = file.name.toLowerCase();
    const ok =
      lower.endsWith('.e01') ||
      lower.endsWith('.001') ||
      lower.endsWith('.mp4') ||
      lower.endsWith('.avi') ||
  lower.endsWith('.jdr');
    if (!ok) { setShowAlert(true); return; }
  setShowAlert(false);
  startSession(file);           
  setTotalFiles(0);
  const disk = lower.endsWith('.e01') || lower.endsWith('.001');
  setIsDiskImage(disk);
  if (!disk) setVolumeSlack([]);
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
    const filePath = await window.api.openSupportedFile();
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
  }

  const toggleGroup = (cat) => {
    patchSession({
      openGroups: {
        ...openGroups,
        [cat]: !openGroups[cat],
      },
    });
  };

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

    // 전체 선택 토글
  const handleSelectAll = () => {
    if (selectAll) {
      // 전체 해제
      setSelectedFilesForDownload([]);
    } else {
      // 전체 선택: results와 volumeSlack 각각의 path 전부 모으기
      const all = [];

      // results 배열 순회
      for (let i = 0; i < results.length; i++) {
        const file = results[i];
        if (file && file.path) {
          all.push(file.path);
        }
      }

      // volumeSlack 배열 순회
      for (let j = 0; j < volumeSlack.length; j++) {
        const file = volumeSlack[j];
        if (file && file.path) {
          all.push(file.path);
        }
      }

      setSelectedFilesForDownload(all);
    }
    setSelectAll(!selectAll);
  };

  // 다운로드 백엔드
// 다운로드 백엔드
const handleDownloadConfirm = async () => {
  if (
    !Array.isArray(selectedFilesForDownload) ||
    selectedFilesForDownload.length === 0 ||
    !tempOutputDir ||
    !selectedPath
  ) {
    return;
  }

  const choice = saveFrames ? 'both' : 'video';

  // ← 필수: 하위 저장 폴더명 (누락 시 폴더 생성에서 오류)
  const now = new Date();
  const yyyy = String(now.getFullYear());
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  const subdirName = `Virex_${yyyy}${mm}${dd}_download`;

  try {
    setShowDownloadPopup(false);
    setIsDownloading(true);

    await window.api.runDownload({
      e01Path: tempOutputDir,
      choice,
      downloadDir: selectedPath,
      files: selectedFilesForDownload,
      subdirName
    });

    // 완료 처리는 onDownloadComplete에서
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
    const f = results.find((r) => r.name === filename);
    if (!f) return;
    const lowerCaseName = filename.toLowerCase();
    const isMultiChannel = lowerCaseName.endsWith('.avi') || lowerCaseName.endsWith('.jdr');;
    if (isMultiChannel && availableChannels.length > 0) {
      setSelectedChannel('front');
    } else {
      setSelectedChannel(null);
    }
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

  const resetToUpload = () => {
    stopAudio();
    resetSession();
    setShowComplete(false);
    setSelectedAnalysisFile(null);
    setIsRecovering(false);
    setRecoveryDone(false);
    setView('upload');
    setIsDiskImage(false);
    setVolumeSlack([]);
  }

// 17) 스텝바 계산
  let currentStep = 0;

  if (recoveryDone) {
    currentStep = 3;
  } else if (isRecovering) {
    currentStep = 1;
  } else if (selectedAnalysisFile) {
    currentStep = 2;
  } else {
    currentStep = 0;
  }

// 18) 다운로드 완료 후 복원 재시작 핸들러
    const startRecoveryFromDownload = () => {
      setShowDownloadPopup(false);
      setShowComplete(false);
      setIsRecovering(true);
      setCurrentCount(0);
      setProgress(0);
      setTotalFiles(300);
    };

// 19) 화면 전환/탭 가드 네비게이션

    const handleBack = () => {
      stopAudio();
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
          setSelectedChannel(null);

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

  // 20) 디스크 용량 부족 이벤트 수신
  useEffect(() => {
    if (!window.api?.onDiskFull) return;
    const off = window.api.onDiskFull(() => {
      if (!diskFullHandledRef.current) {
        diskFullHandledRef.current = true;
        setShowDiskFullAlert(true);  
      }
      setIsRecovering(false);
      startedRef.current = false;
    });
    return () => { try { off && off(); } catch {} };
  }, []);
  

  // 21) 볼륨 슬랙 팝업 핸들러
  const [showRestartPopup, setShowRestartPopup] = useState(false);
  const [showClosePopup, setShowClosePopup] = useState(false);

  const openMediaViewer = (file) => {
    const lower = String(file?.name || '').toLowerCase();
    const href = toFileUrl(file?.path || '');
    let media = { type: null, src: '' };
    if (/\.(png|jpe?g|bmp|gif|webp)$/i.test(lower)) {
      media = { type: 'image', src: href };
        } else if (/\.(mp4|avi|mov|mkv|webm)$/i.test(lower)) {
      media = { type: 'video', src: href };
    } else if (/\.(h264|264|es)$/i.test(lower)) {
      media = { type: 'video', src: href };
    }
    setSlackChannel(null);
    setSlackMedia(media);
    setShowSlackPopup(true);  // 슬랙 팝업 재사용
  };
  const resultNameSet = useMemo(() => new Set(results.map(r => r.name)), [results]);
  useEffect(() => {
    const total = results.length + volumeSlack.length; 
    setSelectAll(
      total > 0 && selectedFilesForDownload.length === total
    );
  }, [results, volumeSlack, selectedFilesForDownload]);

  const needsRemux = (name) => /\.(?:264|h264|es)$/i.test(name);
  const normalGroups = groupedResults; // 기존 결과
  const carvedGroup = useMemo(() => volumeSlack || [], [volumeSlack]);
  const mergedGroups = useMemo(() => {
    return {
      ...normalGroups,
      ...(carvedGroup.length ? { [CARVED_TITLE]: carvedGroup } : {}),
    };
  }, [normalGroups, carvedGroup]);


  const showFloatingDownload =
    recoveryDone &&
    !selectedAnalysisFile && 
    view === 'result' &&
    !showSlackPopup &&
    !isDownloading &&
    !showComplete &&
    !isRecovering;

  // 재진입/새로고침 시에도 JSON→FS 순으로 로드
  useEffect(() => {
    if (!recoveryDone || !tempOutputDir || !window.api?.readCarvedIndex || !isDiskImage) return;

    (async () => {
      try {
        let list = [];
        const idx = await window.api.readCarvedIndex(tempOutputDir).catch(() => null);

        if (idx?.items?.length) {
          list = idx.items.flatMap(it => {
            const rebuilt = (it.rebuilt || [])
              .filter(x => (x?.rebuilt && x?.ok) || x?.raw)
              .map(x => ({
                name: basename(x.rebuilt || x.raw),
                path: (x.rebuilt || x.raw),
                size: Number(x?.probe?.format?.size || 0),
                _remuxFailed: !x?.rebuilt || !x?.ok
              }));

            const jdr = (it.jdr || [])
              .filter(x => x?.ok && x?.rebuilt)
              .map(x => ({
                name: basename(x.rebuilt),
                path: x.rebuilt,
                size: Number(x?.probe?.format?.size || 0),
              }));
            return [...rebuilt, ...jdr];
          });
        }

        if (!list.length) {
          console.log('[Debug] carved_index empty on refresh → FS scan');
          list = await listCarvedFromFS(tempOutputDir);
        }

        console.log('[Debug] carved list (refresh):', list.length);
        setVolumeSlack(list.map(it => ({ ...it, category: CARVED_TITLE })));
        if (list.length) {
          setOpenGroups(prev => ({ ...prev, [CARVED_TITLE]: true }));
        }
      } catch (e) {
        console.warn("readCarvedIndex/FS refresh failed:", e);
      }
    })();
  }, [recoveryDone, tempOutputDir, isDiskImage]);

  return (
    <div className={`recovery-page ${isDarkMode ? 'dark-mode' : ''}`}>
      <Stepbar currentStep={currentStep} isDarkMode={isDarkMode} />
      <Box isDarkMode={isDarkMode}>
        {showComplete ? (
          <>
            {/* 결과 화면 */}
            <h1 className="upload-title">Result</h1>
            <div className="recovery-complete-area">
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>
                <CompleteIcon className="complete_icon" />
              </div>
              <p style={{ textAlign: 'center', fontSize: '1rem' }}>
                선택된 경로에 복원된 영상이 저장되었습니다.
              </p>
              {!showRestartPopup && (
                <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '1.5rem' }}>
                  <Button
                    variant="dark"
                    onClick={() => {
                      stopAudio();
                      setShowComplete(false);
                      setSelectedAnalysisFile(null);
                      setIsRecovering(false);
                      setRecoveryDone(true);
                      setView && setView('result');
                    }}
                  >
                    뒤로가기
                  </Button>
                  <Button variant="gray" onClick={() => setShowRestartPopup(true)}>
                    새 복원 시작
                  </Button>
                </div>
              )}
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
            <div style={{ display: 'flex', justifyContent: 'center' }}>
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
              <button
                className="close-btn"
                onClick={() => {
                  if (!isRecovering || progress >= 100) {
                    setIsRecovering(false);
                    return;
                  }
                  setShowStopRecoverPopup(true);
                }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'center' }}>
              <Loading />
            </div>

            <div className="progress-bar-wrapper">
              <div
                className="progress-bar-track"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress}
              >
                <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
                <div
                  className="progress-bubble dynamic"
                  style={{
                    left: `${progress}%`,
                    transform:
                      progress === 0
                        ? 'translateX(0) rotate(10deg)'
                        : progress === 100
                        ? 'translateX(-100%) rotate(10deg)'
                        : 'translateX(-50%) rotate(10deg)',
                  }}
                >
                  {progress}%
                </div>
              </div>
            </div>
          </>
        ) : !isRecovering && !recoveryDone ? (
          <>
            {/* 파일 업로드 화면 */}
            <h1 className="upload-title">File Upload</h1>
            <p className="upload-subtitle">E01 / 001 / MP4 / AVI / JDR 파일을 업로드 해주세요</p>

            <div
              className="dropzone"
              id="dadDrop"
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={handleClick}
            >
              <p className="dropzone-title">복구할 파일(E01 / 001 / MP4 / AVI / JDR) 선택</p>
              <p className="dropzone-desc">
                E01 / 001 / MP4 / AVI / JDR 파일을 업로드해주세요<br />
                분할된 E01 파일(.E01, E02, E03 ...)과<br />
                분할된 001 파일(.001, .002, .003 ...)은 자동으로 인식합니다.
              </p>

              <input
                type="file"
                id="dadFile"
                accept=".E01,.001,.mp4,.avi,.jdr"
                ref={inputRef}
                onChange={handleFileChange}
                hidden
              />
              {!showAlert && (
                <Button variant="gray">
                  ⭱ <span>업로드</span>
                </Button>
              )}
            </div>
          </>
        ) : recoveryDone ? (
          selectedAnalysisFile ? (
            <>
              {/* 파서 뷰 */}
              <h1 className="upload-title">Result</h1>

              <div className="recovery-file-box">
                <span className="file-name">
                  {selectedAnalysisFile}
                </span>

                <div className="recovery-file-controls">
                  {(() => {
                    const lowerCaseName = selectedResultFile?.name?.toLowerCase() || '';
                    const isAVI = lowerCaseName.endsWith('.avi');
                    const isJDR = lowerCaseName.endsWith('.jdr');
                    if ((isAVI || isJDR) && availableChannels.length > 0) {
                      return (
                        <>
                          {availableChannels.map((ch) => {
                            const label = ch === 'front' ? 'Front' :
                                        ch === 'rear' ? 'Rear' :
                                        ch === 'side' ? 'Side' :
                                        ch === 'merge' ? 'Merge' : ch;
                            const active = selectedChannel === ch;
                            return (
                              <Badge
                                key={ch}
                                label={label}
                                onClick={() => setSelectedChannel(ch)}
                                style={{
                                  cursor: 'pointer',
                                  opacity: active ? 1 : 0.6,
                                  border: active ? '1px solid #333' : '1px solid transparent',
                                }}
                              />
                            );
                          })}
                        </>
                      );
                    }
                    return null;
                  })()}
                  <button className="close-btn" onClick={handleBack}>✕</button>
                </div>
              </div>

              <div className="result-scroll-area scrollbar-area">
                {/* 뷰어 */}
                <div className="video-container">
                  <video id="parser-video" preload="metadata" controls src={currentVideoSrc} />
                </div>

                {/* 분석 탭 */}
                {analysis && (
                  <>
                    <div className="parser-tabs">
                      <button
                        className={`parser-tab-button ${activeTab === 'basic' ? 'active' : ''}`}
                        onClick={() => handleTabClick('basic')}
                      >
                        <BasicIcon className="tab-icon" />
                        <span>기본 정보</span>
                      </button>
                      <button
                        className={`parser-tab-button ${activeTab === 'integrity' ? 'active' : ''}`}
                        onClick={() => handleTabClick('integrity')}
                      >
                        <IntegrityIcon className="tab-icon" />
                        <span>무결성 검사</span>
                      </button>
                      <button
                        className={`parser-tab-button ${activeTab === 'slack' ? 'active' : ''}`}
                        onClick={() => handleTabClick('slack')}
                      >
                        <SlackIcon className="tab-icon" />
                        <span>
                          {(() => {
                            const lower = selectedResultFile?.name?.toLowerCase() || '';
                            const isAVI = lower.endsWith('.avi');
                            if (isAVI && selectedResultFile?.analysis?.integrity?.damaged) {
                              const channels = Object.values(selectedResultFile.channels || {});
                              const hasRecovered = channels.some(ch => ch?.full_video_path);
                              const hasSlack = channels.some(ch => ch?.recovered);
                              if (hasRecovered && hasSlack) return '복원/슬랙 정보';
                              if (hasRecovered) return '복원 정보';
                              return '슬랙 정보';
                            }
                            // MP4 등 기존 로직
                            if (selectedResultFile?.analysis?.integrity?.damaged && selectedResultFile?.slack_info?.recovered) {
                              return '복원 정보';
                            }
                            return '슬랙 정보';
                          })()}
                        </span>
                      </button>
                      <button
                        className={`parser-tab-button ${activeTab === 'structure' ? 'active' : ''}`}
                        onClick={() => handleTabClick('structure')}
                      >
                        <StructureIcon className="tab-icon" />
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
                          <span className="parser-info-label">생성 시간</span>
                          <span className="parser-info-value">{analysis.basic.timestamps?.created ?? '-'}</span>
                        </div>
                        <div className="parser-info-row">
                          <span className="parser-info-label">수정 시간</span>
                          <span className="parser-info-value">{analysis.basic.timestamps?.modified ?? '-'}</span>
                        </div>
                        <div className="parser-info-row">
                          <span className="parser-info-label">마지막 접근 시간</span>
                          <span className="parser-info-value">{analysis.basic.timestamps?.accessed ?? '-'}</span>
                        </div>
                        <div className="parser-info-row">
                          <span className="parser-info-label">파일 크기</span>
                          <span className="parser-info-value">{selectedResultFile?.size ?? '-'}</span>
                        </div>
                        <div className="parser-info-row">
                          <span className="parser-info-label">비디오 코덱</span>
                          <span className="parser-info-value">{formatCodec(analysis.basic.video_metadata.codec)}</span>
                        </div>
                        <div className="parser-info-row">
                          <span className="parser-info-label">해상도</span>
                          <span className="parser-info-value">
                            {analysis.basic.video_metadata.width}×{analysis.basic.video_metadata.height}
                          </span>
                        </div>
                        <div className="parser-info-row">
                          <span className="parser-info-label">프레임 레이트</span>
                          <span className="parser-info-value">{Math.round(analysis.basic.video_metadata.frame_rate)} fps</span>
                        </div>
                      </div>
                    </div>

                    <div className={`parser-tab-content ${activeTab === 'integrity' ? 'active' : ''}`}>
                      <div className="parser-info-table">
                        <div className="parser-info-row">
                          <span className="parser-info-label">전체 상태</span>
                          <span className="parser-info-value">
                            {analysis.integrity.damaged ? (
                              <IntegrityRed alt="손상" className="status-icon" />
                            ) : (
                              <IntegrityGreen alt="정상" className="status-icon" />
                            )}
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
                          <span className="parser-info-label">전체 크기</span>
                          <span className="parser-info-value">{totalLabel}</span>
                        </div>

                        {(() => {
                          const lower = selectedResultFile?.name?.toLowerCase() || '';
                          const isAVI = lower.endsWith('.avi');
                          const isJDR = lower.endsWith('.jdr');
                          if ((isAVI || isJDR) && selectedResultFile?.analysis?.integrity?.damaged) {
                            const channels = Object.values(selectedResultFile.channels || {});
                            const hasRecovered = channels.some(ch => ch?.full_video_path);
                            const hasSlack = channels.some(ch => ch?.recovered);
                            if (hasRecovered && hasSlack) {
                              const recoveredSize = channels.filter(ch => ch?.full_video_size).reduce((sum, ch) => sum + unitToBytes(ch.full_video_size), 0);
                              const totalSize = unitToBytes(selectedResultFile.size);
                              const recoveredPercent = totalSize > 0 ? Math.round((recoveredSize / totalSize) * 100) : 0;
                              const slackRateSum = channels.filter(ch => ch?.slack_rate).reduce((sum, ch) => sum + Number(ch.slack_rate), 0);
                              const slackSize = channels.filter(ch => ch?.slack_size).reduce((sum, ch) => sum + unitToBytes(ch.slack_size), 0);
                              return (
                                <>
                                  <div className="parser-info-row">
                                    <span className="parser-info-label">복원된 영상 크기</span>
                                    <span className="parser-info-value">{bytesToUnit(recoveredSize)}</span>
                                  </div>
                                  <div className="parser-info-row parser-info-row--withbar">
                                    <div className="data-bar-flex-row-between">
                                      <span className="parser-info-label">전체 영상 대비 복원 영상 비율</span>
                                      {recoveredPercent > 0 && (
                                        <div className="data-bar-wrapper is-single is-narrow">
                                          <div className="data-bar-used" style={{ width: `${recoveredPercent}%`, minWidth: '44px' }}>
                                            <span className="data-bar-text">{recoveredPercent} %</span>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                  <div className="parser-info-row">
                                    <span className="parser-info-label">슬랙 영상 크기</span>
                                    <span className="parser-info-value">{bytesToUnit(slackSize)}</span>
                                  </div>
                                  <div className="parser-info-row parser-info-row--withbar">
                                    <div className="data-bar-flex-row-between">
                                      <span className="parser-info-label">전체 영상 대비 슬랙 영상 비율</span>
                                      {slackRateSum > 0 && (
                                        <div className="data-bar-wrapper is-single is-narrow">
                                          <div className="data-bar-used" style={{ width: `${Math.round(slackRateSum)}%`, minWidth: '44px' }}>
                                            <span className="data-bar-text">{Math.round(slackRateSum)} %</span>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </>
                              );
                            }
                            if (hasRecovered) {
                              const recoveredSize = channels.filter(ch => ch?.full_video_size).reduce((sum, ch) => sum + unitToBytes(ch.full_video_size), 0);
                              const totalSize = unitToBytes(selectedResultFile.size);
                              const recoveredPercent = totalSize > 0 ? Math.round((recoveredSize / totalSize) * 100) : 0;
                              return (
                                <>
                                  <div className="parser-info-row">
                                    <span className="parser-info-label">복원된 영상 크기</span>
                                    <span className="parser-info-value">{bytesToUnit(recoveredSize)}</span>
                                  </div>
                                  <div className="parser-info-row parser-info-row--withbar">
                                    <div className="data-bar-flex-row-between">
                                      <span className="parser-info-label">전체 영상 대비 복원 영상 비율</span>
                                      {recoveredPercent > 0 && (
                                        <div className="data-bar-wrapper is-single is-narrow">
                                          <div className="data-bar-used" style={{ width: `${recoveredPercent}%`, minWidth: '44px' }}>
                                            <span className="data-bar-text">{recoveredPercent} %</span>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </>
                              );
                            }
                          }
                          if (isDamagedAndRecovered) {
                            return (
                              <>
                                <div className="parser-info-row">
                                  <span className="parser-info-label">복원된 영상 크기</span>
                                  <span className="parser-info-value">{slackLabel}</span>
                                </div>
                                <div className="parser-info-row parser-info-row--withbar">
                                  <div className="data-bar-flex-row-between">
                                    <span className="parser-info-label">전체 영상 대비 복원 영상 비율</span>
                                    {slackPercent > 0 && (
                                      <div className="data-bar-wrapper is-single is-narrow">
                                        <div className="data-bar-used" style={{ width: `${slackPercent}%`, minWidth: '44px' }}>
                                          <span className="data-bar-text">{slackPercent} %</span>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </>
                            );
                          }
                          return (
                            <>
                              <div className="parser-info-row">
                                <span className="parser-info-label">원본 영상 크기</span>
                                <span className="parser-info-value">{usedLabel}</span>
                              </div>
                              <div className="parser-info-row">
                                <span className="parser-info-label">슬랙 영상 크기</span>
                                <span className="parser-info-value">{slackLabel}</span>
                              </div>
                              <div className="parser-info-row parser-info-row--withbar">
                                <div className="data-bar-flex-row-between">
                                  <span className="parser-info-label">전체 영상 대비 슬랙 영상 비율</span>
                                  {slackPercent > 0 && (
                                    <div className="data-bar-wrapper is-single is-narrow">
                                      <div className="data-bar-used" style={{ width: `${slackPercent}%`, minWidth: '44px' }}>
                                        <span className="data-bar-text">{slackPercent} %</span>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    </div>

                    <div className={`parser-tab-content ${activeTab === 'structure' ? 'active' : ''}`}>
                      <div className="parser-structure">
                        <h4>{analysis.structure.type.toUpperCase()} Structure</h4>
                        <pre className="structure-pre">{analysis.structure.structure.join('\n')}</pre>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </>
          ) : (
            <>
              {/* 복원 결과 리스트 */}
              <div className="result-header">
                <h1 className="upload-title">Result</h1>
                <button className="close-btn header-close" onClick={() => setShowClosePopup(true)}>✕</button>
              </div>

              <div className="recovery-file-box">
                <span className="result-recovery-text">복원된 파일 목록</span>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={selectAll}
                    onChange={handleSelectAll}
                    style={{ marginRight: '8px' }}
                  />
                  <span>전체 선택</span>
                </div>
              </div>

              <div className="result-wrapper">
                  <div className="result-scroll-area scrollbar-area" style={{ position: 'relative' }}>
                    {resultsLoading ? (
                      <div className="result-summary" style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <span className="skeleton-bar result-skel-summary" />
                      </div>
                    ) : (
                      <p className="result-summary">
                        총 {results.length + volumeSlack.length}개의 파일, 용량{" "}
                        {bytesToUnit(
                          results.reduce((sum, f) => sum + unitToBytes(f.size), 0) + (volumeSlackBytes || 0)
                        )}
                      </p>
                    )}

                    {resultsLoading ? (
                      <div className="result-group">
                        <div className="result-group-header">
                          <span className="skeleton-bar result-skel-header" />
                        </div>
                      </div>
                    ) : (
                      Object.entries(groupedResults).map(([category, files]) => {
                        const isCarvedGroup = category === CARVED_TITLE;
                        return(
                        <div className="result-group" key={category}>
                          <div
                            className={`result-group-header ${openGroups[category] ? 'open' : ''}`}
                            onClick={() => toggleGroup(category)}
                          >
                            <span className="result-group-toggle" />
                            {React.createElement(getCategoryIcon(category), { className: "result-group-icon" })}
                            {category} ({files.length})
                          </div>

                          {openGroups[category] && (
                            <div className="result-file-list">
                              {(files || []).filter(Boolean).map((file) => {
                                if (!file) return null;

                                // 일반 파일 처리
                                const sizeLabel = typeof file.size === 'string' ? file.size : bytesToUnit(file.size);
                                const filename = String(file?.name ?? '');
                                const isJDR = filename.toLowerCase().endsWith('.jdr');
                                const isAVI = filename.toLowerCase().endsWith('.avi');
                                const isAVIorJDR = isAVI || isJDR;
                                const isMP4 = filename.toLowerCase().endsWith('.mp4');
                                const totalBytes = unitToBytes(file.size || 0);

                                const aviJdrSlackBytes =
                                  isAVIorJDR && file.channels
                                    ? Object.values(file.channels)
                                        .filter(Boolean)
                                        .reduce((sum, ch) => sum + (ch?.slack_size ? unitToBytes(ch.slack_size) : 0), 0)
                                    : 0;

                                let mp4SlackBytes = 0;
                                if (isMP4 && file.slack_info) {
                                  const s = file.slack_info;
                                  mp4SlackBytes = s.slack_size
                                    ? unitToBytes(s.slack_size)
                                    : Number(s.slack_rate) > 0 && totalBytes
                                    ? Math.round(totalBytes * (Number(s.slack_rate) / 100))
                                    : 0;
                                }

                                const mp4Media = isMP4 ? getSlackForMp4(file) : null;
                                const aviJdrHasMedia =
                                  isAVIorJDR && ['front', 'rear', 'side'].some((ch) => !!getSlackForChannel(file, ch));
                                const hasSlackMedia = isAVIorJDR ? aviJdrHasMedia : !!mp4Media;

                                const slackRatePercent = (() => {
                                    if (!totalBytes) return 0;
                                    if (isAVIorJDR) {
                                      const p = (aviJdrSlackBytes / totalBytes) * 100;
                                      return p > 0 && p < 1 ? 1 : Math.round(p);
                                    }
                                    const r = Number(file?.slack_info?.slack_rate ?? 0);
                                    const pct = Number.isFinite(r) ? (r <= 1 ? r * 100 : r) : (mp4SlackBytes / totalBytes) * 100;
                                    return pct > 0 && pct < 1 ? 1 : Math.round(pct);
                                  })();

                                const hasSlackBytes = (isAVIorJDR ? aviJdrSlackBytes : mp4SlackBytes) > 0;
                                const hasSlackBadge = hasSlackBytes && hasSlackMedia;

                                const unsupported = typeof needsRemux === 'function' ? needsRemux(file.name) : false;
                                const checked = selectedFilesForDownload.includes(file.path);

                                return (
                                  <div className="result-file-item" key={file.path}>
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={(e) => {
                                        let updated;
                                        if (e.target.checked) {
                                          updated = [...selectedFilesForDownload, file.path];
                                        } else {
                                          updated = selectedFilesForDownload.filter((p) => p !== file.path);
                                        }
                                        setSelectedFilesForDownload(updated);
                                      }}
                                    />
                                    <div className="result-file-info">
                                      <div className="result-file-title-row">
                                        {unsupported ? (
                                          <>
                                            <span className="text-button disabled" title="브라우저에서 재생 불가">
                                              {file.name}
                                            </span>
                                            <VolBadge label="복원 불가" variant="gray" />
                                          </>
                                        ) : (
                                          isCarvedGroup ? (
                                            <button className="text-button" onClick={() => openMediaViewer(file)}>
                                              {file.name}
                                            </button>
                                          ) : (
                                            <button className="text-button" onClick={() => handleFileClick(file.name)}>
                                              {file.name}
                                            </button>
                                          )
                                        )}
                                        {!isCarvedGroup && (
                                          <>
                                            {isAVI && hasSlackBadge && (
                                              <Badge
                                                label="슬랙"
                                                style={{ cursor: 'pointer' }}
                                                onClick={() => {
                                                  setSelectedSlackFile(file);
                                                  setSlackChannel('front');
                                                  const media = getSlackForChannel(file, 'front');
                                                  setSlackMedia(media || { type: null, src: '' });
                                                  setShowSlackPopup(true);
                                                }}
                                                variant="blue"
                                              />
                                            )}
                                            {file?.analysis?.integrity?.damaged && (
                                              <Badge label="손상" variant="red" />
                                            )}
                                            {isAVI && file?.analysis?.integrity?.damaged && Object.values(file.channels || {}).some(ch => ch?.full_video_path) && (
                                              <Badge label="복원 완료" variant="yellow" />
                                            )}
                                            {isMP4 && file?.slack_info?.recovered && (
                                              <Badge label="복원 완료" variant="yellow" />
                                            )}
                                            {hasSlackBadge && !file?.analysis?.integrity?.damaged && (
                                              <Badge
                                                label="슬랙"
                                                style={{ cursor: 'pointer' }}
                                                onClick={() => {
                                                  setSelectedSlackFile(file);
                                                  const isAVIorJDR = file.name.toLowerCase().endsWith('.avi') || file.name.toLowerCase().endsWith('.jdr');
                                                  if (isAVIorJDR) {
                                                    setSlackChannel('front');
                                                    const media = getSlackForChannel(file, 'front');
                                                    setSlackMedia(media || { type: null, src: '' });
                                                  } else {
                                                    setSlackChannel(null);
                                                    setSlackMedia(mp4Media || { type: null, src: '' });
                                                  }
                                                  setShowSlackPopup(true);
                                                }}
                                                variant="blue"
                                              />
                                            )}
                                          </>
                                        )}
                                    </div>
                                    {isCarvedGroup
                                      ? sizeLabel
                                      : (() => {
                                          const isAviDamagedAndRecovered =
                                            isAVI && file?.analysis?.integrity?.damaged &&
                                            Object.values(file.channels || {}).some(ch => ch?.full_video_path);
                                          const hasRecoveredSlack = isAVI && file?.analysis?.integrity?.damaged &&
                                            Object.values(file.channels || {}).some(ch => ch?.recovered);
                                          if (isAviDamagedAndRecovered && hasRecoveredSlack) {
                                            // 복원 비율 계산
                                            const recoveredSize = Object.values(file.channels || {})
                                              .filter(ch => ch?.full_video_size)
                                              .reduce((sum, ch) => sum + unitToBytes(ch.full_video_size), 0);
                                            const totalSize = unitToBytes(file.size);
                                            const recoveredPercent = totalSize > 0 ? Math.round((recoveredSize / totalSize) * 100) : 0;
                                            // 슬랙 비율 계산 (채널별 slack_rate 합산)
                                            const slackRateSum = Object.values(file.channels || {})
                                              .filter(ch => ch?.slack_rate)
                                              .reduce((sum, ch) => sum + Number(ch.slack_rate), 0);
                                            return `${sizeLabel} ・ 복원 비율: ${recoveredPercent} % ・ 슬랙 비율: ${Math.round(slackRateSum)} %`;
                                          }
                                          if (isAviDamagedAndRecovered) {
                                            const recoveredSize = Object.values(file.channels || {})
                                              .filter(ch => ch?.full_video_size)
                                              .reduce((sum, ch) => sum + unitToBytes(ch.full_video_size), 0);
                                            const totalSize = unitToBytes(file.size);
                                            const recoveredPercent = totalSize > 0 ? Math.round((recoveredSize / totalSize) * 100) : 0;
                                            return `${sizeLabel} ・ 복원 비율: ${recoveredPercent} %`;
                                          }
                                          if (hasRecoveredSlack) {
                                            const slackRateSum = Object.values(file.channels || {})
                                              .filter(ch => ch?.slack_rate)
                                              .reduce((sum, ch) => sum + Number(ch.slack_rate), 0);
                                            return `${sizeLabel} ・ 슬랙 비율: ${Math.round(slackRateSum)} %`;
                                          }
                                          // 기존 MP4 복원/슬랙 비율
                                          return `${sizeLabel} ・ ${
                                            file?.analysis?.integrity?.damaged && file?.slack_info?.recovered
                                              ? '복원 비율'
                                              : '슬랙 비율'
                                          }: ${slackRatePercent} %`;
                                        })()
                                    }
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                      );
                    })
                  )}

                  {showFloatingDownload && (
                    <div style={{ position: 'fixed', right: 70, bottom: 80, zIndex: 2000 }}>
                      <Button variant="dark" onClick={handleDownload}>다운로드</Button>
                    </div>
                  )}
                </div>
              </div>
          </>
        )
      ) : null}
      </Box>

    {/* Alert 조건문 */}
      {showAlert && (
        <Alert
          icon={<AlertIcon className='alert-icon' />}
          title="파일 형식 오류"
          isDarkMode={isDarkMode}
          description={
            <>
            지원되는 형식: .E01 / .001 / .MP4 / .AVI / .JDR<br />
            다른 형식은 업로드할 수 없습니다.<br />
            올바른 파일을 다시 선택해 주세요.
            </>
          }
        >
          <Button variant="dark" onClick={() => setShowAlert(false)}>다시 선택</Button>
        </Alert>
      )}

      {showRestartPopup && (
        <Alert
          icon={<ResetIcon />}
          title="복원 세션 초기화"
          isDarkMode={isDarkMode}
          description={
            <>
              새 복원을 시작하시면 현재 복구하신 파일의<br />
              분석 작업이 모두 초기화 됩니다. <br />
              계속 진행하시겠습니까?
            </>
          }
        >
          <div style={{ display: 'flex', gap: '12px', marginTop: '1rem', justifyContent: 'center' }}>
            <Button
              variant="gray"
              onClick={() => {
                setShowRestartPopup(false);
                setShowComplete(false);         
                setSelectedAnalysisFile(null);  
                setIsRecovering(false);
                setRecoveryDone(true);         
                setView && setView('result');
              }}
            >
              취소
            </Button>

            {/* 세션 리셋 */}
            <Button
              variant="dark"
              onClick={() => {
                setShowRestartPopup(false);
                stopAudio();
                resetSession();
                setShowComplete(false);
                setSelectedAnalysisFile(null);
                setIsRecovering(false);
                setRecoveryDone(false);
                setView && setView('upload'); 
                setIsDiskImage(false);
                setVolumeSlack([]);
              }}
            >
              확인
            </Button>
          </div>
        </Alert>
      )}

      {showTabGuardPopup && (
        <Alert
          icon={<RecoveryPauseIcon/>}
          title="복원 중단 경고"
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
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            backgroundColor: "rgba(0, 0, 0, 0.85)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 9999,
          }}
        >
          <div style={{ position: 'absolute', top: 20, right: 30, display: 'flex', gap: 8 }}>
            {(() => {
              const lowerCaseName = String(selectedSlackFile?.name ?? '').toLowerCase();
              const isMultiChannel = lowerCaseName.endsWith('.avi') || lowerCaseName.endsWith('.jdr');
              const isAVI = lowerCaseName.endsWith('.avi');
              
              if (isMultiChannel) {
                const channelBadges = ['front', 'rear', 'side'].map((ch) => {
                  const media = getSlackForChannel(selectedSlackFile, ch);
                  if (!media) return null;
                  const label = ch === 'front' ? 'Front' : ch === 'rear' ? 'Rear' : 'Side';
                  const active = slackChannel === ch;
                  return (
                    <Badge
                      key={ch}
                      label={label}
                      onClick={() => {
                        setSlackChannel(ch);
                        setSlackMedia(media);
                      }}
                      size="big"
                      style={{
                        cursor: 'pointer',
                        opacity: active ? 1 : 0.6,
                        border: active ? '1px solid #fff' : '1px solid transparent',
                        background: '#333',
                        color: '#fff'
                      }}
                    />
                  );
                });

                // AVI/JDR 모두 Audio 배지 추가
                const isAVIorJDR = isAVI || lowerCaseName.endsWith('.jdr');
                const audioBadge = isAVIorJDR && selectedSlackFile?.channels?.audio ? (
                  <Badge 
                    key="audio"
                    label={
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span>Audio</span>
                      </div>
                    }
                    onClick={() => {
                      // 슬랙 팝업에서는 항상 슬랙 오디오를 재생
                      handleAudioPlay('slack', selectedSlackFile);
                    }}
                    size="big"
                    style={{
                      cursor: 'pointer',
                      opacity: currentAudio?.file?.name === selectedSlackFile?.name ? 1 : 0.6,
                      border: currentAudio?.file?.name === selectedSlackFile?.name ? '1px solid #fff' : '1px solid transparent',
                      background: isAudioPlaying && currentAudio?.file?.name === selectedSlackFile?.name ? '#555' : '#333',
                      color: '#fff'
                    }}
                  />
                ) : null;

                return [...channelBadges.filter(Boolean), audioBadge].filter(Boolean);
              }
              // MP4 slack에 오디오가 있으면 오디오 뱃지 추가
              if (lowerCaseName.endsWith('.mp4') && selectedSlackFile?.slack_info?.audio?.slack) {
                return [
                  <Badge
                    key="audio"
                    label={<div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span>Audio</span></div>}
                    onClick={() => handleAudioPlay('slack', selectedSlackFile)}
                    style={{
                      cursor: 'pointer',
                      opacity: currentAudio?.file?.name === selectedSlackFile?.name ? 1 : 0.6,
                      border: currentAudio?.file?.name === selectedSlackFile?.name ? '1px solid #fff' : '1px solid transparent',
                      background: isAudioPlaying && currentAudio?.file?.name === selectedSlackFile?.name ? '#555' : '#333',
                      color: '#fff'
                    }}
                  />
                ];
              }
              return null;
            })()}
            <Button variant="gray" onClick={() => { stopAudio(); setShowSlackPopup(false); }}>
              닫기
            </Button>
          </div>

          <div
            style={{
                width: '90vw', maxWidth: 1280, height: '80vh',
                display: 'flex', justifyContent: 'center', alignItems: 'center',
                background: 'black', borderRadius: 12, overflow: 'hidden', padding: 12
              }}
          >
            {slackMedia?.type === 'video' ? (
              <video
                controls preload="metadata"
                style={{ width: '100%', height: '100%' }}
                src={slackMedia.src}
                onError={() => {
                  if (slackMedia.fallback) {
                    setSlackMedia({ type: 'image', src: slackMedia.fallback });
                  }
                }}
                onLoadedMetadata={(e) => {
                  const dur = e.currentTarget.duration;
                  if ((Number.isFinite(dur) && dur === 0) && slackMedia.fallback) {
                    setSlackMedia({ type: 'image', src: slackMedia.fallback });
                  }
                }}
              />
            ) : slackMedia?.type === 'image' ? (
              <img
                alt="slack"
                style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
                src={slackMedia.src}
              />
            ) : (
              <div style={{ color: '#fff' }}>표시할 슬랙 매체가 없습니다.</div>
            )}
          </div>
        </div>
      )}

      {showDiskFullAlert && (
        <Alert
          icon={<StorageFullIcon />}
          title="용량 부족 알림"
          isDarkMode={isDarkMode}
          description={
            <>
              복원 영상을 저장할 드라이브에 용량이 부족합니다<br />
              용량을 비우고 다시 시도해주세요
            </>
          }
        >
          <Button
            variant="dark"
            onClick={() => {
              setShowDiskFullAlert(false);      
              diskFullHandledRef.current = false; 
            }}
          >
            확인
          </Button>
        </Alert>
      )}

      {showDownloadPopup && (
        <Alert
          icon={<DownloadIcon />}
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
                  style={{ flex: 1, height: '26px' }}
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
            <Button
              variant="dark"
              onClick={handleDownloadConfirm}
              disabled={
                isDownloading ||
                !selectedPath ||
                selectedFilesForDownload.length === 0
              }
            >
              완료
            </Button>
          </div>
        </Alert>
      )}

      {showClosePopup && (
        <Alert
          icon={<RecoveryPauseIcon style={{ color: '#eab308' }} />}
          title="복원 결과 닫기"
          isDarkMode={isDarkMode}
          description= {
            <>
              복원 결과를 닫고 파일 업로드로 돌아갈까요?
            </>
          }
        >
          <div className="alert-buttons">
            <Button variant="gray" onClick={() => { stopAudio(); setShowClosePopup(false); }}>취소</Button>
            <Button
              variant="dark"
              onClick={() => {
                setShowClosePopup(false);
                resetToUpload();
              }}
            >
              확인
            </Button>
          </div>
        </Alert>
      )}

      {showStopRecoverPopup && (
        <Alert
          icon={<RecoveryPauseIcon style={{ color: '#eab308' }} />}
          title="복원 종료"
          isDarkMode={isDarkMode}
          description={
            <>
              복원을 종료할까요?<br />
              진행 중인 작업이 즉시 중지됩니다.
            </>
          }
        >
          <div className="alert-buttons">
            <Button variant="gray" onClick={() => setShowStopRecoverPopup(false)}>취소</Button>
            <Button
              variant="dark"
              onClick={async () => {
                try {
                  await window.api.cancelRecovery();
                } catch {}
                setShowStopRecoverPopup(false);
              }}
            >
              종료
            </Button>
          </div>
        </Alert>
      )}
    </div>
  );
}
export default Recovery;