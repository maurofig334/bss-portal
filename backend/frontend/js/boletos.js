/* Tela de Boletos. */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let pagina = 1;
let timer = null;

function brl(n) { return Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }
function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtMes(d) {
  if (!d) return "—";
  const dt = new Date(d);
  const meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
  return `${meses[dt.getUTCMonth()]}/${String(dt.getUTCFullYear()).slice(-2)}`;
}

function badgeStatus(s) {
  const cores = {
    pago: "bg-emerald-100 text-emerald-800",
    gerado: "bg-slate-100 text-slate-700",
    enviado: "bg-blue-100 text-blue-800",
    vencido: "bg-rose-100 text-rose-800",
    cancelado: "bg-slate-200 text-slate-500 line-through",
  };
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cores[s] || "bg-slate-100 text-slate-600"}">${s || "—"}</span>`;
}

function ler() {
  return {
    busca: document.getElementById("f-busca").value.trim(),
    status: document.getElementById("f-status").value,
    mes_referencia: document.getElementById("f-mes").value,
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
  tbody.innerHTML = `<tr><td colspan="9" class="px-3 py-6 text-center text-slate-400">Carregando…</td></tr>`;
  const t0 = performance.now();
  try {
    const data = await apiFetch(`/boletos?${montarQuery()}`);
    const dur = (performance.now() - t0).toFixed(0);
    document.getElementById("tempo").textContent = `⚡ ${dur}ms`;
    document.getElementById("stats").textContent = `${data.total.toLocaleString("pt-BR")} boletos encontrados`;

    if (!data.linhas.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="px-3 py-6 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }

    tbody.innerHTML = data.linhas.map(b => `
      <tr class="border-t border-slate-100 hover:bg-slate-50">
        <td class="px-3 py-2 font-mono text-xs">${b.numero_boleto || b.nosso_numero || "—"}</td>
        <td class="px-3 py-2 font-medium text-slate-900">${b.empresa || "—"}</td>
        <td class="px-3 py-2 text-slate-600 text-xs">${b.sindicato || "—"}</td>
        <td class="px-3 py-2 text-center">${fmtMes(b.mes_referencia)}</td>
        <td class="px-3 py-2 text-right font-mono">${(b.qtd_trabalhadores || 0).toLocaleString("pt-BR")}</td>
        <td class="px-3 py-2 text-right font-mono">${brl(b.valor_total)}</td>
        <td class="px-3 py-2 text-center">${badgeStatus(b.status)}</td>
        <td class="px-3 py-2 text-right text-xs text-slate-500">${fmtData(b.data_vencimento)}</td>
        <td class="px-3 py-2 text-right text-xs text-emerald-700">${fmtData(b.data_pagamento)}</td>
      </tr>
    `).join("");

    montarPaginacao(data);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="px-3 py-6 text-center text-rose-600">Erro: ${e.message}</td></tr>`;
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
  document.getElementById("f-mes").value = "";
  recarregar();
}

carregar();
