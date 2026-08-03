/**
 * Cloudflare Worker: static assets + custom auth (OTP → password).
 * Bindings: ASSETS, AUTH_DB (D1), AUTH_SECRET, RESEND_API_KEY, AUTH_FROM_EMAIL
 */

const ALLOWED_EMAIL_DOMAIN = 'ngn.no';
const OTP_TTL_MS = 15 * 60 * 1000;
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 14;
const MIN_PASSWORD_LENGTH = 8;
const OTP_MAX_ATTEMPTS = 5;
const COOKIE_NAME = 'ng_session';

const PUBLIC_PREFIXES = [
  '/login.html',
  '/auth.js',
  '/assets/',
  '/api/auth/',
  '/favicon',
];

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    try {
      if (url.pathname.startsWith('/api/auth/')) {
        return await handleAuthApi(request, env, url);
      }

      if (!isPublicPath(url.pathname) && !(await getSessionEmail(request, env))) {
        const next = url.pathname.replace(/^\//, '') || 'index.html';
        return Response.redirect(new URL(`/login.html?next=${encodeURIComponent(next)}`, url.origin), 302);
      }

      return env.ASSETS.fetch(request);
    } catch (error) {
      console.error('Worker error:', error);
      return json({ error: 'Intern feil' }, 500);
    }
  },
};

function isPublicPath(pathname) {
  if (pathname === '/' || pathname === '') return false;
  return PUBLIC_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(prefix));
}

async function handleAuthApi(request, env, url) {
  try {
    const path = url.pathname.replace(/\/+$/, '');

    if (request.method === 'GET' && path.endsWith('/me')) {
      const email = await getSessionEmail(request, env);
      if (!email) return json({ authenticated: false }, 401);
      return json({ authenticated: true, email });
    }

    if (request.method === 'POST' && path.endsWith('/logout')) {
      return withClearedCookie(json({ ok: true }));
    }

    if (request.method !== 'POST') {
      return json({ error: 'Method not allowed' }, 405);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: 'Ugyldig JSON' }, 400);
    }

    if (path.endsWith('/send-code')) {
      return await sendCode(env, body);
    }
    if (path.endsWith('/verify-code')) {
      return await verifyCode(env, body);
    }
    if (path.endsWith('/set-password')) {
      return await setPassword(request, env, body);
    }
    if (path.endsWith('/login')) {
      return await login(env, body);
    }

    return json({ error: 'Not found' }, 404);
  } catch (error) {
    const status = error && error.status ? error.status : 500;
    const message = error && error.message ? error.message : 'Intern feil';
    if (status >= 500) console.error('Auth API error:', error);
    return json({ error: message }, status);
  }
}

function normalizeEmail(email) {
  return String(email || '').trim().toLowerCase();
}

function isAllowedEmail(email) {
  const normalized = normalizeEmail(email);
  const at = normalized.lastIndexOf('@');
  if (at < 1) return false;
  return normalized.slice(at + 1) === ALLOWED_EMAIL_DOMAIN;
}

function assertAllowedEmail(email) {
  const normalized = normalizeEmail(email);
  if (!isAllowedEmail(normalized)) {
    const error = new Error('Ugyldig e-post');
    error.status = 400;
    throw error;
  }
  return normalized;
}

async function sendCode(env, body) {
  ensureAuthConfigured(env);
  const email = assertAllowedEmail(body.email);
  const code = String(Math.floor(100000 + Math.random() * 900000));
  const codeHash = await sha256(`${email}:${code}:${env.AUTH_SECRET}`);
  const expiresAt = new Date(Date.now() + OTP_TTL_MS).toISOString();

  await env.AUTH_DB.prepare(
    `INSERT INTO otps (email, code_hash, expires_at, attempts)
     VALUES (?, ?, ?, 0)
     ON CONFLICT(email) DO UPDATE SET
       code_hash = excluded.code_hash,
       expires_at = excluded.expires_at,
       attempts = 0`
  ).bind(email, codeHash, expiresAt).run();

  await sendOtpEmail(env, email, code);
  return json({ ok: true });
}

async function verifyCode(env, body) {
  ensureAuthConfigured(env);
  const email = assertAllowedEmail(body.email);
  const code = String(body.code || '').replace(/\s+/g, '');
  if (!/^\d{6}$/.test(code)) {
    return json({ error: 'Ugyldig kode' }, 400);
  }

  const row = await env.AUTH_DB.prepare(
    'SELECT code_hash, expires_at, attempts FROM otps WHERE email = ?'
  ).bind(email).first();

  if (!row) {
    return json({ error: 'Ingen aktiv kode. Be om ny kode.' }, 400);
  }
  if (Number(row.attempts) >= OTP_MAX_ATTEMPTS) {
    return json({ error: 'For mange forsøk. Be om ny kode.' }, 429);
  }
  if (new Date(row.expires_at).getTime() < Date.now()) {
    return json({ error: 'Koden er utløpt. Be om ny kode.' }, 400);
  }

  const codeHash = await sha256(`${email}:${code}:${env.AUTH_SECRET}`);
  if (codeHash !== row.code_hash) {
    await env.AUTH_DB.prepare(
      'UPDATE otps SET attempts = attempts + 1 WHERE email = ?'
    ).bind(email).run();
    return json({ error: 'Ugyldig kode' }, 400);
  }

  await env.AUTH_DB.prepare('DELETE FROM otps WHERE email = ?').bind(email).run();

  const now = new Date().toISOString();
  await env.AUTH_DB.prepare(
    `INSERT INTO users (email, password_hash, password_salt, created_at, updated_at)
     VALUES (?, NULL, NULL, ?, ?)
     ON CONFLICT(email) DO UPDATE SET updated_at = excluded.updated_at`
  ).bind(email, now, now).run();

  const token = await createSessionToken(env, email);
  return withSessionCookie(json({ ok: true, email }), token);
}

async function setPassword(request, env, body) {
  ensureAuthConfigured(env);
  const email = await getSessionEmail(request, env);
  if (!email) return json({ error: 'Ikke innlogget' }, 401);

  const password = String(body.password || '');
  const passwordConfirm = String(body.passwordConfirm || '');
  if (password.length < MIN_PASSWORD_LENGTH) {
    return json({ error: `Passordet må være minst ${MIN_PASSWORD_LENGTH} tegn.` }, 400);
  }
  if (password !== passwordConfirm) {
    return json({ error: 'Passordene er ikke like.' }, 400);
  }

  const salt = crypto.randomUUID().replace(/-/g, '');
  const passwordHash = await hashPassword(password, salt);
  const now = new Date().toISOString();

  await env.AUTH_DB.prepare(
    `UPDATE users
     SET password_hash = ?, password_salt = ?, updated_at = ?
     WHERE email = ?`
  ).bind(passwordHash, salt, now, email).run();

  const token = await createSessionToken(env, email);
  return withSessionCookie(json({ ok: true }), token);
}

async function login(env, body) {
  ensureAuthConfigured(env);
  const email = assertAllowedEmail(body.email);
  const password = String(body.password || '');
  if (password.length < MIN_PASSWORD_LENGTH) {
    return json({ error: 'Feil e-post eller passord' }, 401);
  }

  const user = await env.AUTH_DB.prepare(
    'SELECT password_hash, password_salt FROM users WHERE email = ?'
  ).bind(email).first();

  if (!user || !user.password_hash || !user.password_salt) {
    return json({ error: 'Feil e-post eller passord' }, 401);
  }

  const passwordHash = await hashPassword(password, user.password_salt);
  if (passwordHash !== user.password_hash) {
    return json({ error: 'Feil e-post eller passord' }, 401);
  }

  const token = await createSessionToken(env, email);
  return withSessionCookie(json({ ok: true, email }), token);
}

function ensureAuthConfigured(env) {
  if (!env.AUTH_DB) {
    const error = new Error('AUTH_DB mangler');
    error.status = 500;
    throw error;
  }
  if (!env.AUTH_SECRET) {
    const error = new Error('AUTH_SECRET mangler');
    error.status = 500;
    throw error;
  }
}

async function sendOtpEmail(env, email, code) {
  if (!env.RESEND_API_KEY || !env.AUTH_FROM_EMAIL) {
    const error = new Error('E-post er ikke konfigurert (RESEND_API_KEY / AUTH_FROM_EMAIL)');
    error.status = 500;
    throw error;
  }

  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: env.AUTH_FROM_EMAIL,
      to: [email],
      subject: 'Verifikasjonskode for NG drivstoffverktøy',
      html: `
        <h2>Bekreft e-posten din</h2>
        <p>Din verifikasjonskode er:</p>
        <p style="font-size:24px;font-weight:700;letter-spacing:4px;">${code}</p>
        <p>Skriv inn koden på registreringssiden. Deretter lager du et eget passord bare for denne siden.</p>
        <p>Hvis du ikke ba om dette, kan du se bort fra e-posten.</p>
      `,
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    console.error('Resend error:', response.status, detail);
    const error = new Error('Kunne ikke sende e-post. Prøv igjen senere.');
    error.status = 502;
    throw error;
  }
}

async function hashPassword(password, salt) {
  const material = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(password),
    'PBKDF2',
    false,
    ['deriveBits']
  );
  const bits = await crypto.subtle.deriveBits(
    {
      name: 'PBKDF2',
      salt: new TextEncoder().encode(salt),
      iterations: 100000,
      hash: 'SHA-256',
    },
    material,
    256
  );
  return bufferToHex(bits);
}

async function sha256(value) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return bufferToHex(digest);
}

function bufferToHex(buffer) {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function createSessionToken(env, email) {
  const exp = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const payload = `${email}|${exp}`;
  const signature = await hmacSign(env.AUTH_SECRET, payload);
  return `${base64UrlEncode(payload)}.${signature}`;
}

async function getSessionEmail(request, env) {
  if (!env.AUTH_SECRET) return null;
  const cookie = parseCookie(request.headers.get('Cookie') || '')[COOKIE_NAME];
  if (!cookie) return null;
  const [payloadEncoded, signature] = cookie.split('.');
  if (!payloadEncoded || !signature) return null;
  let payload;
  try {
    payload = base64UrlDecode(payloadEncoded);
  } catch {
    return null;
  }
  const expected = await hmacSign(env.AUTH_SECRET, payload);
  if (expected !== signature) return null;
  const [email, expRaw] = payload.split('|');
  const exp = Number(expRaw);
  if (!email || !Number.isFinite(exp) || exp * 1000 < Date.now()) return null;
  if (!isAllowedEmail(email)) return null;
  return email;
}

async function hmacSign(secret, value) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value));
  return bufferToHex(signature);
}

function parseCookie(header) {
  const out = {};
  header.split(';').forEach((part) => {
    const index = part.indexOf('=');
    if (index < 0) return;
    const key = part.slice(0, index).trim();
    const value = part.slice(index + 1).trim();
    out[key] = decodeURIComponent(value);
  });
  return out;
}

function base64UrlEncode(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function base64UrlDecode(value) {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((value.length + 3) % 4);
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

function withSessionCookie(response, token) {
  const headers = new Headers(response.headers);
  headers.append(
    'Set-Cookie',
    `${COOKIE_NAME}=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_TTL_SECONDS}`
  );
  return new Response(response.body, { status: response.status, headers });
}

function withClearedCookie(response) {
  const headers = new Headers(response.headers);
  headers.append(
    'Set-Cookie',
    `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`
  );
  return new Response(response.body, { status: response.status, headers });
}
