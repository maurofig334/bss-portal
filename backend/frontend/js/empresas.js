/* Tela de listagem de empresas. */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let pagina = 1;
let timer = null;

function fmtCNPJ(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length !== 14) return c;
  return d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
}

function fmtData(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("pt-BR");
}

function badge(valor, mapa) {
  const cls = mapa[valor] || "bg-slate-100 text-slate-600";
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cls}">${valor || "—"}</span>`;
}

function badgeStatus(s) {
  return badge(s, {
    ativa:     "bg-emerald-100 text-emerald-800",
    inativa:   "bg-slate-200 text-slate-700",
    suspensa:  "bg-amber-100 text-amber-800",
    cancelada: "bg-rose-100 text-rose-800",
  });
}
function badgeAdim(a) {
  return badge(a, {
    adimplente:   "bg-emerald-100 text-emerald-800",
    inadimplente: "bg-rose-100 text-rose-800",
  });
}
function badgeReg(r) {
  return badge(r, {
    regular:   "bg-emerald-100 text-emerald-800",
    irregular: "bg-amber-100 text-amber-800",
  });
}

function ler() {
  return {
    busca:        document.getElementById("f-busca").value.trim(),
    status:       document.getElementById("f-status").value,
    adimplencia:  document.getElementById("f-adim").value,
    regularidade: document.getElementById("f-reg").value,
  };
}

function montarQuery() {
  const f = { ...ler(), pagina, por_pagina: 50 };
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (v !== "" && v != null) params.append(k, v);
  }
  return params.toString();
}

async function recarregar() { pagina = 1; await carregar(); }

async function carregar() {
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-6 text-center text-slate-400">Carregando…</td></tr>`;
  const t0 = performance.now();
  try {
    const data = await apiFetch(`/empresas?${montarQuery()}`);
    const dur = (performance.now() - t0).toFixed(0);
    document.getElementById("tempo").textContent = `⚡ ${dur}ms`;
    document.getElementById("stats").textContent = `${data.total.toLocaleString("pt-BR")} empresas encontradas`;

    if (!data.linhas.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-6 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }

    tbody.innerHTML = data.linhas.map(e => `
      <tr class="border-t border-slate-100 hover:bg-slate-50">
        <td class="px-3 py-2 font-mono text-xs">${fmtCNPJ(e.cnpj)}</td>
        <td class="px-3 py-2 font-medium text-slate-900">${e.razao_social || "—"}</td>
        <td class="px-3 py-2 text-slate-600">${(e.cidade || "—") + (e.uf ? "/" + e.uf : "")}</td>
        <td class="px-3 py-2 text-right font-mono">${(e.qtd_trabalhadores_ativos || 0).toLocaleString("pt-BR")}</td>
        <td class="px-3 py-2 text-center">${badgeStatus(e.status)}</td>
        <td class="px-3 py-2 text-center">${badgeAdim(e.adimplencia)}</td>
        <td class="px-3 py-2 text-center">${badgeReg(e.regularidade)}</td>
        <td class="px-3 py-2 text-right text-xs text-slate-500">${fmtData(e.ultimo_boleto_em)}</td>
      </tr>
    `).join("");

    montarPaginacao(data);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-6 text-center text-rose-600">Erro: ${e.message}</td></tr>`;
  }
}

function montarPaginacao(data) {
  const div = document.getElementById("paginacao");
  if (data.paginas <= 1) { div.innerHTML = ""; return; }
  div.innerHTML = `
    <div class="text-slate-500">Página ${data.pagina} de ${data.paginas}</div>
    <div class="flex gap-2">
      <button onclick="irPagina(${pagina - 1})" ${pagina <= 1 ? "disabled" : ""} class="px-3 py-1 border rounded ${pagina <= 1 ? "text-slate-300" : "hover:bg-slate-100"}">‹ Anterior</button>
      <button onclick="irPagina(${pagina + 1})" ${pagina >= data.paginas ? "disabled" : ""} class="px-3 py-1 border rounded ${pagina >= data.paginas ? "text-slate-300" : "hover:bg-slate-100"}">Próxima ›</button>
    </div>`;
}

function irPagina(p) { pagina = Math.max(1, p); carregar(); }
function agendarBusca() { clearTimeout(timer); timer = setTimeout(recarregar, 300); }
function limparFiltros() {
  document.getElementById("f-busca").value = "";
  document.getElementById("f-status").value = "";
  document.getElementById("f-adim").value = "";
  document.getElementById("f-reg").value = "";
  recarregar();
}

// Permite chegar com filtro pré-aplicado via URL (ex.: link de Empresa no
// detalhe do trabalhador -> empresas.html?busca=<cnpj>).
(function aplicarFiltroDaUrl() {
  const busca = new URL(window.location.href).searchParams.get("busca");
  if (busca) document.getElementById("f-busca").value = busca;
})();

carregar();
