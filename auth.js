(function (global) {
  const ALLOWED_EMAIL_DOMAIN = 'ngn.no';
  const MIN_PASSWORD_LENGTH = 8;
  const SUPABASE_URL = 'https://fnkdbuqsschkvpzeumbz.supabase.co';
  const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZua2RidXFzc2Noa3ZwemV1bWJ6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU1NTM5MjQsImV4cCI6MjA5MTEyOTkyNH0.bI5r0wyEME9BIBqBAINKkzvYCmHlY1QtZwVYHYRiLpI';

  let client = null;

  function getClient() {
    if (client) return client;
    if (!global.supabase || typeof global.supabase.createClient !== 'function') {
      throw new Error('Supabase JS er ikke lastet');
    }
    client = global.supabase.createClient(SUPABASE_URL, SUPABASE_ANON, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        storage: global.localStorage,
      },
    });
    return client;
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

  function validatePassword(password) {
    const value = String(password || '');
    if (value.length < MIN_PASSWORD_LENGTH) {
      throw new Error('Passordet må være minst ' + MIN_PASSWORD_LENGTH + ' tegn.');
    }
  }

  function assertAllowedEmail(email) {
    const normalized = normalizeEmail(email);
    if (!isAllowedEmail(normalized)) {
      throw new Error('Kun e-postadresser på @' + ALLOWED_EMAIL_DOMAIN + ' kan registrere seg eller logge inn.');
    }
    return normalized;
  }

  function markAuthReady() {
    document.documentElement.classList.add('auth-ready');
    document.documentElement.classList.remove('auth-pending');
  }

  async function getSession() {
    const { data, error } = await getClient().auth.getSession();
    if (error) throw error;
    return data.session || null;
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

    const email = session.user && session.user.email ? session.user.email : '';
    if (!isAllowedEmail(email)) {
      await signOut();
      location.replace(loginPath + '?error=domain');
      return null;
    }

    markAuthReady();
    return session;
  }

  async function signUp(email, password) {
    const normalized = assertAllowedEmail(email);
    validatePassword(password);
    const { data, error } = await getClient().auth.signUp({
      email: normalized,
      password: String(password),
    });
    if (error) throw error;
    return data;
  }

  async function signIn(email, password) {
    const normalized = assertAllowedEmail(email);
    validatePassword(password);
    const { data, error } = await getClient().auth.signInWithPassword({
      email: normalized,
      password: String(password),
    });
    if (error) throw error;
    if (!data.session) {
      throw new Error('Innlogging feilet. Sjekk e-post, passord og at kontoen er bekreftet.');
    }
    return data;
  }

  async function resendSignupCode(email) {
    const normalized = assertAllowedEmail(email);
    const { data, error } = await getClient().auth.resend({
      type: 'signup',
      email: normalized,
    });
    if (error) throw error;
    return data;
  }

  async function verifySignupOtp(email, token) {
    const normalized = assertAllowedEmail(email);
    const code = String(token || '').replace(/\s+/g, '');
    if (!/^\d{6,8}$/.test(code)) {
      throw new Error('Skriv inn verifikasjonskoden du fikk på e-post (6 siffer).');
    }
    const { data, error } = await getClient().auth.verifyOtp({
      email: normalized,
      token: code,
      type: 'signup',
    });
    if (error) throw error;
    if (!data.session) {
      throw new Error('Kunne ikke bekrefte kontoen. Prøv å be om ny kode.');
    }
    return data;
  }

  async function signOut() {
    const { error } = await getClient().auth.signOut();
    if (error) throw error;
  }

  async function getAccessToken() {
    const session = await getSession();
    return session && session.access_token ? session.access_token : null;
  }

  function currentUserEmail() {
    return getSession().then(session => (session && session.user && session.user.email) || null);
  }

  global.NgAuth = {
    ALLOWED_EMAIL_DOMAIN,
    MIN_PASSWORD_LENGTH,
    SUPABASE_URL,
    SUPABASE_ANON,
    getClient,
    normalizeEmail,
    isAllowedEmail,
    getSession,
    requireSession,
    signUp,
    signIn,
    resendSignupCode,
    verifySignupOtp,
    signOut,
    getAccessToken,
    currentUserEmail,
    markAuthReady,
  };
})(window);
