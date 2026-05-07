/* Tela de listagem de sindicatos. */

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

function fmtNum(n) {
  if (n == null) return "0";
  return Number(n).toLocaleString("pt-BR");
}

function fmtMoeda(v) {
  if (v == null) return "—";
  return Number(v).toLocaleString("pt-BR", {
    style: "currency", currency: "BRL", minimumFractionDigits: 2,
  });
}

function ler() {
  return {
    busca: document.getElementById("f-busca").value.trim(),
    em_atendimento: document.getElementById("f-atend").value,
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
    const data = await apiFetch(`/sindicatos?${montarQuery()}`);
    const dur = (performance.now() - t0).toFixed(0);
    document.getElementById("tempo").textContent = `⚡ ${dur}ms`;
    document.getElementById("stats").textContent = `${data.total.toLocaleString("pt-BR")} sindicatos encontrados`;

    if (!data.linhas.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="px-3 py-6 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }

    tbody.innerHTML = data.linhas.map(s => {
      // Coluna Parâmetro: nome do parâmetro (legado) + sub com tarifa/benefícios
      let paramCell = '<span class="text-slate-400">—</span>';
      if (s.tem_parametro) {
        const nome = s.parametro_nome || '<span class="text-slate-400">(sem nome)</span>';
        const tarifa = s.tarifa_titular != null ? fmtMoeda(s.tarifa_titular) : null;
        const qtd = s.qtd_tipos_beneficio || 0;
        const partes = [];
        if (tarifa) partes.push(tarifa);
        if (qtd > 0) partes.push(`${qtd} benefício${qtd > 1 ? "s" : ""}`);
        const sub = partes.length
          ? `<span class="block text-[10px] text-slate-500">${partes.join(" · ")}</span>`
          : "";
        paramCell = `<div class="leading-tight"><span class="text-indigo-700">${nome}</span>${sub}</div>`;
      }

      // Coluna Tipo de Sindicato: FEMACO ou NÃO FEMACO (badge)
      const eh_femaco = s.tipo_sindicato === "FEMACO";
      const tipoCell = eh_femaco
        ? `<span class="inline-block px-2 py-0.5 rounded-full text-xs bg-indigo-100 text-indigo-800">FEMACO</span>`
        : `<span class="inline-block px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600">NÃO FEMACO</span>`;

      const nomeExibir = s.razao_social || s.nome_fantasia || "—";
      const subNome = s.nome_fantasia && s.nome_fantasia !== s.razao_social
        ? `<span class="block text-[10px] text-slate-500">${s.nome_fantasia}</span>`
        : "";

      return `
        <tr class="border-t border-slate-100 hover:bg-slate-50">
          <td class="px-3 py-2 font-medium text-slate-900">${nomeExibir}${subNome}</td>
          <td class="px-3 py-2 text-center text-slate-600 font-mono text-xs">${s.uf_abrangencia || "—"}</td>
          <td class="px-3 py-2 text-right font-mono">${fmtNum(s.qtd_trabalhadores_ativos)}</td>
          <td class="px-3 py-2 text-right font-mono text-slate-500">${fmtNum(s.qtd_trabalhadores_inativos)}</td>
          <td class="px-3 py-2">${paramCell}</td>
          <td class="px-3 py-2 font-mono text-xs">${fmtCNPJ(s.cnpj)}</td>
          <td class="px-3 py-2 text-slate-600 text-xs">${s.categoria || "—"}</td>
          <td class="px-3 py-2 text-center">${tipoCell}</td>
          <td class="px-3 py-2 text-slate-600 text-xs">${s.federacao || "—"}</td>
        </tr>
      `;
    }).join("");

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
  document.getElementById("f-atend").value = "";
  recarregar();
}

carregar();
