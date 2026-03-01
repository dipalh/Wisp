import { useState, useRef, useEffect } from 'react';
import { Send, Volume2, ChevronDown, FileText, FolderOpen, Square, Headphones } from 'lucide-react';

type Message = {
    id: string;
    role: 'user' | 'ai';
    content: string;
    sources?: string[];   // file paths returned by the RAG backend
    timestamp: number;
};

const getFileName = (p: string) => p.split(/[/\\]/).pop() ?? p;

type Voice = {
    voice_id: string;
    name: string;
    category: string;
};

const STORAGE_KEY = 'wisp_tts_voice';
const DEFAULT_VOICE_ID = 'pNInz6obpgDQGcFmaJgB'; // Adam

const SAFETY_RULES: Array<{ pattern: RegExp; response: string }> = [
    {
        // Permanent deletion / data destruction
        pattern: /\bpermanent(ly)?\s+delet|hard.?delet|\bwipe\b|\bshred\b|\bdestroy\s+(all\s+)?(my\s+)?(files?|data|documents?)\b/i,
        response: "For your safety, Wisp never permanently deletes files. Any cleanup moves files to a quarantine folder first — you can review and restore from there at any time. Head to the Clean view to see suggested candidates.",
    },
    {
        // Format / wipe drives or disks
        pattern: /\b(format|wipe|erase)\b.{0,30}\b(disk|drive|partition|volume|storage|hdd|ssd)\b/i,
        response: "Formatting or wiping drives is outside what Wisp does. I only work with individual files and folders inside the directories you've indexed.",
    },
    {
        // System / OS directories
        pattern: /\bsystem32\b|\\windows\\|\bprogram files\b|\/etc\/|\/usr\/|\/bin\/|\/sbin\/|\/system\/|\bappdata\\roaming\b/i,
        response: "I can't touch system or application directories — only the personal folders you've added to Wisp. This keeps your operating system safe.",
    },
    {
        // Mass / bulk delete without review
        pattern: /\b(delete|remove|wipe|trash|purge)\s+(all|every(thing)?|each|the\s+entire|my\s+entire)\b/i,
        response: "Mass deletions aren't something I'll do in one go. Wisp reviews each file individually — use the Clean view to go through suggestions one by one so nothing gets removed by accident.",
    },
    {
        // Destructive shell commands
        pattern: /\brm\s+-rf\b|\bdel\s+\/[fqs]\b|\bdeltree\b|\bformat\s+[a-z]:\b|\bmkfs\b/i,
        response: "Shell commands like that are outside my scope. Wisp only proposes safe, reversible file moves — I won't help execute destructive terminal operations.",
    },
];

const NAVIGATION_RULES: Array<{ pattern: RegExp; response: string }> = [
    {
        // What is Wisp / what can you do
        pattern: /\b(what (is|are) wisp|what can (you|wisp) do|what (do you|does wisp) support|your features?|help me|getting started)\b/i,
        response: "Wisp is an AI-powered file organizer. Here's what I can do:\n\n• **Scan & Index** — Pick a folder and embed its files so I can search and answer questions about them (Files tab → Scan & Index).\n• **Clean Up** — Review suggested junk files. Wisp moves them to quarantine, never permanently deletes.\n• **Visualize** — See a treemap of your folder sizes to spot what's taking up space.\n• **Extract Text** — Drop an image or PDF to pull out text via OCR, or drop an audio/video file to transcribe it.\n• **Assistant (here)** — Ask me anything about your indexed folders in plain English.",
    },
    {
        // Scan / index a folder
        pattern: /\b(how (do i|to) (scan|index)|scan a folder|add a folder|index a folder|how (do i|to) add)\b/i,
        response: "To scan and index a folder:\n1. Go to **Files → Scan & Index** in the left sidebar.\n2. Click **Pick Folder** and choose a directory.\n3. Click **Scan & Index** — Wisp will embed your files into the search index.\n\nOnce indexed, you can ask me questions about any of those files.",
    },
    {
        // Clean up / junk / delete suggestions
        pattern: /\b(how (do i|to) (clean|find junk|remove junk|see (delete|cleanup) suggestions)|clean up (my )?files|junk files|what files (can|should) i delete)\b/i,
        response: "To review cleanup suggestions:\n1. Go to **Files → Clean Up** in the sidebar.\n2. Wisp scores your files for junk likelihood based on name, age, and size.\n3. Click **Trash** on any candidate — it moves to your system Trash (recoverable), never permanent deletion.",
    },
    {
        // Visualize / treemap / disk usage
        pattern: /\b(visuali[sz]e|treemap|file map|disk usage|what('s| is) taking (up )?(the most )?space|folder sizes?)\b/i,
        response: "The **Visualize** view (Files tab) shows a sunburst treemap of your folder sizes. Larger segments = more space used. You can click into folders to drill down and see exactly what's taking up room.",
    },
    {
        // Extract text / OCR
        pattern: /\b(extract text|how (do i|to) (ocr|extract|read text from)|text from (an? )?(image|pdf|photo|screenshot))\b/i,
        response: "To extract text from an image or PDF:\n1. Go to **Files → Extract Text** in the sidebar.\n2. Drop a file onto the drop zone, or click **Browse files**.\n3. Supported formats: PNG, JPG, WEBP, BMP, TIFF, PDF.\n\nThe extracted text appears in a scrollable panel you can copy.",
    },
    {
        // Transcribe / audio to text
        pattern: /\b(transcri(be|ption)|audio (to|2) text|voice to text|text from (audio|video|mp3|wav)|how (do i|to) transcri(be|pt))\b/i,
        response: "To transcribe audio or video:\n1. Go to **Files → Extract Text** in the sidebar.\n2. Click **Browse files** and pick an audio or video file (MP3, WAV, M4A, MP4, MOV, etc.).\n3. Wisp sends it to the transcription service and shows the transcript.\n\nYou can also use the **read aloud** button on any text result to hear it spoken back.",
    },
    {
        // Search / find files
        pattern: /\b(how (do i|to) search|semantic search|how (does|do) (search|the search) work|find files (by|using) (meaning|content|description|ai))\b/i,
        response: "Wisp uses semantic (AI-powered) search — just describe what you're looking for in plain English and I'll find relevant files from your indexed folders, even if the exact words don't match the filename.\n\nYou can ask me directly here, like: *\"find my tax documents from last year\"* or *\"which files are about the marketing project?\"*",
    },
];

const LIMITATION_RULES: Array<{ pattern: RegExp; response: string }> = [
    {
        // Asking about contents of a specific unindexed folder by path or common name
        pattern: /\b(what('s| is) in|list( the)? files? in|show (me )?(what('s| is) in|files? in)|contents? of)\b.{0,40}\b(folder|directory|downloads?|desktop|documents?|pictures?|music|videos?|[a-z]:\\|~\/|\/home\/|\/users\/)/i,
        response: "I can only answer questions about folders you've indexed in Wisp. If that folder hasn't been scanned yet, head to **Files → Scan & Index**, pick the folder, and run a scan — then I'll have full context to answer questions about it.",
    },
    {
        // General "my files" / "my computer" type questions without indexed context
        pattern: /\b(what files (do i have|are on my (pc|computer|laptop|machine|disk|drive))|show (me )?my (files|folders|documents)|list (all )?(my )?(files|folders)|what('s| is) on my (computer|pc|hard ?drive|disk))\b/i,
        response: "I can only see files in folders you've indexed with Wisp — I don't have access to your whole PC. To get started:\n1. Go to **Files → Scan & Index**.\n2. Pick the folders you want me to know about.\n3. Run a scan, then ask me anything about those files.",
    },
];

function getStaticResponse(query: string): string | null {
    for (const rule of SAFETY_RULES) {
        if (rule.pattern.test(query)) return rule.response;
    }
    for (const rule of NAVIGATION_RULES) {
        if (rule.pattern.test(query)) return rule.response;
    }
    for (const rule of LIMITATION_RULES) {
        if (rule.pattern.test(query)) return rule.response;
    }
    return null;
}

const WELCOME_MESSAGES: Message[] = [
    {
        id: 'welcome',
        role: 'ai',
        content:
            "Hi! I'm Wisp's file assistant. I can help you find, organize, and clean up files. Ask me anything about your indexed folders — like \"find my largest files\" or \"what duplicates do I have?\"",
        timestamp: Date.now(),
    },
];

export default function AssistantView() {
    const [messages, setMessages] = useState<Message[]>(WELCOME_MESSAGES);
    const [input, setInput] = useState('');
    const [isThinking, setIsThinking] = useState(false);
    const [voices, setVoices] = useState<Voice[]>([]);
    const [selectedVoiceId, setSelectedVoiceId] = useState<string>(
        () => localStorage.getItem(STORAGE_KEY) ?? DEFAULT_VOICE_ID
    );
    const [showVoicePanel, setShowVoicePanel] = useState(false);
    const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null);
    const [missingPaths, setMissingPaths] = useState<Set<string>>(new Set());
    const [autoSpeak, setAutoSpeak] = useState<boolean>(
        () => localStorage.getItem('wisp_auto_speak') === 'true'
    );
    const messagesContainerRef = useRef<HTMLDivElement>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const autoSpeakRef = useRef(autoSpeak);

    useEffect(() => {
        const el = messagesContainerRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages]);

    useEffect(() => {
        (window as any).wispApi.getVoices()
            .then((data: { voices: Voice[] }) => setVoices(data.voices))
            .catch(() => {});
    }, []);

    useEffect(() => { autoSpeakRef.current = autoSpeak; }, [autoSpeak]);

    const stopSpeaking = () => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        setSpeakingMsgId(null);
    };

    const toggleAutoSpeak = () => {
        setAutoSpeak(prev => {
            const next = !prev;
            localStorage.setItem('wisp_auto_speak', String(next));
            autoSpeakRef.current = next;
            if (!next) stopSpeaking();
            return next;
        });
    };

    const speakMsg = async (msgId: string, content: string) => {
        if (speakingMsgId === msgId) { stopSpeaking(); return; }
        stopSpeaking();
        setSpeakingMsgId(msgId);
        try {
            const b64: string = await (window as any).wispApi.speakText(content, selectedVoiceId);
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
    };

    const handleVoiceSelect = (voiceId: string) => {
        setSelectedVoiceId(voiceId);
        setShowVoicePanel(false);
        localStorage.setItem(STORAGE_KEY, voiceId);
        window.dispatchEvent(new CustomEvent('wisp:voiceChanged', { detail: voiceId }));
    };

    const handleSend = async () => {
        const text = input.trim();
        if (!text || isThinking) return;

        const userMsg: Message = {
            id: `user-${Date.now()}`,
            role: 'user',
            content: text,
            timestamp: Date.now(),
        };

        setMessages((prev) => [...prev, userMsg]);
        setInput('');

        const safetyMsg = getStaticResponse(text);
        if (safetyMsg) {
            const staticMsg: Message = { id: `ai-${Date.now()}`, role: 'ai', content: safetyMsg, timestamp: Date.now() };
            setMessages((prev) => [...prev, staticMsg]);
            if (autoSpeakRef.current) speakMsg(staticMsg.id, staticMsg.content);
            return;
        }

        setIsThinking(true);

        try {
            const res = await (window as any).wispApi.askAssistant(text);
            const aiMsg: Message = {
                id: `ai-${Date.now()}`,
                role: 'ai',
                content: res.answer,
                sources: res.sources?.length ? res.sources : undefined,
                timestamp: Date.now(),
            };
            setMessages((prev) => [...prev, aiMsg]);
            if (autoSpeakRef.current) speakMsg(aiMsg.id, aiMsg.content);
        } catch (err: any) {
            const errMsg: Message = {
                id: `ai-${Date.now()}`,
                role: 'ai',
                content: `Sorry, I couldn't reach the assistant. Make sure the backend is running. (${err?.message ?? 'Unknown error'})`,
                timestamp: Date.now(),
            };
            setMessages((prev) => [...prev, errMsg]);
        } finally {
            setIsThinking(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const selectedVoiceName = voices.find(v => v.voice_id === selectedVoiceId)?.name ?? 'Adam';

    return (
        <div className="assistant-container">
            {/* Messages */}
            <div className="assistant-messages" ref={messagesContainerRef}>
                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        className={`assistant-message ${msg.role === 'user' ? 'assistant-message-user' : 'assistant-message-ai'
                            }`}
                    >
                        {msg.content}
                        {msg.role === 'ai' && (
                            <button
                                className={`assistant-speak-btn${speakingMsgId === msg.id ? ' speaking' : ''}`}
                                onClick={() => speakMsg(msg.id, msg.content)}
                                title={speakingMsgId === msg.id ? 'Stop' : 'Read aloud'}
                            >
                                {speakingMsgId === msg.id
                                    ? <><Square size={10} /> Stop</>
                                    : <><Volume2 size={10} /> Read aloud</>}
                            </button>
                        )}
                        {msg.sources && msg.sources.length > 0 && (
                            <div className="assistant-sources">
                                <span className="assistant-sources-label">Referenced files</span>
                                {msg.sources.map(src => (
                                    <div key={src} className="assistant-source-chip">
                                        <FileText size={11} className="assistant-source-icon" />
                                        <span className="assistant-source-name" title={src}>
                                            {getFileName(src)}
                                        </span>
                                        {missingPaths.has(src) ? (
                                            <span className="assistant-source-missing">Not found</span>
                                        ) : (<>
                                            <button
                                                className="assistant-source-btn"
                                                title="Show in folder"
                                                onClick={async () => {
                                                    const r = await (window as any).wispApi.showInFolder(src);
                                                    if (!r.ok) setMissingPaths(p => new Set(p).add(src));
                                                }}
                                            >
                                                <FolderOpen size={11} />
                                            </button>
                                            <button
                                                className="assistant-source-btn"
                                                title="Open file"
                                                onClick={async () => {
                                                    const r = await (window as any).wispApi.openPath(src);
                                                    if (!r.ok) setMissingPaths(p => new Set(p).add(src));
                                                }}
                                            >
                                                Open
                                            </button>
                                        </>)}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ))}

                {isThinking && (
                    <div className="assistant-message assistant-message-ai" style={{ color: 'var(--text-tertiary)' }}>
                        Thinking...
                    </div>
                )}

            </div>

            {/* Voice selector */}
            <div className="assistant-voice-bar">
                {showVoicePanel && (
                    <div className="assistant-voice-panel">
                        <p className="voice-panel-label">Select voice</p>
                        <div className="voice-list">
                            {voices.map(v => (
                                <div
                                    key={v.voice_id}
                                    className={`voice-item${v.voice_id === selectedVoiceId ? ' selected' : ''}`}
                                    ref={v.voice_id === selectedVoiceId ? (el) => el?.scrollIntoView({ block: 'nearest' }) : null}
                                    onClick={() => handleVoiceSelect(v.voice_id)}
                                >
                                    <span className="voice-item-name">{v.name}</span>
                                    {v.category && <span className="chip">{v.category}</span>}
                                </div>
                            ))}
                            {voices.length === 0 && (
                                <p className="voice-panel-empty">No voices loaded.</p>
                            )}
                        </div>
                    </div>
                )}
                <button
                    className={`assistant-autospeak-btn${autoSpeak ? ' active' : ''}`}
                    onClick={toggleAutoSpeak}
                    title={autoSpeak ? 'Auto-play on — click to turn off' : 'Auto-play off — click to turn on'}
                >
                    <Headphones size={12} />
                    {autoSpeak ? 'Auto-play on' : 'Auto-play off'}
                </button>
                <span className="assistant-voice-bar-sep" />
                <Volume2 size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                <span className="assistant-voice-label">Voice</span>
                <button
                    className={`assistant-voice-selector${showVoicePanel ? ' active' : ''}`}
                    onClick={() => setShowVoicePanel(v => !v)}
                    title="Change read-aloud voice"
                >
                    {selectedVoiceName}
                    <ChevronDown size={11} />
                </button>
            </div>

            {/* Input */}
            <div className="assistant-input-bar">
                <textarea
                    className="assistant-input"
                    placeholder="Ask about your files..."
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={1}
                />
                <button
                    className="assistant-send-btn"
                    onClick={handleSend}
                    disabled={!input.trim() || isThinking}
                >
                    <Send size={18} />
                </button>
            </div>
        </div>
    );
}

