/**
 * Client service for Sarvam AI (STT, Translation, TTS)
 */

export interface LanguageOption {
  code: string;
  name: string;
  nativeName: string;
}

export const SUPPORTED_LANGUAGES: LanguageOption[] = [
  { code: "en-US", name: "English", nativeName: "English" },
  { code: "hi-IN", name: "Hindi", nativeName: "हिन्दी" },
  { code: "bn-IN", name: "Bengali", nativeName: "বাংলা" },
  { code: "mr-IN", name: "Marathi", nativeName: "मराठी" },
  { code: "te-IN", name: "Telugu", nativeName: "తెలుగు" },
  { code: "ta-IN", name: "Tamil", nativeName: "தமிழ்" },
  { code: "gu-IN", name: "Gujarati", nativeName: "ગુજરાતી" },
  { code: "kn-IN", name: "Kannada", nativeName: "ಕನ್ನಡ" },
  { code: "or-IN", name: "Odia", nativeName: "ଓଡ଼ିଆ" },
  { code: "ml-IN", name: "Malayalam", nativeName: "മലയാളം" },
  { code: "pa-IN", name: "Punjabi", nativeName: "ਪੰਜਾਬੀ" },
];

/** Normalize UI language codes like en-US to en-IN for Sarvam APIs */
export function normalizeForSarvam(code?: string): string {
  if (!code || typeof code !== "string") return "en-IN";
  const c = code.trim().toLowerCase();
  if (c.startsWith("en") || c === "english") return "en-IN";
  return code.trim();
}

async function requestWithFallbacks(paths: string[], init: RequestInit): Promise<Response> {
  let lastErr: unknown = null;
  for (const path of paths) {
    try {
      const res = await fetch(path, init);
      if (res.ok) return res;
      lastErr = new Error(`Request to ${path} failed with HTTP ${res.status}`);
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

/**
 * Upload audio blob to transcribe speech to text using Sarvam Saaras model
 */
export async function transcribeAudio(
  audioBlob: Blob,
  languageCode?: string
): Promise<{ transcript: string; languageCode?: string }> {
  const formData = new FormData();
  formData.append("file", audioBlob, "recording.webm");
  if (languageCode && languageCode !== "en-US") {
    formData.append("language_code", normalizeForSarvam(languageCode));
  }

  const res = await requestWithFallbacks(
    ["/sarvam/stt", "/api/sarvam/stt"],
    {
      method: "POST",
      body: formData,
    }
  );

  const data = await res.json();
  return {
    transcript: data.transcript || "",
    languageCode: data.language_code,
  };
}

/**
 * Translate text between English and Indian languages using Sarvam Mayura model
 */
export async function translateText(
  text: string,
  sourceLanguageCode: string,
  targetLanguageCode: string
): Promise<string> {
  const src = normalizeForSarvam(sourceLanguageCode);
  const tgt = normalizeForSarvam(targetLanguageCode);

  if (src === tgt || !text.trim()) {
    return text;
  }

  const res = await requestWithFallbacks(
    ["/sarvam/translate", "/api/sarvam/translate"],
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        source_language_code: src,
        target_language_code: tgt,
      }),
    }
  );

  const data = await res.json();
  return data.translated_text || text;
}

/**
 * Synthesize speech from text using Sarvam Bulbul model
 */
export async function synthesizeSpeech(
  text: string,
  languageCode: string = "en-IN",
  speaker: string = "meera"
): Promise<{ audioBase64: string; audioUrl: string }> {
  const lang = normalizeForSarvam(languageCode);

  const res = await requestWithFallbacks(
    ["/sarvam/tts", "/api/sarvam/tts"],
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        language_code: lang,
        speaker,
      }),
    }
  );

  const data = await res.json();
  const base64 = data.audio_base64 || (data.audios && data.audios[0]) || "";
  const audioUrl = `data:audio/wav;base64,${base64}`;
  return { audioBase64: base64, audioUrl };
}
