const { app, BrowserWindow, Menu, ipcMain, dialog, protocol } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const readline = require('readline');
const drivelist = require('drivelist');
const checkDiskSpace = require('check-disk-space').default;
const fs = require('fs').promises;
const fssync = require('fs');
const os = require('os');


let mainWindow = null;

// Classify drive type
function classifyDrive(drive) {
  if (drive.isUSB || drive.isCard || drive.isRemovable) return 'removable';
  if (drive.isSystem) return 'internal';
  return 'external';
}

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
      console.error('Failed to broadcast drives:', err);
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
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    resizable: false,
    fullscreenable: false,
    autoHideMenuBar: true,
    backgroundColor: '#ecf2f8',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });



  mainWindow.loadFile(path.join(__dirname, 'dist/index.html'));
  startDrivePolling();
}

// view
app.whenReady().then(() => {
  // ✅ stream 프로토콜 등록
  protocol.interceptFileProtocol('stream', (request, callback) => {
    const url = request.url.substr(9); // 'stream://' 제거
    const decodedPath = decodeURIComponent(url);
    console.log('📦 stream 요청:', decodedPath);
    callback({ path: decodedPath });
  });

  // 기존 창 생성
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// IPC: get-drives
ipcMain.handle('get-drives', async () => {
  return await getDrivesWithInfo();
});

// IPC: read-folder
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
    console.error('read-folder error:', err);
    return [];
  }
});

ipcMain.on('file-selected', (_event, filePath) => {
  console.log('선택된 E01 파일 경로:', filePath);
});

ipcMain.handle('start-recovery', (_event, e01FilePath) => {
  console.log('▶ start-recovery called with', e01FilePath);

  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, 'python_engine', 'main.py');
    const env = { ...process.env, PYTHONPATH: __dirname };
    const python = spawn('python', [scriptPath, e01FilePath], {
      cwd: path.join(__dirname, 'python_engine'),
      shell: true,
      env,
    });

    console.log('--- Python spawned, waiting for stdout lines ---');

    const rl = readline.createInterface({ input: python.stdout });
    rl.on('line', async line => {
      console.log('⭸ raw line:', line);
      try {
        const data = JSON.parse(line);

        // 1) 진행률 이벤트
        if (data.processed !== undefined && data.total !== undefined) {
          mainWindow.webContents.send('recovery-progress', {
            processed: data.processed,
            total: data.total
          });
          return;
        }

        // 2) analysisPath 이벤트
        if (data.analysisPath) {
          console.log('✔ got analysisPath:', data.analysisPath);
          const tempDir = path.dirname(data.analysisPath);
          mainWindow.webContents.send('analysis-path', tempDir);
          try {
            const raw = await fs.readFile(data.analysisPath, 'utf8');
            const results = JSON.parse(raw);
            console.log('📤 [MAIN.JS] 프론트엔드로 전송할 결과 개수:', results.length);
            results.forEach((result, index) => {
              console.log(`📤 [MAIN.JS] 결과 ${index}: name=${result.name}, slack_info=`, result.slack_info);
            });
            mainWindow.webContents.send('recovery-results', results);
          } catch (err) {
            console.error('Failed to read analysis.json:', err);
            mainWindow.webContents.send('recovery-results', { error: err.message });
          }
          return;
        }

      } catch (e) {
        console.log('⚠️ not JSON:', line);
      }
    });

    python.stderr.on('data', buf => {
      console.error('Python stderr:', buf.toString());
      mainWindow.webContents.send('recovery-error', buf.toString());
    });

    python.on('close', code => {
      console.log('🔚 python exited with code', code);
      rl.close();
      mainWindow.webContents.send('recovery-done');
      code === 0 ? resolve() : reject(new Error(`exit ${code}`));
    });
  });
});

ipcMain.handle('run-download', (_event, { e01Path, choice, downloadDir }) => {
  // 1) 호출된 인자 찍기
  console.log('▶ run-download called with', {
    e01Path, choice, downloadDir
  });

  // 2) 인자 유효성 검사
  if (
    typeof e01Path !== 'string' ||
    typeof choice !== 'string' ||
    typeof downloadDir !== 'string' ||
    !e01Path.trim() ||
    !choice.trim() ||
    !downloadDir.trim()
  ) {
    console.error('❌ run-download invalid args:', {
      e01Path, choice, downloadDir
    });
    // 에러 전송 시에도 어떤 인자가 잘못됐는지 명확히
    mainWindow.webContents.send(
      'download-error',
      `Invalid args for run-download: ${JSON.stringify({ e01Path, choice, downloadDir })}`
    );
    throw new Error('run-download: invalid args');
  }

  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, 'python_engine', 'main.py');
    const env = { ...process.env, PYTHONPATH: __dirname };
    const args = [scriptPath, e01Path, choice, downloadDir];

    console.log('▶ spawning python with args:', args);

    const python = spawn('python', args, {
      cwd: path.join(__dirname, 'python_engine'),
      shell: true,
      env,
    });

    const rl = readline.createInterface({ input: python.stdout });
    rl.on('line', line => {
      console.log('⭸ download line:', line);
      mainWindow.webContents.send('download-log', line);
    });

    python.stderr.on('data', buf => {
      const msg = buf.toString();
      console.error('Python stderr (download):', msg);
      mainWindow.webContents.send('download-error', msg);
    });

    python.on('close', code => {
      console.log('🔚 download python exited with code', code);
      rl.close();
      if (code === 0) {
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

ipcMain.handle('clear-cache', async () => {
  const tempDir = os.tmpdir();
  const files = fssync.readdirSync(tempDir);
  let deleted = 0;
  for (const file of files) {
    if (file.startsWith('retato_')) {
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
