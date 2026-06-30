/* Tela de detalhe do sindicato — espelha o print legado (task #38). */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let _sindicato = null;

function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtDataHora(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
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
function brl(n) { return Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }
function num(n) { return Number(n || 0).toLocaleString("pt-BR"); }

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

function checkbox(v) {
  return `<input type="checkbox" disabled class="w-4 h-4 align-middle" ${v ? "checked" : ""}>`;
}

function getIdFromUrl() {
  const u = new URL(window.location.href);
  return u.searchParams.get("id");
}

async function carregar() {
  const id = getIdFromUrl();
  if (!id) {
    document.getElementById("loading").classList.add("hidden");
    document.getElementById("erro").classList.remove("hidden");
    document.getElementById("erro").textContent = "ID do sindicato não informado na URL.";
    return;
  }
  try {
    const s = await apiFetch(`/sindicatos/${id}/detalhe`);
    _sindicato = s;
    render(s);
  } catch (e) {
    document.getElementById("loading").classList.add("hidden");
    document.getElementById("erro").classList.remove("hidden");
    document.getElementById("erro").textContent = `Erro: ${e.message}`;
  }
}

function render(s) {
  document.getElementById("loading").classList.add("hidden");
  document.getElementById("conteudo").classList.remove("hidden");

  document.getElementById("titulo").innerHTML = `${s.razao_social || "Sindicato"}`;

  // Aba: Informação Básica (2 colunas alternando, igual o print legado)
  const tipoBadge = s.tipo_sindicato_resolvido === "FEMACO"
    ? `<span class="inline-block px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800">FEMACO</span>`
    : `<span class="inline-block px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-700">${s.tipo_sindicato_resolvido || "NAO FEMACO"}</span>`;

  document.getElementById("grid-basica").innerHTML = [
    // Linha: Nome | CNPJ
    par("Nome Sindicato", `<span class="font-medium">${s.razao_social || "—"}</span>`),
    par("CNPJ", s.cnpj ? `<span class="font-mono">${fmtCnpj(s.cnpj)}</span>` : null),
    // Razão social | Em atendimento
    par("Razão social", s.nome_fantasia || null),
    par("Em atendimento", checkbox(s.em_atendimento)),
    // Tipo de Sindicato | Categoria
    par("Tipo de Sindicato", tipoBadge),
    par("Categoria", s.categoria || null),
    // Telefone | Outro telefone
    par("Telefone do Sindicato", s.telefone || null),
    par("Outro Telefone", s.outro_telefone || null),
    // Data Criação | Contato Principal
    par("Data de Criação", fmtDataHora(s.criado_em)),
    par("Contato Principal", s.contato_principal || null),
    // E-mail | UF Abrangência
    par("E-mail Principal", s.email ? `<a href="mailto:${s.email}" class="text-rose-600 hover:underline">${s.email}</a>` : null),
    par("UF Abrangência", s.uf_abrangencia || null),
    // Presidente | Parâmetro
    par("Presidente", s.presidente || null),
    par("Parâmetro", s.parametro_nome
      ? `<span class="text-rose-600">${s.parametro_nome}</span>`
      : null),
    // Vice-presidente | Federação
    par("Vice-Presidente", s.vice_presidente || null),
    par("Federação", s.federacao || null),
    // Patronal/Empresa | Contrato BSS
    par("Patronal / Empresa", s.patronal_empresa || null),
    par("Contrato BSS", s.contrato_bss || null),
    // Trabalhadores Ativos | Inativos
    par("Trabalhadores Ativos", `<span class="font-mono font-semibold text-emerald-700">${num(s.qtd_trabalhadores_ativos)}</span>`),
    par("Trabalhadores Inativos", `<span class="font-mono text-slate-500">${num(s.qtd_trabalhadores_inativos)}</span>`),
    // Tarifas do parâmetro (se houver)
    s.parametro_tarifa_titular
      ? par("Tarifa do Titular", `<span class="font-mono">${brl(s.parametro_tarifa_titular)}</span>`)
      : "",
    s.parametro_aceita_dependentes
      ? par("Tarifa do Dependente", `<span class="font-mono">${brl(s.parametro_tarifa_dependente)}</span>`)
      : "",
    // Tipos de benefício e valor agregado
    par("Tipos de Benefício configurados", num(s.qtd_tipos_beneficio)),
    par("Soma das Indenizações", `<span class="font-mono">${brl(s.valor_total_indenizacoes)}</span>`),
    // Descrição em row completo
    s.descricao ? par("Descrição", s.descricao, "md:col-span-12") : "",
  ].join("");

  // Aba: Informações para Entrega — só um bloco "Endereço de Envio"
  // espelhando o print do legado (3 linhas no estilo carta).
  const linhas = [];
  if (s.endereco_logradouro) linhas.push(s.endereco_logradouro);
  const cidadeUfCep = [
    s.endereco_cidade || "",
    s.endereco_uf     || "",
    s.endereco_cep ? fmtCep(s.endereco_cep) : "",
  ].filter(Boolean).join(" ").trim();
  if (cidadeUfCep) linhas.push(cidadeUfCep);
  if (s.endereco_pais) linhas.push(s.endereco_pais);
  const enderecoHtml = linhas.length
    ? linhas.map(l => `<div>${l}</div>`).join("")
    : '<span class="text-slate-400">Endereço não cadastrado</span>';
  document.getElementById("grid-entrega").innerHTML =
    par("Endereço de Envio", enderecoHtml, "md:col-span-12");

  // LOG
  document.getElementById("grid-log").innerHTML = [
    par("Data de Criação", fmtDataHora(s.criado_em)),
    par("Última Modificação", fmtDataHora(s.atualizado_em)),
    par("ID legado (UUID)", s.id_legado_uuid ? `<span class="font-mono text-xs">${s.id_legado_uuid}</span>` : null, "md:col-span-12"),
  ].join("");
}

function trocarAba(qual) {
  const ativaCls   = "px-4 py-2 text-sm font-medium text-slate-800 border-b-2 border-indigo-600";
  const inativaCls = "px-4 py-2 text-sm text-slate-500 hover:text-slate-800";
  document.getElementById("tab-basica").className   = qual === "basica" ? ativaCls : inativaCls;
  document.getElementById("tab-entrega").className  = qual === "entrega" ? ativaCls : inativaCls;
  document.getElementById("aba-basica").classList.toggle("hidden",  qual !== "basica");
  document.getElementById("aba-entrega").classList.toggle("hidden", qual !== "entrega");
}

carregar();
