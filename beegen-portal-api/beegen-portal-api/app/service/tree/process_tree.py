import sys
import os
import asyncio
import copy
import threading
from typing import Any, Dict, List, Optional

from beeflow.workflow import WorkflowEngine
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START

from app.service.tree.utils.markdown_parser import (
    extract_nodes_from_markdown,
    extract_node_text_content,
    build_tree_from_nodes,
    write_node_id,
    format_structure,
    structure_to_list,
    build_node_summary_prompt,
    should_summarize_text,
)
from app.service.utils.extract_keywords import KeywordExtractor


def _inject_parent_titles(nodes: list, ancestor_titles: list = None) -> list:
    """
    Recursively traverses the tree and prepends ancestor title lines to each
    child node's `text` so that every node carries its full heading breadcrumb.
    Root-level nodes are left unchanged.
    """
    if ancestor_titles is None:
        ancestor_titles = []

    for node in nodes:
        if ancestor_titles:
            # Prepend all ancestor title lines followed by the node's own text
            prefix = "\n".join(ancestor_titles)
            node["text"] = prefix + "\n" + node["text"]

        # Build the heading line for *this* node to pass down to its children
        children = node.get("nodes", [])
        if children:
            # Detect the heading level from the current node's text first line
            own_heading = node["text"].split("\n")[len(ancestor_titles)] if ancestor_titles else node["text"].split("\n")[0]
            _inject_parent_titles(children, ancestor_titles + [own_heading])

    return nodes


def code_extract_and_build_tree(markdown_content: str):
    """
    Extracts nodes from a markdown string, builds a hierarchical tree,
    assigns node IDs, injects ancestor title context into child node texts,
    and formats the structure to remove line_num.
    """
    # 1. Extract nodes
    node_list, markdown_lines = extract_nodes_from_markdown(markdown_content)
    
    # 2. Extract text content for each node
    nodes_with_content = extract_node_text_content(node_list, markdown_lines)
    
    # 3. Build tree
    tree_structure = build_tree_from_nodes(nodes_with_content)
    
    # 4. Write node ID
    write_node_id(tree_structure)
    
    # 5. Format structure to remove line_num and keep only desired keys
    # Keys we want: 'title', 'node_id', 'text', 'nodes'
    # We will add 'summary' in the next step
    tree_structure = format_structure(tree_structure, order=['title', 'node_id', 'text', 'nodes'])

    # 6. Inject ancestor titles into child node texts
    _inject_parent_titles(tree_structure)
    
    return {
        "initial_structure": tree_structure
    }


def _flatten_nodes(structure: list):
    nodes = structure_to_list(structure)
    return {"flat_nodes": nodes}


def _split_nodes_for_summary(nodes: list, summary_token_threshold: int, model: str):
    to_summarize = []
    pass_through = []
    for node in nodes:
        node_text = node.get("text", "")
        title_path = node.get("title_path", "")
        if should_summarize_text(node_text, summary_token_threshold, model=model):
            to_summarize.append({
                "node_id": node.get("node_id"),
                "text": node_text,
                "title_path": title_path,
            })
        else:
            pass_through.append({
                "node_id": node.get("node_id"),
                # For short nodes, the text (already containing ancestor heading
                # breadcrumbs) is used directly as the summary.
                "summary": node_text,
            })
    return {
        "to_summarize": to_summarize,
        "pass_through": pass_through,
    }


def _prepare_summary_prompt(text: str, title_path: str = ""):
    prompt = build_node_summary_prompt(text, title_path=title_path)
    return {"messages": [{"role": "user", "content": prompt}]}


def _wrap_summary_output(node_id_in: str, title_path_in: str, content: str):
    """
    Wrap the LLM-generated summary. The LLM is already instructed via the
    prompt to embed title context naturally in the summary text, so we only
    strip whitespace here without any mechanical prepending.
    """
    return {
        "summary_item": {
            "node_id": node_id_in,
            "summary": (content or "").strip(),
        }
    }


def _merge_loop_results(batch_result: list):
    summaries = []
    for item in batch_result or []:
        if isinstance(item, list):
            summaries.extend(item)
            continue
        if isinstance(item, dict) and "summary_item" in item:
            summaries.append(item["summary_item"])
        elif item:
            summaries.append(item)
    return {"collected_summaries": summaries}


def _merge_summaries(structure_in: list, summaries: list, summaries_llm: list):
    structure = copy.deepcopy(structure_in)
    combined = (summaries or []) + (summaries_llm or [])
    summaries_by_id = {item["node_id"]: item["summary"] for item in combined}

    def apply_summary(nodes):
        for node in nodes:
            node_id = node.get("node_id")
            if node_id in summaries_by_id:
                if node.get("nodes"):
                    node["prefix_summary"] = summaries_by_id[node_id]
                else:
                    node["summary"] = summaries_by_id[node_id]
            if node.get("nodes"):
                apply_summary(node["nodes"])
        return nodes

    tree_structure = apply_summary(structure)

    def fix_summary_key(nodes):
        for node in nodes:
            if "prefix_summary" in node:
                node["summary"] = node.pop("prefix_summary")
            if "nodes" in node:
                fix_summary_key(node["nodes"])
        return nodes

    tree_structure = fix_summary_key(tree_structure)
    tree_structure = format_structure(tree_structure, order=["title", "node_id", "summary", "text", "nodes"])
    return {"final_structure": tree_structure}


def _prepare_keyword_batches(structure_in: list):
    batch_data = []
    for node in structure_to_list(structure_in or []):
        if not isinstance(node, dict):
            continue
        summary = node.get("summary", "")
        if summary:
            batch_data.append({"node_id_in": node.get("node_id"), "summary": summary})
    return {"batch_data": batch_data}


def _extract_keywords_node(summary: str, node_id_in: str) -> Dict[str, Any]:
    extractor = KeywordExtractor()

    async def runner() -> Dict[str, Any]:
        return await extractor.extract(summary)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        result = asyncio.run(runner())
        return {
            "node_id": node_id_in,
            "keywords": result.get("keywords") if isinstance(result, dict) else None,
            "keywords_text": result.get("keywords_text", "") if isinstance(result, dict) else "",
            "continue_loop": False,
        }

    result_container: Dict[str, Any] = {}

    def thread_runner() -> None:
        result_container.update(asyncio.run(runner()))

    thread = threading.Thread(target=thread_runner)
    thread.start()
    thread.join()
    return {
        "node_id": node_id_in,
        "keywords": result_container.get("keywords"),
        "keywords_text": result_container.get("keywords_text", ""),
        "continue_loop": False,
    }


def _merge_keywords(structure_in: list, batches: list) -> Dict[str, Any]:
    structure = copy.deepcopy(structure_in)
    keywords_by_id = {}
    for item in batches or []:
        if not isinstance(item, dict):
            continue
        node_id = item.get("node_id")
        keywords = item.get("keywords")
        if node_id and keywords:
            keywords_by_id[node_id] = keywords

    def apply_keywords(nodes):
        for node in nodes:
            node_id = node.get("node_id")
            if node_id in keywords_by_id:
                node["keywords"] = keywords_by_id[node_id]
            if node.get("nodes"):
                apply_keywords(node["nodes"])
        return nodes

    tree_structure = apply_keywords(structure)
    tree_structure = format_structure(
        tree_structure, order=["title", "node_id", "summary", "text", "keywords", "nodes"]
    )
    return {"final_structure": tree_structure}


class TreeService:
    def __init__(self):
        self._build_tree_workflow()

    def _build_tree_workflow(self):
        with WorkflowEngine(
            name="wf_build_markdown_tree",
            description="Build hierarchical tree from MD string",
            langfuse="beegen-portal"
        ) as wf_tree:
            
            node_extract_build = CodeNode(
                name="code_extract_build",
                code_fn=code_extract_and_build_tree,
                inputs={
                    "markdown_content": {INPUT: "markdown_content"}
                },
                return_keys=["initial_structure: list"]
            )
            
            node_flatten = CodeNode(
                name="code_flatten_nodes",
                code_fn=_flatten_nodes,
                inputs={
                    "structure": {node_extract_build: "initial_structure"}
                },
                return_keys=["flat_nodes: list"]
            )

            node_split = CodeNode(
                name="code_split_nodes",
                code_fn=_split_nodes_for_summary,
                inputs={
                    "nodes": {node_flatten: "flat_nodes"},
                    "summary_token_threshold": 200,
                    "model": "gemini-3.1-flash-lite-chat",
                },
                return_keys=["to_summarize: list", "pass_through: list"]
            )

            with ForLoopNode(
                name="loop_summarize_nodes",
                inputs={
                    "batch_data": {node_split: "to_summarize"}
                }
            ) as loop_summarize_nodes:
                node_prepare_prompt = CodeNode(
                    name="code_prepare_summary_prompt",
                    code_fn=_prepare_summary_prompt,
                    inputs={
                        "text": {INPUT: "text"},
                        "title_path": {INPUT: "title_path"},
                    },
                    return_keys=["messages: List[Dict[str, Any]]"]
                )

                node_llm_summary = LLMNode(
                    name="llm_summary",
                    resource_key="gemini-3.1-flash-lite-chat",
                    inputs={
                        "messages": {node_prepare_prompt: "messages"}
                    }
                )

                node_wrap_summary = CodeNode(
                    name="code_wrap_summary",
                    code_fn=_wrap_summary_output,
                    inputs={
                        "node_id_in": {INPUT: "node_id"},
                        "title_path_in": {INPUT: "title_path"},
                        "content": {node_llm_summary: "content"}
                    },
                    return_keys=["summary_item: Dict[str, Any]"],
                    outputs=OUTPUT
                )

                START >> node_prepare_prompt >> node_llm_summary >> node_wrap_summary >> END

            node_collect = CodeNode(
                name="code_collect_summaries",
                code_fn=_merge_loop_results,
                inputs={
                    "batch_result": {loop_summarize_nodes: "batch_result"}
                },
                return_keys=["collected_summaries: list"]
            )

            node_merge = CodeNode(
                name="code_merge_summary",
                code_fn=_merge_summaries,
                inputs={
                    "structure_in": {node_extract_build: "initial_structure"},
                    "summaries": {node_split: "pass_through"},
                    "summaries_llm": {node_collect: "collected_summaries"}
                },
                return_keys=["final_structure: list"],
            )

            node_prepare_keywords = CodeNode(
                name="code_prepare_keywords",
                code_fn=_prepare_keyword_batches,
                inputs={"structure_in": {node_merge: "final_structure"}},
                return_keys=["batch_data: list"],
            )

            with ForLoopNode(
                name="loop_extract_keywords",
                inputs={
                    "batch_data": {node_prepare_keywords: "batch_data"}
                }
            ) as loop_extract_keywords:
                node_extract_keywords = CodeNode(
                    name="extract_keywords",
                    code_fn=_extract_keywords_node,
                    inputs={
                        "summary": {INPUT: "summary"},
                        "node_id_in": {INPUT: "node_id_in"},
                    },
                    return_keys=[
                        "node_id: str",
                        "keywords: List[str]",
                        "keywords_text: str",
                        "continue_loop: bool",
                    ],
                    outputs=OUTPUT
                )

                START >> node_extract_keywords >> END

            node_merge_keywords = CodeNode(
                name="code_merge_keywords",
                code_fn=_merge_keywords,
                inputs={
                    "structure_in": {node_merge: "final_structure"},
                    "batches": {loop_extract_keywords: "batch_result"},
                },
                return_keys=["final_structure: list"],
                outputs=OUTPUT
            )

            node_pass_through = CodeNode(
                name="code_pass_through",
                code_fn=lambda structure_in: {"final_structure": structure_in},
                inputs={"structure_in": {node_merge: "final_structure"}},
                return_keys=["final_structure: list"],
                outputs=OUTPUT
            )

            branch_keywords = BranchNode(
                name="branch_keywords",
                cases={"extract_keywords == True": node_prepare_keywords},
                default=node_pass_through,
                inputs={"extract_keywords": {INPUT: "extract_keywords"}},
            )

            START >> node_extract_build >> node_flatten >> node_split >> loop_summarize_nodes >> node_collect >> node_merge
            node_merge >> branch_keywords >> [node_prepare_keywords, node_pass_through]
            node_prepare_keywords >> loop_extract_keywords >> node_merge_keywords >> END
            node_pass_through >> END
            
        wf_tree.compile()
        self.tree_workflow = wf_tree
        
    async def run(self, markdown_content: str, extract_keywords: str = False, **kwargs):
        import uuid
        request_id = str(uuid.uuid4())
        
        result = await self.tree_workflow.run(
            request_id=request_id,
            inputs={
                "markdown_content": markdown_content,
                "extract_keywords": extract_keywords
            }
        )
        return result


if __name__ == "__main__":
    # Test function to read a .md file and feed it into the service
    async def main():
        service = TreeService()
        sample_md_path = "assets/sample.md"
        
        if not os.path.exists(sample_md_path):
            print(f"Sample file not found at {sample_md_path}")
            # Create a dummy markdown string if file doesn't exist
            sample_content = "# Title 1\n\nSome text.\n\n## Subtitle 1\n\nMore text."
        else:
            with open(sample_md_path, 'r', encoding='utf-8') as f:
                sample_content = f.read()
                
        print(f"Processing markdown content of length: {len(sample_content)}")
        
        result = await service.run(markdown_content=sample_content, extract_keywords=True)
        
        print("\n=== Output Tree Structure ===")
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))

    asyncio.run(main())
