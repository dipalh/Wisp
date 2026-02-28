/// <reference types="vite/client" />

type TreeNode = {
  name: string;
  path: string;
  type: 'file' | 'folder';
  size: number;
  lastModified: number;
  children: TreeNode[];
};

type TaggedFile = {
  path: string;
  name: string;
  tags: string[];
};

type DeleteSuggestion = {
  type: 'file' | 'folder';
  path: string;
  name: string;
  size: number;
  ageDays: number;
  reason: string;
  score: number;
};

declare global {
  interface Window {
    wispApi: {
      pickFolder: () => Promise<string | null>;
      scanFolder: (folderPath: string) => Promise<TreeNode | null>;
      organizeFolder: (folderPath: string) => Promise<{ moved: number; skipped: number }>;
      tagFiles: (payload: { rootPath: string; provider: 'local' | 'api' }) => Promise<TaggedFile[]>;
      suggestDelete: (folderPath: string) => Promise<DeleteSuggestion[]>;
      trashPath: (targetPath: string) => Promise<{ ok: boolean }>;
    };
  }
}

export {};
