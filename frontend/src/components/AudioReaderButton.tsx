import React, { useState, useRef } from 'react';
import { synthesizeSpeech, normalizeForSarvam } from '@/lib/sarvam';

interface AudioReaderButtonProps {
  text: string;
  lang?: string; // language code like 'hi-IN', 'en-IN' (defaults to 'en-IN')
  className?: string;
  style?: React.CSSProperties;
}

function cleanTextForSpeech(raw: string): string {
  if (!raw) return '';
  return raw
    .replace(/[#*_`~>-]/g, ' ')               // remove markdown characters
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // extract link labels
    .replace(/\s+/g, ' ')                     // collapse whitespace
    .trim()
    .slice(0, 2000);                          // safe limit for Sarvam TTS
}

export default function AudioReaderButton({
  text,
  lang = 'en-IN',
  className,
  style,
}: AudioReaderButtonProps) {
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const handleClick = async () => {
    if (!text) return;

    // Toggle stop if already playing
    if (playing && audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
      setPlaying(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const targetLang = normalizeForSarvam(lang);
      const speechText = cleanTextForSpeech(text);

      const res = await synthesizeSpeech(speechText, targetLang, 'meera');
      const audio = new Audio(res.audioUrl);
      audioRef.current = audio;
      setPlaying(true);

      audio.onended = () => {
        setPlaying(false);
        audioRef.current = null;
      };

      audio.onerror = () => {
        setPlaying(false);
        audioRef.current = null;
      };

      await audio.play();
    } catch (e: any) {
      setError(e.message || 'TTS request failed');
      setPlaying(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      className={className}
      title={playing ? 'Click to stop reading' : 'Listen to this explanation'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '5px 10px',
        borderRadius: 8,
        background: playing ? 'rgba(34,197,94,0.25)' : 'rgba(74,222,128,0.15)',
        border: `1px solid ${playing ? '#86efac' : 'rgba(74,222,128,0.3)'}`,
        color: playing ? '#86efac' : '#dcfce7',
        fontSize: '0.78rem',
        fontWeight: 600,
        cursor: loading ? 'not-allowed' : 'pointer',
        transition: 'all 0.15s ease',
        ...style,
      }}
    >
      {loading ? (
        <span>🔊 Loading…</span>
      ) : playing ? (
        <span>⏸ Stop</span>
      ) : (
        <span>🔊 Read</span>
      )}
      {error && <span style={{ color: '#f87171', marginLeft: 4 }}>({error})</span>}
    </button>
  );
}
