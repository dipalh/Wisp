import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Brain, FileText, FolderOpen, Loader2, Sparkles } from 'lucide-react';

type Message = {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    sources?: string[];
    thinking?: boolean;
    timestamp: number;
};

const getFileName = (p: string) => p.split(/[/\\]/).pop() ?? p;

const WELCOME: Message = {
    id: 'welcome',
    role: 'assistant',
    content:
        "I'm your file memory. Ask me anything about your indexed files, like **\"what PDFs do I have?\"**, **\"find my resume\"**, or **\"summarize the project files\"**.\n\nI search semantically, so describe what you're looking for in plain English.",
    timestamp: Date.now(),
};

type MemoryViewProps = {
    hasRoot: boolean;
    onError: (msg: string) => void;
};

export default function MemoryView({ hasRoot, onError }: MemoryViewProps) {
    const [messages, setMessages] = useState<Message[]>([WELCOME]);
    const [input, setInput] = useState('');
    const [busy, setBusy] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages]);

    const handleOpenFile = useCallback(async (filePath: string) => {
        try {
            await window.wispApi.openFile(filePath);
        } catch (e: any) {
            onError(`Open failed: ${e?.message ?? e}`);
        }
    }, [onError]);

    const handleSend = useCallback(async () => {
        const text = input.trim();
        if (!text || busy) return;

        const userMsg: Message = {
            id: `u-${Date.now()}`,
            role: 'user',
            content: text,
            timestamp: Date.now(),
        };

        const thinkingMsg: Message = {
            id: `think-${Date.now()}`,
            role: 'assistant',
            content: '',
            thinking: true,
            timestamp: Date.now(),
        };

        setMessages(prev => [...prev, userMsg, thinkingMsg]);
        setInput('');
        setBusy(true);

        try {
            const res = await window.wispApi.askAssistant(text);
            const aiMsg: Message = {
                id: `a-${Date.now()}`,
                role: 'assistant',
                content: res.answer,
                sources: res.sources?.length ? res.sources : undefined,
                timestamp: Date.now(),
            };
            setMessages(prev => [...prev.filter(m => !m.thinking), aiMsg]);
        } catch (e: any) {
            const errMsg: Message = {
                id: `e-${Date.now()}`,
                role: 'assistant',
                content: `Something went wrong. Make sure the backend is running.\n\n\`${e?.message ?? 'Unknown error'}\``,
                timestamp: Date.now(),
            };
            setMessages(prev => [...prev.filter(m => !m.thinking), errMsg]);
        } finally {
            setBusy(false);
        }
    }, [input, busy]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    if (!hasRoot) {
        return (
            <div className="memory-empty">
                <div className="memory-empty-icon">
                    <Brain size={48} strokeWidth={1.5} />
                </div>
                <h3>No files in memory yet</h3>
                <p>Add a folder and run <strong>Scan &amp; Index</strong> to start asking questions about your files.</p>
            </div>
        );
    }

    return (
        <div className="memory-chat">
            <div className="memory-messages" ref={scrollRef}>
                {messages.map(msg => (
                    <div key={msg.id} className={`memory-msg memory-msg-${msg.role}`}>
                        {msg.role === 'assistant' && (
                            <div className="memory-msg-avatar">
                                <Sparkles size={14} />
                            </div>
                        )}
                        <div className="memory-msg-body">
                            {msg.thinking ? (
                                <div className="memory-thinking">
                                    <span className="dot-pulse" />
                                    Searching your files...
                                </div>
                            ) : (
                                <div
                                    className="memory-msg-text"
                                    dangerouslySetInnerHTML={{
                                        __html: msg.content
                                            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                                            .replace(/`([^`]+)`/g, '<code>$1</code>')
                                            .replace(/\n/g, '<br/>')
                                    }}
                                />
                            )}

                            {msg.sources && msg.sources.length > 0 && (
                                <div className="memory-sources">
                                    <span className="memory-sources-label">Sources</span>
                                    <div className="memory-sources-list">
                                        {msg.sources.map(src => (
                                            <button
                                                key={src}
                                                className="memory-source-chip"
                                                onClick={() => handleOpenFile(src)}
                                                title={src}
                                            >
                                                <FileText size={12} />
                                                <span>{getFileName(src)}</span>
                                                <FolderOpen size={11} className="memory-source-open" />
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            <div className="memory-input-area">
                <div className="memory-input-bar">
                    <textarea
                        className="memory-input"
                        placeholder="Ask about your files..."
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        rows={1}
                        disabled={busy}
                    />
                    <button
                        className="memory-send-btn"
                        onClick={handleSend}
                        disabled={!input.trim() || busy}
                        aria-label="Send"
                    >
                        {busy ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
                    </button>
                </div>
                <p className="memory-disclaimer">
                    Wisp searches your indexed files using AI. Results depend on what you've scanned.
                </p>
            </div>
        </div>
    );
}
