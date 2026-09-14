import os
from typing import cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from plotly.subplots import make_subplots
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
	return cast(list[dict], response.data)


def load_data() -> pd.DataFrame:
	rows = query_table(create_supabase_client(), TABLE_NAME, ROW_LIMIT)
	return pd.DataFrame(rows)


def find_column(dataframe: pd.DataFrame, names: tuple[str, ...]) -> str | None:
	for column in dataframe.columns:
		normalized = str(column).lower().replace("_", " ")
		if any(name in normalized for name in names):
			return str(column)
	return None


def prepare_weather_data(
	dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, str, str, str, str]:
	temperature_column = find_column(
		dataframe, ("temperatura", "temperature", "temp")
	)
	humidity_column = find_column(
		dataframe, ("umidade", "humidity", "humidade", "humid")
	)
	date_column = find_column(
		dataframe,
		("created at", "timestamp", "datetime", "data hora", "data", "date"),
	)
	hour_column = find_column(dataframe, ("hora", "hour", "time"))

	if not temperature_column:
		raise ValueError("Não encontrei uma coluna de temperatura na tabela.")
	if not humidity_column:
		raise ValueError("Não encontrei uma coluna de umidade na tabela.")
	if not date_column:
		raise ValueError("Não encontrei uma coluna de data ou horário na tabela.")
	if not hour_column:
		raise ValueError("Não encontrei uma coluna 'hora' na tabela.")

	prepared = dataframe.copy()
	prepared[temperature_column] = pd.to_numeric(
		prepared[temperature_column], errors="coerce"
	)
	prepared[humidity_column] = pd.to_numeric(
		prepared[humidity_column], errors="coerce"
	)
	prepared["_momento"] = pd.to_datetime(prepared[date_column], errors="coerce")
	prepared["_dia"] = prepared["_momento"].dt.date
	prepared["_hora_grafico"] = pd.to_datetime(
		prepared["_dia"].astype(str) + " " + prepared[hour_column].astype(str),
		errors="coerce",
	)
	prepared = prepared.dropna(
		subset=[temperature_column, "_momento", "_hora_grafico"]
	)
	prepared = prepared.sort_values("_momento")
	return prepared, temperature_column, humidity_column, date_column, hour_column


def chart_layout(figure) -> None:
	figure.update_layout(
		height=390,
		margin={"l": 20, "r": 20, "t": 60, "b": 20},
		paper_bgcolor="rgba(0,0,0,0)",
		plot_bgcolor="rgba(0,0,0,0)",
	)
	st.plotly_chart(figure, width="stretch")


def render_daily_summary(
	dataframe: pd.DataFrame, temperature_column: str, humidity_column: str
) -> None:
	temperature_summary = dataframe.groupby("_dia")[temperature_column].agg(
		temperatura_maior="max",
		temperatura_menor="min",
		temperatura_media="mean",
	)
	humidity_summary = dataframe.groupby("_dia")[humidity_column].agg(
		umidade_maior="max",
		umidade_menor="min",
		umidade_media="mean",
	)
	summary = temperature_summary.join(humidity_summary).reset_index()
	summary["_dia"] = summary["_dia"].astype(str)
	st.dataframe(summary, width="stretch", hide_index=True)


def render_selected_day(
	dataframe: pd.DataFrame,
	temperature_column: str,
	humidity_column: str,
	hour_column: str,
) -> None:
	days = sorted(dataframe["_dia"].unique())
	selected_day = st.selectbox("Escolha o dia", days, format_func=str)
	selected = dataframe[dataframe["_dia"] == selected_day]
	temperature_samples = selected.dropna(subset=[temperature_column])
	humidity_samples = selected.dropna(subset=[humidity_column])
	start = pd.Timestamp(selected_day)
	end = start + pd.Timedelta(hours=23, minutes=59, seconds=59)

	figure = make_subplots(
		rows=2,
		cols=1,
		shared_xaxes=True,
		vertical_spacing=0.12,
		subplot_titles=("Temperatura", "Umidade"),
	)
	figure.add_trace(
		go.Scatter(
			x=temperature_samples["_hora_grafico"],
			y=temperature_samples[temperature_column],
			mode="lines+markers",
			name="Temperatura",
			line={"color": "#e47b5c", "width": 2},
		),
		row=1,
		col=1,
	)
	figure.add_trace(
		go.Scatter(
			x=humidity_samples["_hora_grafico"],
			y=humidity_samples[humidity_column],
			mode="lines+markers",
			name="Umidade",
			line={"color": "#2d7d82", "width": 2},
		),
		row=2,
		col=1,
	)
	figure.update_xaxes(
		range=[start, end],
		tickformat="%H:%M",
		title_text=hour_column,
		row=2,
		col=1,
	)
	figure.update_yaxes(title_text="Temperatura", row=1, col=1)
	figure.update_yaxes(title_text="Umidade", row=2, col=1)
	figure.update_layout(
		height=650,
		title=f"Evolução dos dados em {selected_day}",
		margin={"l": 20, "r": 20, "t": 90, "b": 20},
		paper_bgcolor="rgba(0,0,0,0)",
		plot_bgcolor="rgba(0,0,0,0)",
		showlegend=False,
	)
	st.plotly_chart(figure, width="stretch")


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
		prepared, temperature_column, humidity_column, _date_column, hour_column = (
			prepare_weather_data(dataframe)
		)
	except ValueError as error:
		st.error(str(error))
		return

	if prepared.empty:
		st.warning("Não existem leituras válidas de temperatura para exibir.")
		return

	st.subheader("Resumo diário")
	render_daily_summary(prepared, temperature_column, humidity_column)
	st.subheader("Leituras por horário")
	render_selected_day(prepared, temperature_column, humidity_column, hour_column)


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
