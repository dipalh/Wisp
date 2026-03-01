import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User } from 'lucide-react';

type Message = {
    id: string;
    role: 'user' | 'ai';
    content: string;
    timestamp: number;
};

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
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

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
        setIsThinking(true);

        // Mock response — replace with real AI call later
        setTimeout(() => {
            const aiMsg: Message = {
                id: `ai-${Date.now()}`,
                role: 'ai',
                content: getMockResponse(text),
                timestamp: Date.now(),
            };
            setMessages((prev) => [...prev, aiMsg]);
            setIsThinking(false);
        }, 800 + Math.random() * 500);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="assistant-container">
            {/* Messages */}
            <div className="assistant-messages">
                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        className={`assistant-message ${msg.role === 'user' ? 'assistant-message-user' : 'assistant-message-ai'
                            }`}
                    >
                        {msg.content}
                    </div>
                ))}

                {isThinking && (
                    <div className="assistant-message assistant-message-ai" style={{ color: 'var(--text-tertiary)' }}>
                        Thinking...
                    </div>
                )}

                <div ref={messagesEndRef} />
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

/** Temporary mock responses until LLM backend is wired */
function getMockResponse(query: string): string {
    const q = query.toLowerCase();

    if (q.includes('largest') || q.includes('biggest') || q.includes('big file')) {
        return "Based on your indexed folders, I'd need to run a scan to identify your largest files. Head over to the Scan view and click \"Rescan\" — then I'll be able to give you a sorted breakdown.";
    }

    if (q.includes('duplicate') || q.includes('same file')) {
        return "Duplicate detection compares files by content hash. Once your files are fully embedded and scored, I can surface exact and near-duplicates. Check the Clean view for automated suggestions.";
    }

    if (q.includes('organize') || q.includes('sort') || q.includes('clean')) {
        return "I can propose organization moves — grouping files by type, project, or date. Use the \"Organize\" action in the Scan view, then review each proposal before it's applied.";
    }

    if (q.includes('delete') || q.includes('trash') || q.includes('remove')) {
        return "For safety, I never permanently delete files. Instead, I move them to quarantine, which you can undo at any time. Use the Clean view to review deletion suggestions one by one.";
    }

    return "I understand your question. Once the AI backend is fully connected, I'll be able to search through your files semantically, propose cleanup actions, and answer questions using your documents as context. For now, try the Scan, Clean, or Visualize views to explore your files.";
}
