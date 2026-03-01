const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const fs = require('node:fs/promises');
const fssync = require('node:fs');
const path = require('node:path');
const dotenv = require('dotenv');

dotenv.config();

const isDev = Boolean(process.env.VITE_DEV_SERVER_URL);
const rendererDevUrl = process.env.VITE_DEV_SERVER_URL;
const apiUrl = process.env.VITE_API_URL || 'http://localhost:8000';

const FILE_TAG_CACHE = new Map();
const TREE_CACHE = new Map(); // path → { node, expiresAt }
const TREE_CACHE_TTL_MS = 60_000; // 1 minute
const MAX_SCAN_FILES = 600;
const MAX_TREE_DEPTH = 8;
const MAX_WALK_DEPTH = 10;

const PRIORITY_KEYWORDS = {
  high: ['important', 'urgent', 'critical', 'priority', 'asap', 'now'],
  low: ['old', 'backup', 'archive', 'temp', 'draft', 'unused', 'deprecated']
};

const DELETE_KEYWORDS = ['trash', 'delete', 'remove', 'junk', 'scrap', 'unused', 'old', 'deprecated', 'backup'];

const CATEGORY_MAP = {
  Documents: ['.pdf', '.doc', '.docx', '.txt', '.md', '.rtf', '.ppt', '.pptx', '.xls', '.xlsx', '.csv'],
  Images: ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.heic'],
  Videos: ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm'],
  Audio: ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a'],
  Archives: ['.zip', '.rar', '.7z', '.tar', '.gz'],
  Code: ['.js', '.ts', '.tsx', '.jsx', '.py', '.java', '.go', '.rs', '.c', '.cpp', '.cs', '.html', '.css', '.json', '.yml', '.yaml']
};

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value > 10 ? 1 : 2)} ${units[unit]}`;
}

function detectCategory(fileName) {
  const ext = path.extname(fileName).toLowerCase();
  for (const [category, extensions] of Object.entries(CATEGORY_MAP)) {
    if (extensions.includes(ext)) {
      return category;
    }
  }
  return 'Others';
}

function extractSemanticGroup(fileName, filePath = '') {
  const nameLower = fileName.toLowerCase();

  // Check context first
  if (SEMANTIC_KEYWORDS.context.school.some(k => nameLower.includes(k))) return 'School';
  if (SEMANTIC_KEYWORDS.context.work.some(k => nameLower.includes(k))) return 'Work';
  if (SEMANTIC_KEYWORDS.context.media.some(k => nameLower.includes(k))) return 'Media';
  if (SEMANTIC_KEYWORDS.context.personal.some(k => nameLower.includes(k))) return 'Personal';

  // Fallback to category
  return detectCategory(fileName);
}

function extractOrganizationSubfolder(filePath = '') {
  const name = path.basename(filePath).toLowerCase();

  // Detect if deletable - higher threshold
  const { deletable, important } = classifyFileSeverity(name);
  if (deletable > 3) return 'Deletable';
  if (important > 3) return 'Important';

  return 'Default';
}

function shouldDelete(fileName, fileContent = '') {
  const { deletable } = classifyFileSeverity(fileName);
  return deletable > 3;
}

async function safeReadDir(dirPath) {
  try {
    return await fs.readdir(dirPath, { withFileTypes: true });
  } catch {
    return [];
  }
}

async function buildTreeNode(targetPath, depth = 0, fileCounter = { count: 0 }) {
  const stat = await fs.stat(targetPath);
  let size = 0;

  // For files, use actual file size
  if (!stat.isDirectory()) {
    size = stat.size;
  }

  const baseNode = {
    name: path.basename(targetPath) || targetPath,
    path: targetPath,
    type: stat.isDirectory() ? 'folder' : 'file',
    size: size,
    lastModified: stat.mtimeMs,
    children: []
  };

  if (!stat.isDirectory() || depth > MAX_TREE_DEPTH || fileCounter.count > MAX_SCAN_FILES) {
    return baseNode;
  }

  const entries = await safeReadDir(targetPath);
  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue;
    const childPath = path.join(targetPath, entry.name);
    try {
      const childNode = await buildTreeNode(childPath, depth + 1, fileCounter);
      baseNode.children.push(childNode);
      if (childNode.type === 'file') {
        fileCounter.count += 1;
      } else {
        // Accumulate folder size
        baseNode.size += childNode.size || 0;
      }
    } catch {
      continue;
    }
  }

  // Final size calculation for folders
  if (baseNode.type === 'folder' && baseNode.children.length > 0) {
    baseNode.size = baseNode.children.reduce((total, child) => total + (child.size || 0), 0);
  }

  baseNode.children.sort((a, b) => b.size - a.size);
  return baseNode;
}

async function walkFiles(rootPath, collector, depth = 0, maxDepth = 5) {
  if (depth > maxDepth || collector.length > MAX_SCAN_FILES) return;
  const entries = await safeReadDir(rootPath);
  for (const entry of entries) {
    if (collector.length > MAX_SCAN_FILES) break;
    const itemPath = path.join(rootPath, entry.name);
    try {
      const stat = await fs.stat(itemPath);
      if (stat.isDirectory()) {
        await walkFiles(itemPath, collector, depth + 1, maxDepth);
      } else {
        collector.push({
          path: itemPath,
          name: entry.name,
          size: stat.size,
          lastModified: stat.mtimeMs
        });
      }
    } catch {
      continue;
    }
  }
}

async function resolveUniquePath(destinationPath) {
  if (!fssync.existsSync(destinationPath)) return destinationPath;

  const parsed = path.parse(destinationPath);
  let attempt = 1;
  while (attempt < 5000) {
    const candidate = path.join(parsed.dir, `${parsed.name} (${attempt})${parsed.ext}`);
    if (!fssync.existsSync(candidate)) return candidate;
    attempt += 1;
  }

  return null;
}

const SEMANTIC_KEYWORDS = {
  important: {
    high: ['resume', 'cv', 'portfolio', 'project_report', 'final_project', 'thesis', 'assignment', 'homework', 'final_paper', 'proposal', 'contract', 'agreement', 'certificate', 'credential', 'transcript', 'invoice', 'receipt', 'research', 'study'],
    medium: ['project', 'business', 'professional', 'final', 'presentation', 'speech']
  },
  deletable: {
    high: ['temp', 'cache', 'log', 'backup', 'old_', '_old', 'archive', 'trash', 'junk', 'unused', 'deprecated', 'delete', 'remove', 'scrap', 'tmp', 'test_', '_test', 'debug', 'staging'],
    medium: ['previous', 'outdated', 'legacy', 'setup', 'installer', 'bak']
  },
  context: {
    school: ['lecture', 'course', 'class', 'subject', 'module', 'exam', 'quiz', 'university', 'college', 'school', 'semester', 'teaching'],
    work: ['project', 'client', 'task', 'meeting', 'employee', 'employee', 'payroll', 'invoice', 'report', 'analysis'],
    media: ['photo', 'video', 'audio', 'music', 'podcast', 'stream', 'movie', 'show', 'recording'],
    personal: ['life', 'family', 'travel', 'hobby', 'personal', 'private', 'diary', 'journal']
  }
};

function classifyFileSeverity(fileName, filePath = '') {
  const nameLower = fileName.toLowerCase();
  let deletableScore = 0;
  let importantScore = 0;

  // Check for deletable patterns (high) - stronger weights
  SEMANTIC_KEYWORDS.deletable.high.forEach(keyword => {
    if (nameLower.includes(keyword)) deletableScore += 4;
  });

  // Check for deletable patterns (medium)
  SEMANTIC_KEYWORDS.deletable.medium.forEach(keyword => {
    if (nameLower.includes(keyword)) deletableScore += 1;
  });

  // Check for important patterns (high) - only HIGH priority items count
  SEMANTIC_KEYWORDS.important.high.forEach(keyword => {
    if (nameLower.includes(keyword)) importantScore += 4;
  });

  // Don't count medium importance - too many false positives

  // Prevent false positives: "notimportant" or random copies
  if (nameLower.includes('not') && nameLower.includes('important')) {
    importantScore = 0;
    deletableScore += 3;
  }

  // Random empty text files are not important
  if (nameLower.match(/^(new|copy|document|untitled)/) && nameLower.endsWith('.txt')) {
    importantScore = 0;
    deletableScore += 2;
  }

  return { deletable: deletableScore, important: importantScore };
}

function localTagsFromName(fileName, filePath = '') {
  const ext = path.extname(fileName).toLowerCase().replace('.', '') || 'unknown';
  const base = path.basename(fileName, path.extname(fileName));
  const nameLower = fileName.toLowerCase();

  // Extract meaningful words from filename
  const words = base
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(w => w.length > 2 && w !== 'the' && w !== 'and' && w !== 'for')
    .slice(0, 5);

  const category = detectCategory(fileName).toLowerCase();
  const severity = classifyFileSeverity(fileName, filePath);

  // Add size-based tag if we have path info
  const sizeTag = [];
  if (filePath) {
    try {
      const stat = fssync.statSync(filePath);
      if (stat.size > 100 * 1024 * 1024) sizeTag.push('large-file');
      else if (stat.size > 10 * 1024 * 1024) sizeTag.push('medium-file');
    } catch { }
  }

  // Add severity tags (use higher threshold to reduce false positives)
  const severityTags = [];
  if (severity.deletable > 3) severityTags.push('deletable');
  if (severity.important > 3) severityTags.push('important');

  // Add context tags
  const contextTags = [];
  Object.entries(SEMANTIC_KEYWORDS.context).forEach(([context, keywords]) => {
    if (keywords.some(k => nameLower.includes(k))) contextTags.push(context);
  });

  const tags = [...new Set([category, ext, ...severityTags, ...contextTags, ...sizeTag, ...words].filter(Boolean))].slice(0, 15);
  return tags;
}

async function geminiTags({ apiKey, fileName, filePath }) {
  if (!apiKey) return null;

  const prompt = `Generate 5 concise search tags for this file. Return only comma-separated words. File name: ${fileName}. Path: ${filePath}`;
  const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.2, maxOutputTokens: 40 }
    })
  });

  if (!response.ok) {
    return null;
  }
  const data = await response.json();
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) return null;

  return text
    .toLowerCase()
    .split(/[,\n]/)
    .map((t) => t.trim().replace(/[^a-z0-9-_ ]/g, ''))
    .filter(Boolean)
    .slice(0, 10);
}

async function suggestDeleteCandidates(rootPath) {
  const files = [];
  await walkFiles(rootPath, files, 0, 4);

  const now = Date.now();
  const staleDays = 180;
  const staleMs = staleDays * 24 * 60 * 60 * 1000;
  const suspiciousFolderNames = ['cache', 'temp', 'tmp', 'logs', '__pycache__', 'thumbnails'];

  const candidates = [];

  for (const file of files) {
    let score = 0;
    const ageMs = now - file.lastModified;
    const ageDays = Math.floor(ageMs / (24 * 60 * 60 * 1000));

    if (shouldDelete(file.name)) score += 5;
    if (ageMs > staleMs) score += 3;
    if (file.size > 500 * 1024 * 1024) score += 3;
    if (file.size > 100 * 1024 * 1024) score += 1;
    if (file.name.toLowerCase().includes('old') || file.name.toLowerCase().includes('backup')) score += 2;
    if (score < 3) continue;

    candidates.push({
      type: 'file',
      path: file.path,
      name: file.name,
      size: file.size,
      ageDays,
      reason: `${ageDays}d old • ${formatBytes(file.size)}`,
      score
    });
  }

  const stack = [rootPath];
  while (stack.length > 0 && candidates.length < 150) {
    const current = stack.pop();
    const entries = await safeReadDir(current);
    for (const entry of entries) {
      const fullPath = path.join(current, entry.name);
      if (!entry.isDirectory()) continue;
      if (entry.name.startsWith('.')) continue;
      stack.push(fullPath);

      const nameLower = entry.name.toLowerCase();
      if (!suspiciousFolderNames.some((flag) => nameLower.includes(flag))) continue;

      try {
        const subtree = await buildTreeNode(fullPath, 1, { count: 0 });
        candidates.push({
          type: 'folder',
          path: fullPath,
          name: entry.name,
          size: subtree.size || 0,
          ageDays: Math.floor((Date.now() - subtree.lastModified) / (24 * 60 * 60 * 1000)),
          reason: `Likely leftover system/app folder • ${formatBytes(subtree.size || 0)}`,
          score: 7
        });
      } catch {
        continue;
      }
    }
  }

  candidates.sort((a, b) => b.score - a.score || b.size - a.size);
  return candidates.slice(0, 60);
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1400,
    height: 920,
    backgroundColor: '#F7F7F5',
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  if (isDev && rendererDevUrl) {
    mainWindow.loadURL(rendererDevUrl);
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'));
  }
}

ipcMain.handle('folder:pick', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory']
  });
  if (result.canceled || !result.filePaths?.[0]) {
    return null;
  }
  return result.filePaths[0];
});

ipcMain.handle('folder:scan', async (_, rootPath) => {
  if (!rootPath) return null;
  const cached = TREE_CACHE.get(rootPath);
  if (cached && Date.now() < cached.expiresAt) return cached.node;
  const node = await buildTreeNode(rootPath, 0, { count: 0 });
  TREE_CACHE.set(rootPath, { node, expiresAt: Date.now() + TREE_CACHE_TTL_MS });
  return node;
});

ipcMain.handle('folder:organize', async (_, rootPath) => {
  try {
    const ingestResp = await fetch(
      `${apiUrl}/api/v1/ingest/directory?path=${encodeURIComponent(rootPath)}`,
      { method: 'POST' }
    );
    if (!ingestResp.ok) throw new Error(`Ingest HTTP ${ingestResp.status}`);
    const { indexed } = await ingestResp.json();

    const suggestResp = await fetch(`${apiUrl}/api/v1/organize/suggestions`);
    if (!suggestResp.ok) throw new Error(`Suggest HTTP ${suggestResp.status}`);
    const suggestions = await suggestResp.json();

    console.log('[organize] recommendation:', suggestions.recommendation);
    suggestions.proposals?.forEach((p, i) =>
      console.log(`  Proposal ${i + 1} (${p.name}): ${p.mappings?.length} file mappings`)
    );

    return { moved: indexed ?? 0, skipped: 0 };
  } catch (err) {
    console.error('[organize] error:', err.message);
    return { moved: 0, skipped: 0 };
  }
})

ipcMain.handle('files:tag', async (_, payload) => {
  const { rootPath, provider } = payload;
  const files = [];
  await walkFiles(rootPath, files, 0, 4);
  const apiKey = process.env.GEMINI_API_KEY;

  const results = await Promise.all(files.map(async (file) => {
    const cacheKey = `${provider}:${file.path}`;
    if (FILE_TAG_CACHE.has(cacheKey)) return FILE_TAG_CACHE.get(cacheKey);

    const tags = (provider === 'api' && apiKey)
      ? ((await geminiTags({ apiKey, fileName: file.name, filePath: file.path })) ?? localTagsFromName(file.name, file.path))
      : localTagsFromName(file.name, file.path);

    const result = { path: file.path, name: file.name, tags };
    FILE_TAG_CACHE.set(cacheKey, result);
    return result;
  }));

  return results;
});

ipcMain.handle('files:suggestDelete', async (_, rootPath) => {
  return suggestDeleteCandidates(rootPath);
});

ipcMain.handle('files:trash', async (_, targetPath) => {
  if (!targetPath) return { ok: false };
  try {
    await shell.trashItem(targetPath);
    TREE_CACHE.delete(path.dirname(targetPath)); // invalidate parent dir

    // Record DELETE action in Python backend (fire-and-forget)
    fetch(`${apiUrl}/api/v1/actions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'DELETE',
        label: `Delete '${path.basename(targetPath)}'`,
        targets: [targetPath],
        before_state: { path: targetPath },
        after_state: {},
        status: 'APPLIED',
      }),
    }).catch(() => { }); // non-blocking; ignore if Python backend isn't running

    return { ok: true };
  } catch {
    return { ok: false };
  }
});

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
