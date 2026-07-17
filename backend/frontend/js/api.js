/*
 * api.js — Helper compartilhado para chamar a API do BSS.
 */

const API_BASE = "";
const TOKEN_KEY = "bss_token";


async function apiLogin(email, password) {
  const body = new URLSearchParams();
  body.append("username", email);
  body.append("password", password);

  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || "Falha no login");
  }

  const data = await resp.json();
  localStorage.setItem(TOKEN_KEY, data.access_token);
  return data.access_token;
}


async function apiFetch(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = {
    ...(options.headers || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (resp.status === 401) {
    logout();
    throw new Error("Sessão expirada");
  }
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `Erro ${resp.status}`);
  }
  return resp.json();
}


/**
 * Baixa um PDF (ou outro binário) autenticado e abre em nova aba.
 *
 * Por que existe: <a href> não envia o header Authorization quando o
 * navegador abre uma nova aba. Então pra rotas protegidas, fazemos
 * fetch + blob + URL.createObjectURL + window.open.
 */
async function apiAbrirPdf(path) {
  const token = localStorage.getItem(TOKEN_KEY);
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (resp.status === 401) {
    logout();
    throw new Error("Sessão expirada");
  }
  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`Erro ${resp.status}: ${txt || resp.statusText}`);
  }
  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  window.open(blobUrl, "_blank");
  // Libera memória depois de 60s — janela já carregou:
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
}


/**
 * Baixa um arquivo autenticado e dispara o "salvar como" do navegador.
 *
 * Mesmo motivo do apiAbrirPdf: <a href> e window.open não mandam o header
 * Authorization. A diferença é que aqui queremos DOWNLOAD com nome de arquivo,
 * não abrir numa aba — .xlsx aberto como blob vira um nome tipo
 * "a3f9-8c2e-..." e o usuário não sabe o que baixou.
 *
 * O nome vem do Content-Disposition que o backend manda; `nomePadrao` é só o
 * fallback.
 */
async function apiBaixarArquivo(path, nomePadrao = "download") {
  const token = localStorage.getItem(TOKEN_KEY);
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (resp.status === 401) {
    logout();
    throw new Error("Sessão expirada");
  }
  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`Erro ${resp.status}: ${txt || resp.statusText}`);
  }

  let nome = nomePadrao;
  const cd = resp.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="?([^"]+)"?/);
  if (m) nome = m[1];

  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}


function logout() {
  localStorage.removeItem(TOKEN_KEY);
  window.location.href = "/app/login.html";
}


function usuarioAtual() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return {
      id:         payload.sub,
      email:      payload.email,
      nome:       payload.nome,
      perfil:     payload.perfil,
      empresas:   payload.empresas   || [],   // [int] — IDs das empresas (perfil=empresa)
      sindicatos: payload.sindicatos || [],   // [int] — IDs dos sindicatos (perfil=sindicato)
    };
  } catch {
    return null;
  }
}


function exigirLogin() {
  const u = usuarioAtual();
  if (!u) {
    window.location.href = "/app/login.html";
    return null;
  }
  return u;
}
