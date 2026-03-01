import { useState, useCallback, useRef, useEffect } from 'react';
import {
    ScanText, Upload, Copy, Check, RotateCcw, AlertCircle,
    ChevronLeft, ChevronRight, Scissors, FileImage, Mic, Volume2, Square, Settings2,
} from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url,
).href;

// ── Types ─────────────────────────────────────────────────────────────────────

type OcrResult = {
    kind: 'ocr';
    text: string;
    word_count?: number;
    char_count?: number;
    confidence?: number;
};

type TranscriptSegment = { speaker: string; text: string };

type TranscriptResult = {
    kind: 'transcript';
    text: string;
    word_count: number;
    char_count: number;
    language: string;
    language_probability: number;
    speakers: number;
    segments: TranscriptSegment[];
};

type AnyResult = OcrResult | TranscriptResult;

type State = 'idle' | 'loading' | 'pdf-select' | 'done' | 'error';

type Rect = { x: number; y: number; w: number; h: number };

const AUDIO_VIDEO_EXTS = new Set([
    'mp3', 'wav', 'm4a', 'ogg', 'flac', 'aac', 'opus',
    'mp4', 'mov', 'webm', 'mkv',
]);

type Voice = {
    voice_id: string;
    name: string;
    category: string | null;
    preview_url: string | null;
};

// Speaker colours — cycles if more than 5 speakers
const SPEAKER_COLORS = [
    'var(--accent)',
    '#E07B54',
    '#5BAD8A',
    '#9B6DD1',
    '#C4A020',
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function ExtractView() {
    const [state, setState]           = useState<State>('idle');
    const [fileName, setFileName]     = useState('');
    const [result, setResult]         = useState<AnyResult | null>(null);
    const [errorMsg, setErrorMsg]     = useState('');
    const [dragging, setDragging]     = useState(false);
    const [copied, setCopied]         = useState(false);
    const [speaking, setSpeaking]         = useState(false);
    const [loadingLabel, setLoadingLabel] = useState('Extracting text from');
    const [voices, setVoices]             = useState<Voice[]>([]);
    const [selectedVoiceId, setSelectedVoiceId] = useState<string>(
        () => localStorage.getItem('wisp_tts_voice') ?? 'pNInz6obpgDQGcFmaJgB'
    );
    const [showVoicePanel, setShowVoicePanel]   = useState(false);
    const [previewingVoiceId, setPreviewingVoiceId] = useState<string | null>(null);
    const audioRef        = useRef<HTMLAudioElement | null>(null);
    const previewAudioRef = useRef<HTMLAudioElement | null>(null);

    // PDF viewer state
    const [pdfDoc, setPdfDoc]           = useState<PDFDocumentProxy | null>(null);
    const [pageNum, setPageNum]         = useState(1);
    const [totalPages, setTotalPages]   = useState(0);
    const [selection, setSelection]     = useState<Rect | null>(null);
    const [isSelecting, setIsSelecting] = useState(false);
    const [dragStart, setDragStart]     = useState<{ x: number; y: number } | null>(null);

    const mainCanvasRef    = useRef<HTMLCanvasElement>(null);
    const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
    const canvasWrapRef    = useRef<HTMLDivElement>(null);

    // ── PDF rendering ──────────────────────────────────────────────────────────

    const renderPage = useCallback(async (doc: PDFDocumentProxy, num: number) => {
        const page    = await doc.getPage(num);
        const main    = mainCanvasRef.current;
        const overlay = overlayCanvasRef.current;
        if (!main || !overlay) return;

        const containerW = (canvasWrapRef.current?.clientWidth ?? 700) - 2;
        const raw   = page.getViewport({ scale: 1 });
        const scale = containerW / raw.width;
        const vp    = page.getViewport({ scale });

        main.width    = vp.width;
        main.height   = vp.height;
        overlay.width  = vp.width;
        overlay.height = vp.height;

        await page.render({ canvas: main, canvasContext: main.getContext('2d')!, viewport: vp }).promise;

        overlay.getContext('2d')!.clearRect(0, 0, overlay.width, overlay.height);
        setSelection(null);
    }, []);

    useEffect(() => {
        if (pdfDoc && state === 'pdf-select') renderPage(pdfDoc, pageNum);
    }, [pdfDoc, pageNum, state, renderPage]);

    useEffect(() => {
        (window as any).wispApi.getVoices()
            .then((data: { voices: Voice[] }) => setVoices(data.voices))
            .catch(() => {});
        const onVoiceChanged = (e: Event) => setSelectedVoiceId((e as CustomEvent).detail);
        window.addEventListener('wisp:voiceChanged', onVoiceChanged);
        return () => window.removeEventListener('wisp:voiceChanged', onVoiceChanged);
    }, []);

    // ── Canvas selection ───────────────────────────────────────────────────────

    const drawRect = (sel: Rect) => {
        const canvas = overlayCanvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d')!;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (sel.w > 4 && sel.h > 4) {
            ctx.fillStyle = 'rgba(91,155,213,0.12)';
            ctx.fillRect(sel.x, sel.y, sel.w, sel.h);
            ctx.beginPath();
            ctx.moveTo(sel.x, sel.y);
            ctx.lineTo(sel.x + sel.w, sel.y);
            ctx.lineTo(sel.x + sel.w, sel.y + sel.h);
            ctx.lineTo(sel.x, sel.y + sel.h);
            ctx.closePath();
            ctx.strokeStyle = 'rgba(91,155,213,0.9)';
            ctx.lineWidth   = 2;
            ctx.setLineDash([6, 3]);
            ctx.stroke();
        }
    };

    const canvasPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
        const cv = overlayCanvasRef.current!;
        const r  = cv.getBoundingClientRect();
        return {
            x: (e.clientX - r.left)  * (cv.width  / r.width),
            y: (e.clientY - r.top)   * (cv.height / r.height),
        };
    };

    const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
        const pos = canvasPos(e);
        setDragStart(pos);
        setIsSelecting(true);
        setSelection(null);
        overlayCanvasRef.current?.getContext('2d')
            ?.clearRect(0, 0, overlayCanvasRef.current.width, overlayCanvasRef.current.height);
    };

    const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
        if (!isSelecting || !dragStart) return;
        const pos = canvasPos(e);
        const sel: Rect = {
            x: Math.min(dragStart.x, pos.x),
            y: Math.min(dragStart.y, pos.y),
            w: Math.abs(pos.x - dragStart.x),
            h: Math.abs(pos.y - dragStart.y),
        };
        setSelection(sel);
        drawRect(sel);
    };

    const handleMouseUp = () => setIsSelecting(false);

    // ── File loading ───────────────────────────────────────────────────────────

    const loadPdf = useCallback(async (source: string | File, name: string) => {
        setFileName(name);
        setPageNum(1);
        setSelection(null);
        try {
            let data: ArrayBuffer;
            if (typeof source === 'string') {
                const b64: string = await (window as any).wispApi.readFileBase64(source);
                const raw = atob(b64);
                const bytes = new Uint8Array(raw.length);
                for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
                data = bytes.buffer;
            } else {
                data = await source.arrayBuffer();
            }
            const doc = await pdfjsLib.getDocument({ data }).promise;
            setPdfDoc(doc);
            setTotalPages(doc.numPages);
            setState('pdf-select');
        } catch (e: any) {
            setErrorMsg(e?.message ?? 'Failed to load PDF.');
            setState('error');
        }
    }, []);

    const runOcr = useCallback(async (filePath: string, name: string) => {
        setFileName(name);
        setLoadingLabel('Extracting text from');
        setState('loading');
        setResult(null);
        setErrorMsg('');
        try {
            const res = await (window as any).wispApi.extractText(filePath);
            setResult({ kind: 'ocr', ...res });
            setState('done');
        } catch (e: any) {
            setErrorMsg(e?.message ?? 'Extraction failed. Check the backend is running and Google Cloud Vision is configured.');
            setState('error');
        }
    }, []);

    const runTranscribe = useCallback(async (filePath: string, name: string) => {
        setFileName(name);
        setLoadingLabel('Transcribing');
        setState('loading');
        setResult(null);
        setErrorMsg('');
        try {
            const res = await (window as any).wispApi.transcribeFile(filePath);
            setResult({ kind: 'transcript', ...res });
            setState('done');
        } catch (e: any) {
            setErrorMsg(e?.message ?? 'Transcription failed. Check the backend is running and ELEVENLABS_API_KEY is configured.');
            setState('error');
        }
    }, []);

    const handleFile = useCallback((fp: string, name: string, fileObj?: File) => {
        const ext = name.split('.').pop()?.toLowerCase() ?? '';
        if (ext === 'pdf') loadPdf(fileObj ?? fp, name);
        else if (AUDIO_VIDEO_EXTS.has(ext)) runTranscribe(fp, name);
        else runOcr(fp, name);
    }, [loadPdf, runOcr, runTranscribe]);

    const handleBrowse = async () => {
        const fp = await (window as any).wispApi.pickFileForOcr();
        if (!fp) return;
        const name = fp.split(/[/\\]/).pop() ?? fp;
        handleFile(fp, name);
    };

    const handleDragOver  = (e: React.DragEvent) => { e.preventDefault(); setDragging(true); };
    const handleDragLeave = () => setDragging(false);
    const handleDrop      = (e: React.DragEvent) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (!file) return;
        const fp = (file as any).path as string | undefined;
        if (!fp) return;
        handleFile(fp, file.name, file);
    };

    // ── Extract canvas region (PDF OCR) ────────────────────────────────────────

    const extractRegion = (sel: Rect | null) => {
        const main = mainCanvasRef.current;
        if (!main) return;

        const tmp = document.createElement('canvas');
        if (sel && sel.w > 4 && sel.h > 4) {
            tmp.width  = sel.w;
            tmp.height = sel.h;
            tmp.getContext('2d')!.drawImage(main, sel.x, sel.y, sel.w, sel.h, 0, 0, sel.w, sel.h);
        } else {
            tmp.width  = main.width;
            tmp.height = main.height;
            tmp.getContext('2d')!.drawImage(main, 0, 0);
        }

        tmp.toBlob(async (blob) => {
            if (!blob) return;
            setState('loading');
            setLoadingLabel('Extracting text from');
            setResult(null);
            setErrorMsg('');
            try {
                const buf   = await blob.arrayBuffer();
                const bytes = new Uint8Array(buf);
                const chunks: string[] = [];
                for (let i = 0; i < bytes.length; i += 8192) {
                    chunks.push(String.fromCharCode(...bytes.subarray(i, i + 8192)));
                }
                const b64  = btoa(chunks.join(''));
                const name = `${fileName}_p${pageNum}.png`;
                const res  = await (window as any).wispApi.extractTextFromBuffer(b64, name);
                setResult({ kind: 'ocr', ...res });
                setState('done');
            } catch (e: any) {
                setErrorMsg(e?.message ?? 'Extraction failed.');
                setState('error');
            }
        }, 'image/png');
    };

    // ── Read aloud ─────────────────────────────────────────────────────────────

    const stopSpeaking = () => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        setSpeaking(false);
    };

    const previewVoice = (url: string | null, voiceId: string) => {
        if (previewAudioRef.current) {
            previewAudioRef.current.pause();
            previewAudioRef.current = null;
        }
        if (previewingVoiceId === voiceId) { setPreviewingVoiceId(null); return; }
        if (!url) return;
        const audio = new Audio(url);
        previewAudioRef.current = audio;
        setPreviewingVoiceId(voiceId);
        audio.onended = () => { setPreviewingVoiceId(null); previewAudioRef.current = null; };
        audio.onerror = () => { setPreviewingVoiceId(null); previewAudioRef.current = null; };
        audio.play();
    };

    const speakOcr = async (text: string) => {
        if (speaking) { stopSpeaking(); return; }
        setSpeaking(true);
        try {
            const b64: string = await (window as any).wispApi.speakText(text, selectedVoiceId);
            const raw  = atob(b64);
            const bytes = new Uint8Array(raw.length);
            for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
            const blob = new Blob([bytes], { type: 'audio/mpeg' });
            const url  = URL.createObjectURL(blob);
            const audio = new Audio(url);
            audioRef.current = audio;
            audio.onended = () => { setSpeaking(false); URL.revokeObjectURL(url); };
            audio.onerror = () => { setSpeaking(false); URL.revokeObjectURL(url); };
            await audio.play();
        } catch {
            setSpeaking(false);
        }
    };

    // ── Copy / Reset ───────────────────────────────────────────────────────────

    const handleCopy = async () => {
        const text = result?.text;
        if (!text) return;
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleReset = () => {
        stopSpeaking();
        setState('idle');
        setFileName('');
        setResult(null);
        setErrorMsg('');
        setPdfDoc(null);
        setPageNum(1);
        setTotalPages(0);
        setSelection(null);
    };

    // ── Render: idle ───────────────────────────────────────────────────────────

    if (state === 'idle') {
        return (
            <div className="extract-container">
                <div
                    className={`extract-dropzone${dragging ? ' dragging' : ''}`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={handleBrowse}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && handleBrowse()}
                >
                    <div className="extract-dropzone-icon">
                        <ScanText size={20} />
                    </div>
                    <p className="extract-dropzone-title">Drop a file here, or click to browse</p>
                    <p className="extract-dropzone-formats">
                        PNG &middot; JPG &middot; WEBP &middot; TIFF &middot; PDF (region select)
                    </p>
                    <p className="extract-dropzone-formats" style={{ marginTop: 2 }}>
                        MP3 &middot; WAV &middot; M4A &middot; MP4 &middot; MOV &middot; WEBM &middot; FLAC
                    </p>
                    <button
                        className="btn btn-primary"
                        style={{ marginTop: 16 }}
                        onClick={(e) => { e.stopPropagation(); handleBrowse(); }}
                    >
                        <Upload size={14} />
                        Browse files
                    </button>
                </div>
            </div>
        );
    }

    // ── Render: loading ────────────────────────────────────────────────────────

    if (state === 'loading') {
        return (
            <div className="extract-container">
                <div className="extract-loading">
                    <span className="status-dot busy" />
                    <span className="extract-loading-text">
                        {loadingLabel} <strong>{fileName}</strong>&hellip;
                    </span>
                </div>
            </div>
        );
    }

    // ── Render: error ──────────────────────────────────────────────────────────

    if (state === 'error') {
        return (
            <div className="extract-container">
                <div className="extract-error">
                    <AlertCircle size={32} className="extract-error-icon" />
                    <p className="extract-error-title">Failed</p>
                    <p className="extract-error-desc">{errorMsg}</p>
                    <button className="btn btn-secondary" onClick={handleReset}>
                        <RotateCcw size={14} />
                        Try another file
                    </button>
                </div>
            </div>
        );
    }

    // ── Render: pdf-select ─────────────────────────────────────────────────────

    if (state === 'pdf-select') {
        const hasSelection = selection != null && selection.w > 4 && selection.h > 4;
        return (
            <div className="extract-container extract-pdf-mode">
                <div className="extract-pdf-header">
                    <ScanText size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                    <span className="extract-result-name">{fileName}</span>
                    <span className="chip">Page {pageNum} / {totalPages}</span>
                    <button
                        className="btn btn-secondary extract-pdf-nav"
                        disabled={pageNum <= 1}
                        onClick={() => setPageNum(p => p - 1)}
                        title="Previous page"
                    >
                        <ChevronLeft size={14} />
                    </button>
                    <button
                        className="btn btn-secondary extract-pdf-nav"
                        disabled={pageNum >= totalPages}
                        onClick={() => setPageNum(p => p + 1)}
                        title="Next page"
                    >
                        <ChevronRight size={14} />
                    </button>
                </div>

                <p className="extract-pdf-hint">
                    Drag to select a region, then click <strong>Extract selection</strong>.
                    Or extract the full page.
                </p>

                <div className="extract-pdf-canvas-wrap" ref={canvasWrapRef}>
                    <canvas ref={mainCanvasRef} className="extract-pdf-canvas" />
                    <canvas
                        ref={overlayCanvasRef}
                        className="extract-pdf-overlay"
                        onMouseDown={handleMouseDown}
                        onMouseMove={handleMouseMove}
                        onMouseUp={handleMouseUp}
                        onMouseLeave={handleMouseUp}
                    />
                </div>

                <div className="extract-pdf-actions">
                    <button
                        className="btn btn-primary"
                        disabled={!hasSelection}
                        onClick={() => extractRegion(selection)}
                        title={hasSelection ? 'Extract selected region' : 'Draw a selection first'}
                    >
                        <Scissors size={14} />
                        Extract selection
                    </button>
                    <button className="btn btn-secondary" onClick={() => extractRegion(null)}>
                        <FileImage size={14} />
                        Extract full page
                    </button>
                    <button className="btn btn-secondary" onClick={handleReset} style={{ marginLeft: 'auto' }}>
                        <RotateCcw size={14} />
                        Cancel
                    </button>
                </div>
            </div>
        );
    }

    // ── Render: done ───────────────────────────────────────────────────────────

    if (!result) return null;

    const wordCount = result.word_count ?? (result.text?.trim().split(/\s+/).filter(Boolean).length ?? 0);
    const charCount = result.char_count ?? (result.text?.length ?? 0);

    // ── Transcript result ──────────────────────────────────────────────────────

    if (result.kind === 'transcript') {
        const speakerNames = [...new Set(result.segments.map(s => s.speaker))];
        const speakerIndex = (id: string) => speakerNames.indexOf(id);
        const speakerLabel = (id: string) => `Speaker ${speakerIndex(id) + 1}`;

        return (
            <div className="extract-container">
                <div className="extract-result">
                    <div className="extract-result-header">
                        <Mic size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                        <span className="extract-result-name">{fileName}</span>
                        <span className="chip">{result.language.toUpperCase()}</span>
                        <span className="chip">{wordCount.toLocaleString()} words</span>
                        {result.speakers > 1 && (
                            <span className="chip">{result.speakers} speakers</span>
                        )}
                        <button
                            className="btn btn-secondary extract-result-copy"
                            onClick={handleCopy}
                            title="Copy full transcript"
                        >
                            {copied ? <Check size={13} /> : <Copy size={13} />}
                            {copied ? 'Copied' : 'Copy'}
                        </button>
                    </div>
                    <div className="extract-result-body">
                        {result.segments.length > 0 ? (
                            <div className="transcript-segments">
                                {result.segments.map((seg, i) => (
                                    <div key={i} className="transcript-segment">
                                        {result.speakers > 1 && (
                                            <span
                                                className="transcript-speaker"
                                                style={{ color: SPEAKER_COLORS[speakerIndex(seg.speaker) % SPEAKER_COLORS.length] }}
                                            >
                                                {speakerLabel(seg.speaker)}
                                            </span>
                                        )}
                                        <p className="transcript-text">{seg.text}</p>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="extract-empty-result">No speech detected in this file.</p>
                        )}
                    </div>
                </div>

                <button className="btn btn-secondary" onClick={handleReset}>
                    <RotateCcw size={14} />
                    Transcribe another file
                </button>
            </div>
        );
    }

    // ── OCR result ─────────────────────────────────────────────────────────────

    return (
        <div className="extract-container">
            <div className="extract-result">
                <div className="extract-result-header">
                    <ScanText size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                    <span className="extract-result-name">{fileName}</span>
                    <span className="chip">{wordCount.toLocaleString()} words</span>
                    <span className="chip">{charCount.toLocaleString()} chars</span>
                    {result.confidence != null && (
                        <span className="chip">{Math.round(result.confidence * 100)}% conf.</span>
                    )}
                    <button
                        className="btn btn-secondary extract-result-copy"
                        onClick={() => speakOcr(result.text)}
                        disabled={!result.text?.trim()}
                        title={speaking ? 'Stop playback' : 'Read aloud'}
                    >
                        {speaking ? <Square size={13} /> : <Volume2 size={13} />}
                        {speaking ? 'Stop' : 'Read aloud'}
                    </button>
                    <button
                        className={`btn btn-secondary extract-result-copy${showVoicePanel ? ' voice-btn-active' : ''}`}
                        onClick={() => setShowVoicePanel(v => !v)}
                        title="Change voice"
                    >
                        <Settings2 size={13} />
                        Voice
                    </button>
                    <button
                        className="btn btn-secondary extract-result-copy"
                        onClick={handleCopy}
                        title="Copy to clipboard"
                    >
                        {copied ? <Check size={13} /> : <Copy size={13} />}
                        {copied ? 'Copied' : 'Copy'}
                    </button>
                </div>
                {showVoicePanel && (
                    <div className="voice-panel">
                        <p className="voice-panel-label">Select voice</p>
                        <div className="voice-list">
                            {voices.map(v => (
                                <div
                                    key={v.voice_id}
                                    className={`voice-item${v.voice_id === selectedVoiceId ? ' selected' : ''}`}
                                    ref={v.voice_id === selectedVoiceId ? (el) => el?.scrollIntoView({ block: 'nearest' }) : null}
                                    onClick={() => {
                                        setSelectedVoiceId(v.voice_id);
                                        localStorage.setItem('wisp_tts_voice', v.voice_id);
                                        window.dispatchEvent(new CustomEvent('wisp:voiceChanged', { detail: v.voice_id }));
                                    }}
                                >
                                    <span className="voice-item-name">{v.name}</span>
                                    {v.category && <span className="chip">{v.category}</span>}
                                    {v.preview_url && (
                                        <button
                                            className="btn btn-secondary voice-preview-btn"
                                            onClick={(e) => { e.stopPropagation(); previewVoice(v.preview_url, v.voice_id); }}
                                            title={previewingVoiceId === v.voice_id ? 'Stop preview' : 'Preview voice'}
                                        >
                                            {previewingVoiceId === v.voice_id ? <Square size={11} /> : <Volume2 size={11} />}
                                        </button>
                                    )}
                                </div>
                            ))}
                            {voices.length === 0 && (
                                <p className="voice-panel-empty">No voices loaded.</p>
                            )}
                        </div>
                    </div>
                )}
                <div className="extract-result-body">
                    {result.text?.trim() ? (
                        <pre className="extract-result-text">{result.text}</pre>
                    ) : (
                        <p className="extract-empty-result">No text found in this selection.</p>
                    )}
                </div>
            </div>

            <button className="btn btn-secondary" onClick={handleReset}>
                <RotateCcw size={14} />
                Extract another file
            </button>
        </div>
    );
}
