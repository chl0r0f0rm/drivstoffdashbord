(function (global) {
  const ALLOWED_EMAIL_DOMAIN = 'ngn.no';
  const MIN_PASSWORD_LENGTH = 8;

  function normalizeEmail(email) {
    return String(email || '').trim().toLowerCase();
  }

  function isAllowedEmail(email) {
    const normalized = normalizeEmail(email);
    const at = normalized.lastIndexOf('@');
    if (at < 1) return false;
    return normalized.slice(at + 1) === ALLOWED_EMAIL_DOMAIN;
  }

  function markAuthReady() {
    document.documentElement.classList.add('auth-ready');
    document.documentElement.classList.remove('auth-pending');
  }

  async function api(path, options) {
    const opts = options || {};
    const method = opts.method || 'GET';
    const headers = { ...(opts.headers || {}) };
    if (method !== 'GET' && method !== 'HEAD') {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }
    const response = await fetch(path, {
      credentials: 'same-origin',
      ...opts,
      method,
      headers,
    });
    let data = null;
    try {
      data = await response.json();
    } catch (error) {
      data = null;
    }
    if (!response.ok) {
      const message = data && data.error ? data.error : 'Noe gikk galt';
      throw new Error(message);
    }
    return data;
  }

  async function getSession() {
    try {
      const data = await api('/api/auth/me', { method: 'GET', headers: {} });
      if (!data || !data.authenticated) return null;
      return { user: { email: data.email } };
    } catch (error) {
      return null;
    }
  }

  async function requireSession(options) {
    const opts = options || {};
    const loginPath = opts.loginPath || 'login.html';
    document.documentElement.classList.add('auth-pending');

    const session = await getSession();
    if (!session) {
      const page = (location.pathname.split('/').pop() || 'index.html') + location.search;
      location.replace(loginPath + '?next=' + encodeURIComponent(page));
      return null;
    }

    markAuthReady();
    return session;
  }

  async function signIn(email, password) {
    if (!isAllowedEmail(email)) throw new Error('Ugyldig e-post');
    if (String(password || '').length < MIN_PASSWORD_LENGTH) {
      throw new Error('Passordet må være minst ' + MIN_PASSWORD_LENGTH + ' tegn.');
    }
    return api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email: normalizeEmail(email),
        password: String(password),
      }),
    });
  }

  async function sendRegisterOtp(email) {
    if (!isAllowedEmail(email)) throw new Error('Ugyldig e-post');
    return api('/api/auth/send-code', {
      method: 'POST',
      body: JSON.stringify({ email: normalizeEmail(email) }),
    });
  }

  async function verifyRegisterOtp(email, token) {
    if (!isAllowedEmail(email)) throw new Error('Ugyldig e-post');
    const code = String(token || '').replace(/\s+/g, '');
    if (!/^\d{6,8}$/.test(code)) {
      throw new Error('Skriv inn verifikasjonskoden du fikk på e-post (6 siffer).');
    }
    return api('/api/auth/verify-code', {
      method: 'POST',
      body: JSON.stringify({
        email: normalizeEmail(email),
        code,
      }),
    });
  }

  async function setPassword(password, passwordConfirm) {
    if (String(password || '').length < MIN_PASSWORD_LENGTH) {
      throw new Error('Passordet må være minst ' + MIN_PASSWORD_LENGTH + ' tegn.');
    }
    if (String(password) !== String(passwordConfirm || '')) {
      throw new Error('Passordene er ikke like.');
    }
    return api('/api/auth/set-password', {
      method: 'POST',
      body: JSON.stringify({
        password: String(password),
        passwordConfirm: String(passwordConfirm),
      }),
    });
  }

  async function signOut() {
    return api('/api/auth/logout', { method: 'POST', body: '{}' });
  }

  global.NgAuth = {
    ALLOWED_EMAIL_DOMAIN,
    MIN_PASSWORD_LENGTH,
    normalizeEmail,
    isAllowedEmail,
    getSession,
    requireSession,
    signIn,
    sendRegisterOtp,
    verifyRegisterOtp,
    setPassword,
    signOut,
    markAuthReady,
  };
})(window);
