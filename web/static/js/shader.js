/**
 * PANTHER — Animated Shader Background
 * Exact GLSL from 21st.dev "animated-shader-background" by @thanh.
 *
 * Uses WebGL2 (GLSL 300 es) for native tanh() support.
 * Falls back to WebGL1 with an inline tanh polyfill if WebGL2 is unavailable.
 */

(function () {
  'use strict';

  /* ────────────────────────────────────────────────────────
     GLSL 300 es  (WebGL 2)
  ──────────────────────────────────────────────────────── */
  const VERT2 = `#version 300 es
    in vec2 position;
    void main() { gl_Position = vec4(position, 0.0, 1.0); }
  `;

  const FRAG2 = `#version 300 es
    precision highp float;

    uniform float iTime;
    uniform vec2  iResolution;

    out vec4 fragColor;

    #define NUM_OCTAVES 3

    float rand(vec2 n) {
      return fract(sin(dot(n, vec2(12.9898, 4.1414))) * 43758.5453);
    }
    float noise(vec2 p) {
      vec2 ip = floor(p);
      vec2 u  = fract(p);
      u = u * u * (3.0 - 2.0 * u);
      float res = mix(
        mix(rand(ip),               rand(ip + vec2(1.0,0.0)), u.x),
        mix(rand(ip + vec2(0.0,1.0)), rand(ip + vec2(1.0,1.0)), u.x), u.y);
      return res * res;
    }
    float fbm(vec2 x) {
      float v = 0.0, a = 0.3;
      vec2  shift = vec2(100.0);
      mat2  rot   = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
      for (int i = 0; i < NUM_OCTAVES; ++i) {
        v += a * noise(x);
        x  = rot * x * 2.0 + shift;
        a *= 0.4;
      }
      return v;
    }

    void main() {
      vec2 shake = vec2(sin(iTime * 1.2) * 0.005, cos(iTime * 2.1) * 0.005);
      vec2 p = ((gl_FragCoord.xy + shake * iResolution.xy) - iResolution.xy * 0.5)
               / iResolution.y * mat2(6.0, -4.0, 4.0, 6.0);
      vec2 v;
      vec4 o = vec4(0.0);

      float f = 2.0 + fbm(p + vec2(iTime * 5.0, 0.0)) * 0.5;

      for (float i = 0.0; i < 35.0; i++) {
        v = p + cos(i * i + (iTime + p.x * 0.08) * 0.025 + i * vec2(13.0, 11.0)) * 3.5
            + vec2(sin(iTime * 3.0 + i) * 0.003, cos(iTime * 3.5 - i) * 0.003);
        float tailNoise = fbm(v + vec2(iTime * 0.5, i)) * 0.3 * (1.0 - (i / 35.0));
        vec4 auroraColors = vec4(
          0.1 + 0.3 * sin(i * 0.2 + iTime * 0.4),
          0.3 + 0.5 * cos(i * 0.3 + iTime * 0.5),
          0.7 + 0.3 * sin(i * 0.4 + iTime * 0.3),
          1.0
        );
        vec4 contrib   = auroraColors
                         * exp(sin(i * i + iTime * 0.8))
                         / length(max(v, vec2(v.x * f * 0.015, v.y * 1.5)));
        float thinness = smoothstep(0.0, 1.0, i / 35.0) * 0.6;
        o += contrib * (1.0 + tailNoise * 0.8) * thinness;
      }

      o = tanh(pow(o / 100.0, vec4(1.6)));
      fragColor = o * 1.5;
    }
  `;

  /* ────────────────────────────────────────────────────────
     GLSL 100  (WebGL 1) — identical logic + tanh polyfill
  ──────────────────────────────────────────────────────── */
  const VERT1 = `
    attribute vec2 position;
    void main() { gl_Position = vec4(position, 0.0, 1.0); }
  `;

  const FRAG1 = `
    precision highp float;

    uniform float iTime;
    uniform vec2  iResolution;

    #define NUM_OCTAVES 3

    /* tanh polyfill for WebGL 1 */
    float tanh_f(float x) { float e = exp(2.0*x); return (e-1.0)/(e+1.0); }
    vec4  tanh_v(vec4  x) { vec4  e = exp(2.0*x); return (e-vec4(1.0))/(e+vec4(1.0)); }

    float rand(vec2 n) {
      return fract(sin(dot(n, vec2(12.9898, 4.1414))) * 43758.5453);
    }
    float noise(vec2 p) {
      vec2 ip = floor(p);
      vec2 u  = fract(p);
      u = u * u * (3.0 - 2.0 * u);
      float res = mix(
        mix(rand(ip),               rand(ip + vec2(1.0,0.0)), u.x),
        mix(rand(ip + vec2(0.0,1.0)), rand(ip + vec2(1.0,1.0)), u.x), u.y);
      return res * res;
    }
    float fbm(vec2 x) {
      float v = 0.0, a = 0.3;
      vec2  shift = vec2(100.0);
      mat2  rot   = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
      for (int i = 0; i < NUM_OCTAVES; ++i) {
        v += a * noise(x);
        x  = rot * x * 2.0 + shift;
        a *= 0.4;
      }
      return v;
    }

    void main() {
      vec2 shake = vec2(sin(iTime * 1.2) * 0.005, cos(iTime * 2.1) * 0.005);
      vec2 p = ((gl_FragCoord.xy + shake * iResolution.xy) - iResolution.xy * 0.5)
               / iResolution.y * mat2(6.0, -4.0, 4.0, 6.0);
      vec2 v;
      vec4 o = vec4(0.0);

      float f = 2.0 + fbm(p + vec2(iTime * 5.0, 0.0)) * 0.5;

      for (int ii = 0; ii < 35; ii++) {
        float i = float(ii);
        v = p + cos(i * i + (iTime + p.x * 0.08) * 0.025 + i * vec2(13.0, 11.0)) * 3.5
            + vec2(sin(iTime * 3.0 + i) * 0.003, cos(iTime * 3.5 - i) * 0.003);
        float tailNoise = fbm(v + vec2(iTime * 0.5, i)) * 0.3 * (1.0 - (i / 35.0));
        vec4 auroraColors = vec4(
          0.1 + 0.3 * sin(i * 0.2 + iTime * 0.4),
          0.3 + 0.5 * cos(i * 0.3 + iTime * 0.5),
          0.7 + 0.3 * sin(i * 0.4 + iTime * 0.3),
          1.0
        );
        vec4 contrib   = auroraColors
                         * exp(sin(i * i + iTime * 0.8))
                         / length(max(v, vec2(v.x * f * 0.015, v.y * 1.5)));
        float thinness = smoothstep(0.0, 1.0, i / 35.0) * 0.6;
        o += contrib * (1.0 + tailNoise * 0.8) * thinness;
      }

      o = tanh_v(pow(o / 100.0, vec4(1.6)));
      gl_FragColor = o * 1.5;
    }
  `;

  /* ────────────────────────────────────────────────────────
     WebGL utilities
  ──────────────────────────────────────────────────────── */
  function compile(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.error('[ShaderBG] compile error:', gl.getShaderInfoLog(sh));
      return null;
    }
    return sh;
  }

  function link(gl, vsrc, fsrc) {
    const v = compile(gl, gl.VERTEX_SHADER,   vsrc);
    const f = compile(gl, gl.FRAGMENT_SHADER, fsrc);
    if (!v || !f) return null;
    const p = gl.createProgram();
    gl.attachShader(p, v);
    gl.attachShader(p, f);
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      console.error('[ShaderBG] link error:', gl.getProgramInfoLog(p));
      return null;
    }
    return p;
  }

  /* ────────────────────────────────────────────────────────
     Boot
  ──────────────────────────────────────────────────────── */
  function init() {
    const canvas = document.createElement('canvas');
    canvas.id = 'shaderBg';
    Object.assign(canvas.style, {
      position: 'fixed', inset: '0',
      width: '100%', height: '100%',
      zIndex: '0', pointerEvents: 'none', display: 'block',
    });
    document.body.insertBefore(canvas, document.body.firstChild);

    /* Try WebGL2 first, then fall back to WebGL1 */
    let gl  = canvas.getContext('webgl2', { antialias: false, alpha: false });
    let isV2 = !!gl;
    if (!gl) gl = canvas.getContext('webgl', { antialias: false, alpha: false });
    if (!gl) { canvas.remove(); return; }

    const prog = link(gl, isV2 ? VERT2 : VERT1, isV2 ? FRAG2 : FRAG1);
    if (!prog)  { canvas.remove(); return; }

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER,
      new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);

    const posLoc  = gl.getAttribLocation(prog,  'position');
    const timeLoc = gl.getUniformLocation(prog, 'iTime');
    const resLoc  = gl.getUniformLocation(prog, 'iResolution');

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width  = Math.floor(window.innerWidth  * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
    }
    resize();
    window.addEventListener('resize', resize, { passive: true });

    let iTime = 0, raf;
    function frame() {
      iTime += 0.016;
      gl.useProgram(prog);
      gl.enableVertexAttribArray(posLoc);
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);
      gl.uniform1f(timeLoc, iTime);
      gl.uniform2f(resLoc, canvas.width, canvas.height);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      raf = requestAnimationFrame(frame);
    }

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) cancelAnimationFrame(raf);
      else raf = requestAnimationFrame(frame);
    });

    raf = requestAnimationFrame(frame);
    console.log('[ShaderBG] Running on', isV2 ? 'WebGL2' : 'WebGL1');
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', init);
  else
    init();
})();
