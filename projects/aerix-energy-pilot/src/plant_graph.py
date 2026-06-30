from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd
import plotly.graph_objects as go

try:
    import networkx as nx  # type: ignore[import]

    NETWORKX_AVAILABLE = True
except Exception:
    nx = None  # type: ignore[assignment]
    NETWORKX_AVAILABLE = False


class FallbackDiGraph:
    """Small deterministic digraph fallback for environments without NetworkX."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: set[tuple[str, str]] = set()
        self._pred: dict[str, set[str]] = defaultdict(set)
        self._succ: dict[str, set[str]] = defaultdict(set)

    @property
    def nodes(self) -> dict[str, dict[str, Any]]:
        return self._nodes

    def edges(self) -> list[tuple[str, str]]:
        return sorted(self._edges)

    def add_node(self, node: str, **attrs: Any) -> None:
        self._nodes[str(node)] = dict(attrs)

    def add_edges_from(self, edges: list[tuple[str, str]]) -> None:
        for source, target in edges:
            src = str(source)
            tgt = str(target)
            self._edges.add((src, tgt))
            self._pred[tgt].add(src)
            self._succ[src].add(tgt)

    def predecessors(self, node: str) -> list[str]:
        return sorted(self._pred.get(str(node), set()))

    def successors(self, node: str) -> list[str]:
        return sorted(self._succ.get(str(node), set()))

    def number_of_nodes(self) -> int:
        return len(self._nodes)


GraphType = Any


def _new_graph() -> GraphType:
    if NETWORKX_AVAILABLE:
        return nx.DiGraph()  # type: ignore[union-attr]
    return FallbackDiGraph()


def _demo_edges(machine_ids: list[str]) -> list[tuple[str, str]]:
    if len(machine_ids) < 2:
        return []
    return [(machine_ids[idx], machine_ids[idx + 1]) for idx in range(len(machine_ids) - 1)]


def _add_node(graph: GraphType, node: str, attrs: dict[str, Any]) -> None:
    if NETWORKX_AVAILABLE:
        graph.add_node(node, **attrs)
    else:
        graph.add_node(node, **attrs)


def _add_edges(graph: GraphType, edges: list[tuple[str, str]]) -> None:
    graph.add_edges_from(edges)


def _graph_nodes(graph: GraphType) -> list[str]:
    if NETWORKX_AVAILABLE:
        return sorted(str(node) for node in graph.nodes())
    return sorted(str(node) for node in graph.nodes.keys())


def _graph_node_attrs(graph: GraphType, node: str) -> dict[str, Any]:
    if NETWORKX_AVAILABLE:
        return dict(graph.nodes[node])
    return dict(graph.nodes.get(node, {}))


def _graph_edges(graph: GraphType) -> list[tuple[str, str]]:
    if NETWORKX_AVAILABLE:
        return sorted((str(source), str(target)) for source, target in graph.edges())
    return graph.edges()


def _predecessors(graph: GraphType, node: str) -> list[str]:
    if NETWORKX_AVAILABLE:
        return sorted(str(pred) for pred in graph.predecessors(node))
    return graph.predecessors(node)


def build_plant_graph(equipment_df: pd.DataFrame) -> GraphType:
    graph = _new_graph()

    if equipment_df is None or equipment_df.empty:
        return graph

    machine_ids = sorted(str(machine_id) for machine_id in equipment_df["machine_id"].tolist())
    for machine_id in machine_ids:
        machine_row = equipment_df[equipment_df["machine_id"] == machine_id].iloc[0]
        _add_node(
            graph,
            machine_id,
            {
                "machine_type": str(machine_row.get("machine_type", "generic")),
                "priority": str(machine_row.get("priority", "medium")),
                "power_mw": float(machine_row.get("power_mw", 0.0)),
                "availability": bool(machine_row.get("availability", True)),
            },
        )

    edges: list[tuple[str, str]] = []
    if "dependencies" in equipment_df.columns:
        for row in equipment_df.itertuples(index=False):
            machine_id = str(getattr(row, "machine_id"))
            dependencies = getattr(row, "dependencies", [])
            if isinstance(dependencies, list):
                for dependency in sorted(str(dep) for dep in dependencies if str(dep).strip()):
                    if dependency in _graph_nodes(graph) and machine_id in _graph_nodes(graph):
                        edges.append((dependency, machine_id))

    if not edges:
        edges = _demo_edges(machine_ids)

    _add_edges(graph, edges)
    return graph


def get_downstream_machines(graph: GraphType, machine_id: str) -> list[str]:
    node = str(machine_id)
    if node not in _graph_nodes(graph):
        return []

    visited: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if NETWORKX_AVAILABLE:
            successors = [str(item) for item in graph.successors(current)]
        else:
            successors = graph.successors(current)
        for child in sorted(successors):
            if child not in visited:
                visited.add(child)
                stack.append(child)

    return sorted(machine for machine in visited if machine != node)


def build_plant_graph_figure(graph: GraphType) -> go.Figure:
    figure = go.Figure()
    if graph is None:
        return figure

    node_ids = _graph_nodes(graph)
    if not node_ids:
        figure.update_layout(
            template="plotly_dark",
            title="Plant Energy Graph",
            annotations=[
                {
                    "text": "No machine graph data available",
                    "x": 0.5,
                    "y": 0.5,
                    "xref": "paper",
                    "yref": "paper",
                    "showarrow": False,
                }
            ],
        )
        return figure

    if NETWORKX_AVAILABLE:
        layout = nx.spring_layout(graph, seed=42, k=0.9, iterations=80)  # type: ignore[union-attr]
    else:
        layout = {node: (idx, 0.0) for idx, node in enumerate(node_ids)}

    edge_x: list[float] = []
    edge_y: list[float] = []
    for source, target in _graph_edges(graph):
        x0, y0 = layout[source]
        x1, y1 = layout[target]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    figure.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line={"width": 1.2, "color": "#6B7CFF"},
            hoverinfo="none",
            showlegend=False,
        )
    )

    node_x: list[float] = []
    node_y: list[float] = []
    node_text: list[str] = []
    node_color: list[str] = []

    for node in node_ids:
        x, y = layout[node]
        node_x.append(x)
        node_y.append(y)
        attrs = _graph_node_attrs(graph, node)
        availability = bool(attrs.get("availability", True))
        node_color.append("#37E39A" if availability else "#FF5F77")
        node_text.append(
            f"Machine: {node}<br>"
            f"Type: {attrs.get('machine_type', 'generic')}<br>"
            f"Priority: {attrs.get('priority', 'medium')}<br>"
            f"Power: {float(attrs.get('power_mw', 0.0)):.2f} MW"
        )

    figure.add_trace(
        go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            text=node_ids,
            textposition="top center",
            marker={"size": 16, "color": node_color, "line": {"width": 1, "color": "#FFFFFF"}},
            hovertemplate="%{customdata}<extra></extra>",
            customdata=node_text,
            showlegend=False,
        )
    )

    figure.update_layout(
        template="plotly_dark",
        title="Plant Energy Graph",
        margin={"l": 20, "r": 20, "t": 45, "b": 20},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure
