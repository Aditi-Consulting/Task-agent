import re
import json
from openai import OpenAI, AzureOpenAI
from app.utility.config import OPENAI_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION

# Use Azure OpenAI if endpoint is configured, else fall back to standard OpenAI
if AZURE_OPENAI_ENDPOINT:
    client = AzureOpenAI(
        api_key=OPENAI_KEY,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_version=AZURE_OPENAI_API_VERSION
    )
    USE_AZURE = True
else:
    client = OpenAI(api_key=OPENAI_KEY)
    USE_AZURE = False


def extract_json_from_response(resp):
    try:
        return json.loads(resp)
    except Exception:
        m = re.search(r"(\{(?:.|\n)*\})", resp)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
    return None


def call_llm_for_json(prompt, model="gpt-4o-mini", temperature=0.0, max_tokens=2000):
    if USE_AZURE:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )
        text = response.choices[0].message.content
    else:
        response = client.responses.create(
            model=model, input=prompt,
            temperature=temperature, max_output_tokens=max_tokens
        )
        text = getattr(response, "output_text", "") or str(response)

    json_obj = extract_json_from_response(text)
    if json_obj is None:
        return {"__error__": "couldn't parse JSON from model response", "raw_text": text}
    return json_obj