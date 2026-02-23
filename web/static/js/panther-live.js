/**
 * PANTHER Live — Voice Assistant Overlay (Embedded)
 *
 * Fixed implementation based on reference gemini-live-assistant project:
 *  - Continuous PCM streaming (not VAD-batched)
 *  - Proper turn signaling (turnComplete only on silence)
 *  - Raw Int16 PCM base64 encoding (no WAV wrapper)
 *
 * Exposes: window.PantherLive.open() / window.PantherLive.close()
 */

(function () {
  'use strict';

  /* ══════════════════════════════════════════════════════════
     DOM References
  ══════════════════════════════════════════════════════════ */
  const $ = id => document.getElementById(id);
  const el = {
    overlay:       $('vaOverlay'),
    backdrop:      $('vaBackdrop'),
    closeBtn:      $('vaCloseBtn'),
    agentBadge:    $('vaAgentBadge'),
    agentName:     $('vaAgentName'),
    particleCanvas:$('vaParticleCanvas'),
    statusText:    $('vaStatusText'),
    transcript:    $('vaTranscript'),
    transcriptText:$('vaTranscriptText'),
    response:      $('vaResponse'),
    responseText:  $('vaResponseText'),
    timeoutWarn:   $('vaTimeoutWarning'),
    stayActiveBtn: $('vaStayActiveBtn'),
    micBtn:        $('vaMicBtn'),
    micIcon:       $('vaMicIcon'),
    micLabel:      $('vaMicLabel'),
    error:         $('vaError'),
  };

  /* ══════════════════════════════════════════════════════════
     State
  ══════════════════════════════════════════════════════════ */
  let micOn = false;
  let isOpen = false;
  let assistantState = 'idle';
  let apiKey = '';
  let geminiWs = null;
  let audioContext = null;
  let micStream = null;
  let micProcessor = null;
  let bubbleInitialized = false;
  let wsReady = false;

  // Idle timeout refs
  let warningTimer = null;
  let closeTimer = null;

  // VAD state for turn detection
  const SILENCE_THRESHOLD = 0.015;
  const SILENCE_AFTER_SPEECH_MS = 1200; // how long silence before sending turnComplete
  let isSpeaking = false;
  let silenceStart = 0;
  let turnCompleteSent = true; // start as true (no pending turn)

  // Audio playback queue (like reference project)
  let playbackQueue = [];
  let isPlaying = false;

  // ── Agent integration state ──────────────────────────────────────
  let agentSessionId = null;        // Voice session ID (created on first command)
  let transcriptBuffer = '';        // Accumulates Gemini text within one turn
  let isProcessingAgent = false;    // Prevent overlapping agent calls
  let pendingConfirmation = null;   // Stores pending destructive action

  const MIC_ON_PATH = 'M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.49 6-3.31 6-6.72h-1.7z';
  const MIC_OFF_PATH = 'M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3z';

  /* ══════════════════════════════════════════════════════════
     1. Agent Router
  ══════════════════════════════════════════════════════════ */
  const SYSTEM_PROMPT = `You are PANTHER, an advanced conversational voice AI assistant.

RULES:
- Be concise, helpful, and conversational. Respond in 1-3 sentences unless asked for detail.
- Match the user's energy and speaking pace.
- Quick answer: 1-3 sentences. Standard response: 2-4 sentences.
- Avoid preambles like "That's a great question!" or "Certainly!"
- Use natural connectors: "So...", "I see", "Got it...", "Alright..."
- Be warm and natural, not robotic.
- If uncertain, say so briefly. Never hallucinate.
- If corrected: "You're right, [correct info]."`;

  /* ══════════════════════════════════════════════════════════
     2. Three.js Particle Bubble
  ══════════════════════════════════════════════════════════ */
  const STATE_CONFIG = {
    idle:                    { primaryColor: 0xFF9A3C, speed: 0.3, turbulence: 0.02, spread: 2.0 },
    listening:               { primaryColor: 0xFF6B35, speed: 1.5, turbulence: 0.15, spread: 2.8 },
    speaking:                { primaryColor: 0xFFAA5C, speed: 1.0, turbulence: 0.08, spread: 2.4 },
    processing:              { primaryColor: 0xFFCC80, speed: 0.7, turbulence: 0.05, spread: 2.2 },
    'agent-processing':      { primaryColor: 0x9C27B0, speed: 1.2, turbulence: 0.12, spread: 2.6 },
    'awaiting-confirmation': { primaryColor: 0xFF9800, speed: 0.8, turbulence: 0.10, spread: 2.4 },
    'timeout-warning':       { primaryColor: 0xFF4444, speed: 0.5, turbulence: 0.03, spread: 2.0 },
  };
  const PARTICLE_COUNT = 2500;
  let bubbleAnimId = null;

  function initParticleBubble() {
    if (bubbleInitialized) return;
    if (typeof THREE === 'undefined') { console.warn('Three.js not loaded'); return; }
    const mount = el.particleCanvas;
    const w = mount.clientWidth, h = mount.clientHeight;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, w / h, 0.1, 100);
    camera.position.z = 5;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);

    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const origPositions = new Float32Array(PARTICLE_COUNT * 3);
    const phases = new Float32Array(PARTICLE_COUNT);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 1.5 + (Math.random() - 0.5) * 0.6;
      const x = r * Math.sin(phi) * Math.cos(theta);
      const y = r * Math.sin(phi) * Math.sin(theta);
      const z = r * Math.cos(phi);
      positions[i * 3] = x;  positions[i * 3 + 1] = y;  positions[i * 3 + 2] = z;
      origPositions[i * 3] = x;  origPositions[i * 3 + 1] = y;  origPositions[i * 3 + 2] = z;
      phases[i] = Math.random() * Math.PI * 2;
    }
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.PointsMaterial({
      size: 0.04, color: 0xFF9A3C, transparent: true, opacity: 0.85,
      blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    const glowGeo = new THREE.SphereGeometry(1.3, 32, 32);
    const glowMat = new THREE.MeshBasicMaterial({ color: 0xFF9A3C, transparent: true, opacity: 0.06, side: THREE.BackSide });
    scene.add(new THREE.Mesh(glowGeo, glowMat));

    let time = 0;

    function animate() {
      if (!isOpen) { bubbleAnimId = null; return; }
      bubbleAnimId = requestAnimationFrame(animate);
      const cfg = STATE_CONFIG[assistantState] || STATE_CONFIG.idle;
      time += 0.01 * cfg.speed;

      material.color.set(cfg.primaryColor);
      const pos = geometry.attributes.position.array;
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const ox = origPositions[i * 3], oy = origPositions[i * 3 + 1], oz = origPositions[i * 3 + 2];
        const phase = phases[i];
        const breathe = 1.0 + 0.08 * Math.sin(time * 1.2 + phase);
        pos[i * 3]     = ox * breathe * (cfg.spread / 2.0) + cfg.turbulence * Math.sin(time * 2.3 + phase);
        pos[i * 3 + 1] = oy * breathe * (cfg.spread / 2.0) + cfg.turbulence * Math.cos(time * 1.7 + phase * 0.8);
        pos[i * 3 + 2] = oz * breathe * (cfg.spread / 2.0) + cfg.turbulence * Math.sin(time * 2.0 + phase * 1.2);
      }
      geometry.attributes.position.needsUpdate = true;
      particles.rotation.y += 0.002 * cfg.speed;
      particles.rotation.x += 0.001 * cfg.speed;
      glowMat.opacity = 0.04 + 0.04 * Math.sin(time * 1.5);
      glowMat.color.set(cfg.primaryColor);
      renderer.render(scene, camera);
    }

    function startBubble() {
      if (!bubbleAnimId) bubbleAnimId = requestAnimationFrame(animate);
    }

    window._pantherBubbleStart = startBubble;

    window.addEventListener('resize', () => {
      const nw = mount.clientWidth, nh = mount.clientHeight;
      if (nw && nh) {
        camera.aspect = nw / nh;
        camera.updateProjectionMatrix();
        renderer.setSize(nw, nh);
      }
    });

    bubbleInitialized = true;
    startBubble();
  }

  /* ══════════════════════════════════════════════════════════
     3. Gemini Live WebSocket — FIXED
     
     Key fixes from reference project:
     - Stream raw Int16 PCM continuously via realtimeInput
     - Only send clientContent.turnComplete after silence
     - Don't batch/wrap audio in WAV
     - Use response_modalities: ["AUDIO"] for voice
  ══════════════════════════════════════════════════════════ */
  const GEMINI_WS_URL = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent';

  function connectGeminiWS() {
    if (geminiWs && geminiWs.readyState === WebSocket.OPEN) return;
    if (!apiKey) { showError('No Google API key configured. Set it in Settings.'); return; }

    console.log('[Panther Live] Connecting to Gemini WS...');
    geminiWs = new WebSocket(`${GEMINI_WS_URL}?key=${apiKey}`);
    wsReady = false;

    geminiWs.onopen = () => {
      console.log('[Panther Live] WS connected, sending setup...');
      // Setup message — modeled after reference project's _build_config
      const setupMsg = {
        setup: {
          model: 'models/gemini-2.5-flash-native-audio-latest',
          generationConfig: {
            responseModalities: ['AUDIO'],
            speechConfig: {
              voiceConfig: {
                prebuiltVoiceConfig: { voiceName: 'Puck' }
              }
            }
          },
          systemInstruction: {
            parts: [{ text: SYSTEM_PROMPT }]
          }
        }
      };
      geminiWs.send(JSON.stringify(setupMsg));
    };

    geminiWs.onmessage = async (event) => {
      try {
        const raw = event.data instanceof Blob ? await event.data.text() : event.data;
        const data = JSON.parse(raw);

        // Setup complete
        if (data.setupComplete) {
          wsReady = true;
          console.log('[Panther Live] Setup complete — ready for audio');
          return;
        }

        // Model response (audio/text)
        if (data.serverContent?.modelTurn?.parts) {
          for (const part of data.serverContent.modelTurn.parts) {
            if (part.text) {
              console.log('[Panther Live] AI text:', part.text);
              transcriptBuffer += part.text;
              setResponse(part.text);
            }
            if (part.inlineData?.mimeType?.startsWith('audio/')) {
              setState('speaking');
              queueAudioPlayback(part.inlineData.data);
            }
          }
        }

        // Turn complete — route transcript to agent
        if (data.serverContent?.turnComplete) {
          console.log('[Panther Live] Turn complete');
          const transcript = transcriptBuffer.trim();
          transcriptBuffer = '';

          // Route the transcript through the agent pipeline
          if (transcript) {
            routeTranscript(transcript);
          }

          // Wait for audio queue to drain, then switch to listening
          waitForAudioDrain(() => {
            if (!isProcessingAgent) {
              if (micOn) setState('listening');
              else setState('idle');
            }
          });
        }
      } catch (err) {
        console.error('[Panther Live] WS message error:', err);
      }
    };

    geminiWs.onerror = (err) => {
      console.error('[Panther Live] WS error:', err);
      showError('Gemini connection error. Check API key & network.');
      wsReady = false;
    };

    geminiWs.onclose = (ev) => {
      console.log('[Panther Live] WS closed:', ev.code, ev.reason);
      wsReady = false;
    };
  }

  /**
   * Send raw Int16 PCM audio as base64 via realtimeInput.
   * This is called continuously as audio is captured — no batching.
   */
  function streamAudioChunk(int16Array) {
    if (!geminiWs || geminiWs.readyState !== WebSocket.OPEN || !wsReady) return;

    const base64 = arrayBufferToBase64(int16Array.buffer);
    geminiWs.send(JSON.stringify({
      realtimeInput: {
        mediaChunks: [{
          mimeType: 'audio/pcm;rate=16000',
          data: base64
        }]
      }
    }));
  }

  /**
   * NOTE: Turn detection is handled server-side by the native audio model.
   * We do NOT send clientContent.turnComplete manually — the model detects
   * when the user stops speaking via its own VAD.
   */

  /* ══════════════════════════════════════════════════════════
     4. Audio Playback Queue (from reference project)
     Plays audio chunks sequentially using AudioContext.
  ══════════════════════════════════════════════════════════ */
  let playbackContext = null;

  function queueAudioPlayback(base64Audio) {
    playbackQueue.push(base64Audio);
    if (!isPlaying) processPlaybackQueue();
  }

  async function processPlaybackQueue() {
    if (isPlaying) return;
    if (playbackQueue.length === 0) {
      isPlaying = false;
      return;
    }

    isPlaying = true;
    const base64Audio = playbackQueue.shift();

    try {
      if (!playbackContext) {
        playbackContext = new AudioContext({ sampleRate: 24000 });
      }
      if (playbackContext.state === 'suspended') {
        await playbackContext.resume();
      }

      // Decode base64 → Int16 PCM → Float32 (24kHz output from Gemini)
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const pcm16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768.0;
      }

      const buffer = playbackContext.createBuffer(1, float32.length, 24000);
      buffer.getChannelData(0).set(float32);

      const source = playbackContext.createBufferSource();
      source.buffer = buffer;
      source.connect(playbackContext.destination);

      source.onended = () => {
        isPlaying = false;
        processPlaybackQueue();
      };

      source.start(0);
    } catch (e) {
      console.error('[Panther Live] Playback error:', e);
      isPlaying = false;
      processPlaybackQueue();
    }
  }

  function waitForAudioDrain(callback) {
    if (playbackQueue.length === 0 && !isPlaying) {
      callback();
    } else {
      setTimeout(() => waitForAudioDrain(callback), 200);
    }
  }

  function clearPlaybackQueue() {
    playbackQueue = [];
    isPlaying = false;
  }

  /* ══════════════════════════════════════════════════════════
     5. Microphone — Continuous Streaming + VAD for Turn Detection
     
     Key difference from before:
     - Audio is streamed CONTINUOUSLY to Gemini (every ScriptProcessor callback)
     - VAD only controls when to send turnComplete (not when to send audio)
  ══════════════════════════════════════════════════════════ */
  async function startMic() {
    try {
      audioContext = new AudioContext({ sampleRate: 16000 });

      // Resume if needed (Chrome autoplay policy)
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      const source = audioContext.createMediaStreamSource(micStream);
      micProcessor = audioContext.createScriptProcessor(512, 1, 1); // small buffer for low latency

      micProcessor.onaudioprocess = (e) => {
        if (!micOn || !wsReady) return;

        const floatSamples = e.inputBuffer.getChannelData(0);

        // Convert Float32 → Int16 PCM (what Gemini expects)
        const int16 = floatTo16BitPCM(floatSamples);

        // Stream EVERY chunk to Gemini continuously
        streamAudioChunk(int16);

        // VAD: detect speech/silence for turn signaling
        let energy = 0;
        for (let i = 0; i < floatSamples.length; i++) {
          energy += floatSamples[i] * floatSamples[i];
        }
        energy = Math.sqrt(energy / floatSamples.length);

        if (energy > SILENCE_THRESHOLD) {
          // User is speaking — update UI
          if (!isSpeaking) {
            isSpeaking = true;
            setState('listening');
            resetIdleTimer();
          }
          silenceStart = 0;
        } else {
          // Silence — update UI only (model handles turn detection)
          if (isSpeaking) {
            if (!silenceStart) silenceStart = Date.now();
            if (Date.now() - silenceStart > SILENCE_AFTER_SPEECH_MS) {
              isSpeaking = false;
              // Don't send turnComplete — model handles this
              // Just show processing state so user knows we're waiting
              setState('processing');
              resetIdleTimer();
            }
          }
        }
      };

      source.connect(micProcessor);
      micProcessor.connect(audioContext.destination);
      console.log('[Panther Live] Mic started, streaming audio');
    } catch (err) {
      console.error('[Panther Live] Mic error:', err);
      showError('Microphone access denied. Please allow mic permissions.');
      micOn = false;
      updateMicUI();
    }
  }

  function stopMic() {
    if (micProcessor) { micProcessor.disconnect(); micProcessor = null; }
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (audioContext) { audioContext.close().catch(() => {}); audioContext = null; }
    isSpeaking = false;
    silenceStart = 0;
  }

  /**
   * Convert Float32 audio samples to Int16 PCM (ArrayBuffer).
   * Matches reference project's floatTo16BitPCM.
   */
  function floatTo16BitPCM(float32Array) {
    const int16 = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16;
  }

  /**
   * Convert ArrayBuffer to base64 string.
   * Matches reference project's arrayBufferToBase64.
   */
  function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  /* ══════════════════════════════════════════════════════════
     6. Idle Timeout Manager
  ══════════════════════════════════════════════════════════ */
  function resetIdleTimer() {
    clearIdleTimer();
    if (!micOn) return;
    warningTimer = setTimeout(() => {
      setState('timeout-warning');
      el.timeoutWarn.classList.add('visible');
      closeTimer = setTimeout(() => closeOverlay(), 5000);
    }, 30000);
  }

  function clearIdleTimer() {
    if (warningTimer) { clearTimeout(warningTimer); warningTimer = null; }
    if (closeTimer)   { clearTimeout(closeTimer);   closeTimer = null; }
    el.timeoutWarn.classList.remove('visible');
  }

  /* ══════════════════════════════════════════════════════════
     7. UI Helpers
  ══════════════════════════════════════════════════════════ */
  function setState(s) {
    assistantState = s;
    const map = {
      idle: 'Click the mic to start',
      listening: '🎤 Listening...',
      processing: '⚡ Thinking...',
      speaking: '🔊 Speaking...',
      'timeout-warning': '⏱️ Still there?'
    };
    el.statusText.textContent = map[s] || '';
  }

  function setResponse(text) {
    el.responseText.textContent = text;
    el.response.classList.add('visible');
  }

  function showError(msg) {
    el.error.textContent = msg;
    el.error.classList.add('visible');
    setTimeout(() => el.error.classList.remove('visible'), 5000);
  }

  function updateMicUI() {
    el.micBtn.classList.toggle('on', micOn);
    el.micBtn.classList.toggle('pulse', micOn && assistantState === 'listening');
    el.micIcon.innerHTML = micOn ? `<path d="${MIC_ON_PATH}"/>` : `<path d="${MIC_OFF_PATH}"/>`;
    el.micLabel.textContent = micOn ? 'Listening' : 'Tap to Speak';
  }

  /* ══════════════════════════════════════════════════════════
     8. Open / Close / Toggle
  ══════════════════════════════════════════════════════════ */
  function openOverlay() {
    if (isOpen) return;
    isOpen = true;
    el.overlay.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    setState('idle');
    el.transcript.classList.remove('visible');
    el.response.classList.remove('visible');
    el.agentBadge.classList.remove('visible');

    // Reset agent state for new overlay session
    agentSessionId = null;
    transcriptBuffer = '';
    isProcessingAgent = false;
    pendingConfirmation = null;

    initParticleBubble();
    if (window._pantherBubbleStart) window._pantherBubbleStart();

    if (!apiKey) fetchApiKey();
  }

  function closeOverlay() {
    if (!isOpen) return;
    isOpen = false;
    micOn = false;
    updateMicUI();
    stopMic();
    clearIdleTimer();
    clearPlaybackQueue();

    // Close agent session (fire-and-forget)
    if (agentSessionId) {
      fetch(`/api/voice-session/${agentSessionId}/close`, { method: 'POST' })
        .catch(() => {});
      agentSessionId = null;
    }

    if (geminiWs) { geminiWs.close(); geminiWs = null; wsReady = false; }
    if (playbackContext) {
      playbackContext.close().catch(() => {});
      playbackContext = null;
    }
    el.overlay.style.display = 'none';
    document.body.style.overflow = '';
  }

  async function toggleMic() {
    if (!micOn) {
      micOn = true;
      updateMicUI();
      setState('listening');
      await startMic();

      // Connect Gemini WS proactively
      if (!geminiWs || geminiWs.readyState !== WebSocket.OPEN) {
        connectGeminiWS();
      }
      resetIdleTimer();
    } else {
      micOn = false;
      updateMicUI();
      setState('idle');
      stopMic();
      clearIdleTimer();
    }
  }

  async function fetchApiKey() {
    try {
      const res = await fetch('/api/google-key');
      const data = await res.json();
      apiKey = data.key || '';
      if (!apiKey) showError('No Google API key set. Configure it in Settings.');
    } catch (err) {
      showError('Failed to fetch API key from server.');
    }
  }

  /* ══════════════════════════════════════════════════════════
     9. Agent Integration — Voice → Backend Pipeline
  ══════════════════════════════════════════════════════════ */

  /**
   * Route a Gemini transcript to the backend or handle confirmation.
   */
  async function routeTranscript(transcript) {
    // Handle pending confirmation response ("yes" / "cancel")
    if (pendingConfirmation) {
      await handleConfirmationResponse(transcript);
      return;
    }

    // Very short utterances (≤3 words) stay in Gemini Live
    const wordCount = transcript.trim().split(/\s+/).length;
    if (wordCount <= 3) {
      console.log('[Panther Live] Short utterance — staying in Gemini Live');
      return;
    }

    // Don't overlap concurrent agent calls
    if (isProcessingAgent) {
      console.warn('[Panther Live] Agent already processing — ignoring');
      return;
    }

    // Route to backend AgentOrchestrator
    console.log('[Panther Live] Routing to agent:', transcript.slice(0, 60));
    await callVoiceCommandAPI(transcript);
  }

  /**
   * POST transcript to /api/voice-command, consume SSE stream.
   */
  async function callVoiceCommandAPI(text, confirmed = false) {
    isProcessingAgent = true;
    setState('agent-processing');
    setStatusText('🧠 Processing with PANTHER agent...');

    try {
      const response = await fetch('/api/voice-command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          session_id: agentSessionId,
          confirmed,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      await consumeSSEStream(response);

    } catch (err) {
      console.error('[Panther Live] API call failed:', err);
      showError('Connection error. Please try again.');
    } finally {
      isProcessingAgent = false;
      if (micOn) setState('listening');
      else setState('idle');
    }
  }

  /**
   * Consume SSE events from /api/voice-command response.
   */
  async function consumeSSEStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop(); // Keep incomplete trailing chunk

      for (const eventStr of events) {
        if (!eventStr.trim()) continue;

        const lines = eventStr.split('\n');
        const eventType = lines.find(l => l.startsWith('event:'))?.slice(7).trim();
        const dataLine  = lines.find(l => l.startsWith('data:'))?.slice(5).trim();
        if (!eventType || !dataLine) continue;

        let data;
        try { data = JSON.parse(dataLine); }
        catch { continue; }

        switch (eventType) {
          case 'session':
            agentSessionId = data.session_id;
            console.log('[Panther Live] Agent session:', data.session_id);
            break;

          case 'progress':
            setStatusText(data.message);
            break;

          case 'chunk':
            // Streamed agent response chunk
            appendResponse(data.text);
            break;

          case 'confirmation_required':
            await handleConfirmationGate(data);
            return; // Stop consuming — new stream after confirm

          case 'result':
            setResponse(data.text);
            console.log(`[Panther Live] Agent result (${data.intent}):`, data.text.slice(0, 100));
            break;

          case 'summary':
            // Speak short summary via Gemini TTS
            speakSummary(data.text);
            break;

          case 'error':
            showError(data.message);
            speakSummary('I ran into an issue. ' + data.message);
            break;

          case 'done':
            syncSidebarSessions();
            break;
        }
      }
    }
  }

  /**
   * Append text to the response area (for streaming chunks).
   */
  function appendResponse(text) {
    if (el.responseText && el.response) {
      el.response.classList.add('visible');
      el.responseText.textContent += text;
    }
  }

  /**
   * Handle confirmation gate for destructive actions.
   */
  async function handleConfirmationGate(data) {
    pendingConfirmation = data;
    setState('awaiting-confirmation');
    setStatusText('⚠️ ' + data.prompt);
    setResponse(data.prompt);

    // Speak confirmation prompt via Gemini
    speakSummary(data.prompt);
  }

  /**
   * Handle user's confirmation response ("yes" / "cancel").
   */
  async function handleConfirmationResponse(transcript) {
    const response = transcript.toLowerCase().trim();
    const yesWords = ['yes', 'yeah', 'yep', 'confirm', 'proceed', 'ok', 'okay', 'do it', 'go ahead'];

    if (yesWords.some(w => response.includes(w))) {
      const pending = pendingConfirmation;
      pendingConfirmation = null;
      console.log('[Panther Live] Confirmed:', pending.original_text);
      await callVoiceCommandAPI(pending.original_text, true);
    } else {
      pendingConfirmation = null;
      setStatusText('Cancelled.');
      speakSummary('Okay, I cancelled that.');
      if (micOn) setState('listening');
      else setState('idle');
    }
  }

  /**
   * Speak a summary text via Gemini Live (send as text input for TTS).
   */
  function speakSummary(text) {
    if (!text || !geminiWs || geminiWs.readyState !== WebSocket.OPEN || !wsReady) {
      console.log('[Panther Live] Cannot speak summary — WS not ready');
      return;
    }
    // Send text as realtimeInput text for the model to speak aloud
    geminiWs.send(JSON.stringify({
      clientContent: {
        turns: [{
          role: 'user',
          parts: [{ text: `Please read this aloud naturally: "${text}"` }],
        }],
        turnComplete: true,
      },
    }));
  }

  /**
   * Refresh the sidebar session list so voice sessions appear.
   */
  function syncSidebarSessions() {
    if (typeof window.refreshSessionList === 'function') {
      window.refreshSessionList();
    } else if (window.chatWS?.readyState === WebSocket.OPEN) {
      window.chatWS.send(JSON.stringify({ type: 'list_sessions' }));
    }
    console.log('[Panther Live] Sidebar sessions synced');
  }

  /* ══════════════════════════════════════════════════════════
     10. Event Listeners
  ══════════════════════════════════════════════════════════ */
  el.micBtn.addEventListener('click', toggleMic);
  el.closeBtn.addEventListener('click', closeOverlay);
  el.backdrop.addEventListener('click', closeOverlay);
  el.stayActiveBtn.addEventListener('click', () => {
    el.timeoutWarn.classList.remove('visible');
    resetIdleTimer();
    setState('listening');
  });

  window.addEventListener('keydown', (e) => {
    if (!isOpen) return;
    if (e.key === 'Escape') closeOverlay();
    if (e.key === ' ' && e.ctrlKey) { e.preventDefault(); toggleMic(); }
  });

  /* ══════════════════════════════════════════════════════════
     11. Public API
  ══════════════════════════════════════════════════════════ */
  window.PantherLive = { open: openOverlay, close: closeOverlay };

  console.log('[Panther Live] Module loaded (agent integration)');
})();
