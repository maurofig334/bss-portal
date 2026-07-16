/* Listagem de Contatos — usuários externos que administram empresas.
 * Padrão OCSP, reusando o grid-utils.js. Ver docs/AUTOCADASTRO.md.
 */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

const TELA = "contatos";
const ALINHA = { left: "text-left", center: "text-center", right: "text-right" };

let pagina = 1;
let timer = null;
let ordenacao = { campo: "nome", desc: false };
let colsOcultas = gridLerColunasOcultas(TELA);

/* ------------------------------- helpers -------------------------------- */

function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtDataHora(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function pill(txt, cls) {
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cls}">${txt}</span>`;
}

function badgeAtivo(a) {
  return a ? pill("ativo", "bg-emerald-100 text-emerald-800")
           : pill("inativo", "bg-slate-200 text-slate-600");
}
function badgeTipo(t) {
  return t === "auto" ? pill("autocadastro", "bg-indigo-100 text-indigo-800")
                      : pill("interno", "bg-slate-100 text-slate-600");
}
// E-mail sintético do sync: contato sem login (ficha de telefone/endereço)
function ehSemEmail(email) { return (email || "").endsWith("@contato.invalid"); }

/* ------------------------------- colunas -------------------------------- */

const COLUNAS = [
  { id: "nome", label: "Nome", align: "left", sort: "nome", fixa: true,
    render: c => `<a href="/app/contato-detalhe.html?id=${c.id}" class="text-indigo-700 hover:underline font-medium" onclick="event.stopPropagation()">${c.nome || "—"}</a>` },
  { id: "email", label: "E-mail (login)", align: "left", sort: "email",
    render: c => ehSemEmail(c.email)
      ? `<span class="text-slate-400 italic text-xs" title="Contato sem e-mail no legado — não é usuário do portal">sem e-mail</span>`
      : `<span class="text-xs text-slate-600">${c.email}</span>` },
  { id: "telefone", label: "Telefone", align: "left", sort: null,
    render: c => `<span class="text-xs text-slate-600">${c.telefone || "—"}</span>` },
  { id: "empresas", label: "Empresas", align: "right", sort: "qtd_empresas",
    render: c => {
      const n = c.qtd_empresas || 0;
      // O legado mostra 1 empresa por contato. Aqui aparece o número real —
      // tem gente com 54. Destaque quando for além do trivial.
      const cls = n > 5 ? "font-semibold text-indigo-700" : n === 0 ? "text-slate-300" : "text-slate-700";
      return `<span class="font-mono ${cls}">${n}</span>`;
    } },
  { id: "tipo", label: "Cadastro", align: "center", sort: null,
    render: c => badgeTipo(c.tipo_cadastro) },
  { id: "ativo", label: "Situação", align: "center", sort: "ativo",
    render: c => badgeAtivo(c.ativo) },
  { id: "criado", label: "Cadastrado em", align: "right", sort: "criado_em",
    render: c => `<span class="text-xs text-slate-500">${fmtData(c.criado_em)}</span>` },
  { id: "ultimo_login", label: "Último acesso", align: "right", sort: "ultimo_login",
    render: c => `<span class="text-xs text-slate-500">${c.ultimo_login ? fmtDataHora(c.ultimo_login) : "nunca"}</span>` },
];

function colsVisiveis() { return COLUNAS.filter(c => !colsOcultas.includes(c.id)); }

/* -------------------------------- grid ---------------------------------- */

function montarQuery() {
  const p = new URLSearchParams();
  const busca = document.getElementById("f-busca").value.trim();
  if (busca) p.append("busca", busca);
  const tipo = document.getElementById("f-tipo").value;
  if (tipo) p.append("tipo_cadastro", tipo);
  const ativo = document.getElementById("f-ativo").value;
  if (ativo) p.append("ativo", ativo);
  p.append("ordem", ordenacao.campo);
  if (ordenacao.desc) p.append("desc", "true");
  p.append("pagina", pagina);
  p.append("por_pagina", 50);
  return p.toString();
}

function renderThead() {
  document.getElementById("thead-row").innerHTML = colsVisiveis().map(c => {
    const cls = `px-3 py-2 ${ALINHA[c.align]} ${c.sort ? "cursor-pointer select-none hover:text-slate-700" : ""}`;
    const seta = c.sort ? gridSeta(c.sort, ordenacao) : "";
    const onclick = c.sort ? `onclick="ordenarPor('${c.sort}')"` : "";
    return `<th class="${cls}" ${onclick}>${c.label}${seta}</th>`;
  }).join("");
}

function renderLinhas(linhas) {
  const cols = colsVisiveis();
  document.getElementById("tbody").innerHTML = linhas.map(c => `
    <tr class="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" onclick="abrirContato(${c.id})">
      ${cols.map(col => `<td class="px-3 py-2 ${ALINHA[col.align]}">${col.render(c)}</td>`).join("")}
    </tr>`).join("");
}

function abrirContato(id) { window.location.href = `/app/contato-detalhe.html?id=${id}`; }

function ordenarPor(campo) {
  if (ordenacao.campo === campo) ordenacao.desc = !ordenacao.desc;
  else ordenacao = { campo, desc: false };
  carregar();
}

function abrirColunas() {
  gridAbrirModalColunas({
    colunas: COLUNAS.map(c => ({ id: c.id, label: c.label, fixa: c.fixa })),
    ocultas: colsOcultas,
    onSalvar: (novas) => {
      colsOcultas = novas;
      gridSalvarColunasOcultas(TELA, novas);
      renderThead();
      carregar();
    },
  });
}

async function recarregar() { pagina = 1; await carregar(); }
function agendarBusca() { clearTimeout(timer); timer = setTimeout(recarregar, 300); }
function irPagina(p) { pagina = Math.max(1, p); carregar(); }

async function carregar() {
  renderThead();
  const tbody = document.getElementById("tbody");
  const n = colsVisiveis().length;
  tbody.innerHTML = `<tr><td colspan="${n}" class="px-3 py-6 text-center text-slate-400">Carregando…</td></tr>`;
  const t0 = performance.now();
  try {
    const data = await apiFetch(`/contatos?${montarQuery()}`);
    document.getElementById("tempo").textContent = `⚡ ${(performance.now() - t0).toFixed(0)}ms`;
    document.getElementById("subtitulo").textContent =
      `${data.total.toLocaleString("pt-BR")} contatos · clique numa linha para abrir`;
    if (!data.linhas.length) {
      tbody.innerHTML = `<tr><td colspan="${n}" class="px-3 py-10 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }
    renderLinhas(data.linhas);
    montarPaginacao(data);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="${n}" class="px-3 py-6 text-center text-rose-600">Erro: ${e.message}</td></tr>`;
  }
}

function montarPaginacao(data) {
  const div = document.getElementById("paginacao");
  if (data.paginas <= 1) { div.innerHTML = ""; return; }
  div.innerHTML = `
    <div class="text-slate-500">Página ${data.pagina} de ${data.paginas}</div>
    <div class="flex gap-2">
      <button onclick="irPagina(${pagina - 1})" ${pagina <= 1 ? "disabled" : ""}
              class="px-3 py-1 border rounded ${pagina <= 1 ? "text-slate-300" : "hover:bg-slate-100"}">‹ Anterior</button>
      <button onclick="irPagina(${pagina + 1})" ${pagina >= data.paginas ? "disabled" : ""}
              class="px-3 py-1 border rounded ${pagina >= data.paginas ? "text-slate-300" : "hover:bg-slate-100"}">Próxima ›</button>
    </div>`;
}

/* ------------------------------- sininho -------------------------------- */
// Solicitações de acesso aguardando análise. Todo contato novo passa por um
// analista interno — se ninguém olhar a fila, o cadastro morre esperando.
async function carregarSininho() {
  try {
    const d = await apiFetch("/contatos/pendentes/contagem");
    if (d.pendentes > 0) {
      document.getElementById("sininho").classList.remove("hidden");
      document.getElementById("sininho-badge").textContent = d.pendentes;
    }
  } catch (e) { /* silencioso: sininho não pode quebrar a tela */ }
}

carregar();
carregarSininho();
