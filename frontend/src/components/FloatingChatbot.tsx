"use client";

import React, { FormEvent, useState, useRef, useEffect } from "react";
import {
  SUPPORTED_LANGUAGES,
  transcribeAudio,
  translateText,
  synthesizeSpeech,
} from "@/lib/sarvam";

type ChatMessage = {
  role: "user" | "model";
  content: string;
  originalEnglish?: string;
  audioUrl?: string;
};

type FloatingChatbotProps = {
  simulationContext: unknown;
};

export default function FloatingChatbot({ simulationContext }: FloatingChatbotProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState("");

  // Step 2: Language state defaulting to English
  const [selectedLanguage, setSelectedLanguage] = useState("en-US");
  const [autoPlayAudio, setAutoPlayAudio] = useState(true);

  // Audio recording state
  const [recording, setRecording] = useState(false);
  const [playingAudioId, setPlayingAudioId] = useState<number | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusMessage]);

  const isEnglish = selectedLanguage === "en-US" || selectedLanguage === "en-IN";

  // Play audio helper
  const playAudio = (url: string, index?: number) => {
    try {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
        currentAudioRef.current = null;
      }
      const audio = new Audio(url);
      currentAudioRef.current = audio;
      if (index !== undefined) setPlayingAudioId(index);

      audio.onended = () => {
        if (index !== undefined) setPlayingAudioId(null);
      };
      audio.onerror = () => {
        if (index !== undefined) setPlayingAudioId(null);
      };

      audio.play().catch((err) => {
        console.warn("Audio autoplay blocked by browser policy:", err);
        if (index !== undefined) setPlayingAudioId(null);
      });
    } catch (err) {
      console.warn("Audio playback error:", err);
      if (index !== undefined) setPlayingAudioId(null);
    }
  };

  // Helper to call Gemini backend
  async function queryGemini(englishPrompt: string, history: ChatMessage[]) {
    const formattedMessages = history.map((m) => ({
      role: m.role,
      content: m.originalEnglish || m.content,
    }));
    formattedMessages.push({ role: "user", content: englishPrompt });

    const endpoints = [
      "/api/vision/chat",
      "http://localhost:8000/vision/chat",
    ];

    let lastError: unknown = null;
    for (const ep of endpoints) {
      try {
        const response = await fetch(ep, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sector: "industry",
            messages: formattedMessages,
            context_data: simulationContext,
          }),
        });
        if (response.ok) {
          const data = await response.json();
          return data.reply as string;
        }
        const errJson = await response.json().catch(() => ({}));
        lastError = new Error(errJson.detail || `HTTP ${response.status}`);
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError instanceof Error ? lastError : new Error(String(lastError));
  }

  // ─── Step 3 & 4: Manual Text Submission Pipeline ─────────────────────────────
  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const rawContent = input.trim();
    if (!rawContent || loading || recording) return;

    setError("");
    setLoading(true);
    setInput("");

    try {
      let englishPrompt = rawContent;
      // If native language is selected, translate user prompt to English first
      if (!isEnglish) {
        setStatusMessage("Translating question to English...");
        englishPrompt = await translateText(rawContent, selectedLanguage, "en-IN");
      }

      const userMsg: ChatMessage = {
        role: "user",
        content: rawContent,
        originalEnglish: englishPrompt,
      };

      const nextMessages = [...messages, userMsg];
      setMessages(nextMessages);

      // Query Gemini AI
      setStatusMessage("Gemini is thinking...");
      const geminiReplyEnglish = await queryGemini(englishPrompt, messages);

      // Reverse translation if user chose an Indian language
      let displayedReply = geminiReplyEnglish;
      if (!isEnglish) {
        setStatusMessage("Translating response to selected language...");
        displayedReply = await translateText(geminiReplyEnglish, "en-IN", selectedLanguage);
      }

      // Synthesize speech via Sarvam TTS
      setStatusMessage("Synthesizing voice response...");
      let audioUrl: string | undefined = undefined;
      try {
        const ttsRes = await synthesizeSpeech(
          displayedReply,
          selectedLanguage,
          "meera"
        );
        audioUrl = ttsRes.audioUrl;
      } catch (ttsErr) {
        console.warn("TTS synthesis error:", ttsErr);
      }

      const modelMsg: ChatMessage = {
        role: "model",
        content: displayedReply,
        originalEnglish: geminiReplyEnglish,
        audioUrl,
      };

      setMessages([...nextMessages, modelMsg]);

      // Automatically play audio if enabled
      if (audioUrl && autoPlayAudio) {
        playAudio(audioUrl, nextMessages.length);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not complete assistant query.");
    } finally {
      setLoading(false);
      setStatusMessage(null);
    }
  }

  // ─── Step 3 & 4: Microphone Recording & Audio STT Pipeline ──────────────────
  async function handleAudioProcess(blob: Blob) {
    setError("");
    setLoading(true);
    try {
      setStatusMessage("Transcribing your speech with Sarvam AI...");
      const sttRes = await transcribeAudio(blob, selectedLanguage);
      const recognizedText = sttRes.transcript.trim();

      if (!recognizedText) {
        setError("No speech detected. Please speak clearly into your microphone.");
        setLoading(false);
        setStatusMessage(null);
        return;
      }

      let englishPrompt = recognizedText;
      if (!isEnglish) {
        setStatusMessage("Translating transcript to English...");
        englishPrompt = await translateText(recognizedText, selectedLanguage, "en-IN");
      }

      const userMsg: ChatMessage = {
        role: "user",
        content: recognizedText,
        originalEnglish: englishPrompt,
      };

      const nextMessages = [...messages, userMsg];
      setMessages(nextMessages);

      // Query Gemini AI
      setStatusMessage("Gemini is thinking...");
      const geminiReplyEnglish = await queryGemini(englishPrompt, messages);

      // Reverse translation to selected language
      let displayedReply = geminiReplyEnglish;
      if (!isEnglish) {
        setStatusMessage("Translating response to selected language...");
        displayedReply = await translateText(geminiReplyEnglish, "en-IN", selectedLanguage);
      }

      // Synthesize speech via Sarvam TTS
      setStatusMessage("Synthesizing voice response...");
      let audioUrl: string | undefined = undefined;
      try {
        const ttsRes = await synthesizeSpeech(
          displayedReply,
          selectedLanguage,
          "meera"
        );
        audioUrl = ttsRes.audioUrl;
      } catch (ttsErr) {
        console.warn("TTS synthesis error:", ttsErr);
      }

      const modelMsg: ChatMessage = {
        role: "model",
        content: displayedReply,
        originalEnglish: geminiReplyEnglish,
        audioUrl,
      };

      setMessages([...nextMessages, modelMsg]);

      if (audioUrl && autoPlayAudio) {
        playAudio(audioUrl, nextMessages.length);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Speech-to-text processing failed.");
    } finally {
      setLoading(false);
      setStatusMessage(null);
    }
  }

  const startRecording = async () => {
    try {
      setError("");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        if (blob.size > 0) {
          await handleAudioProcess(blob);
        }
      };

      mediaRecorder.start();
      setRecording(true);
    } catch (err) {
      console.error("Microphone access error:", err);
      setError("Microphone access denied or not supported by browser.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    setRecording(false);
  };

  // Re-synthesize and listen on demand if audio was not yet cached
  const handleListenClick = async (message: ChatMessage, index: number) => {
    if (playingAudioId === index) {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
        currentAudioRef.current = null;
      }
      setPlayingAudioId(null);
      return;
    }

    if (message.audioUrl) {
      playAudio(message.audioUrl, index);
      return;
    }

    try {
      setPlayingAudioId(index);
      const res = await synthesizeSpeech(message.content, selectedLanguage, "meera");
      message.audioUrl = res.audioUrl;
      playAudio(res.audioUrl, index);
    } catch (err) {
      console.warn("Failed to generate TTS on demand:", err);
      setPlayingAudioId(null);
    }
  };

  return (
    <div style={{ position: "fixed", right: 24, bottom: 24, zIndex: 1100, fontFamily: "system-ui, -apple-system, sans-serif" }}>
      {open && (
        <section
          aria-label="Multilingual AI Assistant"
          style={{
            width: "min(400px, calc(100vw - 32px))",
            height: 540,
            marginBottom: 12,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            borderRadius: 20,
            border: "1.5px solid rgba(226,98,58,0.45)",
            background: "#0c111a",
            color: "#ffe4d6",
            boxShadow: "0 20px 60px rgba(0,0,0,0.85), 0 0 30px rgba(194,65,12,0.25)",
            backdropFilter: "blur(12px)",
          }}
        >
          {/* ══ Header ══ */}
          <header style={{
            padding: "12px 16px",
            background: "linear-gradient(90deg, #9a3412 0%, #c2410c 50%, #ea580c 100%)",
            color: "white",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: "1.2rem" }}>🌐</span>
                <span style={{ fontWeight: 800, fontSize: ".95rem", letterSpacing: ".04em" }}>
                  Multilingual AI Assistant
                </span>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close chat"
                style={{
                  background: "rgba(0,0,0,0.25)",
                  border: 0,
                  borderRadius: "50%",
                  width: 26,
                  height: 26,
                  color: "white",
                  fontSize: 16,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                ✕
              </button>
            </div>

            {/* Language Selector Dropdown (Step 2) */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
                <label htmlFor="sarvam-lang-select" style={{ fontSize: ".72rem", color: "#fed7aa", fontWeight: 700, textTransform: "uppercase" }}>
                  Language:
                </label>
                <select
                  id="sarvam-lang-select"
                  value={selectedLanguage}
                  onChange={(e) => setSelectedLanguage(e.target.value)}
                  style={{
                    flex: 1,
                    background: "rgba(0,0,0,0.45)",
                    border: "1px solid rgba(255,255,255,0.25)",
                    color: "#ffffff",
                    borderRadius: 8,
                    padding: "4px 8px",
                    fontSize: ".78rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    outline: "none",
                  }}
                >
                  {SUPPORTED_LANGUAGES.map((lang) => (
                    <option key={lang.code} value={lang.code} style={{ background: "#111827", color: "#fff" }}>
                      {lang.nativeName} ({lang.name})
                    </option>
                  ))}
                </select>
              </div>

              {/* Auto-TTS Toggle */}
              <button
                type="button"
                onClick={() => setAutoPlayAudio((prev) => !prev)}
                title={autoPlayAudio ? "Auto-read responses enabled" : "Auto-read responses disabled"}
                style={{
                  background: autoPlayAudio ? "rgba(34,197,94,0.3)" : "rgba(255,255,255,0.1)",
                  border: `1px solid ${autoPlayAudio ? "#86efac" : "rgba(255,255,255,0.2)"}`,
                  color: autoPlayAudio ? "#86efac" : "#d1d5db",
                  borderRadius: 6,
                  padding: "3px 8px",
                  fontSize: ".7rem",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
              >
                {autoPlayAudio ? "🔊 Auto" : "🔇 Mute"}
              </button>
            </div>
          </header>

          {/* ══ Chat Messages ══ */}
          <div aria-live="polite" style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
            {messages.length === 0 && (
              <div style={{ color: "#a88575", fontSize: ".85rem", lineHeight: 1.5, textAlign: "center", margin: "auto 0" }}>
                <p style={{ margin: "0 0 6px", fontSize: "1.8rem" }}>💬</p>
                <p style={{ margin: "0 0 4px", fontWeight: 700, color: "#ffe4d6" }}>
                  Ask questions in any Indian Language
                </p>
                <p style={{ margin: 0, fontSize: ".78rem" }}>
                  Speak or type in Hindi, Tamil, Telugu, Kannada, Bengali, etc. Sarvam AI translates & Gemini analyzes.
                </p>
              </div>
            )}

            {messages.map((message, index) => {
              const isUser = message.role === "user";
              const isPlaying = playingAudioId === index;

              return (
                <div
                  key={index}
                  style={{
                    alignSelf: isUser ? "flex-end" : "flex-start",
                    maxWidth: "85%",
                    borderRadius: 14,
                    padding: "10px 14px",
                    background: isUser ? "#3a1c12" : "#141c2c",
                    border: `1px solid ${isUser ? "rgba(234,88,12,0.4)" : "rgba(59,130,246,0.3)"}`,
                    color: "#ffe4d6",
                    fontSize: ".88rem",
                    lineHeight: 1.45,
                    boxShadow: "0 4px 14px rgba(0,0,0,0.3)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: ".7rem", fontWeight: 800, color: isUser ? "#fb923c" : "#60a5fa", textTransform: "uppercase" }}>
                      {isUser ? "You" : "Gemini Advisor"}
                    </span>

                    {!isUser && (
                      <button
                        onClick={() => handleListenClick(message, index)}
                        title="Listen to this response"
                        style={{
                          background: isPlaying ? "rgba(34,197,94,0.25)" : "rgba(255,255,255,0.08)",
                          border: `1px solid ${isPlaying ? "#86efac" : "rgba(255,255,255,0.15)"}`,
                          color: isPlaying ? "#86efac" : "#fdba74",
                          borderRadius: 6,
                          padding: "2px 7px",
                          fontSize: ".7rem",
                          fontWeight: 700,
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: 3,
                        }}
                      >
                        {isPlaying ? "⏸ Playing" : "🔊 Listen"}
                      </button>
                    )}
                  </div>

                  <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{message.content}</p>

                  {/* If native language was used, optionally show small translated query indicator */}
                  {message.originalEnglish && message.originalEnglish !== message.content && (
                    <div style={{ marginTop: 6, paddingTop: 4, borderTop: "1px solid rgba(255,255,255,0.08)", fontSize: ".72rem", color: "#9ca3af" }}>
                      <span style={{ color: "#d1d5db" }}>EN: </span>
                      {message.originalEnglish.slice(0, 120)}
                      {message.originalEnglish.length > 120 ? "..." : ""}
                    </div>
                  )}
                </div>
              );
            })}

            {statusMessage && (
              <div style={{
                alignSelf: "flex-start",
                padding: "8px 12px",
                borderRadius: 12,
                background: "rgba(234,88,12,0.15)",
                border: "1px dashed rgba(234,88,12,0.4)",
                color: "#fdba74",
                fontSize: ".78rem",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}>
                <span className="sarvam-pulse" style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "#ea580c" }} />
                <span>{statusMessage}</span>
              </div>
            )}

            {error && (
              <div role="alert" style={{
                padding: "8px 12px",
                borderRadius: 10,
                background: "rgba(239,68,68,0.15)",
                border: "1px solid rgba(239,68,68,0.35)",
                color: "#fca5a5",
                fontSize: ".78rem",
              }}>
                ⚠ {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* ══ Input Bar ══ */}
          <form
            onSubmit={sendMessage}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "10px 12px",
              borderTop: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(10,14,22,0.95)",
            }}
          >
            {/* Microphone Button (Step 3) */}
            <button
              type="button"
              onClick={recording ? stopRecording : startRecording}
              disabled={loading}
              title={recording ? "Click to stop recording" : "Record voice input via Sarvam STT"}
              style={{
                width: 38,
                height: 38,
                borderRadius: 10,
                border: `1.5px solid ${recording ? "#ef4444" : "rgba(234,88,12,0.4)"}`,
                background: recording ? "#ef4444" : "rgba(234,88,12,0.12)",
                color: recording ? "#ffffff" : "#fb923c",
                fontSize: "1.1rem",
                cursor: loading ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                transition: "all .2s ease",
                boxShadow: recording ? "0 0 14px rgba(239,68,68,0.8)" : "none",
              }}
            >
              {recording ? "⏹" : "🎤"}
            </button>

            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading || recording}
              placeholder={
                recording
                  ? "Listening to speech... click ⏹ when done"
                  : isEnglish
                  ? "Ask Gemini about results, pathways..."
                  : `Type in ${SUPPORTED_LANGUAGES.find((l) => l.code === selectedLanguage)?.name || "native language"}...`
              }
              aria-label="Message"
              style={{
                minWidth: 0,
                flex: 1,
                padding: "10px 14px",
                borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.15)",
                background: "#070a0f",
                color: "#ffe4d6",
                fontSize: ".88rem",
                outline: "none",
              }}
            />

            <button
              disabled={loading || !input.trim() || recording}
              type="submit"
              style={{
                border: 0,
                borderRadius: 10,
                padding: "10px 16px",
                background: "linear-gradient(90deg, #c2410c, #ea580c)",
                color: "#ffffff",
                fontWeight: 700,
                fontSize: ".84rem",
                cursor: loading || !input.trim() || recording ? "not-allowed" : "pointer",
                opacity: loading || !input.trim() || recording ? 0.45 : 1,
                transition: "all .2s ease",
              }}
            >
              Send
            </button>
          </form>
        </section>
      )}

      {/* Floating Launcher Button */}
      <button
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        style={{
          float: "right",
          border: 0,
          borderRadius: 999,
          padding: "13px 20px",
          background: "linear-gradient(90deg, #c2410c 0%, #ea580c 100%)",
          color: "white",
          fontWeight: 700,
          fontSize: ".95rem",
          letterSpacing: ".02em",
          cursor: "pointer",
          boxShadow: "0 6px 24px rgba(194,65,12,0.45)",
          display: "flex",
          alignItems: "center",
          gap: 8,
          transition: "transform .2s ease",
        }}
      >
        <span>💬</span>
        <span>Multilingual AI</span>
      </button>
    </div>
  );
}
