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

interface WispApi {
  getUsername: () => string;
  pickFolder: () => Promise<string | null>;
  scanFolder: (folderPath: string) => Promise<TreeNode | null>;
  organizeFolder: (folderPath: string) => Promise<{ moved: number; skipped: number }>;
  tagFiles: (payload: { rootPath: string; provider: 'local' | 'api' }) => Promise<TaggedFile[]>;
  suggestDelete: (folderPath: string) => Promise<DeleteSuggestion[]>;
  trashPath: (targetPath: string) => Promise<{ ok: boolean }>;
  startScanJob: (folders: string[]) => Promise<{ job_id: string }>;
  pollJob: (jobId: string) => Promise<{
    job_id: string;
    type: string;
    status: 'queued' | 'running' | 'success' | 'failed';
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
}

interface Window {
  wispApi: WispApi;
}
