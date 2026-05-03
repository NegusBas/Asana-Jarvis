const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

// Minimal .env parser (no external dep). Returns a plain object of KEY=VALUE pairs.
const loadDotenv = (envPath) => {
  try {
    if (!fs.existsSync(envPath)) return {};
    const out = {};
    const text = fs.readFileSync(envPath, 'utf8');
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) continue;
      const eq = line.indexOf('=');
      if (eq === -1) continue;
      const key = line.slice(0, eq).trim();
      let val = line.slice(eq + 1).trim();
      if ((val.startsWith('"') && val.endsWith('"')) ||
          (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      out[key] = val;
    }
    return out;
  } catch (e) {
    console.warn('[env] failed to read', envPath, e.message);
    return {};
  }
};

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
try {
  if (require('electron-squirrel-startup')) {
    app.quit();
  }
} catch (e) {
  // Module might not be installed yet
}

let mainWindow;
let pythonProcess;
let windowCreated = false;

const openWindowOnce = () => {
  if (!windowCreated) {
    windowCreated = true;
    createWindow();
  }
};

const createPythonBackend = () => {
  const isDev = !app.isPackaged;

  // In dev, use the pre-built binary in the repo's resources/ folder.
  // In prod, Electron copies that same folder to Contents/Resources/backend.
  const backendPath = isDev
    ? path.join(__dirname, '..', 'resources', 'backend', 'asana-brain', 'asana-brain')
    : path.join(process.resourcesPath, 'backend', 'asana-brain', 'asana-brain');

  // The frozen binary does `os.chdir(dirname(sys.executable))`, so a .env next to it
  // would be found — but we don't ship one. Instead, we load the repo/app .env here
  // and inject it into the subprocess env. This works in dev AND prod.
  const envCandidates = isDev
    ? [path.join(__dirname, '..', '.env'), path.join(__dirname, '..', 'backend', '.env')]
    : [
        path.join(process.resourcesPath, '.env'),
        path.join(process.resourcesPath, 'backend', '.env'),
        path.join(path.dirname(app.getPath('exe')), '.env'),
      ];

  let loadedEnv = {};
  for (const p of envCandidates) {
    const parsed = loadDotenv(p);
    if (Object.keys(parsed).length) {
      console.log('[backend] loaded env from', p);
      loadedEnv = { ...loadedEnv, ...parsed };
      break;
    }
  }
  if (!loadedEnv.GEMINI_API_KEY) {
    console.warn('[backend] WARNING: GEMINI_API_KEY not found in .env candidates:', envCandidates);
  }

  console.log(`[backend] launching (${isDev ? 'dev' : 'prod'}):`, backendPath);

  pythonProcess = spawn(backendPath, [], {
    detached: false,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, ...loadedEnv },
  });

  pythonProcess.stdout.on('data', (data) => {
    const text = data.toString();
    process.stdout.write(`[backend] ${text}`);
    // Open window as soon as uvicorn signals it is ready
    if (!windowCreated && text.includes('Application startup complete')) {
      openWindowOnce();
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    process.stderr.write(`[backend] ${data}`);
  });

  pythonProcess.on('error', (err) => {
    console.error('[backend] failed to start:', err);
  });

  pythonProcess.on('exit', (code, signal) => {
    console.log(`[backend] exited (code=${code}, signal=${signal})`);
    pythonProcess = null;
  });
};

const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    titleBarStyle: 'hidden',
    backgroundColor: '#000000',
    webPreferences: {
      // Use fallback if preload.js is missing
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  // Handle both Dev Server and Production Build paths
  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
};

// IPC handlers for custom title bar window controls
ipcMain.on('window-minimize', () => mainWindow && mainWindow.minimize());
ipcMain.on('window-maximize', () => {
  if (mainWindow) {
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
  }
});
ipcMain.on('window-close', () => mainWindow && mainWindow.close());

app.on('ready', () => {
  const appDir = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..');
  if (/Mobile Documents|\.Trash/.test(appDir)) {
    console.warn(
      '\n[asana] WARNING: app is running from an iCloud or Trash path:\n  ' +
        appDir +
        '\n  iCloud may evict the bundled backend files, causing the backend to hang silently.\n' +
        '  Move the project to a local path like ~/Projects/asana-Jarvis and re-run.\n'
    );
  }
  createPythonBackend();
  // Window opens when backend signals readiness via stdout ("Application startup complete").
  // Fallback: open after 4 seconds in case the signal is missed or backend is slow.
  setTimeout(() => openWindowOnce(), 4000);
});

// KILL SWITCH: Kill backend when app closes or crashes
const killBackend = () => {
  if (pythonProcess) {
    try { pythonProcess.kill('SIGTERM'); } catch (_) {}
    pythonProcess = null;
  }
};

app.on('will-quit', killBackend);
app.on('before-quit', killBackend);
process.on('exit', killBackend);
process.on('SIGINT', () => { killBackend(); process.exit(0); });
process.on('SIGTERM', () => { killBackend(); process.exit(0); });

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
