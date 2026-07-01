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
      const d = await apiFetch(`/trabalhadores?id_empresa=${id}&por_pagina=50&situacao=`);
      document.getElementById("rcount-trabalhadores").textContent = num(d.total);
      alvo.innerHTML = tabelaTrabalhadores(d.linhas, d.total);
    } else if (qual === "boletos") {
      const d = await apiFetch(`/boletos?id_empresa=${id}&por_pagina=50`);
      const linhas = d.linhas || d;
      alvo.innerHTML = tabelaBoletos(linhas);
    }
  } catch (e) {
    _relCarregada.delete(qual);
    alvo.innerHTML = `<div class="py-8 text-center text-rose-600 text-sm">Erro: ${e.message}</div>`;
  }
}

function vazio(cols, msg) {
  return `<tr><td colspan="${cols}" class="px-5 py-8 text-center text-slate-400">${msg}</td></tr>`;
}

function tabelaTrabalhadores(linhas, total) {
  const body = (linhas && linhas.length) ? linhas.map(t => `
    <tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="px-5 py-2"><a href="/app/trabalhador-detalhe.html?id=${t.id}" class="text-indigo-700 hover:underline">${t.nome_completo || "—"}</a></td>
      <td class="px-3 py-2 font-mono text-xs">${fmtCpf(t.cpf)}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${t.sindicato || "—"}</td>
      <td class="px-3 py-2 text-center text-xs">${(t.situacao || "—").toUpperCase()}</td>
    </tr>`).join("") : vazio(4, "Nenhum trabalhador vinculado.");
  const aviso = (total > (linhas ? linhas.length : 0))
    ? `<div class="px-5 py-2 text-xs text-slate-500">Mostrando ${linhas.length} de ${num(total)} · veja todos na <a href="/app/trabalhadores.html" class="text-indigo-700 hover:underline">listagem</a>.</div>` : "";
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Nome</th><th class="px-3 py-2 text-left">CPF</th>
        <th class="px-3 py-2 text-left">Sindicato</th><th class="px-3 py-2 text-center">Situação</th>
      </tr></thead><tbody>${body}</tbody></table></div>${aviso}`;
}

function tabelaBoletos(linhas) {
  const body = (linhas && linhas.length) ? linhas.map(b => `
    <tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="px-5 py-2"><a href="/app/boleto-detalhe.html?id=${b.id}" class="text-indigo-700 hover:underline font-mono text-xs">${b.numero_boleto || b.id}</a></td>
      <td class="px-3 py-2 text-xs">${fmtCompetencia(b.mes_referencia)}</td>
      <td class="px-3 py-2 text-right font-mono">${brl(b.valor_total)}</td>
      <td class="px-3 py-2 text-center text-xs text-slate-500">${fmtData(b.data_vencimento)}</td>
      <td class="px-3 py-2 text-center text-xs">${(b.status || "—").toUpperCase()}</td>
    </tr>`).join("") : vazio(5, "Nenhum boleto para esta empresa.");
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Nº Boleto</th><th class="px-3 py-2 text-left">Competência</th>
        <th class="px-3 py-2 text-right">Valor</th><th class="px-3 py-2 text-center">Vencimento</th>
        <th class="px-3 py-2 text-center">Status</th>
      </tr></thead><tbody>${body}</tbody></table></div>`;
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
