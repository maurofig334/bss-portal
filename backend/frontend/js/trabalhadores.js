/* Tela de listagem de trabalhadores. */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let pagina = 1;
let timer = null;

function formatarCPF(cpf) {
  if (!cpf) return "—";
  const d = String(cpf).replace(/\D/g, "");
  if (d.length !== 11) return cpf;
  return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
}

function formatarData(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("pt-BR");
}

function badgeSituacao(s) {
  const cores = {
    ativo:    "bg-emerald-100 text-emerald-800",
    inativo:  "bg-slate-200 text-slate-700",
    carencia: "bg-amber-100 text-amber-800",
  };
  const cls = cores[s] || "bg-slate-100 text-slate-600";
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cls}">${s || "—"}</span>`;
}


// Cache de dependentes por CPF do titular (evita refetch em hovers repetidos)
const _depCache = new Map();

async function carregarDependentes(cpfTitular) {
  if (_depCache.has(cpfTitular)) return _depCache.get(cpfTitular);
  try {
    const lista = await apiFetch(`/trabalhadores/dependentes/${cpfTitular}`);
    _depCache.set(cpfTitular, lista);
    return lista;
  } catch (e) {
    return [];
  }
}

async function mostrarTooltipDependentes(ev, cpf, qtd) {
  const tt = document.getElementById("dep-tooltip");
  const conteudo = tt.querySelector(".tt-conteudo");
  conteudo.innerHTML = `<div class="text-xs text-slate-500 italic">Carregando…</div>`;
  tt.style.left = (ev.clientX + 12) + "px";
  tt.style.top  = (ev.clientY + 12) + "px";
  tt.classList.remove("hidden");
  const lista = await carregarDependentes(cpf);
  if (!lista.length) {
    conteudo.innerHTML = `<div class="text-xs text-slate-500">Sem dependentes cadastrados.</div>`;
    return;
  }
  const linhas = lista.map(d =>
    `<div class="text-xs text-slate-700 leading-tight">
      <span class="font-mono text-[10px] text-slate-500">${formatarCPF(d.cpf)}</span>
      <span class="ml-1">${d.nome_completo || "—"}</span>
    </div>`
  ).join("");
  conteudo.innerHTML = `
    <div class="text-[11px] font-semibold text-slate-600 mb-1">${qtd} dependente${qtd > 1 ? "s" : ""}</div>
    ${linhas}
  `;
}

function esconderTooltip() {
  const tt = document.getElementById("dep-tooltip");
  if (tt) tt.classList.add("hidden");
}

function badgeTit(t) {
  if (t.titularidade === "dependente") {
    const titulo = t.cpf_titular ? `Dependente de ${formatarCPF(t.cpf_titular)}` : "Dependente";
    return `<span class="inline-block w-6 h-6 leading-6 rounded-full text-center text-xs font-bold bg-amber-100 text-amber-800" title="${titulo}">D</span>`;
  }
  // Titular: T com hover lista dependentes (se tiver)
  const qtd = t.qtd_dependentes_ativos || 0;
  if (qtd > 0) {
    return `<span class="inline-block w-6 h-6 leading-6 rounded-full text-center text-xs font-bold bg-indigo-100 text-indigo-800 cursor-help"
              onmouseenter="mostrarTooltipDependentes(event, '${t.cpf}', ${qtd})"
              onmousemove="(function(ev){const tt=document.getElementById('dep-tooltip');if(!tt.classList.contains('hidden')){tt.style.left=(ev.clientX+12)+'px';tt.style.top=(ev.clientY+12)+'px';}})(event)"
              onmouseleave="esconderTooltip()">T</span>`;
  }
  return `<span class="inline-block w-6 h-6 leading-6 rounded-full text-center text-xs font-bold bg-slate-100 text-slate-600" title="Titular sem dependentes">T</span>`;
}

// ==========================================================================
// Grid (padrão OCSP): colunas dinâmicas, ordenação server-side, filtros.
// ==========================================================================
const TELA = "trabalhadores";
const ALINHA = { left: "text-left", center: "text-center", right: "text-right" };

// Config de colunas. sort = chave aceita pelo ORDER BY do backend (ou null).
const COLUNAS = [
  { id: "tit", label: "Tit", align: "center", fixa: true, sort: null, render: badgeTit },
  { id: "cpf", label: "CPF", align: "left", sort: "cpf",
    render: t => `<span class="font-mono text-xs">${formatarCPF(t.cpf)}</span>` },
  { id: "nome", label: "Nome", align: "left", sort: "nome_completo",
    render: t => `<a href="/app/trabalhador-detalhe.html?id=${t.id}" class="text-indigo-700 hover:underline font-medium" onclick="event.stopPropagation()">${t.nome_completo || "—"}</a>` },
  { id: "empresa", label: "Empresa", align: "left", sort: "empresa",
    render: t => `<span class="text-slate-700">${t.empresa || "—"}</span>` },
  { id: "sindicato", label: "Sindicato", align: "left", sort: "sindicato",
    render: t => `<span class="text-xs text-slate-600">${t.sindicato || "—"}</span>` },
  { id: "uf", label: "UF", align: "center", sort: "trab_uf",
    render: t => t.trab_uf || "—" },
  { id: "situacao", label: "Situação", align: "center", sort: "situacao",
    render: t => badgeSituacao(t.situacao) },
  { id: "ultimo_pgto", label: "Último pgto", align: "right", sort: "ultimo_pagamento_em",
    render: t => `<span class="text-xs text-slate-500">${formatarData(t.ultimo_pagamento_em)}</span>` },
];

// Campos do Filtro avançado (Onda 1: mapeiam direto pros params do backend).
const FILTRO_CAMPOS = [
  { id: "situacao", label: "Situação", tipo: "select", operadores: ["é igual a"],
    opcoes: [{ value: "ativo", label: "Ativo" }, { value: "inativo", label: "Inativo" }, { value: "carencia", label: "Carência" }] },
  { id: "uf", label: "UF", tipo: "text", operadores: ["é igual a", "preenchido", "vazio"] },
];

let ordenacao = { campo: "nome_completo", desc: false };
let condicoes = [];                              // filtro avançado ativo
let colsOcultas = gridLerColunasOcultas(TELA);

function colsVisiveis() { return COLUNAS.filter(c => !colsOcultas.includes(c.id)); }

function condicoesParaParams(conds) {
  const p = {};
  for (const c of conds) {
    if (c.campo === "situacao" && c.operador === "é igual a" && c.valor) p.situacao = c.valor;
    if (c.campo === "uf") {
      if (c.operador === "é igual a" && c.valor) p.uf = String(c.valor).toUpperCase();
    }
  }
  return p;
}

function montarQuery() {
  const params = new URLSearchParams();
  const busca = document.getElementById("f-busca").value.trim();
  if (busca) params.append("busca", busca);

  const adv = condicoesParaParams(condicoes);
  const preset = document.getElementById("f-preset").value;
  const situacao = adv.situacao || preset;     // filtro avançado tem prioridade
  if (situacao) params.append("situacao", situacao);
  if (adv.uf) params.append("uf", adv.uf);

  params.append("ordem", ordenacao.campo);
  if (ordenacao.desc) params.append("desc", "true");
  params.append("pagina", pagina);
  params.append("por_pagina", 50);

  // Perfil empresa: manda a empresa escolhida no seletor. Sem isso o backend
  // cai em usuario.empresas[0] e o usuário vê UMA das suas N empresas, sem
  // saber qual nem como trocar. Não faz nada pra perfis internos.
  comEmpresaAtual(params);

  return params.toString();
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
  document.getElementById("tbody").innerHTML = linhas.map(t => `
    <tr class="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" onclick="abrirTrab(${t.id})">
      ${cols.map(c => `<td class="px-3 py-2 ${ALINHA[c.align]}">${c.render(t)}</td>`).join("")}
    </tr>`).join("");
}

function abrirTrab(id) { window.location.href = `/app/trabalhador-detalhe.html?id=${id}`; }

function ordenarPor(campo) {
  if (ordenacao.campo === campo) ordenacao.desc = !ordenacao.desc;
  else ordenacao = { campo, desc: false };
  carregar();
}

function abrirColunas() {
  gridAbrirModalColunas({
    colunas: COLUNAS.map(c => ({ id: c.id, label: c.label, fixa: c.fixa })),
    ocultas: colsOcultas,
    onSalvar: (novas) => { colsOcultas = novas; gridSalvarColunasOcultas(TELA, novas); renderThead(); carregar(); },
  });
}

function atualizarBadgeFiltro() {
  const b = document.getElementById("filtro-badge");
  if (condicoes.length) { b.textContent = condicoes.length; b.classList.remove("hidden"); }
  else b.classList.add("hidden");
}

function abrirFiltro() {
  gridAbrirModalFiltro({
    campos: FILTRO_CAMPOS,
    condicoes,
    onAplicar: (conds) => { condicoes = conds; atualizarBadgeFiltro(); recarregar(); },
    onSalvarComo: (nome, conds) => {
      const l = gridLerFiltrosSalvos(TELA); l.push({ nome, condicoes: conds });
      gridSalvarFiltrosSalvos(TELA, l);
      condicoes = conds; atualizarBadgeFiltro(); recarregar();
    },
  });
}

function abrirMeusFiltros(ev) {
  gridAbrirMeusFiltros({
    ancora: ev.currentTarget,
    lista: gridLerFiltrosSalvos(TELA),
    onAplicar: (conds) => { condicoes = conds; atualizarBadgeFiltro(); recarregar(); },
    onExcluir: (i) => { const l = gridLerFiltrosSalvos(TELA); l.splice(i, 1); gridSalvarFiltrosSalvos(TELA, l); },
  });
}

async function recarregar() {
  pagina = 1;
  await carregar();
}

async function carregar() {
  renderThead();
  const tbody = document.getElementById("tbody");
  const ncols = colsVisiveis().length;
  tbody.innerHTML = `<tr><td colspan="${ncols}" class="px-3 py-6 text-center text-slate-400">Carregando…</td></tr>`;
  document.getElementById("tempo").textContent = "";

  const t0 = performance.now();
  try {
    const data = await apiFetch(`/trabalhadores?${montarQuery()}`);
    const dur = (performance.now() - t0).toFixed(0);

    document.getElementById("tempo").textContent = `⚡ ${dur}ms`;
    document.getElementById("subtitulo").textContent =
      `${data.total.toLocaleString("pt-BR")} trabalhadores · clique numa linha para abrir`;

    if (data.linhas.length === 0) {
      tbody.innerHTML = `<tr><td colspan="${ncols}" class="px-3 py-10 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }
    renderLinhas(data.linhas);
    montarPaginacao(data);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="${ncols}" class="px-3 py-6 text-center text-rose-600">Erro: ${e.message}</td></tr>`;
  }
}

function montarPaginacao(data) {
  const div = document.getElementById("paginacao");
  if (data.paginas <= 1) {
    div.innerHTML = "";
    return;
  }
  div.innerHTML = `
    <div class="text-slate-500">Página ${data.pagina} de ${data.paginas}</div>
    <div class="flex gap-2">
      <button onclick="irPagina(${pagina - 1})" ${pagina <= 1 ? "disabled" : ""}
              class="px-3 py-1 border rounded ${pagina <= 1 ? "text-slate-300" : "hover:bg-slate-100"}">‹ Anterior</button>
      <button onclick="irPagina(${pagina + 1})" ${pagina >= data.paginas ? "disabled" : ""}
              class="px-3 py-1 border rounded ${pagina >= data.paginas ? "text-slate-300" : "hover:bg-slate-100"}">Próxima ›</button>
    </div>
  `;
}

function irPagina(p) {
  pagina = Math.max(1, p);
  carregar();
}

function agendarBusca() {
  // Debounce: aguarda 300ms sem digitar pra rodar
  clearTimeout(timer);
  timer = setTimeout(recarregar, 300);
}

function limparFiltros() {
  document.getElementById("f-busca").value = "";
  condicoes = [];
  atualizarBadgeFiltro();
  document.getElementById("f-preset").value = "ativo";
  recarregar();
}

// Carga inicial
atualizarBadgeFiltro();


// ==========================
// Upload de planilha (3 modos: carregar / inativar / dependentes)
// ==========================
const UPLOAD_MODOS = {
  carregar: {
    titulo:        "Carregar Trabalhadores",
    endpoint:      "/lista-mensal/upload-trabalhadores",
    template:      "/lista-mensal/template",
    template_nome: "trabalhadores_modelo.xlsx",
    btn_label:     "Carregar",
  },
  inativar: {
    titulo:        "Inativar Trabalhadores",
    endpoint:      "/lista-mensal/upload-inativacao",
    template:      "/lista-mensal/template-inativacao",
    template_nome: "trabalhadores_inativos_modelo.xlsx",
    btn_label:     "Analisar",
    fluxo_2_etapas: true,
  },
  dependentes: {
    titulo:        "Carregar Dependentes",
    endpoint:      "/lista-mensal/upload-dependentes",
    template:      "/lista-mensal/template-dependentes",
    template_nome: "dependentes_modelo.xlsx",
    btn_label:     "Carregar",
  },
};

let _modo_atual = "carregar";

function abrirModalUpload(modo) {
  _modo_atual = modo || "carregar";
  const cfg = UPLOAD_MODOS[_modo_atual];
  document.getElementById("modal-upload").classList.remove("hidden");
  document.getElementById("modal-titulo").textContent = cfg.titulo;
  document.getElementById("f-arquivo").value = "";
  document.getElementById("modal-status").innerHTML = "";
  const btn = document.getElementById("btn-carregar");
  btn.textContent = cfg.btn_label;
  btn.disabled = false;
  btn.classList.remove("hidden");
  document.getElementById("btn-confirmar-inativacao").classList.add("hidden");
}

function fecharModalUpload() {
  document.getElementById("modal-upload").classList.add("hidden");
}

async function baixarTemplate(ev) {
  ev.preventDefault();
  const cfg = UPLOAD_MODOS[_modo_atual];
  const token = localStorage.getItem("bss_token");
  try {
    const resp = await fetch(cfg.template, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = cfg.template_nome;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("Erro ao baixar template: " + e.message);
  }
}

function renderErros(payload) {
  const cats = payload.erros || {};
  const titulos = {
    estrutura:                "Erros de estrutura no arquivo",
    cnpj_invalido:            "CNPJ inválido (deve ter 14 dígitos)",
    cnpj_nao_cadastrado:      "Empresas com CNPJ não identificado",
    cnpj_sem_permissao:       "CNPJs sem permissão para este usuário",
    cpf_invalido:             "CPF Incorreto (11 dígitos com DV válido)",
    nome_vazio:               "Nome em branco",
    sindicato_vazio:          "Sindicato em branco",
    sindicato_nao_cadastrado: "Sindicato Laboral não identificado",
    cpf_duplicado_na_planilha:"CPF duplicado na planilha (mesma empresa)",
  };
  let html = `<div class="bg-rose-50 border border-rose-300 rounded-lg p-4">
    <p class="text-rose-800 font-semibold mb-3">${payload.mensagem || "Carga não realizada."}</p>`;
  for (const cat of Object.keys(titulos)) {
    const itens = cats[cat] || [];
    if (!itens.length) continue;
    html += `<div class="mt-2">
      <p class="text-sm font-semibold text-slate-700">${titulos[cat]}:</p>
      <ul class="text-xs font-mono text-rose-700 mt-1 ml-4 list-disc">`;
    for (const v of itens) html += `<li>${v}</li>`;
    html += `</ul></div>`;
  }
  // Categorias não previstas (defesa)
  for (const cat of Object.keys(cats)) {
    if (!titulos[cat]) {
      html += `<div class="mt-2">
        <p class="text-sm font-semibold text-slate-700">${cat}:</p>
        <ul class="text-xs font-mono text-rose-700 mt-1 ml-4 list-disc">`;
      for (const v of cats[cat]) html += `<li>${v}</li>`;
      html += `</ul></div>`;
    }
  }
  html += `</div>`;
  return html;
}

async function enviarUpload() {
  const inp = document.getElementById("f-arquivo");
  const status = document.getElementById("modal-status");
  const btn = document.getElementById("btn-carregar");
  if (!inp.files.length) {
    status.innerHTML = `<div class="text-rose-600">Selecione um arquivo.</div>`;
    return;
  }
  btn.disabled = true;
  status.innerHTML = `<div class="text-slate-500">Enviando e processando…</div>`;

  const cfg = UPLOAD_MODOS[_modo_atual];
  const fd = new FormData();
  fd.append("arquivo", inp.files[0]);
  const token = localStorage.getItem("bss_token");

  // Inativação tem fluxo de 2 etapas: 1ª chamada com confirmar=false (preview)
  let url = cfg.endpoint;
  if (cfg.fluxo_2_etapas) url += "?confirmar=false";

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    });
    const data = await resp.json();
    if (!resp.ok) {
      const payload = data.detail || data;
      status.innerHTML = renderErros(payload);
      btn.disabled = false;
      return;
    }
    if (cfg.fluxo_2_etapas && data.modo === "preview") {
      // Render preview com botão Efetivar
      status.innerHTML = renderPreviewInativacao(data);
      btn.classList.add("hidden");                                  // esconde "Analisar"
      const bc = document.getElementById("btn-confirmar-inativacao");
      bc.classList.remove("hidden");
      bc.disabled = (data.qtd_validas === 0);
      _arquivo_pendente_inativacao = inp.files[0];
      return;
    }
    // Sucesso final (carregar/dependentes)
    renderSucessoFinal(data);

    // Fluxo empresa: depois de CARREGAR trabalhadores, a próxima ação natural é
    // gerar os boletos do mês. Em vez de o usuário navegar até Boletos e abrir o
    // modal, mandamos direto pra tela de emissão com o preview já aberto — basta
    // conferir e clicar "Gerar Boleto". Só pro modo 'carregar' (inativar e
    // dependentes não geram boleto) e só pro perfil empresa (interno faz carga
    // de várias empresas, não quer ser jogado na emissão a cada uma).
    const u = usuarioAtual();
    if (_modo_atual === "carregar" && u && u.perfil === "empresa") {
      setTimeout(() => { window.location.href = "/app/boletos.html?emitir=1"; }, 1800);
      return;
    }

    setTimeout(() => { fecharModalUpload(); recarregar(); }, 2500);
  } catch (e) {
    status.innerHTML = `<div class="text-rose-600">Erro de rede: ${e.message}</div>`;
    btn.disabled = false;
  }
}

let _arquivo_pendente_inativacao = null;

async function confirmarInativacao() {
  const status = document.getElementById("modal-status");
  const bc = document.getElementById("btn-confirmar-inativacao");
  if (!_arquivo_pendente_inativacao) return;
  bc.disabled = true;
  status.innerHTML = `<div class="text-slate-500">Efetivando inativação…</div>`;

  const fd = new FormData();
  fd.append("arquivo", _arquivo_pendente_inativacao);
  const token = localStorage.getItem("bss_token");

  try {
    const resp = await fetch("/lista-mensal/upload-inativacao?confirmar=true", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    });
    const data = await resp.json();
    if (!resp.ok) {
      status.innerHTML = renderErros(data.detail || data);
      bc.disabled = false;
      return;
    }
    renderSucessoFinal(data);
    _arquivo_pendente_inativacao = null;
    setTimeout(() => { fecharModalUpload(); recarregar(); }, 2500);
  } catch (e) {
    status.innerHTML = `<div class="text-rose-600">Erro de rede: ${e.message}</div>`;
    bc.disabled = false;
  }
}

function renderPreviewInativacao(data) {
  const cats = data.erros || {};
  const titulosErro = {
    cnpj_invalido:            "CNPJ inválido (14 dígitos)",
    cnpj_nao_cadastrado:      "Empresas com CNPJ não identificado",
    cnpj_sem_permissao:       "CNPJs sem permissão para este usuário",
    cpf_invalido:             "CPF Incorreto (11 dígitos com DV válido)",
    cpf_nao_cadastrado:       "CPF não cadastrado no sistema",
    cpf_nao_ativo_neste_cnpj: "CPF não está ativo neste CNPJ neste mês",
  };
  let html = `<div class="bg-amber-50 border border-amber-300 rounded-lg p-4 mb-3">
    <p class="font-semibold text-amber-900">
      Preview da inativação (mês ${data.mes_referencia})
    </p>
    <ul class="text-sm mt-2 text-amber-900">
      <li>Total de linhas na planilha: <strong>${data.qtd_total_planilha}</strong></li>
      <li>Linhas válidas que serão inativadas: <strong>${data.qtd_validas}</strong></li>
    </ul>
  </div>`;
  if (Object.keys(cats).length) {
    html += `<div class="bg-rose-50 border border-rose-300 rounded-lg p-4 mb-3">
      <p class="font-semibold text-rose-800 mb-2">Linhas que serão IGNORADAS por erro:</p>`;
    for (const cat of Object.keys(titulosErro)) {
      const itens = cats[cat] || [];
      if (!itens.length) continue;
      html += `<div class="mt-2"><p class="text-sm font-semibold text-slate-700">${titulosErro[cat]}:</p>
        <ul class="text-xs font-mono text-rose-700 mt-1 ml-4 list-disc">`;
      for (const v of itens) html += `<li>${v}</li>`;
      html += `</ul></div>`;
    }
    for (const cat of Object.keys(cats)) {
      if (titulosErro[cat]) continue;
      html += `<div class="mt-2"><p class="text-sm font-semibold text-slate-700">${cat}:</p>
        <ul class="text-xs font-mono text-rose-700 mt-1 ml-4 list-disc">`;
      for (const v of cats[cat]) html += `<li>${v}</li>`;
      html += `</ul></div>`;
    }
    html += `</div>`;
  }
  if (data.qtd_validas > 0) {
    html += `<div class="text-sm text-slate-700">Clique em <strong>Efetivar Inativação</strong> pra inativar ${data.qtd_validas} vínculo(s).</div>`;
  } else {
    html += `<div class="text-sm text-rose-600">Nenhuma linha válida pra efetivar.</div>`;
  }
  return html;
}

function renderSucessoFinal(data) {
  const status = document.getElementById("modal-status");
  let html = `<div class="bg-emerald-50 border border-emerald-300 rounded-lg p-4 text-emerald-900">
    <p class="font-semibold">${data.mensagem || "Concluído."}</p>
    <ul class="text-sm mt-2">`;
  if (data.qtd_processadas != null)
    html += `<li>Processados: <strong>${data.qtd_processadas}</strong></li>`;
  if (data.qtd_inativadas != null)
    html += `<li>Inativados: <strong>${data.qtd_inativadas}</strong></li>`;
  if (data.qtd_listas_criadas != null)
    html += `<li>Listas criadas: <strong>${data.qtd_listas_criadas}</strong></li>`;
  html += `</ul></div>`;
  status.innerHTML = html;
}


// Seletor de empresa (só renderiza pra perfil 'empresa' com +1 CNPJ).
// recarregar() volta pra página 1 — trocar de empresa e cair na página 7 da
// anterior seria confuso.
montarSeletorEmpresa("#seletor-empresa", recarregar);

carregar();
