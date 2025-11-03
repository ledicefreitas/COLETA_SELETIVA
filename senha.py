# admin_usuarios_supabase.py
import streamlit as st
from supabase import create_client, Client
from dotenv import load_dotenv
import os
import bcrypt

# ======================================
# Conexão com Supabase
# ======================================
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ======================================
# Funções auxiliares
# ======================================
def create_user(username: str, nome_completo: str, plain_password: str):
    if len(plain_password) < 3:
        raise ValueError("Senha fraca: mínimo 3 caracteres")

    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(12))
    hashed_str = hashed.decode("utf-8")

    data = {"username": username, "nome_completo": nome_completo, "senha": hashed_str}
    response = supabase.table("usuarios").insert(data).execute()

    if hasattr(response, "error") and response.error:
        raise Exception(response.error.message)
    return response


def update_user(id_usuario: str, novo_nome: str = None, nova_senha: str = None):
    data = {}
    if novo_nome:
        data["nome_completo"] = novo_nome
    if nova_senha:
        hashed = bcrypt.hashpw(nova_senha.encode("utf-8"), bcrypt.gensalt(12))
        data["senha"] = hashed.decode("utf-8")

    if not data:
        raise ValueError("Nenhuma alteração informada.")

    response = supabase.table("usuarios").update(data).eq("id_usuario", id_usuario).execute()

    if hasattr(response, "error") and response.error:
        raise Exception(response.error.message)
    return response


def listar_usuarios():
    response = (
        supabase.table("usuarios")
        .select("id_usuario, username, nome_completo")
        .order("username")
        .execute()
    )
    if hasattr(response, "error") and response.error:
        raise Exception(response.error.message)
    return response.data


# ======================================
# Interface Streamlit (Painel Admin)
# ======================================
st.set_page_config(page_title="Painel Admin - Usuários", page_icon="🧩")
st.title("🧩 Painel Administrativo - Gerenciamento de Usuários")

menu = st.radio("Escolha uma ação:", ["Cadastrar novo usuário", "Editar usuário existente"])

# ---- CADASTRAR NOVO USUÁRIO ----
if menu == "Cadastrar novo usuário":
    st.subheader("📋 Novo Usuário")
    nome_completo = st.text_input("Nome completo:")
    username = st.text_input("Usuário (login):")
    senha = st.text_input("Senha:", type="password")

    if st.button("Criar usuário"):
        try:
            create_user(username, nome_completo, senha)
            st.success(f"✅ Usuário '{username}' criado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao criar usuário: {e}")

# ---- EDITAR USUÁRIO EXISTENTE ----
elif menu == "Editar usuário existente":
    st.subheader("✏️ Editar Usuário")
    try:
        usuarios = listar_usuarios()
    except Exception as e:
        st.error(f"Erro ao carregar usuários: {e}")
        st.stop()

    if not usuarios:
        st.info("Nenhum usuário cadastrado.")
        st.stop()

    # Selecionar o usuário
    nomes_opcoes = {
        f"{u['username']} - {u.get('nome_completo', '')}": u["id_usuario"] for u in usuarios
    }
    escolha = st.selectbox("Selecione o usuário:", list(nomes_opcoes.keys()))

    id_usuario = nomes_opcoes[escolha]
    novo_nome = st.text_input("Novo nome completo (deixe em branco para não alterar):")
    nova_senha = st.text_input("Nova senha (deixe em branco para não alterar):", type="password")

    if st.button("Salvar alterações"):
        try:
            update_user(id_usuario, novo_nome or None, nova_senha or None)
            st.success("✅ Usuário atualizado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao atualizar: {e}")

