import os
from datetime import datetime

from dash import Dash, Input, Output, dash_table, dcc, html
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


def create_supabase_client() -> Client:
	load_dotenv()

	url = os.getenv("SUPABASE_URL")
	key = os.getenv("SUPABASE_KEY")

	if not url or not key:
		raise RuntimeError(
			"Defina SUPABASE_URL e SUPABASE_KEY no arquivo .env ou no ambiente."
		)

	return create_client(url, key)


def query_table(client: Client, table: str, limit: int) -> list[dict]:
	response = client.table(table).select("*").limit(limit).execute()
	return response.data


TABLE_NAME = os.getenv("SUPABASE_TABLE", "leituras")
ROW_LIMIT = int(os.getenv("SUPABASE_ROW_LIMIT", "100"))

app = Dash(__name__)
app.title = "Dashboard de Leituras"
server = app.server

app.layout = html.Main(
	[
		html.Div(
			[
				html.P("SUPABASE / MONITORAMENTO", className="eyebrow"),
				html.H1("Leituras da estação"),
				html.P(
					"Dados atualizados diretamente da sua tabela no Supabase.",
					className="subtitle",
				),
			],
			className="hero",
		),
		html.Section(
			[
				html.Div(
					[
						html.Div([html.Span("Tabela"), html.Strong(TABLE_NAME)]),
						html.Div(
							[html.Span("Registros"), html.Strong(id="row-count")]
						),
						html.Div(
							[
								html.Span("Última atualização"),
								html.Strong(id="last-update"),
							]
						),
					],
					className="stats",
				),
				html.Div(id="error-message", className="error-message"),
				dash_table.DataTable(
					id="data-table",
					data=[],
					columns=[],
					page_size=15,
					sort_action="native",
					filter_action="native",
					style_table={"overflowX": "auto"},
					style_cell={
						"fontFamily": "IBM Plex Mono, monospace",
						"fontSize": "13px",
						"padding": "13px 16px",
						"textAlign": "left",
						"minWidth": "130px",
						"maxWidth": "320px",
						"overflow": "hidden",
						"textOverflow": "ellipsis",
					},
					style_header={
						"backgroundColor": "#183b3b",
						"color": "#f4f1e8",
						"fontWeight": "600",
						"border": "none",
					},
					style_data={
						"backgroundColor": "#fffdf8",
						"color": "#24302f",
						"border": "1px solid #e4e2d9",
					},
					style_data_conditional=[
						{
							"if": {"row_index": "odd"},
							"backgroundColor": "#f7f5ee",
						}
					],
				),
				html.P(id="status-message", className="status-message"),
			],
			className="content",
		),
		dcc.Interval(id="refresh-interval", interval=60 * 1000, n_intervals=0),
	]
)


@app.callback(
	Output("data-table", "data"),
	Output("data-table", "columns"),
	Output("row-count", "children"),
	Output("last-update", "children"),
	Output("status-message", "children"),
	Output("error-message", "children"),
	Input("refresh-interval", "n_intervals"),
)
def update_table(_n_intervals: int):
	try:
		rows = query_table(create_supabase_client(), TABLE_NAME, ROW_LIMIT)
		columns = [
			{"name": column, "id": column}
			for column in (rows[0].keys() if rows else [])
		]
		return (
			rows,
			columns,
			str(len(rows)),
			datetime.now().strftime("%H:%M:%S"),
			f"{len(rows)} registro(s) carregado(s)",
			"",
		)
	except Exception as error:
		return [], [], "0", "--:--:--", "", f"Não foi possível carregar os dados: {error}"


if __name__ == "__main__":
	app.run(debug=True)
