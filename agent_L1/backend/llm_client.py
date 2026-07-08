import os
import json
import urllib.request
import re
from typing import Dict, Any, List, Tuple

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "llm_config.json")

DEFAULT_CONFIG = {
    "mode": "local",  # "local" for rule database, "llm" for large language model
    "url": "http://localhost:11434/v1",
    "model": "deepseek-r1:7b",
    "api_key": ""
}

def load_config() -> Dict[str, Any]:
    """Loads LLM configurations from config file."""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            # Ensure all keys exist
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
            return config
    except Exception:
        return DEFAULT_CONFIG

def save_config(config: Dict[str, Any]):
    """Saves LLM configurations to config file."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving LLM config: {e}")

def call_api(url: str, model: str, api_key: str, messages: List[Dict[str, str]], timeout: int = 60) -> str:
    """Calls OpenAI-compatible completion API endpoint using built-in urllib."""
    api_url = f"{url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1
    }
    
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    if "localhost" in api_url or "127.0.0.1" in api_url:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    else:
        opener = urllib.request.build_opener()
        
    with opener.open(req, timeout=timeout) as response:
        response_bytes = response.read()
        res_json = json.loads(response_bytes.decode("utf-8"))
        return res_json["choices"][0]["message"]["content"]

def test_connection(url: str, model: str, api_key: str) -> Tuple[bool, str]:
    """Tests the connection to the specified LLM API URL and Model."""
    messages = [
        {"role": "user", "content": "Respond with the single word 'OK' to verify API connection."}
    ]
    try:
        response = call_api(url, model, api_key, messages, timeout=30)
        if "OK" in response.upper():
            return True, "连接测试成功！模型响应正常。"
        return True, f"已连接，但响应不符合预期: {response}"
    except Exception as e:
        return False, f"连接测试失败: {str(e)}"

def parse_llm_json_response(response_text: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Renders and clean responses from LLM.
    Strips reasoning <think>...</think> blocks, parses JSON arrays, and returns suggestions + think log.
    """
    # 1. Extract thinking log if present
    think_log = ""
    think_match = re.search(r'<think>(.*?)</think>', response_text, re.DOTALL)
    if think_match:
        think_log = think_match.group(1).strip()
    
    # Clean out the think block
    cleaned = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
    
    # 2. Try to extract JSON array
    json_str = ""
    # Look for code block markdown first
    json_code_block = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', cleaned, re.DOTALL)
    if json_code_block:
        json_str = json_code_block.group(1).strip()
    else:
        # Fallback to finding [ ] boundaries
        array_match = re.search(r'\[\s*\{.*\}\s*\]', cleaned, re.DOTALL)
        if array_match:
            json_str = array_match.group(0).strip()
        else:
            # Last fallback
            json_str = cleaned.strip()
            
    try:
        suggestions = json.loads(json_str)
        if isinstance(suggestions, list):
            # Validate structure
            valid_suggestions = []
            for item in suggestions:
                if isinstance(item, dict) and "parameter" in item and "action" in item and "target_value" in item:
                    valid_suggestions.append(item)
            return valid_suggestions, think_log
        return [], think_log
    except Exception as e:
        print(f"Error parsing LLM response JSON: {e}\nRaw JSON string attempted: {json_str}")
        return [], think_log

def get_llm_suggestions(
    material: str,
    thickness: float,
    current_power: float,
    current_speed: float,
    current_gas_type: str,
    current_gas_pressure: float,
    current_focus: float,
    quality_report: Dict[str, Any],
    target_recipe: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], str]:
    """Constructs the prompt, calls the configured LLM API, and parses the response suggestions."""
    config = load_config()
    
    system_prompt = (
        "You are an expert Laser Cutting Process Control Engineer.\n"
        "Your task is to analyze laser cutting defects and recommend parameter adjustments (offsets) for the next test cut.\n\n"
        "Available parameters you can adjust:\n"
        "- laser_power: Laser power in Watts (W).\n"
        "- speed: Cutting speed in mm/min.\n"
        "- gas_pressure: Assist gas pressure in bar.\n"
        "- focus_position: Focal position in mm.\n\n"
        "Your final response must contain ONLY a JSON array, with no other conversational text. Do not wrap the JSON in anything other than a standard json markdown block. "
        "If you output a reasoning/thinking process (like in deepseek-r1), wrap it inside <think>...</think> tags, but follow it strictly with the JSON array.\n\n"
        "CRITICAL: You must write the thinking process and the 'reason' field in Chinese.\n\n"
        "JSON Schema for each item in the array:\n"
        "{\n"
        "  \"parameter\": \"laser_power\" | \"speed\" | \"gas_pressure\" | \"focus_position\",\n"
        "  \"action\": \"increase\" | \"decrease\" | \"set\",\n"
        "  \"delta\": float (change amount relative to the current value),\n"
        "  \"target_value\": float (the new proposed value: current_value + delta),\n"
        "  \"reason\": \"用中文清晰说明基于缺陷症状为何需要此项调整\",\n"
        "  \"risk\": \"low\" | \"medium\" | \"high\",\n"
        "  \"requires_approval\": boolean\n"
        "}\n\n"
        "Example Output:\n"
        "[\n"
        "  {\n"
        "    \"parameter\": \"speed\",\n"
        "    \"action\": \"decrease\",\n"
        "    \"delta\": -500.0,\n"
        "    \"target_value\": 5500.0,\n"
        "    \"reason\": \"检测到明显的底部挂渣（熔渣）。降低 500 mm/min 的切割速度能够给辅助气体和热输入留出更充足的时间来完全吹除熔融金属。\",\n"
        "    \"risk\": \"low\",\n"
        "    \"requires_approval\": false\n"
        "  }\n"
        "]"
    )
    
    user_prompt = (
        f"Material: {material}\n"
        f"Thickness: {thickness:.1f} mm\n\n"
        f"--- Cut Experiment Setup ---\n"
        f"Current Run Parameters:\n"
        f"- Laser Power: {current_power:.0f} W\n"
        f"- Speed: {current_speed:.0f} mm/min\n"
        f"- Gas Type: {current_gas_type}\n"
        f"- Gas Pressure: {current_gas_pressure:.1f} bar\n"
        f"- Focus Position: {current_focus:.2f} mm\n\n"
        f"Standard Expert Target Parameters (Baseline Reference):\n"
        f"- Target Laser Power: {target_recipe['laser_power']:.0f} W\n"
        f"- Target Speed: {target_recipe['speed']:.0f} mm/min\n"
        f"- Target Gas Type: {target_recipe['gas_type']}\n"
        f"- Target Gas Pressure: {target_recipe['gas_pressure']:.1f} bar\n"
        f"- Target Focus Position: {target_recipe['focus_position']:.2f} mm\n\n"
        f"--- Post-Cut Quality Feedback Sensor Report ---\n"
        f"- Penetrated: {quality_report.get('penetrated', True)}\n"
        f"- Quality Comprehensive Score: {quality_report.get('quality_score', 0)}/100\n"
        f"- Dross Score: {quality_report.get('dross_score', 100)}/100 (Dross Slag Height: {quality_report.get('dross_height', 0)} mm)\n"
        f"- Overburn Score: {quality_report.get('burning_score', 100)}/100 (Burning level: {quality_report.get('burning_level', 'none')})\n"
        f"- Dimension Score: {quality_report.get('dimension_score', 100)}/100 (Kerf Width: {quality_report.get('kerf_width', 0.35)} mm)\n"
        f"- Roughness Score: {quality_report.get('roughness_score', 100)}/100 (Section Ra: {quality_report.get('roughness_ra', 3.0)} um)\n"
        f"- Visual Inspection Summary: {quality_report.get('visual_summary', '')}\n\n"
        f"Please diagnose the issues and output the JSON suggestions to optimize parameters towards the 90%+ quality score. Write all thinking, reasoning, and reasons in Chinese."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        response_text = call_api(config["url"], config["model"], config["api_key"], messages, timeout=60)
        suggestions, think_log = parse_llm_json_response(response_text)
        
        # If think log is empty, we can just use the raw text as the reasoning log
        if not think_log:
            # remove the json part from response to keep only comments
            reasoning_log = re.sub(r'\[\s*\{.*\}\s*\]', '', response_text, flags=re.DOTALL)
            reasoning_log = re.sub(r'```(?:json)?\s*```', '', reasoning_log).strip()
            think_log = reasoning_log if reasoning_log else "大模型处理完毕。"
            
        return suggestions, think_log
    except Exception as e:
        raise Exception(f"大模型智能体调用失败: {str(e)}")
