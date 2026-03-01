import { useMemo } from 'react';
import { ResponsiveContainer, Treemap, Tooltip } from 'recharts';
import { ArrowUpLeft, Folder, FolderPlus } from 'lucide-react';
import type { TreeNode } from '../components/AppShell';

type VisualizeViewProps = {
    tree: TreeNode | null;
    focusPath: string;
    onNavigate: (path: string) => void;
    rootFolders: string[];
    onAddFolder: () => void;
};

type TreeMapDatum = {
    name: string;
    path: string;
    value: number;
    type: 'file' | 'folder';
    size: number;
    fill?: string;
};

/* Light-mode palette: soft blues for folders, warm grays for files */
const folderColors = ['#5B9BD5', '#6DAAE0', '#7FB8EA', '#91C6F4'];
const fileColors = ['#D6D3D1', '#C4C0BC', '#B0ACA8', '#9E9A96'];

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

export default function VisualizeView({
    tree,
    focusPath,
    onNavigate,
    rootFolders,
    onAddFolder,
}: VisualizeViewProps) {
    const nodeByPath = useMemo(() => {
        const map = new Map<string, TreeNode>();
        const walk = (node: TreeNode) => {
            map.set(node.path, node);
            node.children?.forEach(walk);
        };
        if (tree) walk(tree);
        return map;
    }, [tree]);

    const currentNode = nodeByPath.get(focusPath) ?? tree;

    const breadcrumbs = useMemo(() => {
        if (!currentNode || !tree) return [];
        const result: TreeNode[] = [];
        let currentPath = currentNode.path;
        while (currentPath) {
            const node = nodeByPath.get(currentPath);
            if (!node) break;
            result.unshift(node);
            if (node.path === tree.path) break;
            const sep = currentPath.includes('/') ? '/' : '\\';
            const parts = currentPath.split(sep);
            parts.pop();
            const parent = parts.join(sep);
            if (!parent || parent === currentPath) break;
            currentPath = parent;
        }
        return result;
    }, [currentNode, nodeByPath, tree]);

    const { chartData, totalSize } = useMemo(() => {
        if (!currentNode?.children) return { chartData: [] as TreeMapDatum[], totalSize: 0 };
        const validChildren = currentNode.children.filter((c) => (c.size ?? 0) > 0);
        const total = validChildren.reduce((sum, c) => sum + (c.size ?? 0), 0);
        const sorted = validChildren.sort((a, b) => (b.size ?? 0) - (a.size ?? 0));
        const mapped = sorted.map((child, i) => ({
            name: child.name,
            path: child.path,
            type: child.type,
            size: child.size,
            value: Math.max(child.size, 1),
            fill: child.type === 'folder'
                ? folderColors[i % folderColors.length]
                : fileColors[i % fileColors.length],
        }));
        return { chartData: mapped, totalSize: total };
    }, [currentNode]);

    const getParentPath = (p: string): string | null => {
        const sep = p.includes('/') ? '/' : '\\';
        const parts = p.split(sep);
        if (parts.length <= 1) return null;
        parts.pop();
        return parts.join(sep);
    };

    if (!tree) {
        return (
            <div className="empty-state">
                <Folder size={40} className="empty-state-icon" />
                <h3 className="empty-state-title">No data to visualize</h3>
                <p className="empty-state-desc">
                    {rootFolders.length === 0
                        ? 'Add a folder first to see your storage breakdown.'
                        : 'Scan your folder to populate the treemap.'}
                </p>
                {rootFolders.length === 0 && (
                    <button className="btn btn-primary" onClick={onAddFolder} style={{ marginTop: 'var(--sp-4)' }}>
                        <FolderPlus size={16} />
                        Add folder
                    </button>
                )}
            </div>
        );
    }

    const parentPath = currentNode ? getParentPath(currentNode.path) : null;

    return (
        <div>
            <div className="viz-header">
                <div className="viz-breadcrumb">
                    {breadcrumbs.map((node, i) => (
                        <span key={node.path} style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-1)' }}>
                            {i > 0 && <span className="viz-breadcrumb-sep">/</span>}
                            <button
                                className={`viz-breadcrumb-item ${node.path === currentNode?.path ? 'active' : ''}`}
                                onClick={() => onNavigate(node.path)}
                            >
                                {node.name}
                            </button>
                        </span>
                    ))}
                </div>
                {parentPath && (
                    <button className="btn btn-ghost" onClick={() => onNavigate(parentPath)} title="Go up">
                        <ArrowUpLeft size={16} />
                        Up
                    </button>
                )}
            </div>

            {chartData.length > 0 ? (
                <div className="viz-treemap">
                    <ResponsiveContainer width="100%" height="100%">
                        <Treemap
                            data={chartData}
                            dataKey="value"
                            nameKey="name"
                            stroke="var(--bg-surface)"
                            fill="var(--text-disabled)"
                            isAnimationActive={false}
                            onClick={(node: TreeMapDatum) => {
                                if (node?.type === 'folder' && node.path) onNavigate(node.path);
                            }}
                        >
                            <Tooltip
                                content={({ active, payload }) => {
                                    if (!active || !payload?.[0]?.payload) return null;
                                    const item = payload[0].payload as TreeMapDatum;
                                    const pct = totalSize > 0 ? (item.size / totalSize) * 100 : 0;
                                    return (
                                        <div className="viz-tooltip">
                                            <div className="viz-tooltip-name">{item.name}</div>
                                            <div className="viz-tooltip-meta">{formatBytes(item.size)}</div>
                                            <div className="viz-tooltip-meta">{pct.toFixed(1)}% of folder</div>
                                            <div className="viz-tooltip-kind">
                                                {item.type === 'folder' ? 'Folder (click to open)' : 'File'}
                                            </div>
                                        </div>
                                    );
                                }}
                            />
                        </Treemap>
                    </ResponsiveContainer>
                </div>
            ) : (
                <div className="empty-state" style={{ minHeight: '200px' }}>
                    <p className="empty-state-desc">This folder is empty</p>
                </div>
            )}

            {currentNode?.children && currentNode.children.length > 0 && (
                <div className="viz-file-table">
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th style={{ width: '100px', textAlign: 'right' }}>Size</th>
                                <th style={{ width: '80px', textAlign: 'right' }}>Type</th>
                            </tr>
                        </thead>
                        <tbody>
                            {currentNode.children
                                .filter((c) => c.size > 0)
                                .sort((a, b) => b.size - a.size)
                                .slice(0, 30)
                                .map((child) => (
                                    <tr
                                        key={child.path}
                                        onClick={() => child.type === 'folder' && onNavigate(child.path)}
                                        style={{ cursor: child.type === 'folder' ? 'pointer' : 'default' }}
                                    >
                                        <td>
                                            <div className="file-name-cell">
                                                <Folder size={14} style={{ color: child.type === 'folder' ? 'var(--accent)' : 'var(--text-tertiary)', flexShrink: 0 }} />
                                                {child.name}
                                            </div>
                                        </td>
                                        <td className="file-size-cell" style={{ textAlign: 'right' }}>{formatBytes(child.size)}</td>
                                        <td style={{ textAlign: 'right', color: 'var(--text-tertiary)' }}>{child.type}</td>
                                    </tr>
                                ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
