import streamlit as st
from supabase import create_client, Client
from postgrest.exceptions import APIError
from dotenv import load_dotenv
import os
import pandas as pd
import re

# ======================================
# Configurações Iniciais
# ======================================
st.set_page_config(page_title="Coleta Seletiva", page_icon="♻️", layout="wide")
st.title("♻️ Sistema de Coleta Seletiva")

# ======================================
# Conexão com Supabase
# ======================================
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ======================================
# Funções Auxiliares
# ======================================
def get_data(table_name):
    response = supabase.table(table_name).select("*").execute()
    if response.data:
        return pd.DataFrame(response.data)
    return pd.DataFrame()

def insert_data(table_name, data, success_msg="✅ Registro inserido com sucesso!"):
    try:
        supabase.table(table_name).insert(data).execute()
        st.success(success_msg)
        st.rerun()
    except APIError as e:
        st.error(f"❌ Erro ao inserir: {e}")

def formatar_celular(valor):
    if pd.isna(valor):
        return ""
    apenas_numeros = re.sub(r"\D", "", str(valor))
    if len(apenas_numeros) == 11:
        return f"({apenas_numeros[:2]}) {apenas_numeros[2:7]}-{apenas_numeros[7:]}"
    elif len(apenas_numeros) == 10:
        return f"({apenas_numeros[:2]}) {apenas_numeros[2:6]}-{apenas_numeros[6:]}"
    return valor

# ======================================
# Função de Paginação
# ======================================
def paginate_dataframe(df, page_size=10, key_prefix=""):
    total_pages = (len(df) - 1) // page_size + 1 if not df.empty else 1
    page = st.session_state.get(f"{key_prefix}_page", 1)

    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("⬅️ Anterior", key=f"{key_prefix}_prev") and page > 1:
            page -= 1
    with col3:
        if st.button("Próxima ➡️", key=f"{key_prefix}_next") and page < total_pages:
            page += 1

    st.session_state[f"{key_prefix}_page"] = page
    start = (page - 1) * page_size
    end = start + page_size
    st.write(f"📄 Página {page}/{total_pages}")

    return df.iloc[start:end]


#=======================================    
# Dicionário de usuários autorizados
#=======================================   

USERS = {
    "admin": "1234",
    "leticia": "senha123",
    "coleta": "verde2025"
}

#=======================================   
# Estado de login
#=======================================   

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def login():
    st.title("🔒 Login - Sistema de Coleta Seletiva")

    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if username in USERS and USERS[username] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("✅ Login bem-sucedido!")
            st.rerun()
        else:
            st.error("❌ Usuário ou senha incorretos.")

def logout():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.rerun()

# Exibe a tela de login se o usuário não estiver autenticado
if not st.session_state.logged_in:
    login()
    st.stop()  # interrompe o app até logar

# ======================================
# Continua o app (após login)
# ======================================
st.sidebar.success(f"👋 Olá, {st.session_state.username}")
if st.sidebar.button("Sair"):
    logout()
    
# ======================================
# Menu lateral
# ======================================
menu = st.sidebar.radio("Navegação", ["Coletores", "Materiais", "Pesagens", "Ranking"])

# ======================================
# 1️⃣ Coletores (edição inline)
# ======================================
if menu == "Coletores":
    st.markdown(
        "<p style='font-weight:bold; color:#2E8B57; font-size:20px;'>Cadastro de Coletores</p>",
        unsafe_allow_html=True
    )
    df_coletores = get_data("coletores")

    with st.form("add_coletor"):
        nome = st.text_input("Nome completo do coletor")
        endereco = st.text_input("Endereço")
        telefone = st.text_input("Telefone (apenas números, ex: 31999999999)")
        telefone = ''.join(filter(str.isdigit, telefone))

        submitted = st.form_submit_button("Salvar coletor")

        if submitted:
            if not nome:
                st.error("❌ O nome é obrigatório.")
            elif len(telefone) != 11:
                st.error("❌ O telefone deve ter exatamente 11 dígitos (DDD + número).")
            else:
                insert_data("coletores", {
                    "nome_completo": nome,
                    "endereco": endereco,
                    "telefone_celular": telefone
                })

    if not df_coletores.empty:
        df = df_coletores.rename(columns={
            "id_coletor": "ID",
            "nome_completo": "Nome",
            "endereco": "Endereço",
            "telefone_celular": "Telefone"
        })
        df["Telefone"] = df["Telefone"].apply(formatar_celular)

        filtro_nome = st.text_input("🔎 Filtrar por nome do coletor")
        if filtro_nome:
            df = df[df["Nome"].str.contains(filtro_nome, case=False, na=False)]

        df_paginado = paginate_dataframe(df, key_prefix="coletores")

        st.markdown("<p style='font-weight:bold; color:#2E8B57; font-size:18px;'>✏️ Editar coletores </p>", unsafe_allow_html=True)
        df_edit = st.data_editor(df_paginado, use_container_width=True, num_rows="fixed", key="editor_coletores")

        if not df_paginado.equals(df_edit):
            if st.button("💾 Salvar alterações"):
                try:
                    for i in range(len(df_edit)):
                        old = df_paginado.iloc[i]
                        new = df_edit.iloc[i]
                        if not old.equals(new):
                            supabase.table("coletores").update({
                                "nome_completo": new["Nome"],
                                "endereco": new["Endereço"],
                                "telefone_celular": new["Telefone"]
                            }).eq("id_coletor", new["ID"]).execute()
                    st.success("✅ Alterações salvas!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao salvar alterações: {e}")

# ======================================
# 2️⃣ Materiais (edição inline)
# ======================================
elif menu == "Materiais":
    st.markdown(
        "<p style='font-weight:bold; color:#2E8B57; font-size:20px;'>Cadastro de Materiais</p>",
        unsafe_allow_html=True
    )
    df_materiais = get_data("materiais")

    with st.form("add_material"):
        nome = st.text_input("Nome do material")
        descricao = st.text_area("Descrição")
        unidade = st.selectbox("Tipo de pesagem", ["kg", "g"], index=0)
        submitted = st.form_submit_button("Salvar material")

        if submitted and nome:
            insert_data("materiais", {
                "nome_material": nome,
                "descricao": descricao,
                "tipo_pesagem": unidade
            })

    if not df_materiais.empty:
        df = df_materiais.rename(columns={
            "id_material": "ID",
            "nome_material": "Nome",
            "descricao": "Descrição",
            "tipo_pesagem": "Unidade"
        })

        filtro_nome = st.text_input("🔎 Filtrar por nome do material")
        if filtro_nome:
            df = df[df["Nome"].str.contains(filtro_nome, case=False, na=False)]

        df_paginado = paginate_dataframe(df, key_prefix="materiais")

        st.markdown("<p style='font-weight:bold; color:#2E8B57; font-size:18px;'>✏️ Editar materiais </p>", unsafe_allow_html=True)
        df_edit = st.data_editor(df_paginado, use_container_width=True, num_rows="fixed", key="editor_materiais")

        if not df_paginado.equals(df_edit):
            if st.button("💾 Salvar alterações"):
                try:
                    for i in range(len(df_edit)):
                        old = df_paginado.iloc[i]
                        new = df_edit.iloc[i]
                        if not old.equals(new):
                            supabase.table("materiais").update({
                                "nome_material": new["Nome"],
                                "descricao": new["Descrição"],
                                "tipo_pesagem": new["Unidade"]
                            }).eq("id_material", new["ID"]).execute()
                    st.success("✅ Alterações salvas!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao salvar alterações: {e}")

# ======================================
# 3️⃣ Pesagens (edição + exclusão inline)
# ======================================
elif menu == "Pesagens":
    st.markdown("<p style='font-weight:bold; color:#2E8B57; font-size:20px;'>Registro de Pesagens</p>", unsafe_allow_html=True)

    df_coletores = get_data("coletores")
    df_materiais = get_data("materiais")

    if df_coletores.empty or df_materiais.empty:
        st.warning("Cadastre coletores e materiais antes de registrar pesagens.")
    else:
        coletores_dict = dict(zip(df_coletores["id_coletor"], df_coletores["nome_completo"]))
        materiais_dict = dict(zip(df_materiais["id_material"], df_materiais["nome_material"]))

        with st.form("add_pesagem"):
            coletor = st.selectbox("Coletor", list(coletores_dict.values()))
            material = st.selectbox("Material", list(materiais_dict.values()))
            peso = st.number_input("Peso", min_value=0.0, step=0.1)
            data_pesagem = st.date_input("Data da pesagem")
            submitted = st.form_submit_button("Registrar pesagem")

            if submitted:
                id_coletor = next(k for k, v in coletores_dict.items() if v == coletor)
                id_material = next(k for k, v in materiais_dict.items() if v == material)
                insert_data("pesagens", {
                    "id_coletor": id_coletor,
                    "id_material": id_material,
                    "peso": peso,
                    "data_pesagem": str(data_pesagem)
                }, success_msg="✅ Pesagem registrada com sucesso!")

    # ---- Tabela de edição + exclusão ----
    try:
        query = supabase.table("pesagens")\
            .select("id_pesagem, peso, data_pesagem, coletores(nome_completo), materiais(nome_material)")\
            .execute()

        if query.data:
            df = pd.DataFrame(query.data)
            df["Coletor"] = df["coletores"].apply(lambda x: x["nome_completo"])
            df["Material"] = df["materiais"].apply(lambda x: x["nome_material"])
            df = df.rename(columns={
                "id_pesagem": "ID",
                "peso": "Peso (kg)",
                "data_pesagem": "Data"
            })[["ID", "Coletor", "Material", "Peso (kg)", "Data"]]

            # Filtros
            col1, col2 = st.columns(2)
            with col1:
                filtro_coletor = st.text_input("🔎 Filtrar por nome do coletor")
            with col2:
                filtro_data = st.date_input("📅 Filtrar por data da pesagem", value=None)

            if filtro_coletor:
                df = df[df["Coletor"].str.contains(filtro_coletor, case=False, na=False)]
            if filtro_data:
                df = df[df["Data"] == str(filtro_data)]

            df_paginado = paginate_dataframe(df, key_prefix="pesagens")

            st.markdown("<p style='font-weight:bold; color:#2E8B57; font-size:18px;'>✏️ Editar / Excluir pesagens</p>", unsafe_allow_html=True)

            # Exibir registros com campos editáveis
            for i, row in df_paginado.iterrows():
                st.write("---")
                cols = st.columns([1, 2, 2, 2, 2, 1])
                with cols[0]:
                    st.write(f"ID: {row['ID']}")
                with cols[1]:
                    st.write(row["Coletor"])
                with cols[2]:
                    st.write(row["Material"])
                with cols[3]:
                    novo_peso = st.number_input("Peso (kg)", value=float(row["Peso (kg)"]), key=f"peso_{row['ID']}")
                with cols[4]:
                    nova_data = st.date_input("Data", value=pd.to_datetime(row["Data"]).date(), key=f"data_{row['ID']}")
                with cols[5]:
                    if st.button("🗑️ Excluir", key=f"del_{row['ID']}"):
                        try:
                            supabase.table("pesagens").delete().eq("id_pesagem", row["ID"]).execute()
                            st.success(f"✅ Pesagem {row['ID']} excluída com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao excluir pesagem {row['ID']}: {e}")

            # Salvar alterações em lote
            if st.button("💾 Salvar alterações"):
                try:
                    for i, row in df_paginado.iterrows():
                        novo_peso = st.session_state[f"peso_{row['ID']}"]
                        nova_data = st.session_state[f"data_{row['ID']}"]
                        if novo_peso != row["Peso (kg)"] or str(nova_data) != row["Data"]:
                            supabase.table("pesagens").update({
                                "peso": novo_peso,
                                "data_pesagem": str(nova_data)
                            }).eq("id_pesagem", row["ID"]).execute()
                    st.success("✅ Alterações salvas!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao salvar alterações: {e}")

        else:
            st.info("Ainda não há pesagens registradas.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar pesagens: {e}")

# ======================================
# 4️⃣ Ranking
# ======================================
elif menu == "Ranking":
    st.markdown("<p style='font-weight:bold; color:#2E8B57; font-size:20px;'>🏆 Ranking de Coletores</p>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        data_inicial = st.date_input("Data inicial")
    with col2:
        data_final = st.date_input("Data final")

    if data_inicial and data_final:
        if data_inicial > data_final:
            st.error("❌ A data inicial não pode ser maior que a data final.")
        else:
            try:
                query = supabase.rpc(
                    "ranking_coletores",
                    {"data_inicial": str(data_inicial), "data_final": str(data_final)}
                ).execute()
                df_ranking = pd.DataFrame(query.data) if query.data else pd.DataFrame()
            except Exception:
                df_pesagens = get_data("pesagens")
                df_coletores = get_data("coletores")

                if df_pesagens.empty or df_coletores.empty:
                    st.info("ℹ️ Ainda não há dados para gerar o ranking.")
                    df_ranking = pd.DataFrame()
                else:
                    df_pesagens["data_pesagem"] = pd.to_datetime(df_pesagens["data_pesagem"]).dt.date
                    df_filtrado = df_pesagens[
                        (df_pesagens["data_pesagem"] >= data_inicial) &
                        (df_pesagens["data_pesagem"] <= data_final)
                    ]

                    if df_filtrado.empty:
                        st.warning("⚠️ Nenhuma pesagem encontrada nesse intervalo.")
                        df_ranking = pd.DataFrame()
                    else:
                        df_ranking = (
                            df_filtrado.merge(df_coletores, on="id_coletor")
                            .groupby("nome_completo")["peso"]
                            .sum()
                            .reset_index()
                            .rename(columns={"nome_completo": "Coletor", "peso": "Total (kg)"})
                            .sort_values(by="Total (kg)", ascending=False)
                        )

            if not df_ranking.empty:
                st.markdown(
                    f"<p style='font-weight:bold; color:#2E8B57; font-size:18px;'>📅 Ranking de {data_inicial.strftime('%d/%m/%Y')} até {data_final.strftime('%d/%m/%Y')}</p>",
                    unsafe_allow_html=True
                )
                st.dataframe(df_ranking, use_container_width=True)
    else:
        st.info("👆 Selecione a data inicial e final para exibir o ranking.")
# ======================================
# Rodapé fixo
# ======================================
import datetime
ano_atual = datetime.date.today().year

st.markdown(
    f"""
    <style>
    .footer {{
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #f5f5f5;
        color: gray;
        text-align: center;
        padding: 8px;
        font-size: 14px;
        border-top: 1px solid #dcdcdc;
        z-index: 100;
    }}
    </style>
    <div class="footer">
        Desenvolvido por <b>Ana</b> © {ano_atual} — Sistema de Coleta Seletiva ♻️
    </div>
    """,
    unsafe_allow_html=True
)






