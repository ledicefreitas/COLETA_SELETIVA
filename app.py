import streamlit as st
from supabase import create_client, Client
from postgrest.exceptions import APIError
from dotenv import load_dotenv
import os
import pandas as pd
import re
import random
import bcrypt
import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

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
        error_message = str(e)

        # Trata violação de chave única (duplicidade)
        if "23505" in error_message or "duplicate key value violates unique constraint" in error_message:
            if table_name == "coletores":
                st.warning("⚠️ Já existe um coletor cadastrado com esse nome e telefone.")
            else:
                st.warning("⚠️ Registro duplicado: este item já existe.")
        else:
            st.error(f"❌ Erro ao inserir: {error_message}")


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
# Paginação
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

# ======================================
# Funções do protocolo e PDF
# ======================================
def gerar_numero_protocolo():
    """Gera número de protocolo no formato AAMMXXXX, garantindo unicidade."""
    hoje = datetime.date.today()
    ano_mes = hoje.strftime("%y%m")  # Ex: 2511

    # Busca o último protocolo do mês atual
    result = supabase.table("pesagens")\
        .select("numero_protocolo")\
        .like("numero_protocolo", f"{ano_mes}%")\
        .order("numero_protocolo", desc=True)\
        .limit(1)\
        .execute()

    if result.data and result.data[0].get("numero_protocolo"):
        ultimo = int(result.data[0]["numero_protocolo"][-4:]) + 1
    else:
        ultimo = 1

    novo_protocolo = f"{ano_mes}{str(ultimo).zfill(4)}"

    # Confirma se já existe (caso raro)
    check = supabase.table("pesagens")\
        .select("id_pesagem")\
        .eq("numero_protocolo", novo_protocolo)\
        .execute()

    while check.data:
        ultimo += 1
        novo_protocolo = f"{ano_mes}{str(ultimo).zfill(4)}"
        check = supabase.table("pesagens")\
            .select("id_pesagem")\
            .eq("numero_protocolo", novo_protocolo)\
            .execute()

    return novo_protocolo


def gerar_pdf_comprovante(dados):
    """Gera um PDF de comprovante de pesagem e retorna um buffer de bytes."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    # Cabeçalho
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, 27 * cm, "♻️ SISTEMA DE COLETA SELETIVA")
    c.setFont("Helvetica", 12)
    c.drawString(2 * cm, 26.2 * cm, "Comprovante de Pesagem")

    # Linha divisória
    c.setStrokeColor(colors.green)
    c.setLineWidth(2)
    c.line(2 * cm, 26 * cm, 18 * cm, 26 * cm)

    # Corpo do comprovante
    y = 24.5 * cm
    c.setFont("Helvetica", 11)
    c.drawString(2 * cm, y, f"Protocolo: {dados['protocolo']}")
    y -= 1 * cm
    c.drawString(2 * cm, y, f"Data: {dados['data']}")
    y -= 1 * cm
    c.drawString(2 * cm, y, f"Coletor: {dados['coletor']}")
    y -= 1 * cm
    c.drawString(2 * cm, y, f"Material: {dados['material']}")
    y -= 1 * cm
    c.drawString(2 * cm, y, f"Peso: {dados['peso']} kg")

    # Rodapé
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.gray)
    c.drawString(2 * cm, 2.5 * cm, "Emitido automaticamente pelo Sistema de Coleta Seletiva")
    c.drawString(2 * cm, 2 * cm, f"Desenvolvido por Leticia Freitas © {datetime.date.today().year}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def sortear_protocolo(qtd=1):
    """Sorteia protocolos ainda não sorteados, registra na tabela 'sorteios' e exibe a lista."""
    # Busca as pesagens ainda não sorteadas
    result = supabase.table("pesagens")\
        .select("id_pesagem, numero_protocolo, coletores(nome_completo, telefone_celular)")\
        .eq("sorteado", False)\
        .execute()

    if not result.data:
        st.warning("🎉 Todos os protocolos já foram sorteados!")
        return

    df = pd.DataFrame(result.data)
    if len(df) < qtd:
        qtd = len(df)
        st.warning(f"⚠️ Existem apenas {qtd} protocolos disponíveis para sorteio.")

    # Sorteia aleatoriamente
    sorteados = df.sample(qtd)
    ids_sorteados = sorteados["id_pesagem"].tolist()

    # Pega o próximo número de sorteio
    existing = supabase.table("sorteios").select("numero_sorteio").order("numero_sorteio", desc=True).limit(1).execute()
    next_number = existing.data[0]["numero_sorteio"] + 1 if existing.data else 1

    # Insere sorteados na tabela de sorteios e marca como sorteado
    for i, row in enumerate(sorteados.itertuples(), start=next_number):
        supabase.table("sorteios").insert({
            "id_pesagem": row.id_pesagem,
            "numero_protocolo": row.numero_protocolo,
            "numero_sorteio": i
        }).execute()

        supabase.table("pesagens").update({"sorteado": True}).eq("id_pesagem", row.id_pesagem).execute()

    st.success("🎊 Sorteio realizado com sucesso!")

    # Exibe sorteados
    sorteados_fmt = pd.DataFrame([{
        "Sorteio nº": i,
        "Protocolo": row.numero_protocolo,
        "Nome": row.coletores["nome_completo"],
        "Telefone": f"({row.coletores['telefone_celular'][:2]}) {row.coletores['telefone_celular'][2:7]}-{row.coletores['telefone_celular'][7:]}"
    } for i, row in enumerate(sorteados.itertuples(), start=next_number)])

    st.dataframe(sorteados_fmt, use_container_width=True)

# ======================================
# Login
# ======================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def login():
    st.title("🔒 Login - Sistema de Coleta Seletiva")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        response = supabase.table("usuarios").select("*").eq("username", username).execute()

        if response.data:
            user = response.data[0]
            senha_hash = user["senha"]

            if bcrypt.checkpw(password.encode("utf-8"), senha_hash.encode("utf-8")):
                st.session_state.logged_in = True
                st.session_state.username = user.get("nome_completo") or username
                st.success("✅ Login bem-sucedido!")
                st.rerun()
            else:
                st.error("❌ Usuário ou senha incorretos.")
        else:
            st.error("❌ Usuário não encontrado.")
            
def logout():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.rerun()

if not st.session_state.logged_in:
    login()
    st.stop()

# ======================================
# Menu lateral
# ======================================
st.sidebar.success(f"👋 Olá, {st.session_state.nome_completo}")
if st.sidebar.button("Sair"):
    logout()

#menu = st.sidebar.radio("Navegação", ["Coletores", "Materiais", "Pesagens", "Ranking"])
menu = st.sidebar.radio("Navegação", ["Coletores", "Materiais", "Pesagens", "Ranking", "Sorteio"])


# ======================================
# Coletores
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
        telefone = st.text_input("Telefone (somente números)")
        telefone = ''.join(filter(str.isdigit, telefone))
        submitted = st.form_submit_button("Salvar coletor")

        if submitted:
            if not nome:
                st.error("❌ O nome é obrigatório.")
            elif len(telefone) != 11:
                st.error("❌ O telefone deve ter 11 dígitos (DDD + número).")
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
        st.dataframe(df_paginado, use_container_width=True)

# ======================================
# Materiais
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
        st.dataframe(df_paginado, use_container_width=True)

# ======================================
# 3️⃣ Pesagens (registro, listagem, filtros e comprovante)
# ======================================
elif menu == "Pesagens":
    st.markdown(
        "<p style='font-weight:bold; color:#2E8B57; font-size:20px;'>Registro de Pesagens</p>",
        unsafe_allow_html=True
    )

    df_coletores = get_data("coletores")
    df_materiais = get_data("materiais")

    if df_coletores.empty or df_materiais.empty:
        st.warning("Cadastre coletores e materiais antes de registrar pesagens.")
    else:
        coletores_dict = dict(zip(df_coletores["id_coletor"], df_coletores["nome_completo"]))
        materiais_dict = dict(zip(df_materiais["id_material"], df_materiais["nome_material"]))

        # ------------------------
        # Formulário de nova pesagem
        # ------------------------
        with st.form("add_pesagem"):
            coletor = st.selectbox("Coletor", list(coletores_dict.values()))
            material = st.selectbox("Material", list(materiais_dict.values()))
            peso = st.number_input("Peso", min_value=0.0, step=0.1)
            data_pesagem = st.date_input("Data da pesagem", datetime.date.today())
            submitted = st.form_submit_button("Registrar pesagem")

            if submitted:
                id_coletor = next(k for k, v in coletores_dict.items() if v == coletor)
                id_material = next(k for k, v in materiais_dict.items() if v == material)

                # Impede mais de uma pesagem no mesmo dia por coletor e material
                verifica = supabase.table("pesagens")\
                    .select("id_pesagem")\
                    .eq("id_coletor", id_coletor)\
                    .eq("id_material", id_material)\
                    .eq("data_pesagem", str(data_pesagem))\
                    .execute()

                if verifica.data:
                    st.warning(f"⚠️ O coletor {coletor} já registrou pesagem de {material} em {data_pesagem}.")
                else:
                    numero_protocolo = gerar_numero_protocolo()
                    response = supabase.table("pesagens").insert({
                        "id_coletor": id_coletor,
                        "id_material": id_material,
                        "peso": peso,
                        "data_pesagem": str(data_pesagem),
                        "numero_protocolo": numero_protocolo
                    }).execute()

                    if response.data:
                        st.success(f"✅ Pesagem registrada com sucesso! Protocolo: {numero_protocolo}")
                        st.session_state["ultimo_comprovante"] = {
                            "protocolo": numero_protocolo,
                            "coletor": coletor,
                            "material": material,
                            "peso": peso,
                            "data": str(data_pesagem)
                        }
                        st.rerun()
                    else:
                        st.error("❌ Erro ao registrar pesagem.")

    # ======================================
    # Filtros da listagem
    # ======================================
    st.markdown("---")
    st.subheader("📋 Pesagens registradas")

    filtro_col1, filtro_col2 = st.columns(2)

    with filtro_col1:
        if not df_coletores.empty and "nome_completo" in df_coletores.columns:
            coletores_opcoes = ["Todos"] + df_coletores["nome_completo"].tolist()
        else:
            coletores_opcoes = ["Todos"]
        filtro_coletor = st.selectbox("🔎 Filtrar por coletor", coletores_opcoes)

    with filtro_col2:
        filtro_data = st.date_input("📅 Filtrar por data (opcional)", value=None)

    try:
        query = supabase.table("pesagens")\
            .select("id_pesagem, numero_protocolo, peso, data_pesagem, coletores(nome_completo), materiais(nome_material)")\
            .order("data_pesagem", desc=True)\
            .execute()

        if query.data:
            df = pd.DataFrame(query.data)
            df["Coletor"] = df["coletores"].apply(lambda x: x["nome_completo"])
            df["Material"] = df["materiais"].apply(lambda x: x["nome_material"])
            df = df.rename(columns={
                "id_pesagem": "ID",
                "numero_protocolo": "Protocolo",
                "peso": "Peso (kg)",
                "data_pesagem": "Data"
            })[["ID", "Protocolo", "Coletor", "Material", "Peso (kg)", "Data"]]

            # Aplicar filtros
            if filtro_coletor != "Todos":
                df = df[df["Coletor"] == filtro_coletor]
            if filtro_data:
                df = df[df["Data"] == str(filtro_data)]

            # Exibe tabela com edição apenas do peso
            df_edit = st.data_editor(df, num_rows="fixed", use_container_width=True)

            # Detecta alterações e salva
            if not df.equals(df_edit):
                if st.button("💾 Salvar alterações de peso"):
                    for i in range(len(df_edit)):
                        old_row = df.iloc[i]
                        new_row = df_edit.iloc[i]
                        if old_row["Peso (kg)"] != new_row["Peso (kg)"]:
                            supabase.table("pesagens").update({
                                "peso": new_row["Peso (kg)"]
                            }).eq("id_pesagem", new_row["ID"]).execute()
                    st.success("✅ Alterações salvas com sucesso!")
                    st.rerun()

            # ------------------------------
            # Reimpressão de comprovante
            # ------------------------------
            st.markdown("### 🧾 Reimprimir Comprovante")
            if df.empty:
                st.info("Nenhum registro encontrado com os filtros aplicados.")
            else:
                selected = st.selectbox("Selecione um protocolo:", df["Protocolo"].tolist())
                if st.button("📄 Gerar comprovante selecionado"):
                    registro = df[df["Protocolo"] == selected].iloc[0]
                    st.session_state["ultimo_comprovante"] = {
                        "protocolo": registro["Protocolo"],
                        "coletor": registro["Coletor"],
                        "material": registro["Material"],
                        "peso": registro["Peso (kg)"],
                        "data": registro["Data"]
                    }
                    st.success(f"Comprovante do protocolo {selected} gerado!")
                    st.rerun()
        else:
            st.info("Ainda não há pesagens registradas.")
    except Exception as e:
        st.error(f"❌ Erro ao carregar pesagens: {e}")

    # ======================================
    # Exibir comprovante (novo ou reimpresso)
    # ======================================
    if "ultimo_comprovante" in st.session_state:
        comp = st.session_state["ultimo_comprovante"]
        st.markdown("---")
        st.markdown("### 🧾 Comprovante de Pesagem")
        st.write(f"**Protocolo:** {comp['protocolo']}")
        st.write(f"**Coletor:** {comp['coletor']}")
        st.write(f"**Material:** {comp['material']}")
        st.write(f"**Peso:** {comp['peso']} kg")
        st.write(f"**Data:** {comp['data']}")

        pdf_buffer = gerar_pdf_comprovante(comp)
        st.download_button(
            label="📥 Baixar Comprovante (PDF)",
            data=pdf_buffer,
            file_name=f"comprovante_{comp['protocolo']}.pdf",
            mime="application/pdf"
        )

        # Script para abrir e imprimir o PDF
        st.markdown(
            """
            <script>
            function openAndPrintPDF(base64Data) {
                const pdfData = 'data:application/pdf;base64,' + base64Data;
                const newWindow = window.open(pdfData);
                if (newWindow) {
                    newWindow.onload = function() {
                        newWindow.focus();
                        newWindow.print();
                    };
                } else {
                    alert('Desbloqueie pop-ups para imprimir o comprovante.');
                }
            }
            </script>
            """,
            unsafe_allow_html=True
        )

        import base64
        pdf_base64 = base64.b64encode(pdf_buffer.getvalue()).decode("utf-8")
        st.markdown(
            f"""
            <button onclick="openAndPrintPDF('{pdf_base64}')" style="
                background-color:#2E8B57;
                color:white;
                padding:8px 16px;
                border:none;
                border-radius:6px;
                cursor:pointer;
                font-weight:bold;
            ">
            🖨️ Imprimir Comprovante
            </button>
            """,
            unsafe_allow_html=True
        )


# ======================================
# Ranking
# ======================================
elif menu == "Ranking":
    st.markdown(
        "<p style='font-weight:bold; color:#2E8B57; font-size:20px;'>Ranking de Coletores</p>",
        unsafe_allow_html=True
    )
    col1, col2 = st.columns(2)
    with col1:
        data_inicial = st.date_input("Data inicial")
    with col2:
        data_final = st.date_input("Data final")

    if data_inicial and data_final:
        if data_inicial > data_final:
            st.error("❌ A data inicial não pode ser maior que a data final.")
        else:
            df_pesagens = get_data("pesagens")
            df_coletores = get_data("coletores")
            if df_pesagens.empty or df_coletores.empty:
                st.info("ℹ️ Ainda não há dados para gerar o ranking.")
            else:
                df_pesagens["data_pesagem"] = pd.to_datetime(df_pesagens["data_pesagem"]).dt.date
                df_filtrado = df_pesagens[
                    (df_pesagens["data_pesagem"] >= data_inicial) &
                    (df_pesagens["data_pesagem"] <= data_final)
                ]
                if df_filtrado.empty:
                    st.warning("⚠️ Nenhuma pesagem encontrada nesse intervalo.")
                else:
                    df_ranking = (
                        df_filtrado.merge(df_coletores, on="id_coletor")
                        .groupby("nome_completo")["peso"]
                        .sum()
                        .reset_index()
                        .rename(columns={"nome_completo": "Coletor", "peso": "Total (kg)"})
                        .sort_values(by="Total (kg)", ascending=False)
                    )
                    st.dataframe(df_ranking, use_container_width=True)
# ======================================
# Sorteio
# ======================================

elif menu == "Sorteio":
    st.markdown(
        "<p style='font-weight:bold; color:#2E8B57; font-size:20px;'>Sorteio de Protocolos</p>",
        unsafe_allow_html=True
    )

    qtd = st.number_input("Quantos protocolos sortear?", min_value=1, step=1)
    if st.button("🎯 Realizar sorteio"):
        sortear_protocolo(qtd)

    st.markdown("---")
    st.markdown("### 📜 Histórico de Sorteios")

    query = supabase.table("sorteios")\
        .select("numero_sorteio, numero_protocolo, data_sorteio, pesagens(coletores(nome_completo, telefone_celular))")\
        .order("numero_sorteio", desc=True)\
        .execute()

    if query.data:
        df = pd.DataFrame(query.data)
        df_fmt = pd.DataFrame([{
            "Sorteio nº": row["numero_sorteio"],
            "Protocolo": row["numero_protocolo"],
            "Nome": row["pesagens"]["coletores"]["nome_completo"],
            "Telefone": f"({row['pesagens']['coletores']['telefone_celular'][:2]}) "
                        f"{row['pesagens']['coletores']['telefone_celular'][2:7]}-"
                        f"{row['pesagens']['coletores']['telefone_celular'][7:]}",
            "Data do Sorteio": row["data_sorteio"].split("T")[0]
        } for _, row in df.iterrows()])

        st.dataframe(df_fmt, use_container_width=True)
    else:
        st.info("Nenhum sorteio realizado ainda.")


# ======================================
# Rodapé
# ======================================
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
        Desenvolvido por <b>Leticia Freitas</b> © {ano_atual} — Sistema de Coleta Seletiva ♻️
    </div>
    """,
    unsafe_allow_html=True
)



