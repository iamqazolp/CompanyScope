import os
import json
from typing import Any
from dotenv import load_dotenv
from groq import Groq
from src.tools import get_financial_data, search_filings, calculator
from src.guard import verify_citations

# Load environment variables (GROQ_API_KEY)
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL_NAME = "llama-3.1-8b-instant"

TOOLS_LIST = [
    {
        "type": "function",
        "function": {
            "name": "get_financial_data",
            "description": "Fetches exact financial facts (e.g., 'Revenues', 'NetIncomeLoss', 'Assets') for a given company and year.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "The stock ticker symbol, e.g., AAPL",
                    },
                    "concept": {
                        "type": "string",
                        "description": "The financial concept to fetch, e.g., Revenues",
                    },
                    "year": {
                        "type": "string",
                        "description": "The year of the financial data, e.g., '2024'",
                    },
                },
                "required": ["ticker", "concept", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_filings",
            "description": "Performs a semantic search over SEC filings (10-K, 10-Q) to retrieve narrative chunks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "ticker": {
                        "type": "string",
                        "description": "Optional stock ticker symbol filter",
                    },
                    "year": {"type": "string", "description": "Optional year filter"},
                    "section": {
                        "type": "string",
                        "description": "Optional section filter (e.g., 'Item 1', 'Item 7')",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Safely evaluates simple arithmetic expressions (+, -, *, /, %, ()).",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "get_financial_data": get_financial_data,
    "search_filings": search_filings,
    "calculator": calculator,
}


def load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "system.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def perform_fallback_rag(
    question: str, ticker: str, system_prompt: str, reason: str
) -> dict:
    from src.tools import search_filings
    import json

    chunks = search_filings(query=question, ticker=ticker, k=5)
    context_str = "\n".join(
        [
            f"Chunk ID {c.get('chunk_id')} ({c.get('year')} {c.get('section', '')}):\n{c.get('chunk_text')}"
            for c in chunks
        ]
    )

    fallback_prompt = f"""
You encountered an issue while trying to use tools: {reason}

We have automatically fetched the following context from {ticker}'s filings for you:
{context_str}

Please try to answer the user's question using ONLY this context. If the answer is not here, cleanly state that it is unavailable. Remember to output ONLY a strictly formatted JSON object matching the requested schema.
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Context Ticker: {ticker}\nQuestion: {question}\n\n{fallback_prompt}",
        },
    ]
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME, messages=messages, timeout=30.0  # type: ignore
        )
        content = response.choices[0].message.content or "{}"
        if content.strip().startswith("```"):
            lines = content.strip().split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)

        parsed = json.loads(content)
        mock_history = {"fallback_search": chunks}
        parsed = verify_citations(parsed, mock_history)
        parsed["used_tools"] = ["search_filings (fallback)"]
        return parsed
    except Exception as e:
        return {"error": f"Fallback RAG failed: {str(e)}"}


def process_query(question: str, ticker: str = "AAPL") -> dict:
    """
    Process query using LLM and tools.
    """
    try:
        system_prompt = load_system_prompt()
    except Exception as e:
        return {"error": f"Failed to load system prompt: {e}"}

    messages: list[Any] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context Ticker: {ticker}\nQuestion: {question}"},
    ]
    tool_results_history = {}
    used_tools = []

    for iteration in range(5):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,  # type: ignore
                tools=TOOLS_LIST,  # type: ignore
                tool_choice="auto",
                parallel_tool_calls=False,
                timeout=30.0,
            )

            message = response.choices[0].message

            # Check if the model wants to call tools
            if message.tool_calls:
                # Add assistant message to history
                assistant_msg = {"role": "assistant", "content": message.content or ""}
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
                messages.append(assistant_msg)

                # Execute each tool call
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    used_tools.append(func_name)
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}

                    if func_name in TOOL_FUNCTIONS:
                        func = TOOL_FUNCTIONS[func_name]
                        try:
                            # Execute the local Python function
                            result = func(**func_args)  # type: ignore
                            tool_results_history[tool_call.id] = result
                            tool_result = json.dumps(result)
                        except Exception as e:
                            tool_result = json.dumps({"error": str(e)})
                    else:
                        tool_result = json.dumps(
                            {"error": f"Tool '{func_name}' not found."}
                        )

                    # Append tool result to message history
                    messages.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": func_name,
                            "content": tool_result,
                        }
                    )
            else:
                # Final answer (no tool calls)
                content = message.content or "{}"
                # Clean up potential markdown formatting
                if content.strip().startswith("```"):
                    lines = content.strip().split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    content = "\n".join(lines)
                try:
                    parsed = json.loads(content)
                    # Verify required keys exist
                    if all(
                        k in parsed
                        for k in ["answer", "citations", "needs_clarification"]
                    ):
                        parsed = verify_citations(parsed, tool_results_history)
                        parsed["used_tools"] = list(set(used_tools))
                        return parsed
                    else:
                        return {
                            "error": "Invalid JSON schema: missing required keys.",
                            "raw": content,
                        }
                except json.JSONDecodeError:
                    return {
                        "error": "Model failed to output valid JSON.",
                        "raw": content,
                    }

        except Exception as e:
            err_str = str(e)
            if "failed_generation" in err_str and "<function=" in err_str:
                import re
                import uuid

                match = re.search(
                    r"<function=([a-zA-Z0-9_]+)(\{.*?\})</function>", err_str
                )
                if match:
                    func_name = match.group(1)
                    func_args_str = match.group(2)
                    used_tools.append(func_name)

                    try:
                        func_args = json.loads(func_args_str)
                    except json.JSONDecodeError:
                        func_args = {}

                    if func_name in TOOL_FUNCTIONS:
                        func = TOOL_FUNCTIONS[func_name]
                        try:
                            result = func(**func_args)  # type: ignore
                            fake_id = "call_" + str(uuid.uuid4())[:8]
                            tool_results_history[fake_id] = result
                            tool_result = json.dumps(result)
                        except Exception as ex:
                            tool_result = json.dumps({"error": str(ex)})
                    else:
                        tool_result = json.dumps(
                            {"error": f"Tool '{func_name}' not found."}
                        )

                    messages.append(
                        {
                            "role": "user",
                            "content": f"You tried to call the tool '{func_name}' with arguments {func_args_str}. The result is: {tool_result}\nNow, please use this information to provide the final JSON answer or make another tool call.",
                        }
                    )
                    continue
            else:
                return perform_fallback_rag(
                    question,
                    ticker,
                    system_prompt,
                    f"Agent loop encountered an error: {err_str}",
                )
    return perform_fallback_rag(
        question,
        ticker,
        system_prompt,
        "Max iterations (5) reached without a final answer.",
    )
