/*
 * empresa-atual.js — seletor de "empresa atual" para o perfil `empresa`.
 *
 * POR QUE EXISTE
 * --------------
 * Um contato administra N CNPJs (bss.usuario_empresa é N:N — o usuário de
 * teste tem 11). Mas os endpoints de listagem recebem UM id_empresa, e quando
 * a tela não manda nenhum o backend cai em `usuario.empresas[0]`.
 *
 * Resultado antes disto: o usuário via os trabalhadores de UMA empresa, sem
 * saber qual, sem jeito de trocar, e as outras 10 sumiam em silêncio. Chegou
 * a mostrar tela vazia, porque o [0] caiu numa empresa sem trabalhador ativo.
 *
 * Uso:
 *   <script src="/app/js/api.js"></script>
 *   <script src="/app/js/empresa-atual.js"></script>
 *   ...
 *   await montarSeletorEmpresa("#seletor-empresa", () => recarregar());
 *   const id = empresaAtualId();      // manda em &id_empresa=
 *
 * Perfis internos não têm "empresa atual": empresaAtualId() devolve null e o
 * seletor não é renderizado. Eles veem tudo, ou filtram pela tela de Empresas.
 */

const EMPRESA_ATUAL_KEY = "bss_empresa_atual";

let _empresasDoUsuario = null;   // cache por página: [{id, razao_social, cnpj}]


/** Só o perfil 'empresa' tem escopo por empresa. */
function _temEscopoEmpresa() {
  const u = usuarioAtual();
  return !!u && u.perfil === "empresa" && (u.empresas || []).length > 0;
}


/**
 * ID da empresa selecionada, ou null se o perfil não tem escopo.
 *
 * Valida contra os vínculos do JWT: se o valor guardado no localStorage não
 * estiver mais na lista (vínculo removido, ou outro usuário logou no mesmo
 * navegador), cai no primeiro vínculo em vez de mandar um id que o backend
 * vai recusar com 403.
 */
function empresaAtualId() {
  const u = usuarioAtual();
  if (!_temEscopoEmpresa()) return null;

  const guardado = parseInt(localStorage.getItem(EMPRESA_ATUAL_KEY) || "", 10);
  if (guardado && u.empresas.includes(guardado)) return guardado;

  // `empresas` vem ordenado por id do backend (auth._carregar_vinculos), então
  // este default é estável entre sessões.
  return u.empresas[0];
}


function definirEmpresaAtual(id) {
  localStorage.setItem(EMPRESA_ATUAL_KEY, String(id));
}


/**
 * Acrescenta &id_empresa= a uma querystring, quando fizer sentido.
 * Retorna a string sem alteração pra perfis internos.
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
  const opcoes = empresas
    .map((e) => {
      const sel = e.id === atual ? " selected" : "";
      const cnpj = _formatarCnpj(e.cnpj);
      return `<option value="${e.id}"${sel}>${e.razao_social} — ${cnpj}</option>`;
    })
    .join("");

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
    definirEmpresaAtual(parseInt(ev.target.value, 10));
    if (typeof onChange === "function") onChange();
  });
}


function _formatarCnpj(cnpj) {
  const d = (cnpj || "").replace(/\D/g, "");
  if (d.length !== 14) return cnpj || "";
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}
