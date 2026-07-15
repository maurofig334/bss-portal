/* Tela de Benefícios (processos). */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let pagina = 1;
let timer = null;
let categoriaAtiva = "";

function fmtCPF(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length !== 11) return c;
  return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
}
function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }

function ler() {
  return {
    busca: document.getElementById("f-busca").value.trim(),
    status: document.getElementById("f-status").value,
    tipo: document.getElementById("f-tipo").value,
    status_categoria: categoriaAtiva,
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

const CATEGORIAS = [
  { codigo: "",           label: "Todos",         cor: "slate" },
  { codigo: "analise",    label: "Em análise",    cor: "indigo" },
  { codigo: "aprovacao",  label: "Aprovação",     cor: "blue" },
  { codigo: "bloqueio",   label: "Bloqueio",      cor: "amber" },
  { codigo: "autorizacao",label: "Autorizado",    cor: "emerald" },
  { codigo: "execucao",   label: "Execução",      cor: "purple" },
  { codigo: "terminal",   label: "Finalizados",   cor: "slate" },
];

function renderTabsCategoria() {
  const div = document.getElementById("categoria-tabs");
  div.innerHTML = CATEGORIAS.map(c => {
    const ativo = categoriaAtiva === c.codigo;
    return `
      <button onclick="setCategoria('${c.codigo}')"
              class="px-3 py-1 text-xs rounded-full border transition
                     ${ativo
                       ? `bg-${c.cor}-600 text-white border-${c.cor}-600`
                       : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"}">
        ${c.label}
      </button>`;
  }).join("");
}

function setCategoria(c) {
  categoriaAtiva = c;
  renderTabsCategoria();
  recarregar();
}

async function recarregar() { pagina = 1; await carregar(); }

async function carregar() {
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-6 text-center text-slate-400">Carregando…</td></tr>`;
  const t0 = performance.now();
  try {
    const data = await apiFetch(`/processos?${montarQuery()}`);
    const dur = (performance.now() - t0).toFixed(0);
    document.getElementById("tempo").textContent = `⚡ ${dur}ms`;
    document.getElementById("stats").textContent = `${data.total.toLocaleString("pt-BR")} benefícios encontrados`;

    if (!data.linhas.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-6 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }

    tbody.innerHTML = data.linhas.map(p => {
      const cor = p.status_cor || "#64748B";
      const semResposta = p.ultima_atualizacao_portal_em ? "🔔" : "";
      // (abrirProcesso está definido no fim do arquivo)
      return `
        <tr class="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" onclick="abrirProcesso(${p.id})">
          <td class="px-3 py-2 font-mono text-xs">${semResposta}
            <a href="/app/processo-detalhe.html?id=${p.id}" class="text-indigo-700 hover:underline" onclick="event.stopPropagation()">${p.protocolo || p.numero_processo || "—"}</a>
          </td>
          <td class="px-3 py-2">
            <div class="font-medium text-slate-900">${p.trabalhador_nome || "—"}</div>
            <div class="text-[11px] text-slate-500 font-mono">${fmtCPF(p.trabalhador_cpf)}</div>
          </td>
          <td class="px-3 py-2 text-slate-700">${p.tipo_beneficio || "—"}</td>
          <td class="px-3 py-2 text-slate-600 text-xs">${p.empresa || "—"}</td>
          <td class="px-3 py-2 text-slate-600 text-xs">${p.sindicato || "—"}</td>
          <td class="px-3 py-2 text-center">
            <span class="inline-block px-2 py-0.5 rounded-full text-xs"
                  style="background-color: ${cor}1A; color: ${cor};">
              ${p.status_nome || p.status}
            </span>
          </td>
          <td class="px-3 py-2 text-right text-xs text-slate-500">${fmtData(p.data_evento)}</td>
          <td class="px-3 py-2 text-right text-xs text-slate-500">${fmtData(p.data_finalizacao)}</td>
        </tr>`;
    }).join("");

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
function abrirProcesso(id) { window.location.href = `/app/processo-detalhe.html?id=${id}`; }
function agendarBusca() { clearTimeout(timer); timer = setTimeout(recarregar, 300); }
function limparFiltros() {
  document.getElementById("f-busca").value = "";
  document.getElementById("f-status").value = "";
  document.getElementById("f-tipo").value = "";
  categoriaAtiva = "";
  renderTabsCategoria();
  recarregar();
}

renderTabsCategoria();
carregar();
