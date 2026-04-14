const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

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

const createPythonBackend = () => {
  const isDev = !app.isPackaged;
  
  if (isDev) {
    console.log('Running in Dev Mode - Waiting for manual backend...');
  } else {
    // PROD MODE: Launch the compiled executable
    // Path: Contents/Resources/backend/asana-brain/asana-brain
    const backendPath = path.join(process.resourcesPath, 'backend', 'asana-brain', 'asana-brain');
    console.log('Launching Backend from:', backendPath);
    
    pythonProcess = spawn(backendPath, [], {
      detached: false,
      stdio: 'ignore' 
    });

    pythonProcess.on('error', (err) => {
      console.error('Failed to start backend:', err);
    });
  }
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

app.on('ready', () => {
  createPythonBackend();
  createWindow();
});

// KILL SWITCH: Kill python when app closes
app.on('will-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
});

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
