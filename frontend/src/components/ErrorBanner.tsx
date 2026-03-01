import { useEffect } from 'react';
import { X } from 'lucide-react';

type ErrorBannerProps = {
    message: string | null;
    onDismiss: () => void;
};

const AUTO_DISMISS_MS = 10_000;

export default function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
    useEffect(() => {
        if (!message) return;
        const id = setTimeout(onDismiss, AUTO_DISMISS_MS);
        return () => clearTimeout(id);
    }, [message, onDismiss]);

    if (!message) return null;

    return (
        <div role="alert" className="error-banner">
            <span className="error-banner-msg">{message}</span>
            <button
                className="error-banner-dismiss"
                onClick={onDismiss}
                aria-label="Dismiss error"
            >
                <X size={14} />
            </button>
        </div>
    );
}
