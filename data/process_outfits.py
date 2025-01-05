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
        # Use regex to extract JSON block and attempt to fix
        extracted_json = extract_json_from_text(raw_content)
        if extracted_json:
            try:
                return json.loads(extracted_json)
            except json.JSONDecodeError:
                print("Extracted JSON block is invalid. Attempting to fix with fallback model...")

        # Fallback: Prompt LLM to correct the JSON
        try:
            prompt = (
                "The following text contains improperly formatted JSON. Fix it and return only the corrected JSON:\n\n"
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
            print(f"Failed to fix JSON: {e}")

    if format_type == "non_json":
        # Fallback: Generate JSON from freeform text
        try:
            prompt = (
                "The following text describes an outfit. Convert it into a JSON object using the specified schema:\n\n"
                f"{raw_content}\n\n"
                "Schema:\n"
                "{\n"
                "  \"clothing\": [\n"
                "    {\n"
                "      \"color\": \"string\",\n"
                "      \"material\": \"string\",\n"
                "      \"type\": \"string\",\n"
                "      \"style\": [\"string\", ...],\n"
                "      \"aesthetic\": [\"string\", ...]\n"
                "    }, ...\n"
                "  ],\n"
                "  \"seasons\": [\"string\", ...],\n"
                "  \"time_of_day\": [\"string\", ...],\n"
                "  \"fanciness_level\": \"string\",\n"
                "  \"occasions\": [\"string\", ...]\n"
                "}\n"
                "Output only the corrected JSON."
            )
            json_response = ollama.chat(
                model=fallback_model_name,
                messages=[{
                    'role': 'user',
                    'content': prompt
                }]
            )
            return json.loads(json_response['message']['content'])
        except Exception as e:
            print(f"Failed to convert freeform text to JSON: {e}")

    return None

def analyze_image_with_ollama(image_path, model_name='llama3.2-vision'):
    """
    Analyze an image using Ollama's llama3.2-vision model.
    :param image_path: Path to the image file.
    :param model_name: Name of the model to use.
    :return: A dictionary with the structured JSON response.
    """
    try:
        with open(image_path, 'rb') as img_file:
            print(f"Analyzing image: {image_path}")
            image_data = img_file.read()
            print(f"Image size for {image_path}: {len(image_data)} bytes")
            response = ollama.chat(
                model=model_name,
                messages=[{
                    'role': 'user',
                    'content': (
                                "You are an expert fashion and clothing analyst. Analyze the given image and describe the outfit for yourself. Now, provide "
                                "a detailed JSON response that represents all aspects of the outfit. The JSON must contain the following fields (the more detail the better but be concise):\n"
                                "1. `clothing`: A breakdown of all visible outfit elements. For each element (e.g., top, bottom, shoes, socks,"
                                "accessories), include the following fields:\n"
                                "   - `color`: The various colors of the item. (e.g. ['White'] or ['White','Red'] etc\n"
                                "   - `pattern`: The pattern of the item (e.g., 'Striped', 'Floral', 'Solid').\n" 
                                "   - `material`: The material or fabric of the item.\n"
                                "   - `type`: The general type of the item (e.g., T-shirt, Jeans, Blazer).\n"
                                "   - `style`: A list describing the specific style or cut of the item (e.g., ['Tank top', 'Tight', 'Layered with cardigan and tank top'], "
                                "['Boot Cut', 'Baggy']).\n"
                                "  - `aesthetic`: A list summarizing the vibe of the outfit(e.g., ['Cottage Core', 'Athletic', 'Dark Academia', e.t.c]).\n"
                                "2. `seasons`: A list of suitable seasons for wearing the outfit (e.g., ['Spring', 'Summer']).\n"
                                "3. `time_of_day`: A list of suitable times of day for wearing the outfit (e.g., ['Daytime', 'Evening']).\n"
                                "4. `fanciness_level`: A classification of the outfit's fanciness level (e.g., ['Casual', 'Formal', 'Semi-Formal']).\n"
                                "5. `occasions`: A list of possible occasions for wearing the outfit (e.g., ['Daily wear', 'Office', 'Brunch']).\n"
                                "\nOutput must be in PROPER JSON format (no '\n') only with no extra text outside the JSON block."
                            ),
                    'images': [image_path]
                }]
            )
            print(f"Raw response: {response}")
            # Extract JSON content from response
            raw_content = response['message']['content']
            return convert_to_proper_json(raw_content)
    except Exception as e:
        print(f"Error analyzing image {image_path}: {e}")
        return {
            "clothing": {},
            "seasons": [],
            "time of day": [],
            "fanciness level": [],
            "occasions": [],
            "model": {}
        }

def process_images(file, output_file):
    """
    Process all images listed in the JSON file and append analysis results.
    :param file: Path to the JSON file containing image paths and Pinterest links.
    :param output_file: Path to save the updated JSON file.
    """
    # Load the JSON file
    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Ensure the data is a list
    if not isinstance(data, list):
        raise ValueError("The JSON file must contain a list of image entries.")

    print(f"Analyzing {len(data)} images...")

    # Process each image
    for entry in tqdm(data, desc="Processing Images"):
        try:
            image_path = "outfits/" + entry.get("image_path").split("/")[-1]

            if not image_path:
                print("Skipping entry with no image path.")
                continue

            # Perform the analysis if not already analyzed
            if "analysis" not in entry:
                analysis = analyze_image_with_ollama(image_path)
                entry["analysis"] = analysis
            else:
                print(f"Skipping already analyzed image: {image_path}")
            print(f"\n\nAnalysis: {entry}")

        except Exception as e:
            print(f"Error processing entry: {entry}. Error: {e}")

    # Save updated results to the output file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Analysis completed. Results saved to {output_file}")


if __name__ == "__main__":
    input_file = "outfits.json"
    output_file = "outfits_analyzed.json"

    # Process images and append analysis
    process_images(input_file, output_file)