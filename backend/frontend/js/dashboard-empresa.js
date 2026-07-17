/*
 * dashboard-empresa.js — dashboard do perfil `empresa`.
 *
 * Três listas de recentes (Benefícios, Boletos, Trabalhadores) + o alerta de
 * inadimplência. Tudo consome endpoints que JÁ existem e JÁ aplicam RLS —
 * nenhum SQL novo, nenhum endpoint novo.
 *
 * Ver o cabeçalho do dashboard-empresa.html pro porquê de ser uma tela
 * separada em vez do dashboard.html filtrado.
 */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

const LIMITE = 5;   // "recentes" — o portal legado mostra 5 por bloco


// === Formatação ============================================================

function fmtData(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("pt-BR");
}

function fmtDataHora(d) {
  if (!d) return "—";
  const dt = new Date(d);
  return `${dt.toLocaleDateString("pt-BR")}<br><span class="text-xs text-slate-400">${dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span>`;
}

function fmtMoeda(v) {
  if (v == null) return "—";
  return Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function fmtCpf(cpf) {
  const d = String(cpf || "").replace(/\D/g, "");
  if (d.length !== 11) return cpf || "—";
  return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
}

function fmtMesRef(m) {
  if (!m) return "—";
  const dt = new Date(m);
  return dt.toLocaleDateString("pt-BR", { month: "short", year: "numeric" });
}

/** Escapa texto que vem do banco antes de ir pra innerHTML. */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function badge(texto, cor) {
  return `<span class="px-2 py-0.5 rounded-full text-xs ${cor}">${esc(texto)}</span>`;
}

function corStatusBoleto(status) {
  return {
    pago:      "bg-emerald-50 text-emerald-700",
    vencido:   "bg-rose-50 text-rose-700",
    cancelado: "bg-slate-100 text-slate-500",
  }[status] || "bg-amber-50 text-amber-700";
}

function linhaVazia(cols, msg) {
  return `<tr><td colspan="${cols}" class="px-5 py-8 text-center text-slate-400">${msg}</td></tr>`;
}

function linhaErro(cols, msg) {
  return `<tr><td colspan="${cols}" class="px-5 py-8 text-center text-rose-500">${esc(msg)}</td></tr>`;
}


// === Blocos ================================================================

async function carregarBeneficios() {
  const tb = document.getElementById("tb-beneficios");
  tb.innerHTML = linhaVazia(5, "Carregando…");
  const p = new URLSearchParams({ pagina: 1, por_pagina: LIMITE, ordem: "criado_em", desc: "true" });
  comEmpresaAtual(p);
  try {
    const d = await apiFetch(`/processos?${p}`);
    if (!d.linhas.length) return void (tb.innerHTML = linhaVazia(5, "Nenhum benefício"));
    tb.innerHTML = d.linhas.map((r) => `
      <tr class="hover:bg-slate-50 cursor-pointer"
          onclick="location.href='/app/processo-detalhe.html?id=${r.id}'">
        <td class="px-5 py-3 font-mono text-xs">${esc(r.protocolo || "—")}</td>
        <td class="px-5 py-3">${esc(r.trabalhador_nome || "—")}</td>
        <td class="px-5 py-3">${esc(r.tipo_beneficio || "—")}</td>
        <td class="px-5 py-3">${badge(r.status_nome || r.status, "bg-slate-100 text-slate-700")}</td>
        <td class="px-5 py-3 text-right text-slate-500">${fmtDataHora(r.criado_em)}</td>
      </tr>`).join("");
  } catch (e) {
    tb.innerHTML = linhaErro(5, e.message);
  }
}

async function carregarBoletos() {
  const tb = document.getElementById("tb-boletos");
  tb.innerHTML = linhaVazia(5, "Carregando…");
  const p = new URLSearchParams({ pagina: 1, por_pagina: LIMITE, ordem: "data_vencimento", desc: "true" });
  comEmpresaAtual(p);
  try {
    const d = await apiFetch(`/boletos?${p}`);
    if (!d.linhas.length) return void (tb.innerHTML = linhaVazia(5, "Nenhum boleto"));
    tb.innerHTML = d.linhas.map((r) => `
      <tr class="hover:bg-slate-50 cursor-pointer"
          onclick="location.href='/app/boleto-detalhe.html?id=${r.id}'">
        <td class="px-5 py-3">${fmtMesRef(r.mes_referencia)}</td>
        <td class="px-5 py-3">${fmtData(r.data_vencimento)}</td>
        <td class="px-5 py-3 truncate max-w-xs" title="${esc(r.empresa)}">${esc(r.empresa || "—")}</td>
        <td class="px-5 py-3 text-right font-medium">${fmtMoeda(r.valor_total)}</td>
        <td class="px-5 py-3">${badge(r.status, corStatusBoleto(r.status))}</td>
      </tr>`).join("");
  } catch (e) {
    tb.innerHTML = linhaErro(5, e.message);
  }
}

async function carregarTrabalhadores() {
  const tb = document.getElementById("tb-trabalhadores");
  tb.innerHTML = linhaVazia(4, "Carregando…");
  const p = new URLSearchParams({ pagina: 1, por_pagina: LIMITE, ordem: "atualizado_em", desc: "true" });
  comEmpresaAtual(p);
  try {
    const d = await apiFetch(`/trabalhadores?${p}`);
    if (!d.linhas.length) return void (tb.innerHTML = linhaVazia(4, "Nenhum trabalhador"));
    tb.innerHTML = d.linhas.map((r) => `
      <tr class="hover:bg-slate-50 cursor-pointer"
          onclick="location.href='/app/trabalhador-detalhe.html?id=${r.id}'">
        <td class="px-5 py-3">${esc(r.nome_completo)}
          ${r.titularidade === "dependente"
            ? '<span class="ms-1 text-xs text-slate-400">(dependente)</span>' : ""}</td>
        <td class="px-5 py-3 font-mono text-xs">${fmtCpf(r.cpf)}</td>
        <td class="px-5 py-3 truncate max-w-xs" title="${esc(r.empresa)}">${esc(r.empresa || "—")}</td>
        <td class="px-5 py-3">${badge(
          r.situacao,
          r.situacao === "ativo" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"
        )}</td>
      </tr>`).join("");
  } catch (e) {
    tb.innerHTML = linhaErro(4, e.message);
  }
}


// === Alerta de inadimplência ==============================================

/*
 * O portal legado abre um modal bloqueante no login quando existe empresa
 * inadimplente ou irregular sob gestão do usuário. Reproduzimos aqui usando
 * `adimplencia` e `regularidade`, que a v_empresa já calcula e o GET /empresas
 * já devolve — sem endpoint novo.
 *
 * PENDENTE confirmar com a BSS: o que exatamente define "inadimplente" e
 * "irregular" (boleto vencido? carência? quantos dias?), e se o texto é fixo
 * ou vem de parâmetro por sindicato. Enquanto isso o alerta REPORTA o que o
 * banco diz, sem inventar regra própria.
 */
async function verificarAlerta() {
  if (!empresaAtualId()) return;   // perfil sem escopo por empresa
  let empresas;
  try {
    empresas = await apiFetch("/empresas?por_pagina=200&ordem=razao_social");
  } catch (e) {
    return;   // alerta é informativo; não vale quebrar a tela por ele
  }

  const problema = (empresas.linhas || []).filter(
    (e) => e.adimplencia === "inadimplente" || e.regularidade === "irregular"
  );
  if (!problema.length) return;

  document.getElementById("alerta-texto").textContent =
    `Existe empresa inadimplente ou irregular com as contribuições registrada em seu acesso. ` +
    `Não será emitido o certificado de regularidade para ${problema.length > 1 ? "estas empresas" : "esta empresa"}, ` +
    `e os sindicatos possuem acesso a esta informação e podem tomar as medidas cabíveis.`;

  document.getElementById("alerta-empresas").innerHTML = problema.map((e) => {
    const tags = [];
    if (e.adimplencia === "inadimplente") tags.push(badge("inadimplente", "bg-rose-50 text-rose-700"));
    if (e.regularidade === "irregular") tags.push(badge("irregular", "bg-amber-50 text-amber-700"));
    return `<li class="flex items-center justify-between gap-2 border-b border-slate-100 pb-1">
              <span class="truncate">${esc(e.razao_social)}</span>
              <span class="flex gap-1 flex-shrink-0">${tags.join("")}</span>
            </li>`;
  }).join("");

  document.getElementById("modal-alerta").classList.remove("hidden");
}


// === Carga =================================================================

function recarregarTudo() {
  carregarBeneficios();
  carregarBoletos();
  carregarTrabalhadores();
}

montarSeletorEmpresa("#seletor-empresa", recarregarTudo);
recarregarTudo();
verificarAlerta();
