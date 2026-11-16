# Beeflow Naming Linter (strict rules + extended nodes)
# Usage:
#   python beeflow_name_lint.py /path/to/repo
#   python beeflow_name_lint.py . --json

# Global rules:
# - ALL identifiers must satisfy SNAKE_ID: lower_snake_case, 3–40 chars: ^[a-z][a-z0-9_]{2,39}$
# - Workflow: wf_[domain]_[pipeline]__(env?)__(ver?|date?)   (env in {dev,stg,prod})

# Class-specific naming:
# - GraphNode (Flow):           graph_[item_or_task]
# - CodeNode (Transform):       code_[verb]_[object]
# - DataNode (Transform):       data_[verb]_[object]
# - LambdaNode (Transform):     lambda_[verb]_[object]
# - ParserNode (Transform):     parse_[object]
# - PromptNode (Transform):     prompt_[item_or_task]
# - ForLoopNode (Flow):         for_each_[item_or_task]
# - WhileLoopNode (Flow):       while_each_[item_or_task]
# - BranchNode (Flow):          branch_[condition]
# - LLMNode (AI):               llm_[item_or_task]
# - BasicChainNode (Template):  llm_[item_or_task]
# - EmbeddingNode (AI):         embed_[item_or_task]
# - RerankNode (AI):            rerank_[item_or_task]
# - ReactAgentNode (Template):  agent_[item_or_task]
# - RetrieverNode (Template):   retrieve_[item_or_task]
# - ToolExecutorNode (Template):tool_[verb]_[item_or_task]
# - MongoNode (Data):           mongo_[verb]_[collection]
# - MilvusNode (Data):          milvus_[verb]_[item_or_task]
# - S3Node (Data):              s3_[verb]_[item_or_task]
# - DocumentIONode (Data I/O):  [document_in]2[document_out] (e.g., pdf2images, docx2markdown)

# Additional checks:
# - ParamSet.new().var("key: Type ...") keys must be SNAKE_ID.
# - Warn on BranchNode.cases target names that don't look like snake_case or graph_*,
#   and warn if graph_* target not found among declared GraphNode names in same file.

# Exit codes: 0 (ok), 1 (violations), 2 (internal error).

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional, Set

# ---------- Regexes ----------
SNAKE_ID = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
WF_REGEX = re.compile(r"^wf_[a-z0-9_]+(__(dev|stg|prod))?(__(v[0-9]+|[0-9]{6}|[0-9]{8}))?$")

GRAPH_NAME     = re.compile(r"^graph_[a-z0-9_]+$")
CODE_NODE      = re.compile(r"^code_[a-z]+_[a-z0-9_]+$")
DATA_NODE      = re.compile(r"^data_[a-z]+_[a-z0-9_]+$")
LAMBDA_NODE    = re.compile(r"^lambda_[a-z]+_[a-z0-9_]+$")
PARSER_NODE    = re.compile(r"^parse_[a-z0-9_]+$")
PROMPT_NODE    = re.compile(r"^prompt_[a-z0-9_]+$")
FOR_NODE       = re.compile(r"^for_each_[a-z0-9_]+$")
WHILE_NODE     = re.compile(r"^while_each_[a-z0-9_]+$")
BRANCH_NODE    = re.compile(r"^branch_[a-z0-9_]+$")
LLM_NODE       = re.compile(r"^llm_[a-z0-9_]+$")
EMBED_NODE     = re.compile(r"^embed_[a-z0-9_]+$")
RERANK_NODE    = re.compile(r"^rerank_[a-z0-9_]+$")
AGENT_NODE     = re.compile(r"^agent_[a-z0-9_]+$")
RETRIEVE_NODE  = re.compile(r"^retrieve_[a-z0-9_]+$")
TOOL_NODE      = re.compile(r"^tool_[a-z]+_[a-z0-9_]+$")
MONGO_NODE     = re.compile(r"^mongo_[a-z]+_[a-z0-9_]+$")
MILVUS_NODE    = re.compile(r"^milvus_[a-z]+_[a-z0-9_]+$")
S3_NODE        = re.compile(r"^s3_[a-z]+_[a-z0-9_]+$")
DOCIO_NODE     = re.compile(r"^[a-z0-9_]+2[a-z0-9_]+$")

NODE_CLASS_RULES = {
    "GraphNode": GRAPH_NAME,
    # Transform
    "CodeNode": CODE_NODE,
    "DataNode": DATA_NODE,
    "LambdaNode": LAMBDA_NODE,
    "ParserNode": PARSER_NODE,
    "PromptNode": PROMPT_NODE,
    # Flow Control
    "ForLoopNode": FOR_NODE,
    "WhileLoopNode": WHILE_NODE,
    "BranchNode": BRANCH_NODE,
    # AI
    "LLMNode": LLM_NODE,
    "BasicChainNode": LLM_NODE,
    "EmbeddingNode": EMBED_NODE,
    "RerankNode": RERANK_NODE,
    # Template
    "ReactAgentNode": AGENT_NODE,
    "RetrieverNode": RETRIEVE_NODE,
    "ToolExecutorNode": TOOL_NODE,
    # Data
    "MongoNode": MONGO_NODE,
    "MilvusNode": MILVUS_NODE,
    "S3Node": S3_NODE,
    "DocumentIONode": DOCIO_NODE,
}

WORKFLOW_ENGINE_NAMES = {"WorkflowEngine"}

# ---------- Data ----------
@dataclass
class Finding:
    file: str
    line: int
    kind: str   # workflow|graph|node|param_key|branch_target|branch_target_warn|error
    name: str
    message: str
    rule: str

@dataclass
class ContextNames:
    graphs: Set[str]

# ---------- Helpers ----------
def get_call_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = get_call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None

def literal_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None

# ---------- Visitor ----------
class Linter(ast.NodeVisitor):
    def __init__(self, filename: str, ctx: ContextNames):
        self.filename = filename
        self.ctx = ctx
        self.findings: List[Finding] = []

    def add(self, line: int, kind: str, name: str, message: str, rule: str):
        self.findings.append(Finding(self.filename, line, kind, name, message, rule))

    def _enforce_snake(self, kind: str, name: str, line: int):
        if not SNAKE_ID.match(name):
            self.add(line, kind, name, "must be lower_snake_case (3–40 chars)", "SNAKE_ID")

    def visit_With(self, node: ast.With):
        # with WorkflowEngine(name="...") as wf:
        for item in node.items:
            call = item.context_expr
            if isinstance(call, ast.Call):
                callee = get_call_name(call.func) or ""
                short = callee.split(".")[-1]
                if short in WORKFLOW_ENGINE_NAMES:
                    for kw in call.keywords:
                        if kw.arg == "name":
                            wf_name = literal_str(kw.value)
                            if wf_name:
                                self._enforce_snake("workflow", wf_name, node.lineno)
                                if not WF_REGEX.match(wf_name):
                                    self.add(node.lineno, "workflow", wf_name,
                                             "workflow must match wf_[domain]_[pipeline]__(env?)__(ver?|date?)",
                                             "WF_REGEX")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        callee = get_call_name(node.func) or ""
        short = callee.split(".")[-1]

        if short in NODE_CLASS_RULES:
            pattern = NODE_CLASS_RULES[short]
            for kw in node.keywords:
                if kw.arg == "name":
                    n = literal_str(kw.value)
                    if n:
                        self._enforce_snake("node", n, node.lineno)
                        if not pattern.match(n):
                            self.add(node.lineno, "node", n,
                                     f"{short} name must match {pattern.pattern}",
                                     f"{short}_NAME_RULE")
                        if short == "GraphNode" and GRAPH_NAME.match(n):
                            self.ctx.graphs.add(n)

        # ParamSet.new().var("...")
        if isinstance(node.func, ast.Attribute) and node.func.attr == "var":
            if node.args:
                s = literal_str(node.args[0])
                if s:
                    key_clean = s.split(":")[0].strip()
                    if not SNAKE_ID.match(key_clean):
                        self.add(node.lineno, "param_key", key_clean,
                                 "ParamSet.var key must be lower_snake_case (3–40 chars)",
                                 "SNAKE_ID")

        self.generic_visit(node)

# ---------- Branch cases post-check ----------
CASE_MAP_PATTERN = re.compile(r'cases\s*=\s*\{([^}]*)\}', re.DOTALL)
CASE_ENTRY_PATTERN = re.compile(r'("|\')([^"\']+)\1\s*:\s*("|\')([^"\']+)\3')

def check_branch_targets(text: str, filename: str, ctx: ContextNames) -> List[Finding]:
    findings: List[Finding] = []
    for m in CASE_MAP_PATTERN.finditer(text):
        body = m.group(1)
        for em in CASE_ENTRY_PATTERN.finditer(body):
            target = em.group(4)
            line = text[: em.start()].count("\n") + 1
            if not (SNAKE_ID.match(target) or GRAPH_NAME.match(target)):
                findings.append(Finding(filename, line, "branch_target", target,
                                        "branch case target should be snake_case or graph_*",
                                        "GRAPH_OR_SNAKE"))
            else:
                if target.startswith("graph_") and target not in ctx.graphs:
                    findings.append(Finding(filename, line, "branch_target_warn", target,
                                            "graph target not found among declared GraphNode names in this file",
                                            "UNDECLARED_GRAPH"))
    return findings

# ---------- Scan ----------
def scan_file(path: str, ctx: ContextNames) -> List[Finding]:
    try:
        src = open(path, "r", encoding="utf-8").read()
    except Exception as e:
        return [Finding(path, 1, "error", os.path.basename(path), f"cannot read file: {e}", "IO")]

    try:
        tree = ast.parse(src, filename=path)
    except Exception as e:
        return [Finding(path, 1, "error", os.path.basename(path), f"cannot parse file: {e}", "AST")]

    v = Linter(path, ctx)
    v.visit(tree)

    return v.findings + check_branch_targets(src, path, ctx)

def iter_python_files(root: str):
    for base, _, files in os.walk(root):
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(base, fn)

# ---------- CLI ----------
def main():
    p = argparse.ArgumentParser(description="Beeflow naming linter (strict + extended)")
    p.add_argument("path", help="Path to repo/module")
    p.add_argument("--json", action="store_true", help="JSON output")
    args = p.parse_args()

    root = args.path
    if not os.path.exists(root):
        print(f"Path does not exist: {root}", file=sys.stderr)
        sys.exit(2)

    ctx = ContextNames(graphs=set())
    findings: List[Finding] = []
    try:
        for fp in iter_python_files(root):
            findings.extend(scan_file(fp, ctx))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Internal error: {e}", file=sys.stderr)
        sys.exit(2)

    findings.sort(key=lambda x: (x.file, x.line, x.kind))

    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("✅ No naming violations found.")
        else:
            last = None
            for f in findings:
                if f.file != last:
                    print(f"\nFile: {f.file}")
                    last = f.file
                print(f"  L{f.line:>4}  [{f.kind}] {f.name} -> {f.message} ({f.rule})")
            print(f"\nTotal findings: {len(findings)}")

    sys.exit(0 if not findings else 1)

if __name__ == "__main__":
    main()
