import { useMemo } from 'react';
import { Folder, ArrowUpLeft, ChevronRight } from 'lucide-react';
import { ResponsiveContainer, Treemap, Tooltip } from 'recharts';

interface TreeVisualizerProps {
  tree: TreeNode | null;
  focusPath: string;
  onNavigate: (path: string) => void;
}

type TreeMapDatum = {
  name: string;
  path: string;
  value: number;
  type: 'file' | 'folder';
  size: number;
  fill?: string;
};

// Vibrant color palette using app's accent colors
const folderColors = [
  'var(--accent-blue)',
  'var(--accent-cyan)',
  'var(--accent-blue-light)',
  'color-mix(in srgb, var(--accent-blue) 70%, var(--accent-cyan) 30%)'
];

const fileColors = [
  'var(--accent-purple)',
  'color-mix(in srgb, var(--accent-blue) 60%, var(--accent-purple) 40%)',
  'color-mix(in srgb, var(--accent-purple) 70%, var(--accent-cyan) 30%)',
  'var(--accent-blue-light)'
];

const getNodeColor = (type: 'file' | 'folder', index: number): string => {
  const palette = type === 'folder' ? folderColors : fileColors;
  return palette[index % palette.length];
};

const TreeVisualizer = ({ tree, focusPath, onNavigate }: TreeVisualizerProps) => {
  // Find the current node
  const currentNode = useMemo(() => {
    if (!tree) return null;
    
    const find = (node: TreeNode): TreeNode | null => {
      if (node.path === focusPath) return node;
      for (const child of node.children || []) {
        const found = find(child);
        if (found) return found;
      }
      return null;
    };
    
    return find(tree) ?? tree;
  }, [tree, focusPath]);

  // Get parent path
  const getParentPath = (path: string): string | null => {
    const parts = path.split(/[\\/]/);
    if (parts.length <= 1) return null;
    parts.pop();
    return parts.join('\\');
  };

  // Calculate direct children + total size (current folder only)
  const { children, totalSize, chartData } = useMemo(() => {
    if (!currentNode?.children) {
      return { children: [], totalSize: 0, chartData: [] as TreeMapDatum[] };
    }

    const validChildren = currentNode.children.filter((child) => (child.size ?? 0) > 0);
    const total = validChildren.reduce((sum, child) => sum + (child.size ?? 0), 0);
    const mapped = validChildren
      .sort((a, b) => (b.size ?? 0) - (a.size ?? 0))
      .map((child, index) => ({
      name: child.name,
      path: child.path,
      type: child.type,
      size: child.size,
      value: Math.max(child.size, 1),
      fill: getNodeColor(child.type, index)
    }));

    return { children: validChildren, totalSize: total, chartData: mapped };
  }, [currentNode]);

  // Format bytes for display
  const formatBytes = (bytes: number): string => {
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

  if (!tree || !currentNode) {
    return (
      <div className="tree-visualizer">
        <div className="tree-empty">
          <p>No folder loaded</p>
        </div>
      </div>
    );
  }

  const parentPath = getParentPath(currentNode.path);
  const currentPathName = currentNode.name === currentNode.path ? 'root' : currentNode.name;

  return (
    <div className="tree-visualizer">
      <div className="tree-header">
        <div className="tree-header-title">
          <h3 className="tree-title">Storage Hierarchy</h3>
          <span className="tree-subtitle">Current folder breakdown</span>
        </div>
        {parentPath && (
          <button
            className="tree-up-button"
            onClick={() => onNavigate(parentPath)}
            title="Go up one level"
          >
            <ArrowUpLeft size={14} />
            <span>Go Up</span>
          </button>
        )}
      </div>

      <div className="tree-current-path">
        <Folder size={14} />
        <span className="path-label">Current</span>
        <ChevronRight size={12} className="path-chev" />
        <span className="path-value" title={currentNode.path}>
          {currentPathName}
        </span>
      </div>

      <div className="tree-content">
        {children.length === 0 ? (
          <div className="tree-empty-small">
            <p>This folder is empty</p>
          </div>
        ) : (
          <div className="tree-map-host">
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={chartData}
                dataKey="value"
                nameKey="name"
                stroke="var(--border-medium)"
                fill="var(--accent-blue)"
                isAnimationActive={false}
                animationDuration={120}
                onClick={(node: TreeMapDatum) => {
                  if (node?.type === 'folder' && node.path) {
                    onNavigate(node.path);
                  }
                }}
              >
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.[0]?.payload) return null;
                    const item = payload[0].payload as TreeMapDatum;
                    const pct = totalSize > 0 ? (item.size / totalSize) * 100 : 0;

                    return (
                      <div className="tree-map-tooltip">
                        <div className="tree-map-tip-name">{item.name}</div>
                        <div className="tree-map-tip-meta">{formatBytes(item.size)}</div>
                        <div className="tree-map-tip-meta">{pct.toFixed(1)}% of current folder</div>
                        <div className="tree-map-tip-kind">{item.type === 'folder' ? 'Folder (click to open)' : 'File'}</div>
                      </div>
                    );
                  }}
                />
              </Treemap>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
};

export default TreeVisualizer;
