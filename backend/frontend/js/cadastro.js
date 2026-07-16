/* Autocadastro — PROTÓTIPO. Página pública (sem exigirLogin).
 *
 * Fluxo (docs/AUTOCADASTRO.md):
 *   CNPJ existe?  SIM → pede nome/telefone/senha → 2º gestor
 *                 NÃO → RFB → dados read-only → e-mail
 *   Todo contato novo espera aprovação de analista interno.
 */

const TERMO = "Ao prosseguir com este cadastro, estou ciente da minha " +
  "responsabilidade civil e criminal quanto à exatidão dos dados e quanto à " +
  "segurança dos dados que irei incluir, considerando ser a principal " +
  "finalidade o atendimento ao preconizado pela CCT - Convenção Coletiva de " +
  "Trabalho, no tocante às contribuições mensais das empresas e a concessão " +
  "de benefícios de CCT aos seus trabalhadores";

let _estado = { cnpjOk: false, existe: null, empresa: null, rfb: null };

document.getElementById("termo-texto").textContent = TERMO;

/* ------------------------------- helpers -------------------------------- */

function digitos(s) { return (s || "").replace(/\D/g, ""); }

function mascaraCnpj(el) {
  const d = digitos(el.value).slice(0, 14);
  let v = d;
  if (d.length > 2)  v = `${d.slice(0,2)}.${d.slice(2)}`;
  if (d.length > 5)  v = `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5)}`;
  if (d.length > 8)  v = `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8)}`;
  if (d.length > 12) v = `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}`;
  el.value = v;
}

function msg(id, texto, cor) {
  const el = document.getElementById(id);
  el.className = `mt-2 text-sm ${cor}`;
  el.innerHTML = texto;
}

function par(label, valor) {
  return `<div>
      <div class="text-xs font-medium uppercase tracking-wider text-slate-400">${label}</div>
      <div class="mt-0.5 text-slate-700">${valor || '<span class="text-slate-300">—</span>'}</div>
    </div>`;
}

async function api(path, opts = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `Erro ${resp.status}`);
  return data;
}

/* ---------------------------- etapa 1: CNPJ ----------------------------- */

async function verificarCnpj() {
  const cnpj = digitos(document.getElementById("f-cnpj").value);
  if (cnpj.length !== 14) {
    if (cnpj.length) msg("cnpj-msg", "CNPJ incompleto.", "text-amber-700");
    return;
  }
  const btn = document.getElementById("btn-verificar");
  btn.disabled = true;
  msg("cnpj-msg", "Consultando…", "text-slate-500");

  try {
    const d = await api(`/autocadastro/cnpj/${cnpj}`);
    _estado.cnpjOk = true;
    _estado.existe = d.existe;
    _estado.empresa = d.empresa;
    _estado.rfb = d.rfb;

    if (d.existe) {
      msg("cnpj-msg", `✓ ${d.mensagem}`, "text-emerald-700");
      mostrarEmpresa({
        razao_social: d.empresa.razao_social,
        cidade: d.empresa.cidade, uf: d.empresa.uf,
      }, `já cadastrada · ${d.empresa.gestores} gestor(es)`);
    } else {
      msg("cnpj-msg", `✓ ${d.mensagem}`, "text-emerald-700");
      mostrarEmpresa(d.rfb, "dados da Receita Federal — não editáveis");
    }
    document.getElementById("sec-usuario").classList.remove("hidden");
    document.getElementById("sec-termo").classList.remove("hidden");
  } catch (e) {
    _estado.cnpjOk = false;
    msg("cnpj-msg", `✕ ${e.message}`, "text-rose-600");
    document.getElementById("sec-empresa").classList.add("hidden");
    document.getElementById("sec-usuario").classList.add("hidden");
    document.getElementById("sec-termo").classList.add("hidden");
  } finally {
    btn.disabled = false;
  }
}

function mostrarEmpresa(e, origem) {
  document.getElementById("sec-empresa").classList.remove("hidden");
  document.getElementById("empresa-origem").textContent = origem;
  document.getElementById("grid-empresa").innerHTML = [
    par("Razão social", e.razao_social),
    par("Nome fantasia", e.nome_fantasia),
    par("Situação cadastral", e.situacao_cadastral),
    par("Atividade principal", e.cnae_descricao),
    par("Endereço", [e.logradouro, e.numero].filter(Boolean).join(", ")),
    par("Cidade/UF", [e.cidade, e.uf].filter(Boolean).join("/")),
  ].join("");
}

/* --------------------------- etapa 3: e-mail ---------------------------- */
// Se o e-mail já for contato conhecido, não repedimos nome/senha — ele já tem.
// Não existe endpoint público que confirme isso (seria enumeração de usuários),
// então o protótipo sempre pede os dados e o backend decide.

function verificarEmail() {
  const email = document.getElementById("f-email").value.trim();
  if (!email || !email.includes("@")) return;
  document.getElementById("campos-novo").classList.remove("hidden");
  document.getElementById("email-msg").innerHTML =
    '<span class="text-slate-500">Se você já tem cadastro, seus dados atuais ' +
    'serão mantidos e apenas o novo CNPJ será vinculado.</span>';
}

/* ---------------------------- etapa 4: envio ---------------------------- */

async function finalizar() {
  const btn = document.getElementById("btn-finalizar");
  const cnpj = digitos(document.getElementById("f-cnpj").value);
  const email = document.getElementById("f-email").value.trim();
  const nome = document.getElementById("f-nome").value.trim();
  const telefone = document.getElementById("f-telefone").value.trim();
  const senha = document.getElementById("f-senha").value;
  const senha2 = document.getElementById("f-senha2").value;
  const aceite = document.getElementById("f-aceite").checked;

  if (!_estado.cnpjOk) return msg("envio-msg", "Verifique o CNPJ primeiro.", "text-rose-600");
  if (!email.includes("@")) return msg("envio-msg", "Informe um e-mail válido.", "text-rose-600");
  if (!aceite) return msg("envio-msg", "É necessário aceitar o termo.", "text-rose-600");
  if (senha && senha !== senha2) return msg("envio-msg", "As senhas não conferem.", "text-rose-600");
  if (senha && senha.length < 8) return msg("envio-msg", "A senha precisa de ao menos 8 caracteres.", "text-rose-600");

  // Trava do duplo clique — o legado não tem isso e ganhou 94 e-mails duplicados
  btn.disabled = true;
  btn.textContent = "Enviando…";
  msg("envio-msg", "", "");

  try {
    const d = await api("/autocadastro", {
      method: "POST",
      body: JSON.stringify({
        cnpj, email,
        nome: nome || null,
        telefone: telefone || null,
        senha: senha || null,
        aceite,
      }),
    });
    document.getElementById("form").classList.add("hidden");
    document.getElementById("sucesso").classList.remove("hidden");
    document.getElementById("sucesso-msg").textContent = d.duplicada
      ? "Já havia um pedido em análise para este CNPJ com este e-mail. "
        + "Não criamos outro — aguarde o retorno da nossa equipe."
      : d.mensagem;
  } catch (e) {
    msg("envio-msg", `✕ ${e.message}`, "text-rose-600");
    btn.disabled = false;
    btn.textContent = "Finalizar";
  }
}
