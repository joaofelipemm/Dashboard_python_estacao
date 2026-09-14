import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


def get_setting(name: str, default: str | None = None) -> str | None:
	value = os.getenv(name)
	if value:
		return value

	try:
		return st.secrets.get(name, default)
	except FileNotFoundError:
		return default


TABLE_NAME = get_setting("SUPABASE_TABLE", "leituras") or "leituras"
ROW_LIMIT = int(get_setting("SUPABASE_ROW_LIMIT", "100") or "100")


@st.cache_resource
def create_supabase_client() -> Client:
	url = get_setting("SUPABASE_URL")
	key = get_setting("SUPABASE_KEY")

	if not url or not key:
		raise RuntimeError(
			"Defina SUPABASE_URL e SUPABASE_KEY no arquivo .env ou nos Secrets."
		)

	return create_client(url, key)


def query_table(client: Client, table: str, limit: int) -> list[dict]:
	response = client.table(table).select("*").limit(limit).execute()
	return response.data


def render_chart(dataframe: pd.DataFrame) -> None:
	numeric_columns = dataframe.select_dtypes(include="number").columns.tolist()

	if not numeric_columns:
		return

	value_column = st.selectbox("Coluna para visualizar", numeric_columns)
	chart_data = dataframe[[value_column]].reset_index(names="registro")
	figure = px.line(
		chart_data,
		x="registro",
		y=value_column,
		markers=True,
		title=f"Evolução de {value_column}",
	)
	figure.update_layout(
		height=360,
		margin={"l": 20, "r": 20, "t": 60, "b": 20},
		paper_bgcolor="rgba(0,0,0,0)",
		plot_bgcolor="rgba(0,0,0,0)",
	)
	st.plotly_chart(figure, width="stretch")


st.set_page_config(
	page_title="Dashboard de Leituras",
	page_icon="📡",
	layout="wide",
)

st.markdown(
	"""
	<style>
		.stApp { background: #f4f1e8; }
		h1, h2, h3 { color: #183b3b; }
		[data-testid="stMetricValue"] { color: #183b3b; }
		.block-container { padding-top: 3rem; }
	</style>
	""",
	unsafe_allow_html=True,
)

st.title("Leituras da estação")
st.caption("Dados atualizados diretamente da tabela no Supabase.")

with st.sidebar:
	st.header("Configuração")
	st.write(f"Tabela: `{TABLE_NAME}`")
	st.write(f"Limite: `{ROW_LIMIT}` registros")
	if st.button("Atualizar dados", width="stretch"):
		st.cache_resource.clear()
		st.rerun()

try:
	rows = query_table(create_supabase_client(), TABLE_NAME, ROW_LIMIT)
except Exception as error:
	st.error(f"Não foi possível carregar os dados: {error}")
	st.stop()

dataframe = pd.DataFrame(rows)
metric_columns = st.columns(3)
metric_columns[0].metric("Registros", len(dataframe))
metric_columns[1].metric("Tabela", TABLE_NAME)
metric_columns[2].metric("Atualizado", datetime.now().strftime("%H:%M:%S"))

if dataframe.empty:
	st.info("Nenhum registro encontrado.")
else:
	st.subheader("Tabela de dados")
	st.dataframe(dataframe, width="stretch", hide_index=True)
	st.subheader("Visualização")
	render_chart(dataframe)
