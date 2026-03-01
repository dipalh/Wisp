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

interface WispApi {
  pickFolder: () => Promise<string | null>;
  scanFolder: (folderPath: string) => Promise<TreeNode | null>;
  organizeFolder: (folderPath: string) => Promise<{ moved: number; skipped: number }>;
  tagFiles: (payload: { rootPath: string; provider: 'local' | 'api' }) => Promise<TaggedFile[]>;
  suggestDelete: (folderPath: string) => Promise<DeleteSuggestion[]>;
  trashPath: (targetPath: string) => Promise<{ ok: boolean }>;
}

interface Window {
  wispApi: WispApi;
}
