/* Detalhe do Contato — o usuário externo que administra empresas.
 *
 * Cabeçalho = o que o contato É. Empresas = aba, porque é N:N.
 * O legado erra nisso: mostra "Nome da Empresa" como campo único do
 * cabeçalho, e quem administra 54 CNPJs aparece com 1.
 * Ver docs/AUTOCADASTRO.md.
 */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let _contato = null;
const _relCarregada = new Set();

/* ------------------------------- helpers -------------------------------- */

function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtDataHora(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function fmtCnpj(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  return d.length === 14 ? `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12,14)}` : c;
}
function num(n) { return Number(n || 0).toLocaleString("pt-BR"); }
function pill(txt, cls) {
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cls}">${txt}</span>`;
}
function par(label, valor, classCol = "md:col-span-6") {
  const v = (valor === null || valor === undefined || valor === "")
    ? '<span class="text-slate-400">—</span>' : valor;
  return `<div class="${classCol}">
      <div class="text-xs font-medium uppercase tracking-wider text-slate-500">${label}</div>
      <div class="mt-0.5 text-slate-800">${v}</div>
    </div>`;
}
function ehSemEmail(email) { return (email || "").endsWith("@contato.invalid"); }
function getId() { return new URL(window.location.href).searchParams.get("id"); }

/* -------------------------------- carga --------------------------------- */

async function carregar() {
  const id = getId();
  if (!id) return falhar("ID do contato não informado na URL.");
  try {
    _contato = await apiFetch(`/contatos/${id}/detalhe`);
    render(_contato);
    carregarRel("empresas");
  } catch (e) { falhar(`Erro: ${e.message}`); }
}

function falhar(msg) {
  document.getElementById("loading").classList.add("hidden");
  const erro = document.getElementById("erro");
  erro.classList.remove("hidden");
  erro.textContent = msg;
}

function render(c) {
  document.getElementById("loading").classList.add("hidden");
  document.getElementById("conteudo").classList.remove("hidden");

  document.getElementById("titulo").textContent = c.nome || "Contato";

  const semEmail = ehSemEmail(c.email);
  document.getElementById("badges").innerHTML = [
    c.ativo ? pill("ativo", "bg-emerald-100 text-emerald-800")
            : pill("inativo", "bg-slate-200 text-slate-600"),
    c.tipo_cadastro === "auto" ? pill("autocadastro", "bg-indigo-100 text-indigo-800")
                               : pill("cadastro interno", "bg-slate-100 text-slate-600"),
  ].join(" ");

  // Contato sem e-mail = ficha de telefone/endereço, não usuário do portal
  if (semEmail) {
    const av = document.getElementById("aviso-sem-email");
    av.classList.remove("hidden");
    av.innerHTML = `<b>Contato sem e-mail no legado.</b> Não é usuário do portal —
      existe como ficha de telefone/endereço. O endereço abaixo é sintético
      (<span class="font-mono text-xs">@contato.invalid</span>) e não recebe mensagens.`;
  }

  document.getElementById("grid-basica").innerHTML = [
    par("Nome", `<span class="font-medium">${c.nome || "—"}</span>`),
    par("E-mail (login)", semEmail
      ? '<span class="text-slate-400 italic">sem e-mail</span>'
      : `<a href="mailto:${c.email}" class="text-rose-600 hover:underline">${c.email}</a>`),
    par("Telefone", c.telefone || null),
    par("Perfil", c.perfil || null),
    par("Empresas que administra", `<span class="font-mono font-semibold text-indigo-700">${num(c.qtd_empresas)}</span>
      <span class="text-xs text-slate-400 ml-1">(ver aba abaixo)</span>`),
    par("Último acesso", c.ultimo_login ? fmtDataHora(c.ultimo_login)
      : '<span class="text-slate-400">nunca acessou</span>'),
  ].join("");

  // Preferências (JSONB — 4 toggles vindos do legado)
  const p = c.preferencias_notificacao || {};
  const check = (v) => v
    ? '<span class="text-emerald-600">✓</span>'
    : '<span class="text-slate-300">✕</span>';
  document.getElementById("grid-prefs").innerHTML = [
    ["Financeiro", p.financeiro], ["Benefícios", p.beneficio],
    ["Atualização", p.atualizacao], ["Boletos", p.boleto],
  ].map(([label, v]) => `
    <div class="flex items-center gap-2">
      ${check(v)} <span class="text-slate-700">${label}</span>
    </div>`).join("");

  document.getElementById("grid-log").innerHTML = [
    par("Cadastrado em", fmtDataHora(c.criado_em)),
    par("Origem do cadastro", c.tipo_cadastro === "auto"
      ? "Autocadastro pelo portal" : "Cadastro interno (equipe GNB)"),
    par("ID legado (UUID)", c.id_legado_uuid
      ? `<span class="font-mono text-xs">${c.id_legado_uuid}</span>`
      : '<span class="text-slate-400">nativo do BSS</span>', "md:col-span-12"),
  ].join("");
}

/* --------------------------- abas de relacionamento ---------------------- */

const REL = ["empresas", "solicitacoes"];

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
  const alvo = document.getElementById(`rel-${qual}`);
  alvo.innerHTML = `<div class="py-8 text-center text-slate-400 text-sm">Carregando…</div>`;
  try {
    const dados = await apiFetch(`/contatos/${getId()}/${qual}`);
    alvo.innerHTML = qual === "empresas" ? tabelaEmpresas(dados) : tabelaSolicitacoes(dados);
  } catch (e) {
    _relCarregada.delete(qual);
    alvo.innerHTML = `<div class="py-8 text-center text-rose-600 text-sm">Erro: ${e.message}</div>`;
  }
}

function tabelaEmpresas(linhas) {
  document.getElementById("rcount-empresas").textContent = (linhas || []).length;
  if (!linhas || !linhas.length) {
    return `<div class="py-10 text-center text-slate-400 text-sm">
      Este contato não administra nenhuma empresa.</div>`;
  }
  const corpo = linhas.map(e => `
    <tr class="border-t border-slate-100 hover:bg-slate-50">
      <td class="px-5 py-2">
        <a href="/app/empresa-detalhe.html?id=${e.id}" class="text-indigo-700 hover:underline">${e.razao_social || "—"}</a>
      </td>
      <td class="px-3 py-2 font-mono text-xs">${fmtCnpj(e.cnpj)}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${(e.cidade || "—") + (e.uf ? "/" + e.uf : "")}</td>
      <td class="px-3 py-2 text-right font-mono text-xs">${num(e.qtd_trabalhadores_ativos)}</td>
      <td class="px-3 py-2 text-center text-xs">${(e.adimplencia || "—").toUpperCase()}</td>
      <td class="px-3 py-2 text-center">${e.acesso_ativo
        ? pill("ativo", "bg-emerald-100 text-emerald-800")
        : pill("inativo", "bg-slate-200 text-slate-600")}</td>
    </tr>`).join("");
  const nota = linhas.length > 5
    ? `<div class="px-5 py-2 text-xs text-slate-500 border-t border-slate-100">
         ${linhas.length} CNPJs. No portal legado este contato apareceria com
         <b>um</b> — o campo "Nome da Empresa" do cabeçalho mostra só o primeiro.
       </div>` : "";
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Razão social</th>
        <th class="px-3 py-2 text-left">CNPJ</th>
        <th class="px-3 py-2 text-left">Cidade/UF</th>
        <th class="px-3 py-2 text-right">Trabalhadores</th>
        <th class="px-3 py-2 text-center">Adimplência</th>
        <th class="px-3 py-2 text-center">Acesso</th>
      </tr></thead><tbody>${corpo}</tbody></table></div>${nota}`;
}

function tabelaSolicitacoes(linhas) {
  if (!linhas || !linhas.length) {
    return `<div class="py-10 text-center text-slate-400 text-sm">
      Nenhuma solicitação de acesso registrada.<br>
      <span class="text-xs">Contatos migrados do legado não têm histórico —
      a fila de aprovação passa a existir com o autocadastro no BSS.</span></div>`;
  }
  const cor = { pendente: "bg-amber-100 text-amber-800",
                aprovada: "bg-emerald-100 text-emerald-800",
                reprovada: "bg-rose-100 text-rose-700" };
  const corpo = linhas.map(s => `
    <tr class="border-t border-slate-100">
      <td class="px-5 py-2 text-xs text-slate-500">${fmtDataHora(s.criado_em)}</td>
      <td class="px-3 py-2">${s.empresa || "—"}<div class="text-[11px] font-mono text-slate-400">${fmtCnpj(s.cnpj)}</div></td>
      <td class="px-3 py-2 text-center">${pill(s.status, cor[s.status] || "bg-slate-100 text-slate-600")}</td>
      <td class="px-3 py-2 text-xs text-slate-600">${s.avaliado_por || "—"}
        ${s.avaliado_em ? `<div class="text-[11px] text-slate-400">${fmtDataHora(s.avaliado_em)}</div>` : ""}</td>
      <td class="px-3 py-2 text-xs text-rose-700">${s.motivo_reprovacao || ""}</td>
    </tr>`).join("");
  return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="bg-slate-50 text-slate-500"><tr>
        <th class="px-5 py-2 text-left">Solicitado em</th>
        <th class="px-3 py-2 text-left">Empresa</th>
        <th class="px-3 py-2 text-center">Situação</th>
        <th class="px-3 py-2 text-left">Avaliado por</th>
        <th class="px-3 py-2 text-left">Motivo</th>
      </tr></thead><tbody>${corpo}</tbody></table></div>`;
}

carregar();
