import json
import os
import re

import ollama
from tqdm import tqdm


def detect_response_format(raw_content):
    """
    Detects the format of the response to classify it as:
    - "faulty_json": Contains escaped JSON or improperly formatted JSON.
    - "non_json": Contains no JSON structure and is entirely freeform text.
    - "valid_json": Contains valid JSON.
    :param raw_content: The raw content from the model response.
    :return: One of "faulty_json", "non_json", or "valid_json".
    """
    try:
        # Check if it's valid JSON
        json.loads(raw_content)
        return "valid_json"
    except json.JSONDecodeError:
        # Check if it contains JSON-like structure with regex
        if re.search(r"\{.*\}", raw_content, re.DOTALL):
            return "faulty_json"
        else:
            return "non_json"

def extract_json_from_text(raw_content):
    """
    Extract the JSON block from text that contains additional explanations or comments.
    :param raw_content: The raw response from the model.
    :return: The extracted JSON block as a string or None if no valid JSON is found.
    """
    try:
        # Use regex to locate JSON block within the raw content
        json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if json_match:
            return json_match.group(0)
    except Exception as e:
        print(f"Error extracting JSON from text: {e}")
    return None

def convert_to_proper_json(raw_content, fallback_model_name='llama3.2:latest'):
    """
    Converts raw content to proper JSON using extraction and fallback logic.
    Handles both faulty JSON and non-JSON freeform text.
    :param raw_content: The raw response from the model.
    :param fallback_model_name: A text-based model to reprocess the output if necessary.
    :return: A proper JSON object or None if all attempts fail.
    """
    format_type = detect_response_format(raw_content)

    if format_type == "valid_json":
        # If already valid JSON, return as is
        return json.loads(raw_content)

    if format_type == "faulty_json":
        # Attempt to extract JSON block from the text
        extracted_json = extract_json_from_text(raw_content)
        if extracted_json:
            try:
                return json.loads(extracted_json)
            except json.JSONDecodeError:
                print("Extracted JSON block is invalid. Attempting to fix with fallback model...")

        # Use fallback LLM to fix the JSON
        try:
            prompt = (
                "The following response contains improperly formatted JSON or partial JSON. "
                "Please correct it and output ONLY the corrected JSON in valid format:\n\n"
                f"{raw_content}"
            )
            fixed_response = ollama.chat(
                model=fallback_model_name,
                messages=[{
                    'role': 'user',
                    'content': prompt
                }]
            )
            fixed_content = fixed_response['message']['content']
            return json.loads(fixed_content)
        except Exception as e:
            print(f"Failed to fix JSON with fallback model: {e}")

    if format_type == "non_json":
        # Fallback: Reconstruct JSON from freeform text
        try:
            prompt = (
                "The following text describes an outfit. Convert this description into a valid JSON object adhering to the schema below. "
                "Include all details explicitly, even if some fields must be inferred or defaulted:\n\n"
                f"Description:\n{raw_content}\n\n"
                "Schema:\n"
                "{\n"
                "  \"link\": \"string\",\n"
                "  \"image_path\": \"string\",\n"
                "  \"date_added\": \"string\",\n"
                "  \"description\": \"string\",\n"
                "  \"flags\": {\n"
                "    \"has_tops\": true/false,\n"
                "    \"has_bottoms\": true/false,\n"
                "    \"has_shoes\": true/false,\n"
                "    \"has_accessories\": true/false\n"
                "  },\n"
                "  \"elements\": {\n"
                "    \"tops\": {\n"
                "      \"is_layered\": true/false,\n"
                "      \"layered_items\": [\n"
                "        {\"type\": \"string\", \"color\": \"string\", \"pattern\": \"string\", \"material\": \"string\", \"fit\": \"string\"},\n"
                "        ...\n"
                "      ]\n"
                "    },\n"
                "    \"bottoms\": {\"type\": \"string\", \"color\": \"string\", \"pattern\": \"string\", \"material\": \"string\", \"fit\": \"string\"},\n"
                "    \"shoes\": {\"type\": \"string\", \"color\": \"string\", \"style\": \"string\", \"material\": \"string\"},\n"
                "    \"accessories\": []\n"
                "  },\n"
                "  \"overall_features\": {\n"
                "    \"aesthetic\": [\"string\", ...],\n"
                "    \"season\": [\"string\", ...],\n"
                "    \"time_of_day\": [\"string\", ...],\n"
                "    \"fanciness_level\": \"string\",\n"
                "    \"occasions\": [\"string\", ...]\n"
                "  },\n"
                "  \"extra_attributes\": {\n"
                "    \"notable_features\": [\"string\", ...]\n"
                "  }\n"
                "}\n\n"
                "Output ONLY the JSON object. Do not include explanations or additional text."
            )
            json_response = ollama.chat(
                model=fallback_model_name,
                messages=[{
                    'role': 'user',
                    'content': prompt
                }]
            )
            corrected_json = json.loads(json_response['message']['content'])
            return corrected_json
        except Exception as e:
            print(f"Failed to reconstruct JSON from freeform text: {e}")

    return None



def analyze_image_with_ollama(image_path, link, date_added, model_name='llama3.2-vision'):
    """
    Analyze an image using Ollama's llama3.2-vision model with enhanced prompting strategy.
    :param image_path: Path to the image file.
    :param link: Pinterest link for the outfit.
    :param date_added: Date when the pin was added.
    :param model_name: Name of the model to use.
    :return: A dictionary with the structured JSON response.
    """
    try:
        with open(image_path, 'rb') as img_file:
            print(f"Analyzing image: {image_path}")

            prompt = (
                "You are a fashion and clothing analyst. Analyze the provided image and describe the outfit comprehensively and accurately and output a JSON object. "
                "Strictly follow the schema below:\n\n"
                "{\n"
                "  \"description\": \"string\",  // A concise one-line description of the image with the outfit being the focus\n"
                "  \"flags\": {\n"
                "    \"has_tops\": true/false,\n"
                "    \"has_bottoms\": true/false,\n"
                "    \"has_shoes\": true/false,\n"
                "    \"has_accessories\": true/false\n"
                "  },\n"
                "  \"elements\": {\n"
                "    \"tops\": {\n"
                "      \"is_layered\": true/false,\n"
                "      \"layered_items\": [\n"
                "        {\"type\": \"string\", \"color\": \"string\", \"pattern\": \"string\", \"material\": \"string\", \"fit\": \"string\"},\n"
                "        ...\n"
                "      ]\n"
                "    },\n"
                "    \"bottoms\": {\"type\": \"string\", \"color\": \"string\", \"pattern\": \"string\", \"material\": \"string\", \"fit\": \"string\"},\n"
                "    \"shoes\": {\"type\": \"string\", \"color\": \"string\", \"style\": \"string\", \"material\": \"string\"},\n"
                "    \"accessories\": [{\"type\": \"string\", \"color\": \"string\", \"style\": \"string\", \"material\": \"string\"}, ...]\n"
                "  },\n"
                "  \"overall_features\": {\n"
                "    \"aesthetic\": [\"string\", ...],\n"
                "    \"season\": [\"string\", ...], // in reference to LA\n"
                "    \"time_of_day\": [\"string\", ...],\n"
                "    \"fanciness_level\": \"string\",  // Casual/Formal/Semi-formal\n"
                "    \"occasions\": [\"string\", ...]\n"
                "  },\n"
                "  \"extra_attributes\": {\n"
                "    \"notable_features\": [\"string\", ...]  // Any additional inferred details and recognized brands\n"
                "  }\n"
                "}\n\n"
                "Only return valid JSON. Do not include any extra text or explanations."
            )

            response = ollama.chat(
                model=model_name,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [image_path]
                }]
            )

            raw_content = response['message']['content']
            print(f"Raw response: {raw_content}")
            
            # Attempt to parse and validate JSON
            return convert_to_proper_json(raw_content)
    except Exception as e:
        print(f"Error analyzing image {image_path}: {e}")
        return {
            "link": link,
            "image_path": image_path,
            "date_added": date_added,
            "description": "unknown",
            "flags": {
                "has_tops": False,
                "has_bottoms": False,
                "has_shoes": False,
                "has_accessories": False
            },
            "elements": {
                "tops": {"is_layered": False, "layered_items": []},
                "bottoms": {"type": "unknown", "color": "unknown", "pattern": "unknown", "material": "unknown", "fit": "unknown"},
                "shoes": {"type": "unknown", "color": "unknown", "style": "unknown", "material": "unknown"},
                "accessories": []
            },
            "overall_features": {
                "aesthetic": ["unknown"],
                "season": ["unknown"],
                "time_of_day": ["unknown"],
                "fanciness_level": "unknown",
                "occasions": ["unknown"]
            },
            "extra_attributes": {"notable_features": []}
        }

def process_images(input_file, output_file):
    """
    Process all images listed in the JSON file and append analysis results.
    :param input_file: Path to the JSON file containing image paths and Pinterest links.
    :param output_file: Path to save the updated JSON file.
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("The JSON file must contain a list of image entries.")

    print(f"Analyzing {len(data)} images...")

    for entry in tqdm(data, desc="Processing Images"):
        try:
            image_path = entry.get("image_path")
            link = entry.get("link")
            date_added = entry.get("date_added")

            if not image_path or "analysis" in entry:
                print(f"Skipping entry: {link} (already analyzed or missing image path).")
                continue

            analysis = analyze_image_with_ollama(image_path, link, date_added)
            entry["analysis"] = analysis

        except Exception as e:
            print(f"Error processing entry: {entry}. Error: {e}")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Analysis completed. Results saved to {output_file}.")


if __name__ == "__main__":
    input_file = "outfits_test.json"
    output_file = "outfits_test_results.json"

    # Process images and append analysis
    process_images(input_file, output_file)