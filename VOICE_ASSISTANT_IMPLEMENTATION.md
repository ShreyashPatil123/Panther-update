# 🎙️ PANTHER01 — Voice Assistant Implementation Guide

> A fully integrated, multi-agent voice assistant overlay powered by **Gemini Live**, **Three.js** particle effects, **Voice Activity Detection (VAD)**, and intelligent **agent routing** — all built on top of your existing PANTHER01 infrastructure.

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites & Dependencies](#prerequisites--dependencies)
3. [File Structure](#file-structure)
4. [Core Components](#core-components)
   - [VoiceAssistantOverlay](#1-voiceassistantoverlay-component)
   - [Three.js Particle Bubble](#2-threejs-particle-bubble)
   - [Voice Activity Detection (VAD)](#3-voice-activity-detection-vad)
   - [Gemini Live Integration](#4-gemini-live-integration)
   - [Agent Router](#5-agent-router)
   - [Idle Timeout Manager](#6-idle-timeout-manager)
5. [Full Implementation Code](#full-implementation-code)
6. [Agent Routing Table](#agent-routing-table)
7. [Environment Variables](#environment-variables)
8. [Triggering the Overlay](#triggering-the-overlay)
9. [Customization Guide](#customization-guide)
10. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
User clicks "Voice Assistant" button
          │
          ▼
┌─────────────────────────────────────────────┐
│         VoiceAssistantOverlay (fullscreen)  │
│                                             │
│  ┌──────────────┐   ┌─────────────────────┐ │
│  │ Three.js     │   │  Controls           │ │
│  │ Particle     │   │  ┌───────────────┐  │ │
│  │ Bubble       │   │  │ 🎤 Mic Toggle │  │ │
│  │ (orange)     │   │  └───────────────┘  │ │
│  │              │   │  ┌───────────────┐  │ │
│  │  ● ● ●  ●   │   │  │  ✕  Close     │  │ │
│  │ ●   ●  ● ●  │   │  └───────────────┘  │ │
│  │  ●  ●●  ●   │   └─────────────────────┘ │
│  └──────────────┘                           │
└─────────────────────────────────────────────┘
          │
          ▼
   VAD (Voice Activity Detection)
   [Silero VAD via @ricky0123/vad-react]
          │
    ┌─────┴──────┐
    │  Speech    │  No Speech
    │  Detected  │  ──► Idle Timeout
    ▼            ▼
 Gemini Live   Timeout Warning
 WebSocket     ──► Auto Close
    │
    ▼
Agent Router  (classifies intent)
    │
    ├── 🧠 gemini-1.5-pro      → Complex reasoning / general QA
    ├── ⚡ gemini-1.5-flash     → Fast responses / chitchat
    ├── 🔍 gemini-1.5-pro      → Code / technical help
    ├── 📄 gemini-1.5-flash    → Document summarization
    ├── 🌐 Grounding tool      → Web search / real-time data
    └── 🛠️  Custom agents       → (your existing agents)
```

---

## Prerequisites & Dependencies

### Install Required Packages

```bash
# Core audio & VAD
npm install @ricky0123/vad-react @ricky0123/vad-web onnxruntime-web

# Three.js for particle effects
npm install three @types/three

# Gemini AI SDK
npm install @google/generative-ai

# Optional: audio worklet polyfill
npm install standardized-audio-context
```

### Peer Dependencies (verify these are in your project)

```bash
npm install react react-dom
```

---

## File Structure

Add the following files to your existing project:

```
src/
├── components/
│   └── VoiceAssistant/
│       ├── index.tsx                    ← Main overlay component
│       ├── ParticleBubble.tsx           ← Three.js animated bubble
│       ├── MicButton.tsx                ← Mic toggle with animation
│       ├── useVAD.ts                    ← Voice Activity Detection hook
│       ├── useGeminiLive.ts             ← Gemini Live WebSocket hook
│       ├── useIdleTimeout.ts            ← Idle/timeout management
│       ├── agentRouter.ts               ← Multi-agent intent classifier
│       └── voiceAssistant.css           ← Overlay styles
└── utils/
    └── audioUtils.ts                    ← Audio helper functions
```

---

## Core Components

---

### 1. `VoiceAssistantOverlay` Component

**File:** `src/components/VoiceAssistant/index.tsx`

```tsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import ParticleBubble from './ParticleBubble';
import MicButton from './MicButton';
import { useVAD } from './useVAD';
import { useGeminiLive } from './useGeminiLive';
import { useIdleTimeout } from './useIdleTimeout';
import './voiceAssistant.css';

interface VoiceAssistantOverlayProps {
  onClose: () => void;
  apiKey: string; // Pass from your existing env config
}

type AssistantState = 'idle' | 'listening' | 'processing' | 'speaking' | 'timeout-warning';

const VoiceAssistantOverlay: React.FC<VoiceAssistantOverlayProps> = ({ onClose, apiKey }) => {
  const [micOn, setMicOn] = useState(false);
  const [assistantState, setAssistantState] = useState<AssistantState>('idle');
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [showTimeoutWarning, setShowTimeoutWarning] = useState(false);
  const audioContextRef = useRef<AudioContext | null>(null);

  // Initialize Gemini Live
  const { sendAudio, stopSession, isConnected, agentName } = useGeminiLive({
    apiKey,
    onResponse: (text) => {
      setResponse(text);
      setAssistantState('speaking');
    },
    onSpeechEnd: () => {
      setAssistantState(micOn ? 'listening' : 'idle');
    },
  });

  // VAD Hook
  const { startListening, stopListening, isSpeaking } = useVAD({
    enabled: micOn,
    onSpeechStart: () => {
      setAssistantState('listening');
      resetIdleTimer();
    },
    onSpeechEnd: async (audioBlob) => {
      setAssistantState('processing');
      resetIdleTimer();
      await sendAudio(audioBlob);
    },
    onTranscript: (text) => setTranscript(text),
  });

  // Idle Timeout
  const { resetIdleTimer, clearIdleTimer } = useIdleTimeout({
    warningTimeout: 25_000,   // 25s → show warning
    closeTimeout: 30_000,     // 30s → auto-close
    processingTimeout: 60_000, // 60s → timeout if Gemini hangs
    onWarning: () => {
      setShowTimeoutWarning(true);
      setAssistantState('timeout-warning');
    },
    onTimeout: () => {
      handleClose();
    },
    active: micOn,
  });

  // Mic toggle
  const toggleMic = useCallback(async () => {
    if (!micOn) {
      // Initialize AudioContext on first user gesture
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }
      if (audioContextRef.current.state === 'suspended') {
        await audioContextRef.current.resume();
      }
      setMicOn(true);
      setAssistantState('listening');
      startListening();
      resetIdleTimer();
    } else {
      setMicOn(false);
      setAssistantState('idle');
      stopListening();
      clearIdleTimer();
      setShowTimeoutWarning(false);
    }
  }, [micOn, startListening, stopListening, resetIdleTimer, clearIdleTimer]);

  // Close handler — stops everything cleanly
  const handleClose = useCallback(() => {
    stopListening();
    stopSession();
    clearIdleTimer();
    setMicOn(false);
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    onClose();
  }, [stopListening, stopSession, clearIdleTimer, onClose]);

  // Keyboard shortcut: Escape to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
      if (e.key === ' ' && e.ctrlKey) toggleMic(); // Ctrl+Space to toggle mic
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleClose, toggleMic]);

  const bubbleState = isSpeaking
    ? 'user-speaking'
    : assistantState === 'speaking'
    ? 'assistant-speaking'
    : assistantState === 'processing'
    ? 'processing'
    : 'idle';

  return (
    <div className="va-overlay" role="dialog" aria-modal="true" aria-label="Voice Assistant">
      {/* Background blur layer */}
      <div className="va-backdrop" onClick={handleClose} />

      {/* Main panel */}
      <div className="va-panel">
        {/* Close button */}
        <button
          className="va-close-btn"
          onClick={handleClose}
          aria-label="Close voice assistant"
          title="Close (Esc)"
        >
          ✕
        </button>

        {/* Agent label */}
        {agentName && (
          <div className="va-agent-badge">
            <span className="va-agent-dot" />
            {agentName}
          </div>
        )}

        {/* Three.js Particle Bubble */}
        <ParticleBubble state={bubbleState} />

        {/* Status text */}
        <div className="va-status-text">
          {assistantState === 'idle' && !micOn && 'Click the mic to start'}
          {assistantState === 'listening' && '🎤 Listening...'}
          {assistantState === 'processing' && '⚡ Thinking...'}
          {assistantState === 'speaking' && '🔊 Speaking...'}
          {assistantState === 'timeout-warning' && '⏱️ Still there?'}
        </div>

        {/* Transcript */}
        {transcript && (
          <div className="va-transcript" aria-live="polite">
            <span className="va-label">You:</span> {transcript}
          </div>
        )}

        {/* Response */}
        {response && (
          <div className="va-response" aria-live="polite">
            <span className="va-label">PANTHER:</span> {response}
          </div>
        )}

        {/* Timeout warning */}
        {showTimeoutWarning && (
          <div className="va-timeout-warning">
            Closing in a few seconds... <button onClick={() => {
              setShowTimeoutWarning(false);
              resetIdleTimer();
              setAssistantState('listening');
            }}>Stay Active</button>
          </div>
        )}

        {/* Mic toggle button */}
        <MicButton
          isOn={micOn}
          isListening={assistantState === 'listening'}
          isProcessing={assistantState === 'processing'}
          onClick={toggleMic}
        />

        {/* Keyboard hints */}
        <div className="va-hints">
          <kbd>Ctrl</kbd>+<kbd>Space</kbd> toggle mic &nbsp;·&nbsp; <kbd>Esc</kbd> close
        </div>
      </div>
    </div>
  );
};

export default VoiceAssistantOverlay;
```

---

### 2. Three.js Particle Bubble

**File:** `src/components/VoiceAssistant/ParticleBubble.tsx`

```tsx
import React, { useRef, useEffect } from 'react';
import * as THREE from 'three';

type BubbleState = 'idle' | 'user-speaking' | 'assistant-speaking' | 'processing';

interface ParticleBubbleProps {
  state: BubbleState;
}

// Color palette — light orange family
const STATE_CONFIG: Record<BubbleState, {
  primaryColor: number;
  secondaryColor: number;
  speed: number;
  turbulence: number;
  spread: number;
}> = {
  idle:               { primaryColor: 0xFF9A3C, secondaryColor: 0xFFBF69, speed: 0.3,  turbulence: 0.02, spread: 2.0 },
  'user-speaking':    { primaryColor: 0xFF6B35, secondaryColor: 0xFFD166, speed: 1.5,  turbulence: 0.15, spread: 2.8 },
  'assistant-speaking': { primaryColor: 0xFFAA5C, secondaryColor: 0xFFC87A, speed: 1.0, turbulence: 0.08, spread: 2.4 },
  processing:         { primaryColor: 0xFFCC80, secondaryColor: 0xFFE0B2, speed: 0.7,  turbulence: 0.05, spread: 2.2 },
};

const PARTICLE_COUNT = 2500;

const ParticleBubble: React.FC<ParticleBubbleProps> = ({ state }) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    particles: THREE.Points;
    geometry: THREE.BufferGeometry;
    animFrameId: number;
  } | null>(null);
  const stateRef = useRef<BubbleState>(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    if (!mountRef.current) return;

    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight;

    // Scene setup
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 100);
    camera.position.z = 5;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    mountRef.current.appendChild(renderer.domElement);

    // Create particle geometry (sphere distribution)
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const originalPositions = new Float32Array(PARTICLE_COUNT * 3);
    const colors = new Float32Array(PARTICLE_COUNT * 3);
    const sizes = new Float32Array(PARTICLE_COUNT);
    const phases = new Float32Array(PARTICLE_COUNT); // random phase for animation

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      // Distribute particles on a sphere surface with some depth variation
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 1.5 + (Math.random() - 0.5) * 0.6; // slight depth variation

      const x = r * Math.sin(phi) * Math.cos(theta);
      const y = r * Math.sin(phi) * Math.sin(theta);
      const z = r * Math.cos(phi);

      positions[i * 3]     = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;
      originalPositions[i * 3]     = x;
      originalPositions[i * 3 + 1] = y;
      originalPositions[i * 3 + 2] = z;

      // Warm orange gradient
      colors[i * 3]     = 1.0;
      colors[i * 3 + 1] = 0.6 + Math.random() * 0.3;
      colors[i * 3 + 2] = 0.1 + Math.random() * 0.2;

      sizes[i] = 2 + Math.random() * 3;
      phases[i] = Math.random() * Math.PI * 2;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    // Custom shader material for soft glowing particles
    const material = new THREE.ShaderMaterial({
      uniforms: {
        time: { value: 0 },
        primaryColor: { value: new THREE.Color(0xFF9A3C) },
        secondaryColor: { value: new THREE.Color(0xFFBF69) },
      },
      vertexShader: `
        attribute float size;
        attribute vec3 color;
        varying vec3 vColor;
        uniform float time;

        void main() {
          vColor = color;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (300.0 / -mvPosition.z);
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        uniform vec3 primaryColor;

        void main() {
          float dist = length(gl_PointCoord - vec2(0.5));
          if (dist > 0.5) discard;
          float alpha = 1.0 - smoothstep(0.3, 0.5, dist);
          gl_FragColor = vec4(vColor * primaryColor * 1.4, alpha * 0.85);
        }
      `,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      vertexColors: true,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    // Ambient glow sphere (behind particles)
    const glowGeo = new THREE.SphereGeometry(1.3, 32, 32);
    const glowMat = new THREE.MeshBasicMaterial({
      color: 0xFF9A3C,
      transparent: true,
      opacity: 0.06,
      side: THREE.BackSide,
    });
    const glowMesh = new THREE.Mesh(glowGeo, glowMat);
    scene.add(glowMesh);

    let time = 0;

    const animate = () => {
      const animFrameId = requestAnimationFrame(animate);
      if (sceneRef.current) sceneRef.current.animFrameId = animFrameId;

      const cfg = STATE_CONFIG[stateRef.current];
      time += 0.01 * cfg.speed;

      // Update colors
      (material.uniforms.primaryColor.value as THREE.Color).set(cfg.primaryColor);
      (material.uniforms.secondaryColor.value as THREE.Color).set(cfg.secondaryColor);
      material.uniforms.time.value = time;

      // Animate particle positions — breathing + turbulence
      const pos = geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const ox = originalPositions[i * 3];
        const oy = originalPositions[i * 3 + 1];
        const oz = originalPositions[i * 3 + 2];

        const phase = phases[i];
        const breathe = 1.0 + 0.08 * Math.sin(time * 1.2 + phase);
        const turbX = cfg.turbulence * Math.sin(time * 2.3 + phase);
        const turbY = cfg.turbulence * Math.cos(time * 1.7 + phase * 0.8);
        const turbZ = cfg.turbulence * Math.sin(time * 2.0 + phase * 1.2);

        pos[i * 3]     = ox * breathe * (cfg.spread / 2.0) + turbX;
        pos[i * 3 + 1] = oy * breathe * (cfg.spread / 2.0) + turbY;
        pos[i * 3 + 2] = oz * breathe * (cfg.spread / 2.0) + turbZ;
      }
      geometry.attributes.position.needsUpdate = true;

      // Slow rotation
      particles.rotation.y += 0.002 * cfg.speed;
      particles.rotation.x += 0.001 * cfg.speed;

      // Glow pulse
      glowMat.opacity = 0.04 + 0.04 * Math.sin(time * 1.5);

      renderer.render(scene, camera);
    };

    animate();

    const handleResize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    sceneRef.current = { renderer, scene, camera, particles, geometry, animFrameId: 0 };

    return () => {
      window.removeEventListener('resize', handleResize);
      if (sceneRef.current) {
        cancelAnimationFrame(sceneRef.current.animFrameId);
      }
      renderer.dispose();
      geometry.dispose();
      material.dispose();
      if (mountRef.current && renderer.domElement.parentNode === mountRef.current) {
        mountRef.current.removeChild(renderer.domElement);
      }
    };
  }, []); // Only run once

  return <div ref={mountRef} className="va-particle-canvas" aria-hidden="true" />;
};

export default ParticleBubble;
```

---

### 3. Voice Activity Detection (VAD)

**File:** `src/components/VoiceAssistant/useVAD.ts`

```ts
import { useEffect, useRef, useState, useCallback } from 'react';

// Using @ricky0123/vad-web with Silero VAD model (ONNX)
// This gives frame-level voice detection without sending audio to any server

interface VADOptions {
  enabled: boolean;
  onSpeechStart?: () => void;
  onSpeechEnd?: (audioBlob: Blob) => void;
  onTranscript?: (text: string) => void;
  silenceDuration?: number;    // ms of silence before speech-end fires (default: 700ms)
  speechPadding?: number;      // ms of audio to keep before/after speech (default: 300ms)
  minSpeechDuration?: number;  // discard clips shorter than this ms (default: 250ms)
}

export const useVAD = ({
  enabled,
  onSpeechStart,
  onSpeechEnd,
  onTranscript,
  silenceDuration = 700,
  speechPadding = 300,
  minSpeechDuration = 250,
}: VADOptions) => {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const vadRef = useRef<any>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioChunksRef = useRef<Float32Array[]>([]);
  const speechStartTimeRef = useRef<number>(0);

  const stopListening = useCallback(() => {
    if (vadRef.current) {
      vadRef.current.pause?.();
      vadRef.current.destroy?.();
      vadRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setIsSpeaking(false);
  }, []);

  const startListening = useCallback(async () => {
    try {
      // Dynamically import VAD to avoid SSR issues
      const { MicVAD } = await import('@ricky0123/vad-web');

      streamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      vadRef.current = await MicVAD.new({
        stream: streamRef.current,

        // Silero VAD configuration
        positiveSpeechThreshold: 0.6,   // confidence to start speech detection
        negativeSpeechThreshold: 0.35,  // confidence to end speech detection
        minSpeechFrames: 4,             // minimum frames for valid speech
        preSpeechPadFrames: Math.floor(speechPadding / 10),
        redemptionFrames: Math.floor(silenceDuration / 10),

        onSpeechStart: () => {
          setIsSpeaking(true);
          speechStartTimeRef.current = Date.now();
          audioChunksRef.current = [];
          onSpeechStart?.();
        },

        onSpeechEnd: (audio: Float32Array) => {
          setIsSpeaking(false);
          const duration = Date.now() - speechStartTimeRef.current;

          // Discard very short clips (likely noise)
          if (duration < minSpeechDuration) return;

          // Convert Float32Array (16kHz PCM) to WAV Blob
          const wavBlob = float32ToWav(audio, 16000);
          onSpeechEnd?.(wavBlob);
        },

        onVADMisfire: () => {
          // False positive — reset
          setIsSpeaking(false);
          audioChunksRef.current = [];
        },

        workletURL: '/vad.worklet.bundle.min.js',  // copy from node_modules/@ricky0123/vad-web/dist/
        modelURL: '/silero_vad.onnx',               // copy from node_modules/@ricky0123/vad-web/dist/
        ortConfig: (ort: any) => {
          ort.env.wasm.wasmPaths = '/';             // serve WASM from public root
        },
      });

      vadRef.current.start();
    } catch (err) {
      console.error('[PANTHER VAD] Failed to start:', err);
    }
  }, [onSpeechStart, onSpeechEnd, silenceDuration, speechPadding, minSpeechDuration]);

  useEffect(() => {
    if (enabled) {
      startListening();
    } else {
      stopListening();
    }
    return () => stopListening();
  }, [enabled]);

  return { startListening, stopListening, isSpeaking };
};

// ─── Audio Utilities ─────────────────────────────────────────────────────────

function float32ToWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}
```

---

### 4. Gemini Live Integration

**File:** `src/components/VoiceAssistant/useGeminiLive.ts`

```ts
import { useRef, useState, useCallback, useEffect } from 'react';
import { agentRouter, type AgentIntent } from './agentRouter';

interface GeminiLiveOptions {
  apiKey: string;
  onResponse: (text: string) => void;
  onSpeechEnd: () => void;
  onError?: (error: Error) => void;
}

interface GeminiLiveHook {
  sendAudio: (audioBlob: Blob) => Promise<void>;
  sendText: (text: string) => Promise<void>;
  stopSession: () => void;
  isConnected: boolean;
  agentName: string | null;
}

// Gemini Live API endpoint (Multimodal Live API)
const GEMINI_LIVE_ENDPOINT = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent';

export const useGeminiLive = ({
  apiKey,
  onResponse,
  onSpeechEnd,
  onError,
}: GeminiLiveOptions): GeminiLiveHook => {
  const wsRef = useRef<WebSocket | null>(null);
  const audioQueueRef = useRef<Blob[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [agentName, setAgentName] = useState<string | null>(null);
  const currentModelRef = useRef<string>('gemini-2.0-flash-exp');
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const intentHistoryRef = useRef<AgentIntent[]>([]);

  const connectWebSocket = useCallback((model: string, systemInstruction: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = `${GEMINI_LIVE_ENDPOINT}?key=${apiKey}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);

      // Send setup message
      ws.send(JSON.stringify({
        setup: {
          model: `models/${model}`,
          generationConfig: {
            responseModalities: ['AUDIO', 'TEXT'],
            speechConfig: {
              voiceConfig: {
                prebuiltVoiceConfig: { voiceName: 'Puck' }, // Natural voice
              },
            },
          },
          systemInstruction: {
            parts: [{ text: systemInstruction }],
          },
          tools: [{ googleSearch: {} }], // Enable grounding for web search agents
        },
      }));
    };

    ws.onmessage = async (event) => {
      try {
        const data = JSON.parse(
          event.data instanceof Blob ? await event.data.text() : event.data
        );

        // Handle setup complete
        if (data.setupComplete) {
          // Process any queued audio
          while (audioQueueRef.current.length > 0) {
            const blob = audioQueueRef.current.shift()!;
            sendAudioToWS(blob);
          }
        }

        // Handle server content (audio/text response)
        if (data.serverContent?.modelTurn?.parts) {
          for (const part of data.serverContent.modelTurn.parts) {
            if (part.text) {
              onResponse(part.text);
            }
            if (part.inlineData?.mimeType?.startsWith('audio/')) {
              playBase64Audio(part.inlineData.data, part.inlineData.mimeType);
            }
          }
        }

        // Handle turn complete
        if (data.serverContent?.turnComplete) {
          onSpeechEnd();
        }

      } catch (err) {
        console.error('[PANTHER Gemini Live] Parse error:', err);
      }
    };

    ws.onerror = (err) => {
      console.error('[PANTHER Gemini Live] WebSocket error:', err);
      onError?.(new Error('Gemini Live connection error'));
      setIsConnected(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
    };
  }, [apiKey, onResponse, onSpeechEnd, onError]);

  const sendAudioToWS = useCallback((audioBlob: Blob) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    const reader = new FileReader();
    reader.onloadend = () => {
      const base64 = (reader.result as string).split(',')[1];
      wsRef.current?.send(JSON.stringify({
        realtimeInput: {
          mediaChunks: [{
            mimeType: 'audio/pcm;rate=16000',
            data: base64,
          }],
        },
      }));

      // Signal end of user turn
      wsRef.current?.send(JSON.stringify({
        clientContent: {
          turns: [],
          turnComplete: true,
        },
      }));
    };
    reader.readAsDataURL(audioBlob);
  }, []);

  const sendAudio = useCallback(async (audioBlob: Blob) => {
    // Convert WAV to PCM for Gemini Live (it expects raw PCM)
    const pcmBlob = await wavToPcm(audioBlob);

    // Route to correct agent based on transcript
    // Note: We'll re-route once we have the transcript; for now use the PCM directly
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      // Queue it and connect
      audioQueueRef.current.push(pcmBlob);
      const { model, systemPrompt, intentName } = agentRouter.getDefaultAgent();
      setAgentName(intentName);
      connectWebSocket(model, systemPrompt);
    } else {
      sendAudioToWS(pcmBlob);
    }
  }, [connectWebSocket, sendAudioToWS]);

  const sendText = useCallback(async (text: string) => {
    // Route to the correct agent
    const { model, systemPrompt, intentName } = await agentRouter.route(text);
    setAgentName(intentName);

    // Reconnect with correct model if it changed
    if (model !== currentModelRef.current || wsRef.current?.readyState !== WebSocket.OPEN) {
      currentModelRef.current = model;
      wsRef.current?.close();
      connectWebSocket(model, systemPrompt);
      await new Promise(r => setTimeout(r, 500)); // brief wait for connection
    }

    wsRef.current?.send(JSON.stringify({
      clientContent: {
        turns: [{
          role: 'user',
          parts: [{ text }],
        }],
        turnComplete: true,
      },
    }));
  }, [connectWebSocket]);

  const stopSession = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
    setAgentName(null);
    audioQueueRef.current = [];
  }, []);

  const playBase64Audio = (base64: string, mimeType: string) => {
    const audioData = atob(base64);
    const arrayBuffer = new ArrayBuffer(audioData.length);
    const uint8Array = new Uint8Array(arrayBuffer);
    for (let i = 0; i < audioData.length; i++) uint8Array[i] = audioData.charCodeAt(i);
    const blob = new Blob([arrayBuffer], { type: mimeType });
    const url = URL.createObjectURL(blob);

    if (!audioPlayerRef.current) audioPlayerRef.current = new Audio();
    audioPlayerRef.current.src = url;
    audioPlayerRef.current.play().catch(console.error);
    audioPlayerRef.current.onended = () => URL.revokeObjectURL(url);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      audioPlayerRef.current?.pause();
    };
  }, []);

  return { sendAudio, sendText, stopSession, isConnected, agentName };
};

// Convert WAV blob to raw PCM blob for Gemini Live
async function wavToPcm(wavBlob: Blob): Promise<Blob> {
  const arrayBuffer = await wavBlob.arrayBuffer();
  // Strip 44-byte WAV header → raw PCM
  const pcmBuffer = arrayBuffer.slice(44);
  return new Blob([pcmBuffer], { type: 'audio/pcm' });
}
```

---

### 5. Agent Router

**File:** `src/components/VoiceAssistant/agentRouter.ts`

> ⚠️ **IMPORTANT**: Replace the model names below with the exact model identifiers already configured in your PANTHER01 project's agent definitions. Check your existing agent config files and use the same model strings to ensure API key compatibility and consistent behavior.

```ts
export interface AgentIntent {
  intentName: string;
  model: string;
  systemPrompt: string;
  confidence: number;
}

interface AgentConfig {
  model: string;
  systemPrompt: string;
  intentName: string;
}

// ─────────────────────────────────────────────────────────────
// AGENT DEFINITIONS
// Map each intent to the model already used by that agent in PANTHER01.
// Cross-reference with your existing agent configuration files.
// ─────────────────────────────────────────────────────────────
const AGENT_CONFIGS: Record<string, AgentConfig> = {

  // General knowledge & complex reasoning → your primary reasoning agent
  // Replace 'gemini-2.0-flash-exp' with your project's configured model string
  'general': {
    model: 'gemini-2.0-flash-exp',
    intentName: '🧠 General Assistant',
    systemPrompt: `You are PANTHER, an intelligent voice assistant. 
    Be concise, helpful, and conversational. Respond in 1-3 sentences 
    unless asked for detail. Always use the user's language.`,
  },

  // Fast/chitchat → your flash/lightweight agent
  'chitchat': {
    model: 'gemini-2.0-flash-exp',       // ← Replace with your fast-response agent model
    intentName: '⚡ Quick Response',
    systemPrompt: `You are PANTHER in casual mode. Give short, friendly, 
    witty responses. Keep it under 2 sentences. Be conversational.`,
  },

  // Code help → your code/technical agent
  'code': {
    model: 'gemini-2.0-flash-exp',        // ← Replace with your code agent model
    intentName: '💻 Code Assistant',
    systemPrompt: `You are PANTHER's code assistant. Explain code concisely 
    for voice. Avoid code blocks — describe logic verbally. 
    Focus on the key concept in 2-3 sentences.`,
  },

  // Document / text analysis → your document agent
  'document': {
    model: 'gemini-2.0-flash-exp',        // ← Replace with your document agent model
    intentName: '📄 Document Agent',
    systemPrompt: `You are PANTHER's document agent. Summarize and explain 
    documents clearly for voice output. Be precise and structured.`,
  },

  // Web search / real-time info → grounding agent
  'search': {
    model: 'gemini-2.0-flash-exp',        // ← Replace with your search/grounding agent model
    intentName: '🌐 Search Agent',
    systemPrompt: `You are PANTHER's search agent. Use Google Search grounding 
    to answer with up-to-date information. Cite sources briefly at the end.`,
  },

  // Math / calculations → your math agent
  'math': {
    model: 'gemini-2.0-flash-exp',        // ← Replace with your math agent model
    intentName: '🔢 Math Agent',
    systemPrompt: `You are PANTHER's math assistant. Solve problems step by step, 
    but describe steps verbally for voice. Give the final answer clearly.`,
  },

  // Creative writing / generation
  'creative': {
    model: 'gemini-2.0-flash-exp',        // ← Replace with your creative agent model
    intentName: '✍️ Creative Agent',
    systemPrompt: `You are PANTHER's creative assistant. Generate imaginative, 
    engaging content. For voice, keep responses under 4 sentences unless asked for more.`,
  },

  // Task / productivity management
  'task': {
    model: 'gemini-2.0-flash-exp',        // ← Replace with your task-management agent model
    intentName: '📋 Task Manager',
    systemPrompt: `You are PANTHER's task and productivity assistant. 
    Help with scheduling, to-dos, reminders, and planning. 
    Confirm actions clearly and briefly.`,
  },
};

// ─────────────────────────────────────────────────────────────
// Intent Detection — keyword-based first pass, then Gemini classification
// ─────────────────────────────────────────────────────────────
const INTENT_KEYWORDS: Record<string, string[]> = {
  code: ['code', 'function', 'debug', 'error', 'syntax', 'program', 'script',
         'python', 'javascript', 'typescript', 'html', 'css', 'api', 'bug', 'fix'],
  math: ['calculate', 'math', 'equation', 'solve', 'multiply', 'divide',
         'percent', 'formula', 'number', 'sum', 'average', '+', '-', '×', '÷'],
  search: ['latest', 'current', 'today', 'news', 'weather', 'price',
           'who is', 'what happened', 'recent', 'now', 'live'],
  document: ['summarize', 'summary', 'document', 'article', 'read',
             'text', 'paragraph', 'explain this', 'what does this say'],
  creative: ['write', 'create', 'generate', 'story', 'poem', 'essay',
             'imagine', 'design', 'draft', 'compose'],
  task: ['remind', 'schedule', 'todo', 'task', 'plan', 'meeting',
         'appointment', 'calendar', 'set a', 'add to'],
  chitchat: ['hello', 'hi', 'hey', 'how are you', 'what\'s up',
             'thanks', 'thank you', 'bye', 'goodbye', 'cool', 'nice'],
};

class AgentRouter {
  private apiKey: string | null = null;

  init(apiKey: string) {
    this.apiKey = apiKey;
  }

  getDefaultAgent(): AgentConfig & { intentName: string } {
    return AGENT_CONFIGS['general'];
  }

  async route(text: string): Promise<AgentConfig & { intentName: string }> {
    const normalized = text.toLowerCase().trim();

    // Fast keyword-based routing (no API call)
    for (const [intent, keywords] of Object.entries(INTENT_KEYWORDS)) {
      if (keywords.some(kw => normalized.includes(kw))) {
        const cfg = AGENT_CONFIGS[intent] ?? AGENT_CONFIGS['general'];
        console.log(`[PANTHER Router] Intent: ${intent} → ${cfg.intentName}`);
        return cfg;
      }
    }

    // If no keyword match and text is long enough, classify via Gemini Flash
    if (text.length > 15 && this.apiKey) {
      try {
        const intent = await this.classifyWithGemini(text);
        const cfg = AGENT_CONFIGS[intent] ?? AGENT_CONFIGS['general'];
        console.log(`[PANTHER Router] Classified: ${intent} → ${cfg.intentName}`);
        return cfg;
      } catch (e) {
        console.warn('[PANTHER Router] Classification failed, using general agent');
      }
    }

    return AGENT_CONFIGS['general'];
  }

  private async classifyWithGemini(text: string): Promise<string> {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=${this.apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{
            parts: [{
              text: `Classify this query into exactly ONE category. Reply with only the category word.

Categories: code, math, search, document, creative, task, chitchat, general

Query: "${text}"

Category:`,
            }],
          }],
          generationConfig: {
            maxOutputTokens: 10,
            temperature: 0.1,
          },
        }),
      }
    );

    const data = await response.json();
    const result = data.candidates?.[0]?.content?.parts?.[0]?.text?.trim().toLowerCase();
    return Object.keys(AGENT_CONFIGS).includes(result) ? result : 'general';
  }
}

export const agentRouter = new AgentRouter();
```

---

### 6. Idle Timeout Manager

**File:** `src/components/VoiceAssistant/useIdleTimeout.ts`

```ts
import { useRef, useCallback, useEffect } from 'react';

interface IdleTimeoutOptions {
  warningTimeout: number;    // ms before showing warning (e.g. 25_000)
  closeTimeout: number;      // ms before auto-closing (e.g. 30_000)
  processingTimeout: number; // ms timeout for API response (e.g. 60_000)
  onWarning: () => void;
  onTimeout: () => void;
  active: boolean;           // only run when mic is on
}

export const useIdleTimeout = ({
  warningTimeout,
  closeTimeout,
  processingTimeout,
  onWarning,
  onTimeout,
  active,
}: IdleTimeoutOptions) => {
  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const processingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearIdleTimer = useCallback(() => {
    if (warningTimerRef.current) clearTimeout(warningTimerRef.current);
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    warningTimerRef.current = null;
    closeTimerRef.current = null;
  }, []);

  const clearProcessingTimer = useCallback(() => {
    if (processingTimerRef.current) clearTimeout(processingTimerRef.current);
    processingTimerRef.current = null;
  }, []);

  const resetIdleTimer = useCallback(() => {
    if (!active) return;
    clearIdleTimer();

    warningTimerRef.current = setTimeout(() => {
      onWarning();
      // After warning, give user a few more seconds
      closeTimerRef.current = setTimeout(onTimeout, closeTimeout - warningTimeout);
    }, warningTimeout);
  }, [active, warningTimeout, closeTimeout, onWarning, onTimeout, clearIdleTimer]);

  const startProcessingTimer = useCallback(() => {
    clearProcessingTimer();
    processingTimerRef.current = setTimeout(() => {
      console.warn('[PANTHER] Processing timeout hit');
      onTimeout();
    }, processingTimeout);
  }, [processingTimeout, onTimeout, clearProcessingTimer]);

  // Start timer when activated
  useEffect(() => {
    if (active) {
      resetIdleTimer();
    } else {
      clearIdleTimer();
      clearProcessingTimer();
    }
    return () => {
      clearIdleTimer();
      clearProcessingTimer();
    };
  }, [active]);

  return { resetIdleTimer, clearIdleTimer, startProcessingTimer, clearProcessingTimer };
};
```

---

### 7. Mic Button Component

**File:** `src/components/VoiceAssistant/MicButton.tsx`

```tsx
import React from 'react';

interface MicButtonProps {
  isOn: boolean;
  isListening: boolean;
  isProcessing: boolean;
  onClick: () => void;
}

const MicButton: React.FC<MicButtonProps> = ({ isOn, isListening, isProcessing, onClick }) => {
  return (
    <button
      className={`va-mic-btn ${isOn ? 'va-mic-on' : 'va-mic-off'} ${isListening ? 'va-mic-pulse' : ''} ${isProcessing ? 'va-mic-busy' : ''}`}
      onClick={onClick}
      aria-label={isOn ? 'Turn microphone off' : 'Turn microphone on'}
      aria-pressed={isOn}
      disabled={isProcessing}
      title={isOn ? 'Click to mute (Ctrl+Space)' : 'Click to speak (Ctrl+Space)'}
    >
      <svg viewBox="0 0 24 24" fill="currentColor" width="28" height="28">
        {isOn ? (
          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.49 6-3.31 6-6.72h-1.7z"/>
        ) : (
          <>
            <path d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3z"/>
          </>
        )}
      </svg>
      <span className="va-mic-label">
        {isProcessing ? 'Thinking...' : isOn ? 'Listening' : 'Tap to Speak'}
      </span>
    </button>
  );
};

export default MicButton;
```

---

### 8. CSS Styles

**File:** `src/components/VoiceAssistant/voiceAssistant.css`

```css
/* ─── Overlay ─────────────────────────────────────────────────── */
.va-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: va-fade-in 0.3s ease;
}

@keyframes va-fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.va-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(10, 5, 0, 0.85);
  backdrop-filter: blur(12px) saturate(0.8);
}

/* ─── Panel ────────────────────────────────────────────────────── */
.va-panel {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding: 48px 40px;
  width: min(560px, 90vw);
  animation: va-slide-up 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes va-slide-up {
  from { transform: translateY(40px) scale(0.95); opacity: 0; }
  to   { transform: translateY(0) scale(1); opacity: 1; }
}

/* ─── Close Button ─────────────────────────────────────────────── */
.va-close-btn {
  position: absolute;
  top: 16px;
  right: 20px;
  background: rgba(255, 154, 60, 0.12);
  border: 1px solid rgba(255, 154, 60, 0.3);
  color: rgba(255, 200, 140, 0.9);
  width: 40px;
  height: 40px;
  border-radius: 50%;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.va-close-btn:hover {
  background: rgba(255, 100, 50, 0.3);
  color: #fff;
  transform: scale(1.1);
}

/* ─── Agent Badge ──────────────────────────────────────────────── */
.va-agent-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 154, 60, 0.1);
  border: 1px solid rgba(255, 154, 60, 0.25);
  color: rgba(255, 190, 120, 0.9);
  border-radius: 20px;
  padding: 4px 14px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.3px;
}

.va-agent-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #FF9A3C;
  animation: va-pulse 1.5s ease-in-out infinite;
}

/* ─── Particle Canvas ──────────────────────────────────────────── */
.va-particle-canvas {
  width: 280px;
  height: 280px;
  border-radius: 50%;
  overflow: hidden;
  filter: drop-shadow(0 0 40px rgba(255, 154, 60, 0.4));
  transition: filter 0.5s ease;
}

/* ─── Status Text ──────────────────────────────────────────────── */
.va-status-text {
  color: rgba(255, 200, 160, 0.8);
  font-size: 15px;
  font-weight: 400;
  letter-spacing: 0.5px;
  min-height: 22px;
  text-align: center;
}

/* ─── Transcript & Response ────────────────────────────────────── */
.va-transcript,
.va-response {
  max-width: 460px;
  text-align: center;
  font-size: 14px;
  line-height: 1.6;
  border-radius: 12px;
  padding: 10px 16px;
  animation: va-fade-in 0.3s ease;
}

.va-transcript {
  color: rgba(255, 220, 180, 0.7);
  background: rgba(255, 154, 60, 0.06);
  border: 1px solid rgba(255, 154, 60, 0.1);
}

.va-response {
  color: rgba(255, 240, 220, 0.9);
  background: rgba(255, 154, 60, 0.1);
  border: 1px solid rgba(255, 154, 60, 0.2);
}

.va-label {
  font-weight: 600;
  color: rgba(255, 154, 60, 0.9);
  margin-right: 6px;
}

/* ─── Timeout Warning ──────────────────────────────────────────── */
.va-timeout-warning {
  background: rgba(255, 120, 30, 0.15);
  border: 1px solid rgba(255, 120, 30, 0.4);
  border-radius: 10px;
  padding: 10px 18px;
  color: rgba(255, 200, 140, 0.9);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 12px;
  animation: va-pulse-border 1s ease infinite;
}

.va-timeout-warning button {
  background: rgba(255, 154, 60, 0.3);
  border: 1px solid rgba(255, 154, 60, 0.5);
  color: #fff;
  border-radius: 6px;
  padding: 4px 12px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.2s;
}

.va-timeout-warning button:hover {
  background: rgba(255, 154, 60, 0.5);
}

/* ─── Mic Button ───────────────────────────────────────────────── */
.va-mic-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 90px;
  height: 90px;
  border-radius: 50%;
  border: 2px solid rgba(255, 154, 60, 0.4);
  background: rgba(255, 154, 60, 0.08);
  color: rgba(255, 190, 120, 0.9);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: relative;
}

.va-mic-btn svg { flex-shrink: 0; }

.va-mic-label {
  position: absolute;
  bottom: -26px;
  font-size: 11px;
  white-space: nowrap;
  color: rgba(255, 190, 120, 0.6);
  letter-spacing: 0.3px;
}

.va-mic-on {
  background: rgba(255, 120, 40, 0.2);
  border-color: rgba(255, 120, 40, 0.7);
  color: #fff;
  box-shadow: 0 0 0 0 rgba(255, 120, 40, 0.5);
}

.va-mic-pulse {
  animation: va-mic-ripple 1.4s ease infinite;
}

.va-mic-btn:hover:not(:disabled) {
  transform: scale(1.08);
  background: rgba(255, 120, 40, 0.25);
  border-color: rgba(255, 120, 40, 0.8);
}

.va-mic-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}

/* ─── Hints ────────────────────────────────────────────────────── */
.va-hints {
  color: rgba(255, 180, 100, 0.3);
  font-size: 11px;
  letter-spacing: 0.4px;
  margin-top: 8px;
}

kbd {
  display: inline-block;
  background: rgba(255, 154, 60, 0.1);
  border: 1px solid rgba(255, 154, 60, 0.2);
  border-radius: 4px;
  padding: 1px 6px;
  font-family: monospace;
  font-size: 10px;
}

/* ─── Animations ───────────────────────────────────────────────── */
@keyframes va-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.5; transform: scale(0.8); }
}

@keyframes va-mic-ripple {
  0%   { box-shadow: 0 0 0 0 rgba(255, 120, 40, 0.5); }
  70%  { box-shadow: 0 0 0 18px rgba(255, 120, 40, 0); }
  100% { box-shadow: 0 0 0 0 rgba(255, 120, 40, 0); }
}

@keyframes va-pulse-border {
  0%, 100% { border-color: rgba(255, 120, 30, 0.4); }
  50%       { border-color: rgba(255, 120, 30, 0.8); }
}

/* ─── Responsive ───────────────────────────────────────────────── */
@media (max-width: 480px) {
  .va-panel { padding: 32px 20px; gap: 18px; }
  .va-particle-canvas { width: 220px; height: 220px; }
  .va-mic-btn { width: 76px; height: 76px; }
}
```

---

## Full Implementation Code

### Triggering the Overlay

Add this to your main app or any component where you want the trigger button:

```tsx
// In your main App.tsx or layout
import React, { useState } from 'react';
import VoiceAssistantOverlay from './components/VoiceAssistant';
import { agentRouter } from './components/VoiceAssistant/agentRouter';

// Initialize the router with your existing API key
// Use the SAME key that your existing PANTHER01 agents use
agentRouter.init(process.env.NEXT_PUBLIC_GEMINI_API_KEY!);

function App() {
  const [showVoiceAssistant, setShowVoiceAssistant] = useState(false);

  return (
    <>
      {/* Your existing PANTHER01 UI ... */}

      {/* Trigger Button — place anywhere in your UI */}
      <button
        onClick={() => setShowVoiceAssistant(true)}
        className="panther-voice-trigger"
        aria-label="Open Voice Assistant"
        title="Voice Assistant"
      >
        🎙️ PANTHER Voice
      </button>

      {/* Voice Assistant Overlay */}
      {showVoiceAssistant && (
        <VoiceAssistantOverlay
          onClose={() => setShowVoiceAssistant(false)}
          apiKey={process.env.NEXT_PUBLIC_GEMINI_API_KEY!}
        />
      )}
    </>
  );
}
```

---

## Agent Routing Table

| Intent | Trigger Keywords (examples) | Model to Use | Notes |
|---|---|---|---|
| `general` | (default / unmatched) | Your primary reasoning model | Fallback for all queries |
| `chitchat` | hello, thanks, bye, hi | Your fast/flash model | Prioritize low latency |
| `code` | debug, function, error, python, API | Your code agent model | May need code execution tool |
| `math` | calculate, percent, equation, solve | Your math/precise model | Low temperature |
| `search` | latest, today, news, current, weather | Your search/grounding model | Enable `googleSearch` tool |
| `document` | summarize, explain, article, text | Your document agent model | Long context recommended |
| `creative` | write, generate, story, poem | Your creative model | Higher temperature |
| `task` | remind, schedule, todo, meeting | Your task agent model | May integrate with calendar |

> 🔁 **Cross-reference**: Open your existing agent config files (e.g., `agents.config.ts`, `panther.config.json`, or similar) and match each row's "Model to Use" to the exact `model` string defined there.

---

## Environment Variables

These should already exist in your `.env` / `.env.local` file from your current PANTHER01 setup. **Do not create new keys** — reuse the ones already configured:

```env
# ─── Already in your PANTHER01 project ───────────────────────────
NEXT_PUBLIC_GEMINI_API_KEY=your_existing_gemini_api_key

# ─── Optional: separate keys per agent (if your project uses them)
NEXT_PUBLIC_GEMINI_FLASH_KEY=...
NEXT_PUBLIC_GEMINI_PRO_KEY=...

# ─── Voice Assistant Feature Flag (optional)
NEXT_PUBLIC_ENABLE_VOICE_ASSISTANT=true
```

---

## Static Assets (Required for VAD)

Copy the following files from `node_modules/@ricky0123/vad-web/dist/` into your `public/` directory. This is required for the VAD Web Worker and ONNX model to load:

```bash
# Run this after npm install
cp node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js public/
cp node_modules/@ricky0123/vad-web/dist/silero_vad.onnx public/
cp node_modules/onnxruntime-web/dist/*.wasm public/
```

Or add this to your `package.json` scripts:

```json
{
  "scripts": {
    "copy-vad-assets": "cp node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js public/ && cp node_modules/@ricky0123/vad-web/dist/silero_vad.onnx public/ && cp node_modules/onnxruntime-web/dist/*.wasm public/",
    "postinstall": "npm run copy-vad-assets"
  }
}
```

---

## Timeout Behavior Reference

| Scenario | Timer | Action |
|---|---|---|
| Mic on, user idle | 25s | Show "Still there?" warning + pulsing border |
| After warning shown | +5s (30s total) | Auto-close overlay, stop mic |
| Gemini API no response | 60s | Timeout + close (prevents infinite hang) |
| User speaks | Any time | Reset all idle timers |
| User clicks "Stay Active" | — | Reset timers, dismiss warning |
| Processing completes | — | Clear processing timer, restart idle timer |

---

## Additional Suggested Improvements

### Suggested: Speech-to-Text Transcript Display

While Gemini Live handles the audio → response pipeline, adding a **local Whisper.js transcript** gives users visual confirmation of what was heard before Gemini responds:

```ts
// Optional: use openai/whisper-webgpu for local STT transcript
import { pipeline } from '@xenova/transformers';
const transcriber = await pipeline('automatic-speech-recognition', 'Xenova/whisper-tiny.en');
const result = await transcriber(audioBuffer);
setTranscript(result.text);
```

### Suggested: Audio Visualizer Ring

Add a second Three.js ring outside the bubble that pulses with microphone audio amplitude, giving real-time volume feedback beyond just the VAD trigger.

### Suggested: Conversation History

Keep a `messages[]` array per session so users can scroll back through the voice conversation log, with timestamps and agent labels.

### Suggested: Accessibility Mode

Add a `?va=text` URL mode that swaps audio for text input/output for users who prefer or require it, reusing all the same agent routing logic.

### Suggested: Haptic Feedback (Mobile)

```ts
// Trigger vibration when mic starts/stops (mobile only)
if (navigator.vibrate) {
  navigator.vibrate(isOn ? [50] : [30, 50, 30]);
}
```

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| Microphone permission denied | Browser blocked mic | Check browser permissions; serve over HTTPS |
| VAD not detecting speech | WASM/ONNX not in `public/` | Run `copy-vad-assets` script |
| Gemini WebSocket fails to connect | Invalid API key or network | Verify `NEXT_PUBLIC_GEMINI_API_KEY` value |
| Particles don't render | Three.js not installed | `npm install three @types/three` |
| No audio output | AudioContext suspended | Toggle mic to trigger user gesture; AudioContext resumes automatically |
| "Processing" state stuck | Gemini timeout | Processing timer at 60s will auto-close; check API quota |
| VAD fires on non-speech | Threshold too low | Increase `positiveSpeechThreshold` to `0.75` |
| Agent always uses "general" | Keywords not matching | Add more keywords to `INTENT_KEYWORDS` or check classifier logs |

---

## Quick Start Checklist

- [ ] `npm install three @types/three @ricky0123/vad-web @ricky0123/vad-web onnxruntime-web`
- [ ] Copy VAD WASM/ONNX assets to `public/`
- [ ] Create all files from **File Structure** section above
- [ ] Update `agentRouter.ts` with your existing project's model strings
- [ ] Verify `NEXT_PUBLIC_GEMINI_API_KEY` is set in `.env.local`
- [ ] Import `agentRouter.init(apiKey)` in your app entry point
- [ ] Add `<VoiceAssistantOverlay>` and trigger button to your layout
- [ ] Test mic permissions in browser
- [ ] Test VAD by speaking and watching particle bubble react
- [ ] Verify agent routing via browser console logs

---

*Guide generated for PANTHER01 — Voice Assistant Integration v1.0*
