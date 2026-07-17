/* Tela de detalhe da empresa — campos reais + abas de relacionamento (OCSP). */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let _empresa = null;
const _relCarregada = new Set();   // abas já buscadas (lazy-load)

function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtDataHora(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function fmtCompetencia(d) {
  if (!d) return "—";
  const dt = new Date(d);
  return `${String(dt.getMonth() + 1).padStart(2, "0")}/${dt.getFullYear()}`;
}
function fmtCnpj(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length === 14) return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12,14)}`;
  return c;
}
function fmtCpf(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length === 11) return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9,11)}`;
  return c;
}
function fmtCep(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length === 8) return `${d.slice(0,5)}-${d.slice(5,8)}`;
  return c;
}
function brl(n) { return Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }
function num(n) { return Number(n || 0).toLocaleString("pt-BR"); }

function par(label, valor, classCol = "md:col-span-6") {
  const v = (valor === null || valor === undefined || valor === "")
    ? '<span class="text-slate-400">—</span>' : valor;
  return `<div class="${classCol}">
      <div class="text-xs font-medium uppercase tracking-wider text-slate-500">${label}</div>
      <div class="mt-0.5 text-slate-800">${v}</div>
    </div>`;
}

function badge(txt, cor) {
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cor}">${txt}</span>`;
}
function badgeStatus(s) {
  const m = { ativa: "bg-emerald-100 text-emerald-800", suspensa: "bg-amber-100 text-amber-800",
              cancelada: "bg-rose-100 text-rose-700", inativa: "bg-slate-200 text-slate-700" };
  return badge((s || "—").toString(), m[s] || "bg-slate-100 text-slate-600");
}
function badgeAdim(a) {
  const m = { adimplente: "bg-emerald-100 text-emerald-800", inadimplente: "bg-rose-100 text-rose-700" };
  return a ? badge(a.toUpperCase(), m[a] || "bg-slate-100 text-slate-600") : '<span class="text-slate-400">—</span>';
}

function getId() { return new URL(window.location.href).searchParams.get("id"); }

async function carregar() {
  const id = getId();
  if (!id) return falhar("ID da empresa não informado na URL.");
  try {
    _empresa = await apiFetch(`/empresas/${id}/detalhe`);
    render(_empresa);
    carregarRel("trabalhadores");   // primeira aba
  } catch (e) { falhar(`Erro: ${e.message}`); }
}

function falhar(msg) {
  document.getElementById("loading").classList.add("hidden");
  const erro = document.getElementById("erro");
  erro.classList.remove("hidden");
  erro.textContent = msg;
}

function render(e) {
  document.getElementById("loading").classList.add("hidden");
  document.getElementById("conteudo").classList.remove("hidden");
  document.getElementById("titulo").innerHTML = e.razao_social || "Empresa";

  const endereco = montarEndereco(e);
  const enderecoBloco = `
    <div class="flex items-start justify-between gap-3">
      <div>${endereco}</div>
      <button onclick="copiarEndereco()" class="shrink-0 px-2 py-1 text-xs bg-slate-100 hover:bg-slate-200 rounded">Copiar…</button>
    </div>`;

  document.getElementById("grid-basica").innerHTML = [
    par("Razão Social", `<span class="font-medium">${e.razao_social || "—"}</span>`),
    par("CNPJ", e.cnpj ? `<span class="font-mono">${fmtCnpj(e.cnpj)}</span>` : null),
    par("Situação da Empresa", badgeStatus(e.status)),
    par("Status Empresa", badgeAdim(e.adimplencia)),
    par("Regularidade", e.regularidade || null),
    par("Recebe email financeiro", e.recebe_email_financeiro ? "Sim" : "Não"),
    par("Ativos", `<span class="font-mono font-semibold text-emerald-700">${num(e.qtd_trabalhadores_ativos)}</span>`),
    par("Inativos", `<span class="font-mono text-slate-500">${num(e.qtd_trabalhadores_inativos)}</span>`),
    par("Dependentes ativos", `<span class="font-mono">${num(e.qtd_dependentes_ativos)}</span>`),
    par("Telefone do Escritório", e.telefone ? `<span class="text-rose-600">${e.telefone}</span>` : null),
    par("Endereço de Faturamento", enderecoBloco, "md:col-span-6"),
    par("Data de Criação", fmtDataHora(e.criado_em)),
    par("Último Boleto Gerado", fmtData(e.ultimo_boleto_em)),
    par("Última Notificação", fmtData(e.ultima_notificacao_em)),
    e.nome_fantasia ? par("Nome Fantasia", e.nome_fantasia) : "",
    par("ID legado (UUID)", e.id_legado_uuid ? `<span class="font-mono text-xs">${e.id_legado_uuid}</span>` : null, "md:col-span-12"),
  ].join("");
}

function montarEndereco(e) {
  const l1 = [e.logradouro, e.numero].filter(Boolean).join(", ");
  const l2 = [e.complemento, e.bairro].filter(Boolean).join(" — ");
  const l3 = [[e.cidade, e.uf].filter(Boolean).join("/"), e.cep ? fmtCep(e.cep) : ""].filter(Boolean).join(" · ");
  const linhas = [l1, l2, l3].filter(Boolean);
  return linhas.length ? linhas.map(l => `<div>${l}</div>`).join("")
                       : '<span class="text-slate-400">Endereço não cadastrado</span>';
}

function copiarEndereco() {
  const e = _empresa || {};
  const txt = [
    [e.logradouro, e.numero].filter(Boolean).join(", "),
    [e.complemento, e.bairro].filter(Boolean).join(" - "),
    [[e.cidade, e.uf].filter(Boolean).join("/"), e.cep ? fmtCep(e.cep) : ""].filter(Boolean).join(" "),
  ].filter(Boolean).join("\n");
  navigator.clipboard?.writeText(txt);
}

/* ----------------------- Abas de relacionamento -------------------------- */

const REL = ["trabalhadores", "boletos", "usuarios", "historico"];

function trocarRel(qual) {
  const ativa = "px-4 py-2.5 text-sm font-medium text-slate-800 border-b-2 border-indigo-600 whitespace-nowrap";
  const inativa = "px-4 py-2.5 text-sm text-slate-500 hover:text-slate-800 whitespace-nowrap";
  REL.forEach(a => {
    document.getElementById(`rtab-${a}`).className = (a === qual ? ativa : inativa);
    document.getElementById(`rel-${a}`).classList.toggle("hidden", a !== qual);
  });
  carregarRel(qual);
}

function spinner(alvo) {
  document.getElementById(`rel-${alvo}`).innerHTML =
    `<div class="py-8 text-center text-slate-400 text-sm">Carregando…</div>`;
}

/*
 * Filtros dos subpainéis. Ficam em memória (não em localStorage): são filtros
 * de uma tela de detalhe, e reabrir OUTRA empresa com o filtro da anterior
 * ainda aplicado confundiria mais do que ajudaria.
 */
const _filtroRel = {
  trabalhadores: { situacao: "" },   // "" = todas
  boletos:       { status: "" },
};

/** Chamado pelos <select> do subpainel: troca o filtro e recarrega a aba. */
function filtrarRel(qual, campo, valor) {
  _filtroRel[qual][campo] = valor;
  _relCarregada.delete(qual);     // invalida o lazy-load
  carregarRel(qual);
}

async function exportarTrabalhadores(ev) {
  const btn = ev.currentTarget;
  const txt = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Gerando…";
  try {
    const p = new URLSearchParams({ id_empresa: getId() });
    // Manda o MESMO filtro da tela: o arquivo tem que sair igual ao que está
    // à vista. Excel que não bate com a tela destrói a confiança nos dois.
    if (_filtroRel.trabalhadores.situacao) {
      p.set("situacao", _filtroRel.trabalhadores.situacao);
    }
    await apiBaixarArquivo(`/trabalhadores/exportar?${p}`, "trabalhadores.xlsx");
  } catch (e) {
    alert(`Erro ao exportar: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = txt;
  }
}

async function carregarRel(qual) {
  if (_relCarregada.has(qual)) return;
  _relCarregada.add(qual);
  const id = getId();
  const alvo = document.getElementById(`rel-${qual}`);

  if (qual === "usuarios") {
    alvo.innerHTML = mockTabela(["Nome", "Tipo", "E-mail", "Acesso"],
      [["Maria Souza", "Externo (Contato)", "maria.souza@rh.com", "Gerencia 4 CNPJs"],
       ["João Lima", "Externo (Contato)", "joao.lima@rh.com", "Gerencia 2 CNPJs"],
       ["Ana Paula (GNB)", "Interno", "ana@gnb.com.br", "Analista"]],
      "Modelo a definir: usuários externos virão dos Contatos do SuiteCRM (vínculo por CNPJ, N:N) + analistas internos — dados de exemplo (mockup).");
    return;
  }
  if (qual === "historico") {
    alvo.innerHTML = mockTabela(["Data", "Tipo", "Resumo"],
      [["13/05/2025 21:00", "E-mail", "Aviso de inadimplência enviado"],
       ["10/06/2026 09:00", "Sistema", "Boleto de 05/2026 gerado"]],
      "Histórico (mensagens, e-mails, chats) — a detalhar depois (mockup).");
    return;
  }

  spinner(qual);
  try {
    if (qual === "trabalhadores") {
      const p = new URLSearchParams({ id_empresa: id, por_pagina: 50 });
      if (_filtroRel.trabalhadores.situacao) {
        p.set("situacao", _filtroRel.trabalhadores.situacao);
      }
      const d = await apiFetch(`/trabalhadores?${p}`);
      // O contador da aba só reflete o total SEM filtro; com filtro aplicado
      // ele mostraria "852" ao lado de uma lista de inativos.
      if (!_filtroRel.trabalhadores.situacao) {
        document.getElementById("rcount-trabalhadores").textContent = num(d.total);
      }
      alvo.innerHTML = tabelaTrabalhadores(d.linhas, d.total);
    } else if (qual === "boletos") {
      const p = new URLSearchParams({ id_empresa: id, por_pagina: 50 });
      if (_filtroRel.boletos.status) p.set("status", _filtroRel.boletos.status);
      const d = await apiFetch(`/boletos?${p}`);
      const linhas = d.linhas || d;
      alvo.innerHTML = tabelaBoletos(linhas, d.total);
    }
  } catch (e) {
    _relCarregada.delete(qual);
    alvo.innerHTML = `<div class="py-8 text-center text-rose-600 text-sm">Erro: ${e.message}</div>`;
  }
}

function vazio(cols, msg) {
  return `<tr><td colspan="${cols}" class="px-5 py-8 text-center text-slate-400">${msg}</td></tr>`;
}

/* --------------------------- Subpainel: peças ---------------------------- */

/**
 * Barra de filtro do subpainel. O <select> é remontado a cada carga, então o
 * `selected` tem que sair do estado (_filtroRel) — senão volta pro default e
 * mente sobre o que está aplicado.
 */
function barraFiltro(qual, campo, opcoes, extra = "") {
  const atual = _filtroRel[qual][campo];
  const opts = opcoes.map(([v, label]) =>
    `<option value="${v}"${v === atual ? " selected" : ""}>${label}</option>`
  ).join("");
  return `
    <div class="px-5 py-2.5 flex items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/60">
      <label class="flex items-center gap-2">
        <span class="text-xs text-slate-400 uppercase tracking-wider">${campo === "situacao" ? "Situação" : "Status"}</span>
        <select onchange="filtrarRel('${qual}', '${campo}', this.value)"
                class="text-sm border border-slate-300 rounded-lg px-2 py-1 bg-white
                       focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
          ${opts}
        </select>
      </label>
      ${extra}
    </div>`;
}

/**
 * Trabalhador × Dependente.
 *
 * O dependente é uma linha da MESMA tabela bss.trabalhador, distinguida por
 * `titularidade`. Sem essa marca, a lista da MANSERV mistura 1.484 pessoas
 * sem dizer quem é quem — e "852 ativos" não bate com nada visível.
 *
 * Ícone + rótulo, não só ícone: cor e desenho sozinhos falham pra quem tem
 * daltonismo e pra quem nunca viu essa tela antes.
 */
function selo(t) {
  if (t.titularidade === "dependente") {
    return `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs
                         bg-violet-50 text-violet-700 whitespace-nowrap"
                  title="Dependente${t.cpf_titular ? ' de ' + fmtCpf(t.cpf_titular) : ''}">
              <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>
              </svg>Dependente</span>`;
  }
  return `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs
                       bg-sky-50 text-sky-700 whitespace-nowrap" title="Titular">
            <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"/>
            </svg>Trabalhador</span>`;
}

function corSituacao(s) {
  return {
    ativo:    "bg-emerald-50 text-emerald-700",
    inativo:  "bg-slate-100 text-slate-500",
    carencia: "bg-amber-50 text-amber-700",
  }[s] || "bg-slate-100 text-slate-600";
}

function corStatusBoleto(s) {
  return {
    pago:      "bg-emerald-50 text-emerald-700",
    vencido:   "bg-rose-50 text-rose-700",
    cancelado: "bg-slate-100 text-slate-500",
  }[s] || "bg-amber-50 text-amber-700";
}

function tabelaTrabalhadores(linhas, total) {
  const btnExport = `
    <button onclick="exportarTrabalhadores(event)"
            class="px-3 py-1 text-sm rounded-lg border border-slate-300 text-slate-700
                   hover:bg-white disabled:opacity-50 whitespace-nowrap"
            title="Exporta TODAS as linhas do filtro atual, não só as 50 exibidas">
      ⬇ Exportar Excel
    </button>`;

  const filtro = barraFiltro("trabalhadores", "situacao", [
    ["", "Todas"],
    ["ativo", "Ativos"],
    ["inativo", "Inativos"],
    ["carencia", "Em carência"],
  ], btnExport);

  const body = (linhas && linhas.length) ? linhas.map(t => `
    <tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="px-5 py-2">${selo(t)}</td>
      <td class="px-3 py-2"><a href="/app/trabalhador-detalhe.html?id=${t.id}" class="text-indigo-700 hover:underline">${t.nome_completo || "—"}</a></td>
      <td class="px-3 py-2 font-mono text-xs">${fmtCpf(t.cpf)}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${t.sindicato || "—"}</td>
      <td class="px-3 py-2 text-center">
        <span class="px-2 py-0.5 rounded-full text-xs ${corSituacao(t.situacao)}">${t.situacao || "—"}</span>
      </td>
    </tr>`).join("") : vazio(5, "Nenhum trabalhador para este filtro.");

  const aviso = (total > (linhas ? linhas.length : 0))
    ? `<div class="px-5 py-2 text-xs text-slate-500">Mostrando ${linhas.length} de ${num(total)} · o Excel traz todos · veja também na <a href="/app/trabalhadores.html" class="text-indigo-700 hover:underline">listagem</a>.</div>` : "";

  return `${filtro}<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Tipo</th>
        <th class="px-3 py-2 text-left">Nome</th><th class="px-3 py-2 text-left">CPF</th>
        <th class="px-3 py-2 text-left">Sindicato</th><th class="px-3 py-2 text-center">Situação</th>
      </tr></thead><tbody>${body}</tbody></table></div>${aviso}`;
}

function tabelaBoletos(linhas, total) {
  // 'cancelado' está aqui porque este subpainel é da tela INTERNA. O perfil
  // empresa nunca recebe cancelado (boleto_router força incluir_cancelados=
  // False), então pra ele o filtro simplesmente não retorna nada.
  const filtro = barraFiltro("boletos", "status", [
    ["", "Todos (vivos)"],
    ["gerado", "Aberto"],
    ["vencido", "Vencido"],
    ["pago", "Pago"],
    ["pendente", "Pendente"],
    ["cancelado", "Cancelado"],
  ]);

  const body = (linhas && linhas.length) ? linhas.map(b => `
    <tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="px-5 py-2"><a href="/app/boleto-detalhe.html?id=${b.id}" class="text-indigo-700 hover:underline font-mono text-xs">${b.numero_boleto || b.id}</a></td>
      <td class="px-3 py-2 text-xs">${fmtCompetencia(b.mes_referencia)}</td>
      <td class="px-3 py-2 text-right font-mono">${brl(b.valor_total)}</td>
      <td class="px-3 py-2 text-center text-xs text-slate-500">${fmtData(b.data_vencimento)}</td>
      <td class="px-3 py-2 text-center">
        <span class="px-2 py-0.5 rounded-full text-xs ${corStatusBoleto(b.status)}">${b.status || "—"}</span>
      </td>
    </tr>`).join("") : vazio(5, "Nenhum boleto para este filtro.");

  const aviso = (total && total > (linhas ? linhas.length : 0))
    ? `<div class="px-5 py-2 text-xs text-slate-500">Mostrando ${linhas.length} de ${num(total)}.</div>` : "";

  return `${filtro}<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Nº Boleto</th><th class="px-3 py-2 text-left">Competência</th>
        <th class="px-3 py-2 text-right">Valor</th><th class="px-3 py-2 text-center">Vencimento</th>
        <th class="px-3 py-2 text-center">Status</th>
      </tr></thead><tbody>${body}</tbody></table></div>${aviso}`;
}

function tabelaUsuarios(linhas) {
  const body = (linhas && linhas.length) ? linhas.map(u => `
    <tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="px-5 py-2 font-medium text-slate-800">${u.nome || "—"}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${u.email || "—"}</td>
      <td class="px-3 py-2 text-xs">${u.perfil || "—"}</td>
      <td class="px-3 py-2 text-center">${u.acesso_ativo ? badge("ativo", "bg-emerald-100 text-emerald-800") : badge("inativo", "bg-slate-200 text-slate-600")}</td>
    </tr>`).join("") : vazio(4, "Nenhum usuário com acesso a esta empresa.");
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Nome</th><th class="px-3 py-2 text-left">E-mail</th>
        <th class="px-3 py-2 text-left">Perfil</th><th class="px-3 py-2 text-center">Acesso</th>
      </tr></thead><tbody>${body}</tbody></table></div>`;
}

function mockTabela(cols, linhas, nota) {
  const thead = cols.map(c => `<th class="px-5 py-2 text-left">${c}</th>`).join("");
  const body = linhas.map(r => `<tr class="border-t border-slate-100">${r.map(v => `<td class="px-5 py-2 text-slate-600">${v}</td>`).join("")}</tr>`).join("");
  return `<div class="px-5 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-800">⚠ ${nota}</div>
    <div class="overflow-x-auto opacity-70"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>${thead}</tr></thead><tbody>${body}</tbody></table></div>`;
}

carregar();
