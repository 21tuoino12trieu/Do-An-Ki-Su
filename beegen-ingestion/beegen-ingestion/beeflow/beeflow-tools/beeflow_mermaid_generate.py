#!/usr/bin/env python3
"""
Beeflow Workflow to Mermaid Diagram Generator with Nested GraphNode Support
"""

import argparse
import ast
import os
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

NODE_SHAPES = {
    "START": "([{name}])",
    "END": "([{name}])",
    "BranchNode": "{{{name}<br/>{label}}}",
    "ForLoopNode": "[{name}<br/>{label}]",
    "WhileLoopNode": "[{name}<br/>{label}]",
    "GraphNode": "[{name}<br/>{label}]",
    "BasicChainNode": "[{name}<br/>{label}]",
    "CodeNode": "[{name}<br/>{label}]",
    "LLMNode": "[{name}<br/>{label}]",
    "EmbeddingNode": "[{name}<br/>{label}]",
    "RerankNode": "[{name}<br/>{label}]",
    "DocumentIONode": "[{name}<br/>{label}]",
    "MongoNode": "[{name}<br/>{label}]",
    "MilvusNode": "[{name}<br/>{label}]",
    "S3Node": "[{name}<br/>{label}]",
    "default": "[{name}<br/>{label}]"
}


@dataclass
class Node:
    name: str
    node_type: str
    label: Optional[str] = None
    line: int = 0
    parent_path: str = ""  # Full path of parent containers
    child_nodes: List['Node'] = field(default_factory=list)
    child_connections: List['Connection'] = field(default_factory=list)

    @property
    def full_path(self) -> str:
        if self.parent_path:
            return f"{self.parent_path}.{self.name}"
        return self.name

    @property
    def is_container(self) -> bool:
        return self.node_type in ["ForLoopNode", "WhileLoopNode", "GraphNode"]


@dataclass
class Connection:
    source: str
    target: str
    label: Optional[str] = None


@dataclass
class Workflow:
    name: str
    nodes: List[Node] = field(default_factory=list)
    connections: List[Connection] = field(default_factory=list)
    branch_cases: Dict[str, List[str]] = field(default_factory=dict)


class WorkflowParser(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.workflow: Optional[Workflow] = None
        self.container_stack: List[Node] = []  # Stack for nested containers
        self.node_vars: Dict[str, Node] = {}

    @property
    def current_container(self) -> Optional[Node]:
        return self.container_stack[-1] if self.container_stack else None

    @property
    def current_path(self) -> str:
        if self.container_stack:
            return self.container_stack[-1].full_path
        return ""

    def get_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self.get_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def get_string_value(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def extract_node_info(self, call: ast.Call) -> Optional[Tuple[str, str, Optional[str]]]:
        callee = self.get_name(call.func) or ""
        node_type = callee.split(".")[-1]

        node_name = None
        label = None

        for kw in call.keywords:
            if kw.arg == "name":
                node_name = self.get_string_value(kw.value)
            elif kw.arg == "description":
                label = self.get_string_value(kw.value)

        if node_name:
            return node_name, node_type, label
        return None

    def visit_With(self, node: ast.With):
        for item in node.items:
            call = item.context_expr
            if isinstance(call, ast.Call):
                callee = self.get_name(call.func) or ""
                short = callee.split(".")[-1]

                if short == "WorkflowEngine":
                    for kw in call.keywords:
                        if kw.arg == "name":
                            wf_name = self.get_string_value(kw.value)
                            if wf_name:
                                self.workflow = Workflow(name=wf_name)

                    # Process workflow body
                    for stmt in node.body:
                        self.visit(stmt)
                    return

                elif short in ["ForLoopNode", "WhileLoopNode", "GraphNode"]:
                    info = self.extract_node_info(call)
                    if info:
                        node_name, node_type, label = info

                        # Create container node with parent path
                        container_node = Node(
                            name=node_name,
                            node_type=node_type,
                            label=label or node_type,
                            line=node.lineno,
                            parent_path=self.current_path
                        )

                        # Add to parent's children or workflow root
                        if self.current_container:
                            self.current_container.child_nodes.append(container_node)
                        elif self.workflow:
                            self.workflow.nodes.append(container_node)

                        # Store variable reference
                        if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                            self.node_vars[item.optional_vars.id] = container_node

                        # Push to stack and process body
                        self.container_stack.append(container_node)

                        for stmt in node.body:
                            self.visit(stmt)

                        # Pop from stack
                        self.container_stack.pop()
                        return

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        if isinstance(node.value, ast.Call):
            info = self.extract_node_info(node.value)
            if info:
                node_name, node_type, label = info
                new_node = Node(
                    name=node_name,
                    node_type=node_type,
                    label=label or node_type,
                    line=node.lineno,
                    parent_path=self.current_path
                )

                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.node_vars[target.id] = new_node

                # Add to current container or workflow
                if self.current_container:
                    self.current_container.child_nodes.append(new_node)
                elif self.workflow:
                    self.workflow.nodes.append(new_node)

                # Handle BranchNode cases
                if node_type == "BranchNode":
                    for kw in node.value.keywords:
                        if kw.arg == "cases" and isinstance(kw.value, ast.Dict):
                            cases = []
                            for v in kw.value.values:
                                if isinstance(v, ast.Name):
                                    var_name = v.id
                                    if var_name in self.node_vars:
                                        cases.append(self.node_vars[var_name].name)
                                elif isinstance(v, ast.Constant):
                                    cases.append(str(v.value))
                            if cases and self.workflow:
                                self.workflow.branch_cases[node_name] = cases

        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.RShift):
            self.extract_connections(node.value)
        self.generic_visit(node)

    def extract_connections(self, binop: ast.BinOp):
        def get_node_names(node) -> List[str]:
            names = []
            if isinstance(node, ast.List):
                for elt in node.elts:
                    name = get_single_node_name(elt)
                    if name:
                        names.append(name)
            else:
                name = get_single_node_name(node)
                if name:
                    names.append(name)
            return names

        def get_single_node_name(node) -> Optional[str]:
            if isinstance(node, ast.Name):
                var_name = node.id
                if var_name in ["START", "END"]:
                    return var_name
                if var_name in self.node_vars:
                    return self.node_vars[var_name].name
            return None

        def flatten_rshift(node) -> List:
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.RShift):
                return flatten_rshift(node.left) + flatten_rshift(node.right)
            return [node]

        chain = flatten_rshift(binop)
        node_sequence = []
        for item in chain:
            names = get_node_names(item)
            if names:
                node_sequence.append(names)

        # Add connections to current container or workflow
        connections_list = (
            self.current_container.child_connections if self.current_container
            else (self.workflow.connections if self.workflow else [])
        )

        for i in range(len(node_sequence) - 1):
            sources = node_sequence[i]
            targets = node_sequence[i + 1]
            for src in sources:
                for tgt in targets:
                    connections_list.append(Connection(source=src, target=tgt))


def collect_all_nodes(nodes: List[Node], prefix: str = "") -> Dict[str, Node]:
    """Recursively collect all nodes with their full paths"""
    result = {}
    for node in nodes:
        node_id = f"{prefix}{node.name}".replace("-", "_") if prefix else node.name.replace("-", "_")
        result[node.name] = node
        result[node_id] = node

        if node.is_container and node.child_nodes:
            child_prefix = f"{node_id}_"
            child_nodes = collect_all_nodes(node.child_nodes, child_prefix)
            result.update(child_nodes)

    return result


def generate_mermaid(workflow: Workflow, max_depth: int = 3) -> str:
    """Generate Mermaid flowchart with nested structure support"""
    lines = ["flowchart LR"]
    node_map = {}
    all_nodes = collect_all_nodes(workflow.nodes)

    # START/END
    lines.append("    START([START])")
    lines.append("    END([END])")
    node_map["START"] = "START"
    node_map["END"] = "END"
    lines.append("")

    # Generate nodes recursively
    def generate_nodes_recursive(nodes: List[Node], prefix: str = "", depth: int = 0):
        for node in nodes:
            node_id = f"{prefix}{node.name}".replace("-", "_")
            node_map[node.name] = node_id

            if node.is_container and node.child_nodes:
                # Generate as subgraph
                lines.extend(generate_subgraph(node, prefix, depth))
            else:
                # Generate as simple node
                indent = "    " * (depth + 1)
                shape_template = NODE_SHAPES.get(node.node_type, NODE_SHAPES["default"])
                shape = shape_template.format(name=node.name, label=node.label or node.node_type)
                lines.append(f"{indent}{node_id}{shape}")

    generate_nodes_recursive(workflow.nodes)

    # Generate connections recursively
    def generate_connections_recursive(connections: List[Connection], nodes: List[Node],
                                       prefix: str = "", depth: int = 0):
        indent = "    " * (depth + 1)

        for conn in connections:
            src_id = node_map.get(conn.source, f"{prefix}{conn.source}".replace("-", "_"))
            tgt_id = node_map.get(conn.target, f"{prefix}{conn.target}".replace("-", "_"))

            if conn.source in workflow.branch_cases:
                cases = workflow.branch_cases[conn.source]
                if conn.target in cases:
                    idx = cases.index(conn.target)
                    label = "Yes" if idx == 0 else "No" if idx == 1 else f"Case {idx + 1}"
                    lines.append(f"{indent}{src_id} -->|{label}| {tgt_id}")
                else:
                    lines.append(f"{indent}{src_id} --> {tgt_id}")
            elif conn.label:
                lines.append(f"{indent}{src_id} -->|{conn.label}| {tgt_id}")
            else:
                lines.append(f"{indent}{src_id} --> {tgt_id}")

    lines.append("")
    generate_connections_recursive(workflow.connections, workflow.nodes)

    # Styling
    lines.append("")
    lines.append("    %% Styling")
    lines.append("    classDef loopClass fill:#e1f5ff,stroke:#0288d1,stroke-width:2px")
    lines.append("    classDef graphClass fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px")
    lines.append("    classDef branchClass fill:#fff3e0,stroke:#f57c00,stroke-width:2px")
    lines.append("    classDef errorClass fill:#ffebee,stroke:#c62828,stroke-width:2px")
    lines.append("")

    # Collect styled nodes
    def collect_styled_nodes(nodes: List[Node], prefix: str = "") -> Tuple[List[str], List[str], List[str], List[str]]:
        loops, graphs, branches, errors = [], [], [], []

        for node in nodes:
            node_id = f"{prefix}{node.name}".replace("-", "_")

            if node.node_type in ["ForLoopNode", "WhileLoopNode"]:
                loops.append(node_id)
            elif node.node_type == "GraphNode":
                graphs.append(node_id)
            elif node.node_type == "BranchNode":
                branches.append(node_id)

            if "error" in node.name.lower():
                errors.append(node_id)

            if node.is_container and node.child_nodes:
                child_prefix = f"{node_id}_"
                c_loops, c_graphs, c_branches, c_errors = collect_styled_nodes(node.child_nodes, child_prefix)
                loops.extend(c_loops)
                graphs.extend(c_graphs)
                branches.extend(c_branches)
                errors.extend(c_errors)

        return loops, graphs, branches, errors

    loops, graphs, branches, errors = collect_styled_nodes(workflow.nodes)

    if loops:
        lines.append(f"    class {','.join(loops)} loopClass")
    if graphs:
        lines.append(f"    class {','.join(graphs)} graphClass")
    if branches:
        lines.append(f"    class {','.join(branches)} branchClass")
    if errors:
        lines.append(f"    class {','.join(errors)} errorClass")

    return "\n".join(lines)


def generate_subgraph(container: Node, prefix: str = "", depth: int = 0) -> List[str]:
    """Generate subgraph with all nested children"""
    lines = []
    indent = "    " * (depth + 1)
    container_id = f"{prefix}{container.name}".replace("-", "_")

    lines.append(f"{indent}subgraph {container_id}[\"{container.name} ({container.node_type})\"]")
    lines.append(f"{indent}    direction TB")

    # Internal START/END
    lines.append(f"{indent}    {container_id}_START([START])")
    lines.append(f"{indent}    {container_id}_END([END])")

    # Child nodes
    child_prefix = f"{container_id}_"
    for child in container.child_nodes:
        child_id = f"{child_prefix}{child.name}".replace("-", "_")

        if child.is_container and child.child_nodes:
            # Nested subgraph
            nested_lines = generate_subgraph(child, child_prefix, depth + 1)
            lines.extend(nested_lines)
        else:
            shape_template = NODE_SHAPES.get(child.node_type, NODE_SHAPES["default"])
            shape = shape_template.format(name=child.name, label=child.label or child.node_type)
            lines.append(f"{indent}    {child_id}{shape}")

    # Child connections
    for conn in container.child_connections:
        if conn.source == "START":
            src_id = f"{container_id}_START"
        elif conn.source == "END":
            src_id = f"{container_id}_END"
        else:
            src_id = f"{child_prefix}{conn.source}".replace("-", "_")

        if conn.target == "START":
            tgt_id = f"{container_id}_START"
        elif conn.target == "END":
            tgt_id = f"{container_id}_END"
        else:
            tgt_id = f"{child_prefix}{conn.target}".replace("-", "_")

        if conn.label:
            lines.append(f"{indent}    {src_id} -->|{conn.label}| {tgt_id}")
        else:
            lines.append(f"{indent}    {src_id} --> {tgt_id}")

    lines.append(f"{indent}end")
    lines.append("")

    return lines


def process_file(filepath: str, output_path: Optional[str] = None):
    try:
        # Read as binary to handle BOM
        with open(filepath, 'rb') as f:
            content = f.read()

        # Remove BOM if present
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]
            print(f"Removed BOM from {filepath}")

        # Decode to string
        source = content.decode('utf-8')

    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
        return

    parser = WorkflowParser(filepath)
    parser.visit(tree)

    if not parser.workflow:
        print(f"No workflow found in {filepath}", file=sys.stderr)
        return

    mermaid = generate_mermaid(parser.workflow)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(mermaid)
        print(f"✅ Generated: {output_path}")
    else:
        base = os.path.splitext(filepath)[0]
        out_file = f"{base}_diagram.mmd"
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(mermaid)
        print(f"✅ Generated: {out_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate Mermaid diagrams from Beeflow workflows"
    )
    parser.add_argument("path", help="Workflow file or directory")
    parser.add_argument("-o", "--output", help="Output file (for single file mode)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Process all .py files in directory")

    args = parser.parse_args()

    if os.path.isfile(args.path):
        process_file(args.path, args.output)
    elif os.path.isdir(args.path):
        if not args.recursive:
            print("Use --recursive to process directory", file=sys.stderr)
            sys.exit(1)

        for root, _, files in os.walk(args.path):
            for filename in files:
                if filename.endswith('.py') and 'workflow' in filename.lower():
                    filepath = os.path.join(root, filename)
                    process_file(filepath)
    else:
        print(f"Path not found: {args.path}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()