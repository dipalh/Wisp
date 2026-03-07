/// <reference types="vite/client" />

interface TreeNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  size: number;
  lastModified?: number;
  children?: TreeNode[];
}

interface TaggedFile {
  path: string;
  name: string;
  tags: string[];
}

interface DeleteSuggestion {
  type: string;
  path: string;
  name: string;
  size: number;
  ageDays: number;
  reason: string;
  score: number;
}

interface IndexedFile {
  file_id: string;
  job_id: string;
  file_path: string;
  name: string;
  ext: string;
  depth: string;
  chunk_count: number;
  engine: string;
  is_deletable: number;
  tagged_os: number;
  file_state?: string;
  error_code?: string;
  error_message?: string;
  updated_at: string;
}

interface SearchResult {
  file_id: string;
  file_path: string;
  ext: string;
  score: number;
  snippet: string;
  depth: string;
}

interface SearchResponse {
  results: SearchResult[];
  query: string;
  total: number;
}

interface AssistantResponse {
  answer: string;
  proposals: any[];
  query: string;
  sources: string[];
  deepened_files: string[];
}

interface VoiceResult {
  voices: Array<{
    voice_id: string;
    name: string;
    category: string;
    preview_url?: string | null;
    language?: string;
    accent?: string;
  }>;
}

interface OcrResponse {
  filename: string;
  text: string;
  confidence: number;
}

interface TranscribeResponse {
  filename: string;
  text: string;
  duration_seconds: number;
}

interface UndoOrganizeResponse {
  ok: boolean;
  reversed: number;
  failed: number;
  error?: string;
  details: {
    reversed: string[];
    failed: string[];
  };
}

interface WispApi {
  getUsername: () => string;
  pickFolder: () => Promise<string | null>;
  scanFolder: (folderPath: string) => Promise<TreeNode | null>;
  organizeFolder: (folderPath: string) => Promise<{ moved: number; skipped: number; error?: string; categories?: Record<string, number> }>;
  tagFiles: (payload: { rootPath: string; provider: 'local' | 'api' }) => Promise<TaggedFile[]>;
  suggestDelete: (folderPath: string) => Promise<DeleteSuggestion[]>;
  trashPath: (targetPath: string) => Promise<{ ok: boolean }>;
  readFileBase64: (filePath: string) => Promise<string>;
  pickFileForOcr: () => Promise<string | null>;
  extractText: (filePath: string) => Promise<OcrResponse>;
  extractTextFromBuffer: (base64: string, filename?: string) => Promise<OcrResponse>;
  transcribeFile: (filePath: string) => Promise<TranscribeResponse>;
  speakText: (text: string, voiceId?: string) => Promise<string | null>;
  getVoices: () => Promise<VoiceResult>;
  showInFolder: (filePath: string) => Promise<{ ok: boolean }>;
  openPath: (filePath: string) => Promise<{ ok: boolean }>;
  startScanJob: (folders: string[]) => Promise<{ job_id: string }>;
  pollJob: (jobId: string) => Promise<{
    job_id: string;
    type: string;
    status: 'queued' | 'running' | 'success' | 'failed';
    stage: string;
    stats: {
      discovered: number;
      previewed: number;
      embedded: number;
      scored: number;
      cached: number;
      failed: number;
    };
    progress_current: number;
    progress_total: number;
    progress_message: string;
    updated_at: string;
  }>;
  getIndexedFiles: (jobId?: string) => Promise<{
    files: IndexedFile[];
    total: number;
  }>;
  openFile: (filePath: string) => Promise<{ ok: boolean }>;
  searchMemory: (query: string, opts?: { k?: number; ext?: string }) => Promise<SearchResponse>;
  askAssistant: (query: string, k?: number, autoDeepen?: boolean) => Promise<AssistantResponse>;
  undoOrganize: () => Promise<UndoOrganizeResponse>;
  canUndoOrganize: () => Promise<{ canUndo: boolean }>;
  onUndoTriggered: (callback: () => void) => () => void;
  onUndoAvailable: (callback: (data: { canUndo: boolean; label: string }) => void) => () => void;
}

interface Window {
  wispApi: WispApi;
}
