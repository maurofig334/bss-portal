/* Tela de detalhe do trabalhador — espelha os campos do legado (task #37). */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let _trab = null;

function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtDataHora(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function fmtCpf(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length === 11) return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9,11)}`;
  return c;
}
function fmtCnpj(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length === 14) return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12,14)}`;
  return c;
}
function fmtCep(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length === 8) return `${d.slice(0,5)}-${d.slice(5,8)}`;
  return c;
}

function par(label, valor, classCol = "md:col-span-6") {
  const v = (valor === null || valor === undefined || valor === "")
    ? '<span class="text-slate-400">—</span>'
    : valor;
  return `
    <div class="${classCol}">
      <div class="text-xs font-medium uppercase tracking-wider text-slate-500">${label}</div>
      <div class="mt-0.5 text-slate-800">${v}</div>
    </div>
  `;
}

function badgeSituacao(s) {
  const cores = {
    ativo:    "bg-emerald-100 text-emerald-800",
    inativo:  "bg-slate-200 text-slate-700",
    carencia: "bg-amber-100 text-amber-800",
  };
  const cls = cores[s] || "bg-slate-100 text-slate-600";
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cls}">${(s || "—").toUpperCase()}</span>`;
}

// Link "vermelho" pra outra entidade (mesmo padrão do legado)
function linkEntidade(texto, href) {
  if (!texto) return null;
  if (!href) return texto;
  return `<a href="${href}" class="text-rose-600 hover:underline">${texto}</a>`;
}

function getIdFromUrl() {
  return new URL(window.location.href).searchParams.get("id");
}

async function carregar() {
  const id = getIdFromUrl();
  if (!id) {
    falhar("ID do trabalhador não informado na URL.");
    return;
  }
  try {
    _trab = await apiFetch(`/trabalhadores/${id}/detalhe`);
    render(_trab);
  } catch (e) {
    falhar(`Erro: ${e.message}`);
  }
}

function falhar(msg) {
  document.getElementById("loading").classList.add("hidden");
  const erro = document.getElementById("erro");
  erro.classList.remove("hidden");
  erro.textContent = msg;
}

function render(t) {
  document.getElementById("loading").classList.add("hidden");
  document.getElementById("conteudo").classList.remove("hidden");

  document.getElementById("titulo").innerHTML = t.nome_completo || "Trabalhador";

  const ehDependente = t.titularidade === "dependente";

  // Link da empresa -> listagem filtrada por CNPJ; sindicato -> tela de detalhe
  const linkEmpresa = t.empresa
    ? linkEntidade(t.empresa, t.id_empresa_atual ? `/app/empresa-detalhe.html?id=${t.id_empresa_atual}` : null)
    : null;
  const linkSindicato = t.sindicato
    ? linkEntidade(t.sindicato, t.id_sindicato_atual ? `/app/sindicato-detalhe.html?id=${t.id_sindicato_atual}` : null)
    : null;

  // CPF Titular: só pra dependente; vira link pro detalhe do titular se achado
  let cpfTitularHtml = null;
  if (ehDependente && t.cpf_titular) {
    const txt = `<span class="font-mono">${fmtCpf(t.cpf_titular)}</span>`
      + (t.titular ? ` <span class="text-slate-500">— ${t.titular.nome_completo}</span>` : "");
    cpfTitularHtml = t.titular
      ? `<a href="/app/trabalhador-detalhe.html?id=${t.titular.id}" class="text-rose-600 hover:underline">${txt}</a>`
      : txt;
  }

  document.getElementById("grid-basica").innerHTML = [
    par("Titularidade", ehDependente ? "Dependente" : "Trabalhador"),
    par("CPF Titular", cpfTitularHtml),
    par("CPF", `<span class="font-mono">${fmtCpf(t.cpf)}</span>`),
    par("Nome Completo", `<span class="font-medium">${t.nome_completo || "—"}</span>`),
    par("Situação", badgeSituacao(t.situacao)),
    par("Sindicato", linkSindicato),
    par("Empresa", linkEmpresa),
    par("CNPJ da Empresa", t.empresa_cnpj ? `<span class="font-mono">${fmtCnpj(t.empresa_cnpj)}</span>` : null),
    par("Último Pagamento", fmtData(t.ultimo_pagamento_em)),
    par("Dep. Relacionados", ehDependente ? null
      : `<span class="font-mono">${t.qtd_dependentes_ativos || 0}</span>`),
  ].join("");

  // Dados coletados no benefício
  const endereco = montarEndereco(t);
  document.getElementById("grid-beneficio").innerHTML = [
    par("Data de Admissão", fmtData(t.data_admissao)),
    par("Data de Nascimento", fmtData(t.data_nascimento)),
    par("Telefone", t.telefone || null),
    par("E-mail", t.email ? `<a href="mailto:${t.email}" class="text-rose-600 hover:underline">${t.email}</a>` : null),
    par("Endereço Principal", endereco, "md:col-span-12"),
  ].join("");

  // Relacionamentos (abas inferiores)
  renderRelacionamentos(t, ehDependente);

  // LOG
  document.getElementById("grid-log").innerHTML = [
    par("Data de Criação", fmtDataHora(t.criado_em)),
    par("Última Modificação", fmtDataHora(t.atualizado_em)),
    par("ID legado (UUID)", t.id_legado_uuid ? `<span class="font-mono text-xs">${t.id_legado_uuid}</span>` : null, "md:col-span-12"),
  ].join("");
}

function montarEndereco(t) {
  const linha1 = [t.logradouro, t.numero].filter(Boolean).join(", ");
  const linha2 = [t.complemento, t.bairro].filter(Boolean).join(" — ");
  const linha3 = [
    [t.cidade, t.uf].filter(Boolean).join("/"),
    t.cep ? fmtCep(t.cep) : "",
  ].filter(Boolean).join(" · ");
  const linhas = [linha1, linha2, linha3].filter(Boolean);
  return linhas.length
    ? linhas.map(l => `<div>${l}</div>`).join("")
    : '<span class="text-slate-400">Endereço não cadastrado</span>';
}

/* ----------------------- Abas de relacionamento -------------------------- */

function renderRelacionamentos(t, ehDependente) {
  const deps = t.dependentes || [];
  document.getElementById("rcount-dependentes").textContent = deps.length;

  const tb = document.getElementById("tbody-dependentes");
  if (deps.length) {
    tb.innerHTML = deps.map(d => `
      <tr class="border-t border-slate-100 hover:bg-slate-50">
        <td class="px-5 py-2">
          <a href="/app/trabalhador-detalhe.html?id=${d.id}" class="text-indigo-700 hover:underline">${d.nome_completo || "—"}</a>
        </td>
        <td class="px-3 py-2 font-mono text-xs">${fmtCpf(d.cpf)}</td>
        <td class="px-3 py-2 text-center">${badgeSituacao(d.situacao)}</td>
        <td class="px-3 py-2 text-center text-xs text-slate-500">${fmtData(d.data_nascimento)}</td>
      </tr>`).join("");
  } else {
    const msg = ehDependente
      ? "Este trabalhador é um dependente — não possui dependentes próprios."
      : "Nenhum dependente vinculado.";
    tb.innerHTML = `<tr><td colspan="4" class="px-5 py-8 text-center text-slate-400">${msg}</td></tr>`;
  }

  // Boletos e Benefícios: mockup (a serem religados aos endpoints reais).
  document.getElementById("rel-boletos").innerHTML = mockTabela(
    ["Nº Boleto", "Competência", "Valor", "Vencimento", "Status"],
    [
      ["000123456-7", "05/2026", "R$ 142,00", "10/06/2026", "Pago"],
      ["000123410-2", "04/2026", "R$ 142,00", "10/05/2026", "Pago"],
      ["000123380-9", "03/2026", "R$ 142,00", "10/04/2026", "Pago"],
    ],
    "Boletos do trabalhador — dados de exemplo (mockup)."
  );
  document.getElementById("rel-beneficios").innerHTML = mockTabela(
    ["Tipo de Benefício", "Sindicato", "Valor", "Situação"],
    [
      ["Auxílio funeral", "SIEMACO SP - ASSEIO", "R$ 5.000,00", "Ativo"],
      ["Cesta natalidade", "SIEMACO SP - ASSEIO", "R$ 300,00", "Ativo"],
    ],
    "Benefícios do trabalhador — dados de exemplo (mockup)."
  );
}

function mockTabela(cols, linhas, nota) {
  const thead = cols.map(c => `<th class="px-5 py-2 text-left">${c}</th>`).join("");
  const body = linhas.map(r => `
    <tr class="border-t border-slate-100">
      ${r.map(v => `<td class="px-5 py-2 text-slate-600">${v}</td>`).join("")}
    </tr>`).join("");
  return `
    <div class="px-5 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-800">⚠ ${nota}</div>
    <div class="overflow-x-auto opacity-70">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-slate-500"><tr>${thead}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

function trocarRel(qual) {
  const abas = ["dependentes", "boletos", "beneficios"];
  const ativa = "px-4 py-2.5 text-sm font-medium text-slate-800 border-b-2 border-indigo-600 whitespace-nowrap";
  const inativa = "px-4 py-2.5 text-sm text-slate-500 hover:text-slate-800 whitespace-nowrap";
  abas.forEach(a => {
    document.getElementById(`rtab-${a}`).className = (a === qual ? ativa : inativa);
    document.getElementById(`rel-${a}`).classList.toggle("hidden", a !== qual);
  });
}

carregar();
