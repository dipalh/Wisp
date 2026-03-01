import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Brain, FileText, FolderOpen, Loader2, Sparkles, Volume2, Square, Headphones, ChevronDown, Mic } from 'lucide-react';

type Message = {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    sources?: string[];
    thinking?: boolean;
    timestamp: number;
};

type Voice = { voice_id: string; name: string; category: string; preview_url?: string | null; language?: string; accent?: string };
type WebVoice = { voice_id: string; name: string; category: string; _native: SpeechSynthesisVoice; accent?: string };

const getFileName = (p: string) => p.split(/[/\\]/).pop() ?? p;

const STORAGE_KEY = 'wisp_tts_voice';
const WEB_VOICE_KEY = 'wisp_web_voice';
const DEFAULT_VOICE_ID = 'pNInz6obpgDQGcFmaJgB';

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

    // ── TTS state ─────────────────────────────────────────────────────────────
    const [voices, setVoices] = useState<Voice[]>([]);
    const [webVoices, setWebVoices] = useState<WebVoice[]>([]);
    const [useWebSpeech, setUseWebSpeech] = useState(false);
    const [selectedVoiceId, setSelectedVoiceId] = useState<string>(
        () => localStorage.getItem(STORAGE_KEY) ?? DEFAULT_VOICE_ID
    );
    const [selectedWebVoiceId, setSelectedWebVoiceId] = useState<string>(
        () => localStorage.getItem(WEB_VOICE_KEY) ?? ''
    );
    const [showVoicePanel, setShowVoicePanel] = useState(false);
    const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null);
    const [autoSpeak, setAutoSpeak] = useState<boolean>(
        () => localStorage.getItem('wisp_auto_speak') === 'true'
    );
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const uttRef = useRef<SpeechSynthesisUtterance | null>(null);
    const autoSpeakRef = useRef(autoSpeak);

    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages]);

    // ── Load voices: try ElevenLabs, fall back to Web Speech ────────────────
    useEffect(() => {
        (window as any).wispApi.getVoices()
            .then((data: { voices: Voice[] }) => {
                if (data?.voices?.length) {
                    setVoices(data.voices);
                    setUseWebSpeech(false);
                } else {
                    loadWebVoices();
                }
            })
            .catch(() => loadWebVoices());
    }, []);

    function loadWebVoices() {
        setUseWebSpeech(true);
        const populate = () => {
            const synth = window.speechSynthesis;
            if (!synth) return;
            const native = synth.getVoices().filter(v => v.lang.startsWith('en'));
            const mapped: WebVoice[] = native.map(v => ({
                voice_id: v.voiceURI,
                name: v.name,
                category: v.lang,
                _native: v,
                accent: v.lang.includes('GB') ? 'british' : v.lang.includes('AU') ? 'australian' : 'american',
            }));
            setWebVoices(mapped);
            if (!localStorage.getItem(WEB_VOICE_KEY) && mapped.length) {
                const eng = mapped.find(v => v.category.startsWith('en')) ?? mapped[0];
                setSelectedWebVoiceId(eng.voice_id);
                localStorage.setItem(WEB_VOICE_KEY, eng.voice_id);
            }
        };
        populate();
        window.speechSynthesis?.addEventListener('voiceschanged', populate);
    }

    useEffect(() => { autoSpeakRef.current = autoSpeak; }, [autoSpeak]);

    // ── TTS helpers ─────────────────────────────────────────────────────────
    const stopSpeaking = useCallback(() => {
        if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
        if (uttRef.current) { window.speechSynthesis?.cancel(); uttRef.current = null; }
        setSpeakingMsgId(null);
    }, []);

    const stripMarkdown = (s: string) =>
        s.replace(/\*\*(.+?)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1').replace(/#+\s*/g, '');

    const speakWebSpeech = useCallback((msgId: string, content: string) => {
        if (speakingMsgId === msgId) { stopSpeaking(); return; }
        stopSpeaking();
        const synth = window.speechSynthesis;
        if (!synth) return;
        const utt = new SpeechSynthesisUtterance(stripMarkdown(content));
        const match = synth.getVoices().find(v => v.voiceURI === selectedWebVoiceId);
        if (match) utt.voice = match;
        utt.rate = 0.95;
        utt.onend = () => { setSpeakingMsgId(null); uttRef.current = null; };
        utt.onerror = () => { setSpeakingMsgId(null); uttRef.current = null; };
        uttRef.current = utt;
        setSpeakingMsgId(msgId);
        synth.speak(utt);
    }, [speakingMsgId, selectedWebVoiceId, stopSpeaking]);

    const speakMsg = useCallback(async (msgId: string, content: string) => {
        if (useWebSpeech) { speakWebSpeech(msgId, content); return; }
        if (speakingMsgId === msgId) { stopSpeaking(); return; }
        stopSpeaking();
        setSpeakingMsgId(msgId);
        try {
            const b64: string = await (window as any).wispApi.speakText(stripMarkdown(content), selectedVoiceId);
            const raw = atob(b64);
            const bytes = new Uint8Array(raw.length);
            for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
            const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
            const audio = new Audio(url);
            audioRef.current = audio;
            audio.onended = () => { setSpeakingMsgId(null); URL.revokeObjectURL(url); };
            audio.onerror = () => { setSpeakingMsgId(null); URL.revokeObjectURL(url); };
            await audio.play();
        } catch {
            setSpeakingMsgId(null);
        }
    }, [useWebSpeech, speakWebSpeech, speakingMsgId, selectedVoiceId, stopSpeaking]);

    const toggleAutoSpeak = () => {
        setAutoSpeak(prev => {
            const next = !prev;
            localStorage.setItem('wisp_auto_speak', String(next));
            autoSpeakRef.current = next;
            if (!next) stopSpeaking();
            return next;
        });
    };

    const handleVoiceSelect = (voiceId: string) => {
        if (useWebSpeech) {
            setSelectedWebVoiceId(voiceId);
            localStorage.setItem(WEB_VOICE_KEY, voiceId);
        } else {
            setSelectedVoiceId(voiceId);
            localStorage.setItem(STORAGE_KEY, voiceId);
        }
        setShowVoicePanel(false);
    };

    const activeVoices = useWebSpeech ? webVoices : voices;
    const activeVoiceId = useWebSpeech ? selectedWebVoiceId : selectedVoiceId;
    const selectedVoiceName = activeVoices.find(v => v.voice_id === activeVoiceId)?.name
        ?? (useWebSpeech ? 'System voice' : 'Adam');

    // Group voices by accent for the dropdown
    const accentGroups = (() => {
        const groups: Record<string, typeof activeVoices> = {};
        for (const v of activeVoices) {
            const accent = (v.accent ?? 'other').toLowerCase();
            const label = accent.charAt(0).toUpperCase() + accent.slice(1);
            (groups[label] ??= []).push(v);
        }
        return groups;
    })();
    const accentOrder = Object.keys(accentGroups).sort((a, b) => {
        if (a === 'American') return -1;
        if (b === 'American') return 1;
        return a.localeCompare(b);
    });

    // ── File open ─────────────────────────────────────────────────────────────
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
            if (autoSpeakRef.current) speakMsg(aiMsg.id, aiMsg.content);
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
    }, [input, busy, speakMsg]);

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

                            {/* Read aloud button on AI messages */}
                            {msg.role === 'assistant' && !msg.thinking && (
                                <button
                                    className={`memory-speak-btn${speakingMsgId === msg.id ? ' speaking' : ''}`}
                                    onClick={() => speakMsg(msg.id, msg.content)}
                                    title={speakingMsgId === msg.id ? 'Stop' : 'Read aloud'}
                                >
                                    {speakingMsgId === msg.id
                                        ? <><Square size={10} /> Stop</>
                                        : <><Volume2 size={10} /> Read aloud</>}
                                </button>
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

            {/* Voice bar + input */}
            <div className="memory-input-area">
                <div className="memory-voice-bar">
                    {showVoicePanel && (
                        <div className="memory-voice-panel">
                            <p className="memory-voice-panel-label">
                                {useWebSpeech ? 'System voices (built-in)' : 'ElevenLabs voices'}
                            </p>
                            <div className="memory-voice-list">
                                {accentOrder.length > 0 ? accentOrder.map(accent => (
                                    <div key={accent}>
                                        <p className="memory-voice-group-label">{accent}</p>
                                        {accentGroups[accent].map(v => (
                                            <div
                                                key={v.voice_id}
                                                className={`memory-voice-item${v.voice_id === activeVoiceId ? ' selected' : ''}`}
                                                ref={v.voice_id === activeVoiceId ? (el) => el?.scrollIntoView({ block: 'nearest' }) : null}
                                                onClick={() => handleVoiceSelect(v.voice_id)}
                                            >
                                                <span className="memory-voice-item-name">{v.name}</span>
                                            </div>
                                        ))}
                                    </div>
                                )) : (
                                    <p className="memory-voice-panel-empty">No voices found.</p>
                                )}
                            </div>
                        </div>
                    )}
                    <button
                        className={`memory-autospeak-btn${autoSpeak ? ' active' : ''}`}
                        onClick={toggleAutoSpeak}
                        title={autoSpeak ? 'Auto-speak on (click to turn off)' : 'Auto-speak off (click to turn on)'}
                    >
                        <Headphones size={12} />
                        {autoSpeak ? 'Auto-speak on' : 'Auto-speak off'}
                    </button>
                    <span className="memory-voice-bar-sep" />
                    {useWebSpeech
                        ? <span title="Using built-in system TTS" style={{ display: 'flex' }}><Mic size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} /></span>
                        : <Volume2 size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                    }
                    <span className="memory-voice-bar-label">{useWebSpeech ? 'System' : 'ElevenLabs'}</span>
                    <button
                        className={`memory-voice-selector${showVoicePanel ? ' active' : ''}`}
                        onClick={() => setShowVoicePanel(v => !v)}
                        title="Change voice"
                    >
                        {selectedVoiceName}
                        <ChevronDown size={11} />
                    </button>
                </div>
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
