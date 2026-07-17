/*
 * empresa-atual.js — FILTRO opcional de empresa para o perfil `empresa`.
 *
 * O QUE ISTO É, E O QUE NÃO É
 * ---------------------------
 * Isto é um FILTRO. Não é "empresa atual" — esse conceito não existe.
 *
 * Um contato administra N CNPJs (bss.usuario_empresa é N:N; o usuário de teste
 * tem 11) e deve ver TODOS por padrão, com a empresa como coluna. É assim que
 * o portal legado funciona: a tela de Empresas lista as 11 juntas, e as listas
 * de Boletos e Benefícios trazem a coluna "Empresa" justamente porque
 * misturam empresas.
 *
 * A primeira versão deste arquivo era um seletor de "empresa atual", porque o
 * backend só aceitava UM id_empresa e caía em `usuario.empresas[0]` quando a
 * tela não mandava nada. Isso escondia 10 das 11 empresas sem avisar — e,
 * quando o [0] calhava de ser uma empresa sem movimento, a tela vinha vazia e
 * parecia sistema quebrado. Os routers agora aplicam `ids_empresa` (o escopo
 * inteiro) e `id_empresa` virou o que sempre deveria ter sido: opcional.
 *
 * Uso:
 *   <script src="/app/js/api.js"></script>
 *   <script src="/app/js/empresa-atual.js"></script>
 *   ...
 *   await montarSeletorEmpresa("#seletor-empresa", () => recarregar());
 *   comEmpresaAtual(params);   // só acrescenta id_empresa se houver escolha
 *
 * Perfis internos não filtram por aqui: o seletor não é renderizado e
 * empresaAtualId() devolve null.
 */

const EMPRESA_ATUAL_KEY = "bss_empresa_atual";

let _empresasDoUsuario = null;   // cache por página: [{id, razao_social, cnpj}]


/** Só o perfil 'empresa' tem escopo por empresa. */
function _temEscopoEmpresa() {
  const u = usuarioAtual();
  return !!u && u.perfil === "empresa" && (u.empresas || []).length > 0;
}


/**
 * ID da empresa filtrada, ou **null** quando não há filtro (= todas).
 *
 * null é o DEFAULT e é o caso normal: sem filtro, o backend aplica o escopo
 * inteiro (ids_empresa) e o usuário vê as 11. Nunca devolver empresas[0] aqui
 * — foi assim que 10 empresas sumiam caladas.
 *
 * Valida contra os vínculos do JWT: se o valor guardado no localStorage não
 * estiver mais na lista (vínculo removido, ou outro usuário logou no mesmo
 * navegador), o filtro é descartado em vez de mandar um id que o backend
 * recusaria com 403.
 */
function empresaAtualId() {
  const u = usuarioAtual();
  if (!_temEscopoEmpresa()) return null;

  const guardado = parseInt(localStorage.getItem(EMPRESA_ATUAL_KEY) || "", 10);
  if (guardado && u.empresas.includes(guardado)) return guardado;
  return null;   // sem filtro = todas as empresas do usuário
}


function definirEmpresaAtual(id) {
  // "" / null / NaN → limpa o filtro (opção "Todas as empresas").
  if (!id) localStorage.removeItem(EMPRESA_ATUAL_KEY);
  else localStorage.setItem(EMPRESA_ATUAL_KEY, String(id));
}


/**
 * Acrescenta &id_empresa= à querystring SÓ quando há filtro escolhido.
 * Sem escolha, não manda nada — e o backend devolve todas as do escopo.
 */
function comEmpresaAtual(params) {
  const id = empresaAtualId();
  if (id) params.set("id_empresa", id);
  return params;
}


/** Carrega as empresas do usuário (uma vez por página). */
async function _carregarEmpresas() {
  if (_empresasDoUsuario) return _empresasDoUsuario;
  // por_pagina=200 é o teto do repo. Um contato com mais de 200 CNPJs não
  // existe hoje (o maior tem 11); se existir, o seletor mostra os 200
  // primeiros e a tela de Empresas continua sendo o caminho completo.
  const r = await apiFetch("/empresas?por_pagina=200&ordem=razao_social");
  _empresasDoUsuario = r.linhas || [];
  return _empresasDoUsuario;
}


/**
 * Renderiza o <select> no container e chama onChange() quando trocar.
 *
 * Não renderiza nada se o usuário tiver só 1 empresa — seletor de uma opção
 * é ruído. Também não renderiza pra perfil interno.
 */
async function montarSeletorEmpresa(seletorContainer, onChange) {
  const box = document.querySelector(seletorContainer);
  if (!box) return;

  if (!_temEscopoEmpresa()) {
    box.innerHTML = "";
    return;
  }

  let empresas;
  try {
    empresas = await _carregarEmpresas();
  } catch (e) {
    box.innerHTML = `<span class="text-xs text-rose-600">Erro ao carregar empresas</span>`;
    return;
  }

  if (empresas.length <= 1) {
    // Uma empresa só: mostra o nome, sem select.
    box.innerHTML = empresas.length
      ? `<span class="text-sm text-slate-600 truncate max-w-xs" title="${empresas[0].razao_social}">${empresas[0].razao_social}</span>`
      : "";
    return;
  }

  const atual = empresaAtualId();

  // "Todas" é a PRIMEIRA opção e o default. Quem administra 11 CNPJs quer ver
  // os 11; filtrar num deles é a exceção, não a regra.
  const opcoes =
    `<option value=""${atual ? "" : " selected"}>Todas as minhas empresas (${empresas.length})</option>` +
    empresas.map((e) => {
      const sel = e.id === atual ? " selected" : "";
      return `<option value="${e.id}"${sel}>${e.razao_social} — ${_formatarCnpj(e.cnpj)}</option>`;
    }).join("");

  box.innerHTML = `
    <label class="flex items-center gap-2">
      <span class="text-xs text-slate-400 uppercase tracking-wider whitespace-nowrap">Empresa</span>
      <select id="sel-empresa-atual"
              class="text-sm border border-slate-300 rounded-lg px-2 py-1.5 bg-white
                     max-w-md truncate focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
        ${opcoes}
      </select>
    </label>
  `;

  document.getElementById("sel-empresa-atual").addEventListener("change", (ev) => {
    definirEmpresaAtual(parseInt(ev.target.value, 10) || null);
    if (typeof onChange === "function") onChange();
  });
}


function _formatarCnpj(cnpj) {
  const d = (cnpj || "").replace(/\D/g, "");
  if (d.length !== 14) return cnpj || "";
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}
