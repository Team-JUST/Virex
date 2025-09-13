const { app, BrowserWindow, Menu, ipcMain, dialog, protocol } = require('electron');
// 개발 환경에서 핫리로드 적용
const fs = require('fs').promises; 

const fssync = require('fs');     
const path = require('path');
const { spawn } = require('child_process');
const readline = require('readline');
const drivelist = require('drivelist');
const checkDiskSpace = require('check-disk-space').default;
const os = require('os');


const VOL_CARVER = path.join(__dirname, 'python_engine', 'tools', 'vol_carver.py');
const FFMPEG_DIR = path.join(__dirname, 'bin'); // 폴더(파일 아님)

function hasBinFiles(dir) {
  try {
    const list = fssync.readdirSync(dir);
    return list.some(n => n.toLowerCase().endsWith('.bin'));
  } catch { return false; }
}

function waitForUnallocReady(baseDir, { timeoutMs = 120000, intervalMs = 800 } = {}) {
  const unalloc = path.join(baseDir, 'p2_fs_unalloc');
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      if (Date.now() - start > timeoutMs) {
        return reject(new Error('waitForUnallocReady: timeout'));
      }
      if (fssync.existsSync(unalloc) && hasBinFiles(unalloc)) {
        return resolve({ baseDir, unalloc });
      }
      setTimeout(tick, intervalMs);
    };
    tick();
  });
}

function runVolCarver(baseDir, sender) {
  return new Promise((resolve) => {
    const args = [VOL_CARVER, baseDir, '--ffmpeg-dir', FFMPEG_DIR];
    const child = spawn('python', args, {
      cwd: path.dirname(VOL_CARVER),
      shell: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });
    child.stderr.on('data', b => console.warn('[vol_carver]', b.toString()));
    child.on('close', async (code) => {
      const win = BrowserWindow.fromWebContents(sender);
      // 프론트: baseDir 알려주고 → carved_index.json 읽게 함
      win?.webContents.send('analysis-path', baseDir);

      // (선택) 바로 결과도 푸시하고 싶으면 carved_index.json 읽어서 전송
      try {
        const idxPath = path.join(baseDir, 'carved_index.json');
        const raw = await fs.readFile(idxPath, 'utf-8');
        const j = JSON.parse(raw);
        const items = (j?.items || []).flatMap(it => {
          const rebuilt = (it.rebuilt || [])
            .filter(x => (x?.rebuilt && x?.ok) || x?.raw)
            .map(x => ({ name: path.basename(x.rebuilt || x.raw), path: (x.rebuilt || x.raw), size: Number(x?.probe?.format?.size || 0), _remuxFailed: !x?.rebuilt || !x?.ok }));
          const jdr = (it.jdr || [])
            .filter(x => x?.ok && x?.rebuilt)
            .map(x => ({ name: path.basename(x.rebuilt), path: x.rebuilt, size: Number(x?.probe?.format?.size || 0) }));
          return [...rebuilt, ...jdr];
        });
        win?.webContents.send('recovery-results', items);
      } catch (e) {
        console.warn('[vol_carver] no carved_index yet:', e?.message || e);
      }

      resolve(code);
    });
  });
}


if (process.env.NODE_ENV === 'development') {
  try {
    require('electron-reload')(__dirname, {
      electron: require(`${__dirname}/node_modules/electron`),
      // src, public, main.js 등도 감시
      watch: [
        path.join(__dirname, 'main.js'),
        path.join(__dirname, 'preload.js'),
        path.join(__dirname, 'src'),
        path.join(__dirname, 'public')
      ]
    });
    console.log('[Debug] electron-reload enabled');
  } catch (e) {
    console.warn('[Debug] electron-reload not installed or failed:', e);
  }
}



const isSafeTempDir = (dir) => {
  if (!dir) return false;
  const tmp= path.resolve(os.tmpdir());
  const abs = path.resolve(dir);
  return abs.startsWith(tmp) && path.basename(abs).startsWith('Virex_');
}

const removeDirWithRetry = (dir, tries = 2, delay = 150) => {
  const attempt = () => {
    try {
      if (dir && fssync.existsSync(dir)) {
        fssync.rmSync(dir, { recursive: true, force: true });
      }
    } catch (e) {
      if (tries > 0) setTimeout(() => removeDirWithRetry(dir, tries - 1, delay), delay);
    }
  };
  attempt();
}

let mainWindow = null;
let currentRecoveryProc = null;
let currentTempDir = null;
let isCancellingRecovery = false;
let volCarverStarted = false;

// Classify drive type
function classifyDrive(drive) {
  if (drive.isUSB || drive.isCard || drive.isRemovable) return 'removable';
  if (drive.isSystem) return 'internal';
  return 'external';
}

ipcMain.handle('check-disk-space', async (_event, targetPath, requiredBytes) => {
  const root = path.parse(targetPath).root || targetPath; // D:\ 같은 루트
  const { free, size } = await checkDiskSpace(root);
  return { ok: free >= requiredBytes, free, size };
});

// Label formatting
function makeDriveLabel(drive, mountPath) {
  const letterMatch = mountPath.match(/^([A-Z]):/i);
  if (letterMatch) {
    const letter = letterMatch[1].toUpperCase();
    return `${letter}: Drive`;
  }
  return drive.description || mountPath;
}

// Get detailed drive list
async function getDrivesWithInfo() {
  const drives = await drivelist.list();

  const mapped = await Promise.all(
    drives.flatMap((drive, driveIdx) =>
      drive.mountpoints.map(async (mp, mpIdx) => {
        const mountPath = mp.path;
        if (!mountPath) return null;

        let size = 0;
        let free = 0;
        try {
          const space = await checkDiskSpace(mountPath);
          size = space.size ?? 0;
          free = space.free ?? 0;
        } catch {
          size = 0;
          free = 0;
        }

        return {
          id: `${driveIdx}-${mpIdx}`,
          label: makeDriveLabel(drive, mountPath),
          mount: mountPath,
          size,
          free,
          kind: classifyDrive(drive),
          raw: {
            description: drive.description,
            device: drive.device,
            busType: drive.busType,
          },
        };
      })
    )
  );

  return mapped.filter(Boolean);
}

// Push drive list to renderer
function broadcastDrives() {
  if (!mainWindow) return;
  getDrivesWithInfo()
    .then((info) => {
      mainWindow.webContents.send('drives-updated', info);
    })
    .catch((err) => {
      console.error('[Debug] Failed to broadcast drives:', err);
      mainWindow.webContents.send('drives-updated', []);
    });
}

// Start polling drive status
function startDrivePolling() {
  broadcastDrives(); // once on start
  setInterval(broadcastDrives, 5000); // then every 5s
}

// Create the main window
function createWindow() {
  const iconPath = path.join(__dirname, app.isPackaged ? 'dist' : 'public', 'titleIcon.ico');

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    resizable: false,
    fullscreenable: false,
    autoHideMenuBar: true,
    backgroundColor: '#ecf2f8',
    title: 'Virex',
    icon: iconPath,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'));
  }
}


// view
app.whenReady().then(() => {
  protocol.interceptFileProtocol('stream', (request, callback) => {
    const url = request.url.substr(9); // 'stream://' 제거
    const decodedPath = decodeURIComponent(url);
    console.log('[Debug] stream request:', decodedPath);
    callback({ path: decodedPath });
  });

  createWindow();
  startDrivePolling();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.handle('get-drives', async () => {
  return await getDrivesWithInfo();
});

ipcMain.handle('read-folder', async (_event, folderPath) => {
  try {
    const dirents = await fs.readdir(folderPath, { withFileTypes: true });
    dirents.sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));

    const items = [];
    for (const e of dirents) {
      const full = path.join(folderPath, e.name);
      let size = 0;
      if (!e.isDirectory()) {
        try {
          size = (await fs.stat(full)).size;
        } catch {
          try { size = fssync.statSync(full).size; } catch { }
        }
      }
      items.push({
        name: e.name,
        path: full,
        isDirectory: e.isDirectory(),
        isE01: e.name.toLowerCase().endsWith('.e01'),
        size,
      });
    }
    return items;
  } catch (err) {
    console.error('[Debug] read-folder error:', err);
    return [];
  }
});

ipcMain.on('file-selected', (_event, filePath) => {
  console.log("[Debug] selected E01 file path : ", filePath);
});


ipcMain.handle('start-recovery', async (event, e01FilePath) => {
  console.log("[Debug] start-recovery called with : ", e01FilePath);

  // 1) 시작 전 프리플라이트
  const REQUIRED_BYTES = 5 * 1024 * 1024 * 1024;
  const target = os.tmpdir(); 
  const root = path.parse(target).root || target;

  try {
    const { free } = await checkDiskSpace(root);
    if (free < REQUIRED_BYTES) {
      // 렌더러로 알림 전송 (초기부터 부족한 케이스)
      const win = BrowserWindow.fromWebContents(event.sender);
      win?.webContents.send('recovery-disk-full', { free, needed: REQUIRED_BYTES, phase: 'preflight' });
      // 시작 자체를 중단
      return { started: false, reason: 'disk_full' };
    }
  } catch (e) {
    console.warn('[Debug] preflight disk check failed:', e);
    // 보수적으로 막고 알림 띄움
    const win = BrowserWindow.fromWebContents(event.sender);
    win?.webContents.send('recovery-disk-full', { free: null, needed: REQUIRED_BYTES, phase: 'preflight_error' });
    return { started: false, reason: 'disk_check_failed' };
  }

  // 2) (통과 시) 기존 파이썬 spawn 로직 실행
  return await new Promise((resolve, reject) => {
    let abortedByDiskFull = false;
    let sentResults = false;
    const scriptPath = path.join(__dirname, 'python_engine', 'main.py');
    const env = {...process.env, PYTHONPATH: __dirname, PYTHONIOENCODING: 'utf-8',PYTHONUTF8: '1',  };

    const python = spawn('python', [scriptPath, e01FilePath], {
      cwd: path.join(__dirname, 'python_engine'),
      shell: true,
      env,
    });
    currentRecoveryProc = python;
    isCancellingRecovery = false;

    const rl = readline.createInterface({ input: python.stdout });
    rl.on('line', async line => {

      try {
        const data = JSON.parse(line);

        if (data.tempDir) {
          currentTempDir = data.tempDir;
          const win = BrowserWindow.fromWebContents(event.sender);

          // UI가 tempDir 알 수 있게 즉시 알려주기
          win?.webContents.send('analysis-path', data.tempDir);

          // 비할당 .bin 준비 감시 후 vol_carver 실행
          waitForUnallocReady(currentTempDir)
            .then(() => runVolCarver(currentTempDir, event.sender))
            .catch(err => console.warn('[waitForUnallocReady]', err.message));

          return;
        }


        if (data.event === 'extract_done') {
          currentTempDir = data.output_dir || currentTempDir;
          const win = BrowserWindow.fromWebContents(event.sender);
          if (currentTempDir) win?.webContents.send('analysis-path', currentTempDir);
          win?.webContents.send('recovery-results', Array.isArray(data.results) ? data.results : []);
          sentResults = true; 
          return;
        }

        // (중간) 용량 부족 이벤트
        if (data.event === 'disk_full') {
          abortedByDiskFull = true;
          console.warn('[Debug] disk_full:', data);

          const win = BrowserWindow.fromWebContents(event.sender);
          win?.webContents.send('recovery-disk-full', {
            free: data.free ?? null,
            needed: data.needed ?? null,
            phase: 'during',
          });

          try { python.kill(); } catch (_) {}
          return; // 진행률/분석 처리 안 함
        }

        // 진행률
        if (data.processed !== undefined && data.total !== undefined) {
          const win = BrowserWindow.fromWebContents(event.sender);
          win?.webContents.send('recovery-progress', {
            processed: data.processed,
            total: data.total
          });
          return;
        }

        // analysisPath
        if (data.analysisPath) {
          console.log("[Debug] got analysisPath : ", data.analysisPath);
          const tempDir = path.dirname(data.analysisPath);
          currentTempDir = tempDir;

          const win = BrowserWindow.fromWebContents(event.sender);
          win?.webContents.send('analysis-path', tempDir);

          try {
            const raw = await fs.readFile(data.analysisPath, 'utf8');
            const results = JSON.parse(raw);
            console.log("[Debug] results to frontend count : ", results.length);

            results.forEach((result, index) => {
              console.log(`[Debug] result ${index} : name=${result.name}, slack_info = `, result.slack_info);
            });
            win?.webContents.send('recovery-results', results);
          } catch (err) {
            console.error("[Debug] failed to read analysis.json : ", err);
            const win = BrowserWindow.fromWebContents(event.sender);
            win?.webContents.send('recovery-results', { error: err.message });
            sentResults = true;
          }
          return;
        }

      } catch (e) {
        console.log("[Debug] not JSON : ", line);
      }
    });

    python.stderr.on('data', buf => {
    const msg = buf.toString(); 
    console.error("[Debug] python stderr : ", msg);
    const win = BrowserWindow.fromWebContents(event.sender);
    win?.webContents.send('recovery-error', msg);
  });

    python.on('close', code => {
      console.log("[Debug] python exited with code : ", code);
      rl.close();

      volCarverStarted = false;

      const win = BrowserWindow.fromWebContents(event.sender);

      if (!sentResults) {
        console.log('[Debug] no results were sent; sending empty array');
        try { win?.webContents.send('recovery-results', []); } catch {}
      }
      const wasCancelling = isCancellingRecovery;
      const wasDiskFull = abortedByDiskFull;

      currentRecoveryProc = null;
      isCancellingRecovery = false;

      if (wasCancelling) {
        const dir = currentTempDir;
        if (isSafeTempDir(dir)) {
          setTimeout(() => removeDirWithRetry(dir), 50);
        }
        currentTempDir = null;

        try { win?.webContents.send('recovery-cancelled'); } catch {}
        return resolve();
      }

      if (wasDiskFull) {
        const dir = currentTempDir;
        if (isSafeTempDir(dir)) {
          setTimeout(() => removeDirWithRetry(dir), 50);
        }
        currentTempDir = null;

        return reject(new Error('aborted: disk_full'));
      }

      try { win?.webContents.send('recovery-done'); } catch {}
      return code === 0 ? resolve() : reject(new Error(`exit ${code}`));
    });
  });
});

ipcMain.handle('cancel-recovery', async () => {
  if (!currentRecoveryProc) return { ok: true, note: 'no-active-process' };
  if (isCancellingRecovery) return { ok: true, note: 'already-cancelling' };
  isCancellingRecovery = true;
  const proc = currentRecoveryProc;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/PID', String(proc.pid), '/T', '/F']);
    } else {
      process.kill(proc.pid, 'SIGTERM');
      setTimeout(() => { try { process.kill(proc.pid, 'SIGKILL'); } catch {} }, 1500);
    }
    return { ok: true };
  } catch (e) {
    try { proc.kill(); } catch {}
    return { ok: false, error: String(e?.message || e) };
  }
});

ipcMain.handle('run-download', async (_event, { e01Path, choice, downloadDir, files }) => {
  // 1) 호출된 인자 찍기
  console.log("[Debug] run-download called with : ", { e01Path, choice, downloadDir, files });

  // 2) 인자 유효성 검사
  if (
    typeof e01Path !== 'string' ||
    typeof choice !== 'string' ||
    typeof downloadDir !== 'string' ||
    !e01Path.trim() ||
    !choice.trim() ||
    !downloadDir.trim()
  ) {

    console.error("[Debug] run-download invalid args : ", { e01Path, choice, downloadDir });

    mainWindow.webContents.send(
      'download-error',
      `Invalid args for run-download: ${JSON.stringify({ e01Path, choice, downloadDir })}`
    );
    throw new Error('run-download: invalid args');
  }

  if (!Array.isArray(files) || files.length === 0) {
    const msg = 'No files selected';
    console.error('[Debug] run-download:', msg);
    mainWindow.webContents.send('download-error', msg);
  throw new Error(msg);
  }

  const baseNames = files.map(p => path.basename(p));
  const selectedJsonPath = path.join(e01Path, 'selected_files.json');
  await fs.writeFile(selectedJsonPath, JSON.stringify(baseNames, null, 2), 'utf-8');

  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, 'python_engine', 'main.py');
    const env = { ...process.env, PYTHONPATH: __dirname };
    const args = [scriptPath, e01Path, choice, downloadDir, selectedJsonPath];

    console.log("[Debug] spawning python with args : ", args);

    const python = spawn('python', args, {
      cwd: path.join(__dirname, 'python_engine'),
      shell: true,
      env,
    });

    const rl = readline.createInterface({ input: python.stdout });
    rl.on('line', line => {
      console.log("[Debug] download line : ", line);
      mainWindow.webContents.send('download-log', line);
    });

    python.stderr.on('data', buf => {
    const msg = buf.toString();
    console.error("[Debug] python stderr (download) : ", msg);
    mainWindow.webContents.send('download-error', msg);
  });

    python.on('close', code => {
      console.log("[Debug] download python exited with code : ", code);
      rl.close();
      if (code === 0) {
        mainWindow.webContents.send('download-complete');
        resolve();
      } else {

        const err = new Error(`run-download exit ${code} with args ${JSON.stringify(args)}`);
        reject(err);
      }
    });
  });
});

ipcMain.handle('dialog:openDirectory', async (_event, options = {}) => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    properties: ['openDirectory'],
    ...options
  });
  if (canceled) return null;
  return filePaths[0];
});


// carved_index.json 탐색 함수
const tryRead = async (p) => {
  try {
    const raw = await fs.readFile(p, 'utf-8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

ipcMain.handle('readCarvedIndex', async (_event, outDir) => {
  if (!outDir) return { items: [] };

  const candidates = [
    path.join(outDir, 'carved_index.json'),
    path.join(outDir, 'carved', 'carved_index.json'),
    path.join(outDir, 'carving', 'carved_index.json'),
    path.join(outDir, 'results', 'carved_index.json'),
  ];
  for (const p of candidates) {
    const j = await tryRead(p);
    if (j) return j;
  }

  // BFS 탐색
  const maxDepth = 3;
  const queue = [{ dir: outDir, depth: 0 }];
  while (queue.length) {
    const { dir, depth } = queue.shift();
    if (depth > maxDepth) continue;

    let entries = [];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) {
        queue.push({ dir: full, depth: depth + 1 });
      } else if (e.isFile() && e.name.toLowerCase() === 'carved_index.json') {
        const j = await tryRead(full);
        if (j) return j;
      }
    }
  }

  // 못 찾으면 빈 구조 반환
  return { items: [] };
});

ipcMain.handle('clear-cache', async () => {
  const tempDir = os.tmpdir();
  const files = fssync.readdirSync(tempDir);
  let deleted = 0;
  for (const file of files) {
    if (file.startsWith('Virex_')) {
      const fullPath = path.join(tempDir, file);
      try {
        fssync.rmSync(fullPath, { recursive: true, force: true });
        deleted++;
      } catch (e) {
        // 무시
      }
    }
  }
  return deleted;
});



ipcMain.handle('dialog:openE01File', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: 'E01 파일 선택',
    filters: [{ name: 'E01 Files', extensions: ['e01'] }],
    properties: ['openFile'],
  });
  if (canceled) return null;
  return filePaths[0];  // 선택된 파일 경로 하나 반환
});


