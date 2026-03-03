import { useEffect, useRef } from 'react';
import { Undo2, X, Loader2, CheckCircle2, XCircle } from 'lucide-react';

type UndoToastProps = {
    visible: boolean;
    label: string;
    state: 'idle' | 'undoing' | 'done' | 'error';
    resultMessage?: string;
    onUndo: () => void;
    onDismiss: () => void;
};

const AUTO_DISMISS_MS = 8000;
const DONE_DISMISS_MS = 3000;

export default function UndoToast({ visible, label, state, resultMessage, onUndo, onDismiss }: UndoToastProps) {
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        if (timerRef.current) clearTimeout(timerRef.current);
        if (visible && state === 'idle') {
            timerRef.current = setTimeout(onDismiss, AUTO_DISMISS_MS);
        }
        if (visible && (state === 'done' || state === 'error')) {
            timerRef.current = setTimeout(onDismiss, DONE_DISMISS_MS);
        }
        return () => { if (timerRef.current) clearTimeout(timerRef.current); };
    }, [visible, state, onDismiss]);

    if (!visible) return null;

    return (
        <div className={`undo-toast ${state}`}>
            <div className="undo-toast-content">
                {state === 'idle' && (
                    <>
                        <Undo2 size={14} className="undo-toast-icon" />
                        <span className="undo-toast-label">{label}</span>
                        <button className="undo-toast-action" onClick={onUndo}>
                            Undo
                        </button>
                        <span className="undo-toast-hint">⌘Z</span>
                    </>
                )}
                {state === 'undoing' && (
                    <>
                        <Loader2 size={14} className="spin undo-toast-icon" />
                        <span className="undo-toast-label">Reversing file moves...</span>
                    </>
                )}
                {state === 'done' && (
                    <>
                        <CheckCircle2 size={14} className="undo-toast-icon success" />
                        <span className="undo-toast-label">{resultMessage || 'Files restored to original locations'}</span>
                    </>
                )}
                {state === 'error' && (
                    <>
                        <XCircle size={14} className="undo-toast-icon error" />
                        <span className="undo-toast-label">{resultMessage || 'Undo failed'}</span>
                    </>
                )}
            </div>
            <button className="undo-toast-close" onClick={onDismiss} title="Dismiss">
                <X size={12} />
            </button>
        </div>
    );
}
