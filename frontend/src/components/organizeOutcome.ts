export type OrganizeBatchDetail = {
    action_id: string;
    status: string;
    source_path?: string;
    destination_path?: string;
    code?: string;
    message?: string;
};

export type OrganizeApplyBatchResponse = {
    ok: boolean;
    batch_id: string;
    status: string;
    applied: number;
    failed: number;
    partial: boolean;
    details: OrganizeBatchDetail[];
};

export type OrganizeUndoBatchResponse = {
    ok: boolean;
    batch_id: string;
    status: string;
    undone: number;
    failed: number;
    partial: boolean;
    details: OrganizeBatchDetail[];
};

export type OrganizeResult = {
    moved: number;
    skipped: number;
    failed: number;
    partial: boolean;
    categories: Record<string, number>;
    warnings: string[];
};

function categoryFromPath(rootPath: string, targetPath: string): string {
    const relative = rootPath && targetPath.startsWith(rootPath)
        ? targetPath.slice(rootPath.length).replace(/^[/\\]+/, '')
        : targetPath;
    return relative.split(/[\\/]/)[0] || 'Others';
}

export function summarizeApplyBatch(
    rootPath: string,
    response: OrganizeApplyBatchResponse,
): OrganizeResult {
    const categories: Record<string, number> = {};
    for (const detail of response.details) {
        if (detail.status !== 'APPLIED' || !detail.destination_path) continue;
        const category = categoryFromPath(rootPath, detail.destination_path);
        categories[category] = (categories[category] || 0) + 1;
    }

    const warnings = response.details
        .filter((detail) => detail.status === 'FAILED')
        .map((detail) => detail.message || detail.code || 'Action failed');

    return {
        moved: response.applied,
        skipped: 0,
        failed: response.failed,
        partial: response.partial,
        categories,
        warnings,
    };
}

export function buildUndoToastMessage(response: OrganizeUndoBatchResponse): string {
    const undoneLabel = `${response.undone} file${response.undone === 1 ? '' : 's'} restored`;
    if (response.failed > 0) {
        return `${undoneLabel} (${response.failed} failed)`;
    }
    return undoneLabel;
}
