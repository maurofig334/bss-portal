/* Detalhe do Benefício (processo) — cabeçalho + abas de relacionamento.
 * Peça central: o CHECKLIST de documentos (regra do tipo x anexado). Épico #22.
 */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let _proc = null;
const _relCarregada = new Set();

// Espelha processo_repo.PERFIS_INTERNOS. Aqui é só pra decidir o que MOSTRAR
// (nota interna, dropdown de status, lado do balão) — quem decide de verdade
// é o backend. Esconder no frontend não é segurança.
const EH_INTERNO = !!u && ["admin", "interno", "analista"].includes(u.perfil);

let _statusOpcoes = null;   // cache do dropdown de status (carrega uma vez)

/* ------------------------------- helpers -------------------------------- */

function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtDataHora(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function fmtCpf(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  return d.length === 11 ? `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9,11)}` : c;
}
function fmtCnpj(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  return d.length === 14 ? `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12,14)}` : c;
}
function fmtCep(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  return d.length === 8 ? `${d.slice(0,5)}-${d.slice(5,8)}` : c;
}
function brl(n) {
  if (n === null || n === undefined) return "—";
  return Number(n).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function tamanho(b) {
  if (!b) return "";
  const kb = b / 1024;
  return kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${Math.round(kb)} KB`;
}

function par(label, valor, classCol = "md:col-span-6") {
  const v = (valor === null || valor === undefined || valor === "")
    ? '<span class="text-slate-400">—</span>' : valor;
  return `<div class="${classCol}">
      <div class="text-xs font-medium uppercase tracking-wider text-slate-500">${label}</div>
      <div class="mt-0.5 text-slate-800">${v}</div>
    </div>`;
}
function pill(txt, cls) {
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cls}">${txt}</span>`;
}
function linkEnt(texto, href) {
  if (!texto) return null;
  return href ? `<a href="${href}" class="text-rose-600 hover:underline">${texto}</a>` : texto;
}
function getId() { return new URL(window.location.href).searchParams.get("id"); }

/* -------------------------------- carga --------------------------------- */

async function carregar() {
  const id = getId();
  if (!id) return falhar("ID do benefício não informado na URL.");
  try {
    _proc = await apiFetch(`/processos/${id}/detalhe`);
    render(_proc);
    carregarRel("documentos");
  } catch (e) { falhar(`Erro: ${e.message}`); }
}

function falhar(msg) {
  document.getElementById("loading").classList.add("hidden");
  const erro = document.getElementById("erro");
  erro.classList.remove("hidden");
  erro.textContent = msg;
}

function render(p) {
  document.getElementById("loading").classList.add("hidden");
  document.getElementById("conteudo").classList.remove("hidden");

  document.getElementById("titulo").innerHTML =
    `${p.tipo_beneficio || "Benefício"} <span class="text-slate-400 font-normal">· ${p.protocolo || p.numero_processo || p.id}</span>`;

  // Status com a cor vinda de bss.status_processo
  const cor = p.status_cor || "#94A3B8";
  document.getElementById("status-badge").innerHTML =
    `<span class="inline-block px-2.5 py-1 rounded-full text-xs font-medium text-white" style="background:${cor}">
       ${p.status_nome || p.status || "—"}</span>`;

  // Bloqueio de regularidade (as 3 condições)
  if (p.bloqueio_motivo) {
    const av = document.getElementById("aviso-bloqueio");
    av.classList.remove("hidden");
    av.innerHTML = `<b>Benefício bloqueado:</b> ${p.bloqueio_motivo}`;
  }

  // ---- Benefício
  const extras = [];
  if (p.qtd_bebes) extras.push(par("Quantidade de bebês", p.qtd_bebes));
  if (p.data_obito) extras.push(par("Data do óbito", fmtData(p.data_obito)));
  if (p.causa_mortis) extras.push(par("Causa mortis", p.causa_mortis));
  if (p.situacao_acionamento) extras.push(par("Situação do acionamento", p.situacao_acionamento));

  document.getElementById("grid-beneficio").innerHTML = [
    par("Protocolo", `<span class="font-mono">${p.protocolo || "—"}</span>`),
    par("Tipo de Benefício", `<span class="font-medium">${p.tipo_beneficio || "—"}</span>`),
    par("Data de Evento", fmtData(p.data_evento)),
    par("Data de Finalização", fmtData(p.data_finalizacao)),
    par("Valor solicitado", brl(p.valor_solicitado)),
    par("Valor aprovado", brl(p.valor_aprovado)),
    par("Qtd. parcelas", p.qtd_parcelas ?? null),
    par("Forma de pagamento", p.forma_pagamento || null),
    par("Liberalidade", p.liberalidade || null),
    par("Dados revisados", p.dados_revisados ? "Sim" : "Não"),
    ...extras,
  ].join("");

  // ---- Trabalhador + Beneficiário
  const endBenef = montarEndereco(p);
  document.getElementById("grid-pessoas").innerHTML = [
    par("Trabalhador / Dependente",
        linkEnt(p.trabalhador_nome, p.id_trabalhador ? `/app/trabalhador-detalhe.html?id=${p.id_trabalhador}` : null)),
    par("CPF do Trab. / Dep.", `<span class="font-mono">${fmtCpf(p.trabalhador_cpf)}</span>`),
    par("Empresa", linkEnt(p.empresa, p.id_empresa ? `/app/empresa-detalhe.html?id=${p.id_empresa}` : null)),
    par("CNPJ da Empresa", p.empresa_cnpj ? `<span class="font-mono">${fmtCnpj(p.empresa_cnpj)}</span>` : null),
    par("Sindicato", linkEnt(p.sindicato, p.id_sindicato ? `/app/sindicato-detalhe.html?id=${p.id_sindicato}` : null),
        "md:col-span-12"),
    par("Nome do Beneficiário", `<span class="font-medium">${p.beneficiario_nome || "—"}</span>`),
    par("CPF do Beneficiário", p.beneficiario_cpf ? `<span class="font-mono">${fmtCpf(p.beneficiario_cpf)}</span>` : null),
    par("Telefone do Beneficiário", p.beneficiario_telefone || null),
    par("Grau de parentesco", p.beneficiario_grau_parentesco || null),
    par("Endereço do Beneficiário", endBenef, "md:col-span-12"),
  ].join("");

  // ---- Dados bancários
  const db = p.dados_bancarios;
  if (db) {
    document.getElementById("sec-bancarios").classList.remove("hidden");
    document.getElementById("grid-bancarios").innerHTML = [
      par("Titular", db.titular_tipo || null),
      par("CNPJ/CPF do titular", db.cnpj_cpf_titular
        ? `<span class="font-mono">${String(db.cnpj_cpf_titular).length === 14 ? fmtCnpj(db.cnpj_cpf_titular) : fmtCpf(db.cnpj_cpf_titular)}</span>` : null),
      par("Banco", db.banco_codigo || null),
      par("Agência", db.agencia || null),
      par("Conta", [db.conta, db.digito].filter(Boolean).join("-") || null),
      par("Tipo de conta", db.tipo_conta || null),
      par("Chave PIX", db.chave_pix ? `<span class="font-mono text-xs">${db.chave_pix}</span>` : null, "md:col-span-12"),
    ].join("");
  }

  // ---- LOG
  document.getElementById("grid-log").innerHTML = [
    par("Criado em", fmtDataHora(p.criado_em)),
    par("Última modificação", fmtDataHora(p.atualizado_em)),
    par("Última ação do cliente no portal", fmtDataHora(p.ultima_atualizacao_portal_em)),
    par("Nº processo (legado)", p.numero_processo ?? null),
    par("ID legado (UUID)", p.id_legado_uuid ? `<span class="font-mono text-xs">${p.id_legado_uuid}</span>` : null, "md:col-span-12"),
  ].join("");
}

function montarEndereco(p) {
  const l1 = [p.beneficiario_endereco_logradouro, p.beneficiario_endereco_numero].filter(Boolean).join(", ");
  const l2 = [p.beneficiario_endereco_complemento, p.beneficiario_endereco_bairro].filter(Boolean).join(" — ");
  const l3 = [
    [p.beneficiario_endereco_cidade, p.beneficiario_endereco_uf].filter(Boolean).join("/"),
    p.beneficiario_endereco_cep ? fmtCep(p.beneficiario_endereco_cep) : "",
  ].filter(Boolean).join(" · ");
  const linhas = [l1, l2, l3].filter(Boolean);
  return linhas.length ? linhas.map(l => `<div>${l}</div>`).join("")
                       : '<span class="text-slate-400">Endereço não informado</span>';
}

/* --------------------------- abas de relacionamento ---------------------- */

const REL = ["documentos", "mensagens", "pagamentos"];

function trocarRel(qual) {
  const ativa = "px-4 py-2.5 text-sm font-medium text-slate-800 border-b-2 border-indigo-600 whitespace-nowrap";
  const inativa = "px-4 py-2.5 text-sm text-slate-500 hover:text-slate-800 whitespace-nowrap";
  REL.forEach(a => {
    document.getElementById(`rtab-${a}`).className = (a === qual ? ativa : inativa);
    document.getElementById(`rel-${a}`).classList.toggle("hidden", a !== qual);
  });
  carregarRel(qual);
}

async function carregarRel(qual) {
  if (_relCarregada.has(qual)) return;
  _relCarregada.add(qual);
  const id = getId();
  const alvo = document.getElementById(`rel-${qual}`);
  alvo.innerHTML = `<div class="py-8 text-center text-slate-400 text-sm">Carregando…</div>`;
  try {
    const dados = await apiFetch(`/processos/${id}/${qual}`);
    if (qual === "documentos") alvo.innerHTML = renderChecklist(dados);
    else if (qual === "mensagens") {
      alvo.innerHTML = renderMensagens(dados);
      // Só depois do innerHTML o <select> existe no DOM.
      carregarStatusOpcoes();
    }
    else if (qual === "pagamentos") alvo.innerHTML = renderPagamentos(dados);
  } catch (e) {
    _relCarregada.delete(qual);
    alvo.innerHTML = `<div class="py-8 text-center text-rose-600 text-sm">Erro: ${e.message}</div>`;
  }
}

/* ------------------------ CHECKLIST DE DOCUMENTOS ------------------------ */
/*
 * Cada linha = 1 tipo de documento exigido pelo tipo de benefício.
 * status NULL  → nunca anexado
 * 'pendente'   → anexado, aguardando análise
 * 'aprovado'   → analista validou
 * 'rejeitado'  → analista recusou (mostra motivo) — libera reupload
 */
// Estado do TIPO (derivado no backend a partir dos arquivos)
const ESTADO_TIPO = {
  aprovado:    { icone: "✓", cls: "text-emerald-600", badge: ["Aprovado", "bg-emerald-100 text-emerald-800"] },
  rejeitado:   { icone: "✕", cls: "text-rose-600",    badge: ["Reenvio necessário", "bg-rose-100 text-rose-700"] },
  pendente:    { icone: "⏳", cls: "text-sky-600",     badge: ["Em análise", "bg-sky-100 text-sky-800"] },
  nao_enviado: { icone: "○", cls: "text-slate-300",   badge: ["Não enviado", "bg-slate-100 text-slate-500"] },
};

// Estado de cada ARQUIVO dentro do tipo
const ESTADO_ARQ = {
  aprovado:  ["Aceito", "bg-emerald-100 text-emerald-800"],
  rejeitado: ["Rejeitado", "bg-rose-100 text-rose-700"],
  pendente:  ["Em análise", "bg-sky-100 text-sky-800"],
};

function renderArquivo(a) {
  const [txt, cls] = ESTADO_ARQ[a.status] || ["—", "bg-slate-100 text-slate-500"];
  const nome = a.arquivo_url
    ? `<a href="${a.arquivo_url}" target="_blank" class="text-indigo-700 hover:underline">${a.nome_original || "arquivo"}</a>`
    : (a.nome_original || "arquivo");
  const rejeicao = (a.status === "rejeitado")
    ? `<div class="text-xs text-rose-700 mt-0.5">
         <b>Motivo:</b> ${a.motivo_rejeicao || "—"}${a.observacao ? ` — ${a.observacao}` : ""}
       </div>` : "";
  return `
    <div class="flex items-start justify-between gap-3 py-1.5 pl-7 pr-2 border-t border-slate-50">
      <div class="min-w-0">
        <div class="text-xs text-slate-600">
          ${nome}
          ${a.tamanho_bytes ? `<span class="text-slate-400"> · ${tamanho(a.tamanho_bytes)}</span>` : ""}
          ${a.enviado_em ? `<span class="text-slate-400"> · ${fmtDataHora(a.enviado_em)}</span>` : ""}
        </div>
        ${rejeicao}
      </div>
      <div class="shrink-0">${pill(txt, cls)}</div>
    </div>`;
}

function renderChecklist(docs) {
  if (!docs || !docs.length) {
    return `<div class="py-10 text-center text-slate-400 text-sm">
      Este tipo de benefício não exige documentos.
    </div>`;
  }

  const obrig = docs.filter(d => d.obrigatorio);
  const okObrig = obrig.filter(d => d.estado === "aprovado").length;
  const precisaReenvio = docs.filter(d => d.estado === "rejeitado").length;
  const faltando = obrig.filter(d => d.estado === "nao_enviado").length;

  document.getElementById("rcount-documentos").textContent = `${okObrig}/${obrig.length}`;

  // Resumo — regra derivada documentada no schema:
  //   1+ rejeitado → documentacao_pendente | todos obrigatorios aprovados → aprovado_analise
  let resumo, resumoCls;
  if (precisaReenvio) {
    resumo = `${precisaReenvio} documento(s) aguardando reenvio — o processo fica em Documentação Pendente até resolver.`;
    resumoCls = "bg-rose-50 border-rose-200 text-rose-800";
  } else if (obrig.length && okObrig === obrig.length) {
    resumo = "Todos os documentos obrigatórios aprovados — o processo pode seguir para Aprovado (Análise).";
    resumoCls = "bg-emerald-50 border-emerald-200 text-emerald-800";
  } else {
    resumo = `${okObrig} de ${obrig.length} obrigatórios aprovados`
      + (faltando ? ` · ${faltando} ainda não enviado(s)` : "");
    resumoCls = "bg-slate-50 border-slate-200 text-slate-600";
  }

  const linhas = docs.map(d => {
    const e = ESTADO_TIPO[d.estado] || ESTADO_TIPO.nao_enviado;
    const arquivos = d.arquivos && d.arquivos.length
      ? d.arquivos.map(renderArquivo).join("")
      : `<div class="pl-7 pr-2 py-1.5 text-xs text-slate-400 border-t border-slate-50">Nenhum arquivo enviado</div>`;
    return `
      <div class="px-5 py-3 border-t border-slate-100">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-lg leading-none ${e.cls}">${e.icone}</span>
          <span class="font-medium text-slate-800">${d.nome}</span>
          ${d.obrigatorio ? pill("Obrigatório", "bg-slate-800 text-white") : pill("Opcional", "bg-slate-100 text-slate-500")}
          ${pill(e.badge[0], e.badge[1])}
          ${d.bloqueado ? `<span class="text-xs text-slate-400" title="Documento aceito — o portal trava o upload">🔒 travado</span>` : ""}
          ${d.qtd_arquivos > 1 ? `<span class="text-xs text-slate-400">${d.qtd_arquivos} arquivos</span>` : ""}
        </div>
        <div class="mt-1">${arquivos}</div>
      </div>`;
  }).join("");

  return `<div class="px-5 py-2.5 border-b ${resumoCls} text-xs">${resumo}</div>${linhas}`;
}

/* ------------------------------ MENSAGENS ------------------------------- */

/** Escapa texto vindo do banco antes de ir pra innerHTML. */
function escHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function renderMensagens(msgs) {
  const lista = (!msgs || !msgs.length)
    ? `<div class="py-10 text-center text-slate-400 text-sm">
         Nenhuma mensagem ainda.${EH_INTERNO ? "" : " Escreva abaixo para falar com a equipe da BSS."}
       </div>`
    : `<div class="divide-y divide-slate-100">` + msgs.map(m => {
        // Balão à direita = "meu lado". Pro analista, o lado da BSS; pro
        // cliente, o dele. Mensagem migrada (autor NULL) fica à esquerda.
        const meuLado = EH_INTERNO ? !m.eh_externo : m.eh_externo;
        const autor = m.autor_nome
          ? escHtml(m.autor_nome)
          : `<span class="italic text-slate-400">autor não identificado</span>`;

        // Título só existe nas migradas — as novas nascem sem (chat livre).
        const titulo = m.titulo
          ? `<div class="font-medium text-slate-700 text-sm">${escHtml(m.titulo)}</div>` : "";

        return `
        <div class="px-5 py-3 ${m.interno ? "bg-amber-50/50" : ""}">
          <div class="flex ${meuLado ? "justify-end" : "justify-start"}">
            <div class="max-w-2xl ${meuLado ? "text-right" : ""}">
              <div class="flex items-center gap-2 flex-wrap ${meuLado ? "justify-end" : ""}">
                <span class="text-xs font-medium text-slate-600">${autor}</span>
                ${m.eh_externo
                  ? pill("Cliente", "bg-sky-100 text-sky-800")
                  : (m.autor_perfil ? pill("BSS", "bg-indigo-100 text-indigo-800") : "")}
                ${m.interno ? pill("Nota interna — cliente não vê", "bg-amber-100 text-amber-800") : ""}
                <span class="text-xs text-slate-400">${fmtDataHora(m.criado_em)}</span>
              </div>
              ${titulo}
              <div class="text-sm text-slate-700 mt-1 whitespace-pre-wrap">${escHtml((m.corpo || "").trim())}</div>
            </div>
          </div>
        </div>`;
      }).join("") + `</div>`;

  return lista + caixaEscrita();
}

/** Caixa de composição. Internos ganham nota interna + mudança de status. */
function caixaEscrita() {
  const extras = EH_INTERNO ? `
    <div class="flex items-center gap-4 flex-wrap mt-2">
      <label class="inline-flex items-center text-xs text-slate-600">
        <input type="checkbox" id="msg-interno" class="mr-2">
        Nota interna <span class="text-slate-400 ml-1">(o cliente não vê)</span>
      </label>
      <label class="inline-flex items-center gap-2 text-xs text-slate-600">
        Mudar status para
        <select id="msg-status"
                class="text-xs border border-slate-300 rounded-lg px-2 py-1 bg-white
                       focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
          <option value="">— não mudar —</option>
        </select>
      </label>
    </div>` : "";

  return `
    <div class="border-t border-slate-200 bg-slate-50/60 px-5 py-4">
      <textarea id="msg-corpo" rows="3"
                placeholder="${EH_INTERNO ? "Responder ao cliente…" : "Escreva para a equipe da BSS…"}"
                class="w-full text-sm border border-slate-300 rounded-lg px-3 py-2
                       focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"></textarea>
      ${extras}
      <div class="flex items-center justify-between gap-3 mt-2">
        <span id="msg-erro" class="text-xs text-rose-600"></span>
        <button id="msg-enviar" onclick="enviarMensagem()"
                class="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-700 text-white
                       rounded-lg font-medium disabled:opacity-50">
          Enviar
        </button>
      </div>
    </div>`;
}

/** Popula o dropdown de status a partir de bss.status_processo. */
async function carregarStatusOpcoes() {
  if (!EH_INTERNO) return;
  const sel = document.getElementById("msg-status");
  if (!sel) return;
  try {
    if (!_statusOpcoes) _statusOpcoes = await apiFetch("/processos/status-disponiveis");
    sel.innerHTML = `<option value="">— não mudar —</option>` +
      _statusOpcoes
        // O status atual não entra: "mudar" pro que já é seria no-op (o
        // backend ignora) e confundiria quem escolhe.
        .filter(s => s.codigo !== _proc?.status)
        .map(s => `<option value="${s.codigo}">${escHtml(s.nome)}</option>`).join("");
  } catch (e) {
    sel.parentElement.classList.add("hidden");   // some em vez de mostrar erro
  }
}

async function enviarMensagem() {
  const btn = document.getElementById("msg-enviar");
  const txt = document.getElementById("msg-corpo");
  const erro = document.getElementById("msg-erro");
  erro.textContent = "";

  const corpo = (txt.value || "").trim();
  if (!corpo) { erro.textContent = "Escreva alguma coisa antes de enviar."; return; }

  const body = { corpo };
  if (EH_INTERNO) {
    body.interno = document.getElementById("msg-interno")?.checked || false;
    const st = document.getElementById("msg-status")?.value;
    if (st) body.status_novo = st;
  }

  btn.disabled = true;
  btn.textContent = "Enviando…";
  try {
    await apiFetch(`/processos/${getId()}/mensagens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    // Recarrega a aba (invalida o lazy-load). Se o status mudou, recarrega o
    // cabeçalho também — senão o topo continuaria mostrando o status antigo.
    _relCarregada.delete("mensagens");
    await carregarRel("mensagens");
    if (body.status_novo) await carregar();
  } catch (e) {
    erro.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Enviar";
  }
}

/* ---------------------------- CONTAS A PAGAR ---------------------------- */

function renderPagamentos(pgs) {
  if (!pgs || !pgs.length) {
    return `<div class="py-10 text-center text-slate-400 text-sm">Nenhuma parcela gerada para este benefício.</div>`;
  }
  const total = pgs.reduce((a, p) => a + Number(p.valor || 0), 0);
  const corpo = pgs.map(p => `
    <tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="px-5 py-2 text-center font-mono">${p.parcela}</td>
      <td class="px-3 py-2 text-right font-mono">${brl(p.valor)}</td>
      <td class="px-3 py-2 text-xs">${p.forma_pagamento || "—"}</td>
      <td class="px-3 py-2 text-center text-xs">${(p.status || "—").toUpperCase()}</td>
      <td class="px-3 py-2 text-center text-xs text-slate-500">${fmtData(p.data_vencimento)}</td>
      <td class="px-3 py-2 text-center text-xs text-slate-500">${fmtData(p.data_pagamento)}</td>
    </tr>`).join("");
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-center">Parcela</th>
        <th class="px-3 py-2 text-right">Valor</th>
        <th class="px-3 py-2 text-left">Forma</th>
        <th class="px-3 py-2 text-center">Status</th>
        <th class="px-3 py-2 text-center">Vencimento</th>
        <th class="px-3 py-2 text-center">Pagamento</th>
      </tr></thead><tbody>${corpo}</tbody></table></div>
      <div class="px-5 py-2 text-xs text-slate-500 border-t border-slate-100">
        ${pgs.length} parcela(s) · total <b class="font-mono">${brl(total)}</b>
      </div>`;
}

carregar();
