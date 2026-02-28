import { useMemo, useState } from 'react';
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts';

type TreemapNode = {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'folder';
  children?: TreemapNode[];
};

const formatBytes = (bytes: number) => {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value > 10 ? 1 : 2)} ${units[unitIndex]}`;
};

function App() {
  const [rootFolder, setRootFolder] = useState<string>('');
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [focusPath, setFocusPath] = useState<string>('');
  const [busy, setBusy] = useState<string>('');
  const [status, setStatus] = useState<string>('Pick a folder to begin');

  const [tagProvider, setTagProvider] = useState<'local' | 'api'>('local');
  const [taggedFiles, setTaggedFiles] = useState<TaggedFile[]>([]);
  const [searchTag, setSearchTag] = useState<string>('');

  const [suggestions, setSuggestions] = useState<DeleteSuggestion[]>([]);
  const [swipeIndex, setSwipeIndex] = useState(0);

  const nodeByPath = useMemo(() => {
    const map = new Map<string, TreeNode>();
    const walk = (node: TreeNode) => {
      map.set(node.path, node);
      node.children?.forEach(walk);
    };
    if (tree) walk(tree);
    return map;
  }, [tree]);

  const focusNode = nodeByPath.get(focusPath) ?? tree;

  const treemapData = useMemo(() => {
    if (!focusNode?.children) return [];
    const children = focusNode.children
      .filter((child) => (child.size ?? 0) > 0)
      .map((child) => ({
        name: child.name,
        path: child.path,
        size: Math.max(child.size ?? 0, 1024),
        type: child.type,
        children: child.children
      }));
    return children.length > 0 ? children : [];
  }, [focusNode]);

  const breadcrumbs = useMemo(() => {
    if (!focusNode || !rootFolder) return [];
    const result: TreeNode[] = [];
    let currentPath = focusNode.path;
    while (currentPath) {
      const node = nodeByPath.get(currentPath);
      if (!node) break;
      result.unshift(node);
      if (node.path === rootFolder) break;
      const parent = currentPath.split(/[\\/]/).slice(0, -1).join('\\');
      if (!parent || parent === currentPath) break;
      currentPath = parent;
    }
    return result;
  }, [focusNode, nodeByPath, rootFolder]);

  const searchedFiles = useMemo(() => {
    if (!searchTag.trim()) return taggedFiles.slice(0, 30);
    const q = searchTag.toLowerCase();
    return taggedFiles
      .filter((file) => file.tags.some((tag) => tag.includes(q)) || file.name.toLowerCase().includes(q))
      .slice(0, 60);
  }, [taggedFiles, searchTag]);

  const activeSuggestion = suggestions[swipeIndex] ?? null;

  const refreshTree = async (pathToScan = rootFolder) => {
    if (!pathToScan) return;
    const newTree = await window.wispApi.scanFolder(pathToScan);
    setTree(newTree);
    if (!focusPath && newTree) {
      setFocusPath(newTree.path);
    }
  };

  const handlePickFolder = async () => {
    const picked = await window.wispApi.pickFolder();
    if (!picked) return;
    setRootFolder(picked);
    setBusy('Scanning folder...');
    setStatus('Analyzing folder structure...');
    const scanned = await window.wispApi.scanFolder(picked);
    setTree(scanned);
    setFocusPath(scanned?.path ?? '');
    setTaggedFiles([]);
    setSuggestions([]);
    setSwipeIndex(0);
    setBusy('');
    setStatus('Folder loaded. Use organize, tag, or delete suggestions.');
  };

  const handleOrganize = async () => {
    if (!rootFolder) return;
    setBusy('Organizing files...');
    const result = await window.wispApi.organizeFolder(rootFolder);
    await refreshTree(rootFolder);
    setBusy('');
    setStatus(`Moved ${result.moved} files, skipped ${result.skipped}.`);
  };

  const handleTagFiles = async () => {
    if (!rootFolder) return;
    const tagType = tagProvider === 'api' ? 'AI' : 'local';
    setBusy(`Generating ${tagType} tags...`);
    const result = await window.wispApi.tagFiles({
      rootPath: rootFolder,
      provider: tagProvider
    });
    setTaggedFiles(result);
    setBusy('');
    setStatus(`Generated ${tagType} tags for ${result.length} files.`);
  };

  const handleSuggestDelete = async () => {
    if (!rootFolder) return;
    setBusy('Finding delete suggestions...');
    const result = await window.wispApi.suggestDelete(rootFolder);
    setSuggestions(result);
    setSwipeIndex(0);
    setBusy('');
    setStatus(`Prepared ${result.length} suggestions for swipe review.`);
  };

  const handleSwipe = async (decision: 'keep' | 'delete') => {
    if (!activeSuggestion) return;
    if (decision === 'delete') {
      await window.wispApi.trashPath(activeSuggestion.path);
    }
    const next = swipeIndex + 1;
    setSwipeIndex(next);
    if (next >= suggestions.length) {
      setStatus('Swipe queue complete.');
      await refreshTree(rootFolder);
    }
  };

  return (
    <div className="app-shell">
      {!rootFolder ? (
        // Empty State - Clean & Centered
        <section className="welcome-hero">
          <div className="welcome-content">
            <h1 className="welcome-title">Let's tame your file chaos</h1>
            <p className="welcome-subtitle">Visualize disk usage, organize files, and clean up clutter</p>
            
            <div className="quick-actions">
              <button onClick={handlePickFolder} className="action-tile">
                <span className="tile-label">Choose folder</span>
                <span className="tile-hint">Browse directories</span>
              </button>
            </div>
          </div>
        </section>
      ) : (
        <>
          {/* Header bar with folder path and actions */}
          <div className="workspace-header">
            <div className="workspace-path">
              <span className="path-icon">📁</span>
              <span className="path-text">{rootFolder}</span>
              <button 
                className="path-copy" 
                onClick={() => navigator.clipboard.writeText(rootFolder)}
                title="Copy path"
              >
                Copy
              </button>
            </div>
            <button onClick={handlePickFolder} className="change-folder-btn">
              Change folder
            </button>
          </div>

          {/* Status bar */}
          {(busy || status !== 'Pick a folder to begin') && (
            <div className={`status-bar ${busy ? 'loading' : 'complete'}`}>
              {busy || status}
            </div>
          )}

          {/* Action panel - Clean minimal cards */}
          <div className="workspace-actions">
            <button 
              onClick={handleOrganize} 
              disabled={!!busy}
              className="workspace-tile"
            >
              <span className="tile-title">Organize files</span>
              <span className="tile-desc">Sort by category and priority</span>
            </button>
            
            <button 
              onClick={handleSuggestDelete} 
              disabled={!!busy}
              className="workspace-tile"
            >
              <span className="tile-title">Find deletables</span>
              <span className="tile-desc">Review cleanup suggestions</span>
            </button>
            
            <div className="workspace-tile-with-select">
              <div className="tile-header">
                <span className="tile-title">Tag files</span>
                <select 
                  value={tagProvider} 
                  onChange={(e) => setTagProvider(e.target.value as 'local' | 'api')}
                  className="inline-select"
                >
                  <option value="local">Local</option>
                  <option value="api">AI</option>
                </select>
              </div>
              <button 
                onClick={handleTagFiles} 
                disabled={!!busy}
                className="tile-action-btn"
              >
                Generate tags
              </button>
            </div>
          </div>

          {/* Main Content Grid */}
          <main className="workspace-grid">

            {/* Treemap panel */}
            <div className="panel panel-large">
              <div className="panel-title">
                <span>Disk usage</span>
                <div className="breadcrumb-nav">
                  {breadcrumbs.map((node, idx) => (
                    <>
                      {idx > 0 && <span className="breadcrumb-sep">/</span>}
                      <button
                        key={node.path}
                        onClick={() => setFocusPath(node.path)}
                        className={idx === breadcrumbs.length - 1 ? 'breadcrumb-active' : 'breadcrumb-link'}
                      >
                        {node.name === node.path ? 'root' : node.name}
                      </button>
                    </>
                  ))}
                </div>
              </div>

              <div className="panel-content-fill">
                {treemapData.length === 0 ? (
                  <div className="panel-empty">
                    <p>Click blocks to explore subfolders</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <Treemap
                      data={treemapData as TreemapNode[]}
                      dataKey="size"
                      stroke="#0a0a0a"
                      fill="#3b82f6"
                      onClick={(payload: TreemapNode) => {
                        if (payload.type === 'folder') {
                          setFocusPath(payload.path);
                        }
                      }}
                    >
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.[0]?.payload) return null;
                          const item = payload[0].payload as TreemapNode;
                          return (
                            <div className="chart-tooltip">
                              <div className="tooltip-name">{item.name}</div>
                              <div className="tooltip-meta">
                                <span>{formatBytes(item.size)}</span>
                                <span className="sep">•</span>
                                <span>{item.type}</span>
                              </div>
                            </div>
                          );
                        }}
                      />
                    </Treemap>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            {/* Sidebar stack */}
            <div className="panels-column">
              {/* Tag search panel */}
              <div className="panel panel-small">
                <div className="panel-title-with-search">
                  <span>Tagged files</span>
                  <input
                    type="text"
                    placeholder="Filter files..."
                    value={searchTag}
                    onChange={(e) => setSearchTag(e.target.value)}
                    className="panel-search-inline"
                  />
                </div>
                <div className="panel-content-scroll">
                  {searchedFiles.length === 0 ? (
                    <div className="panel-empty">
                      <p>{taggedFiles.length === 0 ? 'No tags yet' : 'No matches'}</p>
                    </div>
                  ) : (
                    <div className="file-items">
                      {searchedFiles.map((file) => (
                        <div className="file-item" key={file.path} title={file.path}>
                          <div className="file-item-name">{file.name}</div>
                          <div className="file-item-tags">
                            {file.tags.slice(0, 4).map((tag) => (
                              <span key={tag} className="mini-tag">{tag}</span>
                            ))}
                            {file.tags.length > 4 && <span className="mini-tag-more">+{file.tags.length - 4}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Delete review panel */}
              <div className="panel panel-small">
                <div className="panel-title">
                  <span>Delete review</span>
                </div>
                {!activeSuggestion ? (
                  <div className="panel-empty">
                    <p>No suggestions yet</p>
                  </div>
                ) : (
                  <div className="review-card">
                    <div className="review-header">
                      <span className="review-badge">{activeSuggestion.type}</span>
                      <span className="review-count">{swipeIndex + 1} / {suggestions.length}</span>
                    </div>
                    <h4 className="review-name">{activeSuggestion.name}</h4>
                    <p className="review-reason">{activeSuggestion.reason}</p>
                    <div className="review-meta">
                      <span>{formatBytes(activeSuggestion.size)}</span>
                      <span>•</span>
                      <span>{activeSuggestion.ageDays}d old</span>
                    </div>
                    <div className="review-path">{activeSuggestion.path}</div>

                    <div className="review-actions">
                      <button onClick={() => handleSwipe('keep')} className="review-btn keep">
                        Keep
                      </button>
                      <button onClick={() => handleSwipe('delete')} className="review-btn delete">
                        Delete
                      </button>
                    </div>

                    <div className="review-progress">
                      <div
                        className="review-progress-bar"
                        style={{ width: `${((swipeIndex + 1) / suggestions.length) * 100}%` }}
                      ></div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </main>
        </>
      )}
    </div>
  );
}

export default App;
