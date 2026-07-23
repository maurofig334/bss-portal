/* Tela de Boletos — listagem + emissão (épico #21). */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

// Internos/admin podem ver cancelados via checkbox:
const PERFIS_INTERNOS = ["admin", "interno", "analista"];
if (u && PERFIS_INTERNOS.includes(u.perfil)) {
  document.getElementById("wrap-cancelados").classList.remove("hidden");
}
// Botão "Gerar Boletos por CNPJ" — pra todos com permissão de emissão:
//   - empresa: agrupamento automático em todos os CNPJs do escopo
//   - admin/interno: abre modal pedindo a empresa específica antes
const PERFIS_EMISSAO = ["admin", "interno", "empresa"];
if (u && !PERFIS_EMISSAO.includes(u.perfil)) {
  document.getElementById("btn-gerar").classList.add("hidden");
}
// Rótulo do botão muda conforme perfil:
if (u && u.perfil === "empresa") {
  document.getElementById("btn-gerar").innerHTML = "⬆ Gerar Boletos por CNPJ";
} else if (u && PERFIS_EMISSAO.includes(u.perfil)) {
  document.getElementById("btn-gerar").innerHTML = "⬆ Gerar Boletos (por empresa)";
}

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

// Mapping DB → UI label
const STATUS_LABEL = {
  gerado: "Aberto",
  pago: "Pago",
  vencido: "Vencido",
  cancelado: "Cancelado",
  pendente: "Pendente",
};
function badgeStatus(s) {
  const cores = {
    gerado: "bg-blue-100 text-blue-800",       // Aberto
    pago: "bg-emerald-100 text-emerald-800",
    vencido: "bg-rose-100 text-rose-800",
    pendente: "bg-amber-100 text-amber-800",
    cancelado: "bg-slate-200 text-slate-500 line-through",
  };
  const label = STATUS_LABEL[s] || s || "—";
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cores[s] || "bg-slate-100 text-slate-600"}">${label}</span>`;
}

// Botão de PDF do boleto conforme status:
function botaoBoleto(b) {
  if (b.status === "gerado" || b.status === "pendente") {
    return `<button onclick="abrirBoletoPdf(${b.id})" class="inline-block px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded">Download</button>`;
  }
  if (b.status === "vencido") {
    return `<button onclick="reemitir(${b.id})" class="inline-block px-3 py-1 text-xs bg-amber-600 hover:bg-amber-700 text-white rounded">Reemitir</button>`;
  }
  // pago / cancelado:
  return `<span class="text-xs text-slate-400">—</span>`;
}

function botaoLista(b) {
  if (b.status === "cancelado" || b.status === "pago") {
    return `<span class="text-xs text-slate-400">—</span>`;
  }
  return `<button onclick="abrirListaPdf(${b.id})" class="inline-block px-3 py-1 text-xs bg-slate-600 hover:bg-slate-700 text-white rounded">Lista</button>`;
}

async function abrirBoletoPdf(id) {
  try { await apiAbrirPdf(`/boletos/${id}/pdf`); }
  catch (e) { alert(`Erro: ${e.message}`); }
}
async function abrirListaPdf(id) {
  try { await apiAbrirPdf(`/boletos/${id}/lista-pdf`); }
  catch (e) { alert(`Erro: ${e.message}`); }
}

function ler() {
  return {
    busca: document.getElementById("f-busca").value.trim(),
    status: document.getElementById("f-status").value,
    mes_referencia: document.getElementById("f-mes").value,
    incluir_cancelados: document.getElementById("f-cancelados")?.checked ? "true" : "",
  };
}

function montarQuery() {
  const f = { ...ler(), pagina, por_pagina: 50 };
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (v !== "" && v != null) params.append(k, v);
  }
  // Perfil empresa: sem isto o backend cai em usuario.empresas[0] e mostra os
  // boletos de UMA das N empresas do usuário. No-op pra perfis internos.
  comEmpresaAtual(params);
  return params.toString();
}

async function recarregar() { pagina = 1; await carregar(); }

async function carregar() {
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = `<tr><td colspan="10" class="px-3 py-6 text-center text-slate-400">Carregando…</td></tr>`;
  const t0 = performance.now();
  try {
    const data = await apiFetch(`/boletos?${montarQuery()}`);
    const dur = (performance.now() - t0).toFixed(0);
    document.getElementById("tempo").textContent = `⚡ ${dur}ms`;
    document.getElementById("stats").textContent = `${data.total.toLocaleString("pt-BR")} boletos encontrados`;

    if (!data.linhas.length) {
      tbody.innerHTML = `<tr><td colspan="10" class="px-3 py-6 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }

    tbody.innerHTML = data.linhas.map(b => `
      <tr class="border-t border-slate-100 hover:bg-slate-50">
        <td class="px-3 py-2 font-mono text-xs">
          <a href="/app/boleto-detalhe.html?id=${b.id}" class="text-indigo-700 hover:underline">${b.nosso_numero || b.numero_boleto || "—"}</a>
        </td>
        <td class="px-3 py-2 font-medium text-slate-900">${b.empresa || "—"}</td>
        <td class="px-3 py-2 text-slate-600 text-xs">${b.sindicato || "—"}</td>
        <td class="px-3 py-2 text-center">${fmtMes(b.mes_referencia)}</td>
        <td class="px-3 py-2 text-right font-mono">${(b.qtd_trabalhadores || 0).toLocaleString("pt-BR")}</td>
        <td class="px-3 py-2 text-right font-mono">${brl(b.valor_total)}</td>
        <td class="px-3 py-2 text-center">${badgeStatus(b.status)}</td>
        <td class="px-3 py-2 text-right text-xs text-slate-500">${fmtData(b.data_vencimento)}</td>
        <td class="px-3 py-2 text-center">${botaoBoleto(b)}</td>
        <td class="px-3 py-2 text-center">${botaoLista(b)}</td>
      </tr>
    `).join("");

    montarPaginacao(data);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="10" class="px-3 py-6 text-center text-rose-600">Erro: ${e.message}</td></tr>`;
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
  if (document.getElementById("f-cancelados")) document.getElementById("f-cancelados").checked = false;
  recarregar();
}

// =============================================================================
// Reemissão (botão na grid)
// =============================================================================

async function reemitir(idBoleto) {
  if (!confirm(`Reemitir este boleto?\n\nO atual será CANCELADO e um novo será emitido com nova data de vencimento.`)) return;
  try {
    const r = await apiFetch(`/boletos/${idBoleto}/reemitir`, { method: "POST" });
    alert(`Boleto reemitido. Novo nosso_numero: ${r.nosso_numero}\nVencimento: ${fmtData(r.data_vencimento)}`);
    carregar();
  } catch (e) {
    alert(`Erro: ${e.message}`);
  }
}

// =============================================================================
// Modal de emissão (preview + confirmação + downloads)
// =============================================================================

let _previewCache = null;
let _empresaSelecionadaId = null;
const PERFIL_EMPRESA = u && u.perfil === "empresa";

function abrirModalEmissao() {
  document.getElementById("modal-emissao").classList.remove("hidden");
  document.getElementById("modal-emissao").classList.add("flex");
  document.getElementById("modal-loading").classList.remove("hidden");
  document.getElementById("modal-conteudo").classList.add("hidden");
  document.getElementById("btn-confirmar").classList.add("hidden");

  if (PERFIL_EMPRESA) {
    // Empresa: carrega tudo direto.
    carregarPreview(null);
  } else {
    // Interno: precisa selecionar empresa primeiro.
    _empresaSelecionadaId = null;
    renderSeletorEmpresa();
  }
}

function fecharModalEmissao() {
  document.getElementById("modal-emissao").classList.add("hidden");
  document.getElementById("modal-emissao").classList.remove("flex");
  _previewCache = null;
  _empresaSelecionadaId = null;
}

function renderSeletorEmpresa() {
  document.getElementById("modal-loading").classList.add("hidden");
  const div = document.getElementById("modal-conteudo");
  div.classList.remove("hidden");
  div.innerHTML = `
    <div class="space-y-4">
      <div class="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-900">
        <b>Perfil interno:</b> selecione a empresa pra ver o preview e gerar boletos.
        A geração massiva por todas as empresas é exclusiva pro perfil "empresa".
      </div>
      <div>
        <label class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Buscar empresa (nome ou CNPJ)</label>
        <input id="busca-empresa" type="text" placeholder="Digite pelo menos 3 caracteres…"
               class="mt-1 w-full px-3 py-2 border border-slate-300 rounded-lg"
               oninput="agendarBuscaEmpresa()">
        <div id="resultado-busca" class="mt-2 max-h-72 overflow-y-auto"></div>
      </div>
    </div>
  `;
  document.getElementById("modal-rodape-info").innerHTML = "";
  setTimeout(() => document.getElementById("busca-empresa")?.focus(), 50);
}

let _timerBuscaEmp = null;
function agendarBuscaEmpresa() {
  clearTimeout(_timerBuscaEmp);
  _timerBuscaEmp = setTimeout(buscarEmpresa, 300);
}
async function buscarEmpresa() {
  const q = document.getElementById("busca-empresa")?.value.trim() || "";
  const div = document.getElementById("resultado-busca");
  if (q.length < 3) { div.innerHTML = ""; return; }
  div.innerHTML = `<div class="text-xs text-slate-400 px-2 py-1">Buscando…</div>`;
  try {
    const data = await apiFetch(`/empresas?busca=${encodeURIComponent(q)}&por_pagina=20`);
    if (!data.linhas || !data.linhas.length) {
      div.innerHTML = `<div class="text-xs text-slate-400 px-2 py-2">Nenhuma empresa encontrada</div>`;
      return;
    }
    div.innerHTML = data.linhas.map(e => `
      <button type="button" onclick="selecionarEmpresa(${e.id}, '${(e.razao_social || '').replace(/'/g, "\\'")}')"
              class="w-full text-left px-3 py-2 border border-slate-200 rounded mb-1 hover:bg-blue-50 hover:border-blue-300">
        <div class="font-medium text-slate-800">${e.razao_social || ""}</div>
        <div class="text-xs text-slate-500 font-mono">${e.cnpj || ""}</div>
      </button>
    `).join("");
  } catch (e) {
    div.innerHTML = `<div class="text-xs text-rose-600">Erro: ${e.message}</div>`;
  }
}
function selecionarEmpresa(id, _nome) {
  _empresaSelecionadaId = id;
  document.getElementById("modal-loading").innerHTML = `<div class="text-center text-slate-500 py-12">Carregando preview…</div>`;
  document.getElementById("modal-loading").classList.remove("hidden");
  document.getElementById("modal-conteudo").classList.add("hidden");
  carregarPreview(id);
}

async function carregarPreview(idEmpresa) {
  try {
    const url = idEmpresa
      ? `/boletos/emissao/preview?id_empresa=${idEmpresa}`
      : `/boletos/emissao/preview`;
    const data = await apiFetch(url);
    _previewCache = data;
    renderPreview(data);
  } catch (e) {
    document.getElementById("modal-loading").innerHTML = `<div class="text-rose-600 text-center py-8">Erro: ${e.message}</div>`;
  }
}

function renderPreview(data) {
  document.getElementById("modal-loading").classList.add("hidden");
  document.getElementById("modal-conteudo").classList.remove("hidden");
  const div = document.getElementById("modal-conteudo");

  if (!data.empresas || !data.empresas.length) {
    div.innerHTML = `
      <div class="text-center text-slate-500 py-12">
        <div class="text-2xl mb-2">📭</div>
        <div>Nenhuma empresa com trabalhadores ativos no seu escopo.</div>
        <div class="text-xs mt-2">Mês de Amparo: <b>${data.mes_amparo || "—"}</b></div>
      </div>`;
    return;
  }

  // Marca todas as empresas que ainda têm sindicatos sem boleto:
  _empresasSelecionadas = new Set();
  data.empresas.forEach(e => {
    if (e.sindicatos.some(s => !s.ja_tem_boleto && s.qtd_titulares + s.qtd_dependentes > 0)) {
      _empresasSelecionadas.add(e.id);
    }
  });

  let totalEstimado = 0;
  let totalSindicatos = 0;
  let totalNovosTrabs = 0;
  data.empresas.forEach(e => {
    e.sindicatos.forEach(s => {
      const novos = s.qtd_titulares + s.qtd_dependentes;
      if (novos > 0) {
        totalEstimado += s.valor_estimado;
        totalSindicatos++;
        totalNovosTrabs += novos;
      }
    });
  });

  const aviso = `
    <div class="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-900">
      <b>⚠ Atenção:</b> faça a manutenção da sua base de Trabalhadores / Dependentes
      antes de gerar os boletos. Carregar / Inativar / Adicionar dependentes — qualquer
      alteração que precise ser feita.
    </div>
  `;

  const cabecalho = `
    <div class="grid grid-cols-3 gap-3 mb-4">
      <div class="p-3 bg-slate-50 rounded border border-slate-200">
        <div class="text-xs text-slate-500 uppercase">Mês de Amparo</div>
        <div class="text-lg font-semibold text-slate-800">${data.mes_amparo}</div>
      </div>
      <div class="p-3 bg-slate-50 rounded border border-slate-200">
        <div class="text-xs text-slate-500 uppercase">Competência</div>
        <div class="text-lg font-semibold text-slate-800">${data.competencia}</div>
      </div>
      <div class="p-3 bg-emerald-50 rounded border border-emerald-200">
        <div class="text-xs text-emerald-700 uppercase">A gerar agora</div>
        <div class="text-lg font-semibold text-emerald-800">${brl(totalEstimado)}</div>
        <div class="text-xs text-emerald-700">${totalSindicatos} boleto(s) · ${totalNovosTrabs} trabalhador(es)</div>
      </div>
    </div>
  `;

  // Renderiza accordion de empresas:
  const empresas = data.empresas.map(e => renderEmpresa(e)).join("");

  div.innerHTML = aviso + cabecalho + `<div class="space-y-2">${empresas}</div>`;

  // Mostra botão confirmar:
  if (totalSindicatos > 0) {
    document.getElementById("btn-confirmar").classList.remove("hidden");
    document.getElementById("modal-rodape-info").innerHTML =
      `Pronto pra gerar <b>${totalSindicatos}</b> boleto(s) totalizando <b>${brl(totalEstimado)}</b>`;
  } else {
    document.getElementById("modal-rodape-info").innerHTML =
      `<span class="text-amber-700">Nenhum boleto pendente de geração — todos os sindicatos já têm boleto vivo.</span>`;
  }
}

function renderEmpresa(e) {
  const totalAtivos = e.qtd_ativos_total;
  const sindLinhas = e.sindicatos.map(s => {
    const valor = s.valor_estimado;
    const totalNovos = s.qtd_titulares + s.qtd_dependentes;
    const totalCobertos = (s.qtd_titulares_cobertos || 0) + (s.qtd_dependentes_cobertos || 0);
    // Cor da borda: verde = tem novos pra emitir; cinza = tudo coberto; âmbar = tem boleto + também novos
    let cor = "border-slate-300 bg-slate-50";
    if (totalNovos > 0 && s.ja_tem_boleto) cor = "border-amber-400 bg-amber-50/50";
    else if (totalNovos > 0) cor = "border-emerald-400";
    else if (s.ja_tem_boleto) cor = "border-blue-300 bg-blue-50/30";

    const trabs = s.trabalhadores.map(t => `
      <tr class="text-xs">
        <td class="px-2 py-1">${t.nome}</td>
        <td class="px-2 py-1 font-mono">${t.cpf}</td>
        <td class="px-2 py-1 text-slate-500">${t.tipo}</td>
      </tr>
    `).join("");
    const trabsCobertos = (s.trabalhadores_cobertos || []).map(t => `
      <tr class="text-xs text-slate-400">
        <td class="px-2 py-1">${t.nome}</td>
        <td class="px-2 py-1 font-mono">${t.cpf}</td>
        <td class="px-2 py-1">${t.tipo}</td>
      </tr>
    `).join("");

    let badgeStatus = "";
    if (s.ja_tem_boleto) {
      badgeStatus = `<span class="ml-2 px-2 py-0.5 bg-blue-100 text-blue-800 rounded text-xs">${s.qtd_boletos_existentes} boleto(s) já gerado(s)</span>`;
    }
    let badgeAcao = "";
    if (totalNovos > 0) {
      badgeAcao = `<span class="ml-2 px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded text-xs font-semibold">+${totalNovos} a gerar</span>`;
    } else {
      badgeAcao = `<span class="ml-2 px-2 py-0.5 bg-slate-200 text-slate-500 rounded text-xs">sem novos</span>`;
    }

    return `
      <div class="border-l-2 ${cor} pl-3 py-2 ml-4">
        <div class="flex items-center justify-between text-sm">
          <div>
            <span class="font-medium">${s.razao_social}</span>
            <span class="text-xs text-slate-500 ml-2">${s.parametro_nome || ""}</span>
            ${badgeStatus}${badgeAcao}
          </div>
          <div class="text-right">
            <div class="font-mono">${brl(valor)}</div>
            <div class="text-xs text-slate-500">
              ${totalNovos > 0
                ? `${s.qtd_titulares} tit${s.qtd_dependentes ? " + " + s.qtd_dependentes + " dep" : ""} novo(s)`
                : `<span class="text-slate-400">${totalCobertos} já em boleto</span>`}
            </div>
          </div>
        </div>
        ${totalNovos > 0 ? `
          <details class="mt-1">
            <summary class="text-xs text-emerald-700 cursor-pointer hover:text-emerald-900">Ver os ${totalNovos} novos a gerar</summary>
            <table class="mt-1 w-full text-xs">
              <thead class="bg-emerald-50 text-emerald-700 uppercase tracking-wider">
                <tr><th class="px-2 py-1 text-left">Nome</th><th class="px-2 py-1 text-left">CPF</th><th class="px-2 py-1 text-left">Tipo</th></tr>
              </thead>
              <tbody>${trabs}</tbody>
            </table>
          </details>` : ""}
        ${totalCobertos > 0 ? `
          <details class="mt-1">
            <summary class="text-xs text-slate-500 cursor-pointer hover:text-slate-700">Ver os ${totalCobertos} já cobertos por boleto vivo</summary>
            <table class="mt-1 w-full text-xs">
              <thead class="bg-slate-100 text-slate-500 uppercase tracking-wider">
                <tr><th class="px-2 py-1 text-left">Nome</th><th class="px-2 py-1 text-left">CPF</th><th class="px-2 py-1 text-left">Tipo</th></tr>
              </thead>
              <tbody>${trabsCobertos}</tbody>
            </table>
          </details>` : ""}
      </div>
    `;
  }).join("");

  return `
    <details open class="border border-slate-200 rounded-lg overflow-hidden">
      <summary class="px-3 py-2 bg-slate-50 cursor-pointer hover:bg-slate-100 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="font-semibold text-slate-800">${e.razao_social}</span>
          <span class="text-xs text-slate-500 font-mono">${e.cnpj || ""}</span>
        </div>
        <span class="text-xs text-slate-600">${totalAtivos} ativos · ${e.sindicatos.length} sindicato(s)</span>
      </summary>
      <div class="p-2 bg-white">${sindLinhas}</div>
    </details>
  `;
}

async function confirmarEmissao() {
  if (!confirm("Confirma a geração dos boletos?\n\nTrabalhadores já cobertos por boletos vivos serão ignorados (regra delta).")) return;

  document.getElementById("btn-confirmar").disabled = true;
  document.getElementById("btn-confirmar").textContent = "Gerando…";
  try {
    // Empresa: backend usa todas as empresas do usuário (body vazio).
    // Interno: tem que mandar ids_empresa = [empresa selecionada].
    const body = PERFIL_EMPRESA
      ? null
      : JSON.stringify({ ids_empresa: [_empresaSelecionadaId] });

    const r = await apiFetch(`/boletos/emissao/emitir`, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body,
    });
    renderResultadoEmissao(r);
    carregar();  // refresh da grid principal
  } catch (e) {
    alert(`Erro: ${e.message}`);
  } finally {
    document.getElementById("btn-confirmar").disabled = false;
    document.getElementById("btn-confirmar").textContent = "Gerar Boleto";
  }
}

function renderResultadoEmissao(r) {
  const div = document.getElementById("modal-conteudo");
  document.getElementById("btn-confirmar").classList.add("hidden");
  document.getElementById("modal-rodape-info").innerHTML = "";

  const gerados = r.gerados || [];
  const pulados = r.pulados || [];
  const erros = r.erros || [];

  let html = `
    <div class="space-y-4">
      <div class="p-3 bg-emerald-50 border border-emerald-200 rounded text-emerald-900">
        <b>✅ ${gerados.length}</b> boleto(s) gerado(s) com sucesso
      </div>
  `;

  if (gerados.length) {
    html += `
      <div>
        <h3 class="font-semibold text-slate-800 mb-2">Boletos gerados — clique para baixar:</h3>
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-xs text-slate-600 uppercase tracking-wider">
            <tr>
              <th class="px-3 py-2 text-left">Empresa</th>
              <th class="px-3 py-2 text-left">Sindicato</th>
              <th class="px-3 py-2 text-right">Valor</th>
              <th class="px-3 py-2 text-center">Boleto</th>
              <th class="px-3 py-2 text-center">Lista</th>
            </tr>
          </thead>
          <tbody>
    `;
    for (const g of gerados) {
      html += `
        <tr class="border-t border-slate-100">
          <td class="px-3 py-2 font-medium">${g.empresa}</td>
          <td class="px-3 py-2 text-xs text-slate-600">${g.sindicato}</td>
          <td class="px-3 py-2 text-right font-mono">${brl(g.valor_total)}</td>
          <td class="px-3 py-2 text-center"><button onclick="abrirBoletoPdf(${g.id_boleto})" class="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded">Boleto</button></td>
          <td class="px-3 py-2 text-center"><button onclick="abrirListaPdf(${g.id_boleto})" class="px-2 py-1 text-xs bg-slate-600 hover:bg-slate-700 text-white rounded">Lista</button></td>
        </tr>
      `;
    }
    html += `</tbody></table></div>`;
  }

  if (pulados.length) {
    html += `
      <div class="p-3 bg-amber-50 border border-amber-200 rounded">
        <h3 class="font-semibold text-amber-900 mb-2">⚠ ${pulados.length} pulado(s) (já existiam):</h3>
        <ul class="text-xs text-amber-900 space-y-1">
          ${pulados.map(p => `<li>${p.empresa} × ${p.sindicato} — ${p.motivo}</li>`).join("")}
        </ul>
      </div>
    `;
  }

  if (erros.length) {
    html += `
      <div class="p-3 bg-rose-50 border border-rose-200 rounded">
        <h3 class="font-semibold text-rose-900 mb-2">❌ ${erros.length} erro(s):</h3>
        <ul class="text-xs text-rose-900 space-y-1">
          ${erros.map(e => `<li>${e.empresa || ""} ${e.sindicato ? "× " + e.sindicato : ""} — ${e.motivo}</li>`).join("")}
        </ul>
      </div>
    `;
  }

  html += `</div>`;
  div.innerHTML = html;
}

// Seletor de empresa (só pro perfil 'empresa' com +1 CNPJ) — ver empresa-atual.js
montarSeletorEmpresa("#seletor-empresa", recarregar);
carregar();

// ?emitir=1 — chegou aqui vindo da carga de trabalhadores (trabalhadores.js).
// Abre o modal de emissão direto, pra empresa conferir e gerar os boletos.
// Limpa o parâmetro da URL pra um F5 não reabrir o modal sem querer.
if (new URLSearchParams(location.search).get("emitir") === "1") {
  history.replaceState(null, "", "/app/boletos.html");
  // Pequeno atraso: deixa a listagem e o seletor montarem antes do modal.
  setTimeout(abrirModalEmissao, 300);
}
