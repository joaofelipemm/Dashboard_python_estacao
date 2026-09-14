import os

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
ROW_LIMIT = int(get_setting("SUPABASE_ROW_LIMIT", "2000") or "2000")
REFRESH_INTERVAL = "60s"


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


def load_data() -> pd.DataFrame:
	rows = query_table(create_supabase_client(), TABLE_NAME, ROW_LIMIT)
	return pd.DataFrame(rows)


def find_column(dataframe: pd.DataFrame, names: tuple[str, ...]) -> str | None:
	for column in dataframe.columns:
		normalized = str(column).lower().replace("_", " ")
		if any(name in normalized for name in names):
			return str(column)
	return None


def prepare_temperature_data(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, str, str]:
	temperature_column = find_column(
		dataframe, ("temperatura", "temperature", "temp")
	)
	date_column = find_column(
		dataframe,
		("created at", "timestamp", "datetime", "data hora", "data", "date"),
	)

	if not temperature_column:
		raise ValueError("Não encontrei uma coluna de temperatura na tabela.")
	if not date_column:
		raise ValueError("Não encontrei uma coluna de data ou horário na tabela.")

	prepared = dataframe.copy()
	prepared[temperature_column] = pd.to_numeric(
		prepared[temperature_column], errors="coerce"
	)
	prepared["_momento"] = pd.to_datetime(prepared[date_column], errors="coerce")
	prepared = prepared.dropna(subset=[temperature_column, "_momento"])
	prepared["_dia"] = prepared["_momento"].dt.date
	prepared = prepared.sort_values("_momento")
	return prepared, temperature_column, date_column


def chart_layout(figure) -> None:
	figure.update_layout(
		height=390,
		margin={"l": 20, "r": 20, "t": 60, "b": 20},
		paper_bgcolor="rgba(0,0,0,0)",
		plot_bgcolor="rgba(0,0,0,0)",
	)
	st.plotly_chart(figure, width="stretch")


def render_daily_summary(dataframe: pd.DataFrame, temperature_column: str) -> None:
	daily = (
		dataframe.groupby("_dia", as_index=False)[temperature_column]
		.agg(maior="max", menor="min", media="mean")
	)
	daily_long = daily.melt(
		id_vars="_dia", var_name="medida", value_name="temperatura"
	)
	figure = px.line(
		daily_long,
		x="_dia",
		y="temperatura",
		color="medida",
		markers=True,
		title="Maior, menor e média por dia",
		labels={"_dia": "Dia", "temperatura": "Temperatura", "medida": ""},
	)
	chart_layout(figure)


def render_selected_day(dataframe: pd.DataFrame, temperature_column: str) -> None:
	days = sorted(dataframe["_dia"].unique())
	selected_day = st.selectbox("Escolha o dia", days, format_func=str)
	selected = dataframe[dataframe["_dia"] == selected_day]

	figure = px.line(
		selected,
		x="_momento",
		y=temperature_column,
		markers=True,
		title=f"Todas as leituras de {selected_day}",
		labels={"_momento": "Horário", temperature_column: "Temperatura"},
	)
	chart_layout(figure)


@st.fragment(run_every=REFRESH_INTERVAL)
def render_dashboard() -> None:
	try:
		dataframe = load_data()
	except Exception as error:
		st.error(f"Não foi possível carregar os dados: {error}")
		return

	if dataframe.empty:
		st.info("Nenhum registro encontrado.")
		return

	try:
		prepared, temperature_column, _date_column = prepare_temperature_data(dataframe)
	except ValueError as error:
		st.error(str(error))
		return

	if prepared.empty:
		st.warning("Não existem leituras válidas de temperatura para exibir.")
		return

	st.subheader("Resumo diário")
	render_daily_summary(prepared, temperature_column)
	st.subheader("Leituras do dia")
	render_selected_day(prepared, temperature_column)


def render_sidebar() -> None:
	with st.sidebar:
		st.header("Configuração")
		st.write(f"Tabela: `{TABLE_NAME}`")
		st.write(f"Limite: `{ROW_LIMIT}` registros")
		st.caption(f"Atualização automática: a cada {REFRESH_INTERVAL}")
		if st.button("Atualizar agora", width="stretch"):
			st.rerun()


def configure_page() -> None:
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


def main() -> None:
	configure_page()
	st.title("Leituras da estação")
	st.caption("Dados atualizados diretamente da tabela no Supabase.")
	render_sidebar()
	render_dashboard()


if __name__ == "__main__":
	main()
